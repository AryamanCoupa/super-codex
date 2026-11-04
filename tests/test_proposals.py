import json
import tempfile
import unittest
from pathlib import Path

from codex_harness.config import ASSETS, load_policy, read
from codex_harness.demo import create
from codex_harness.improve import copy_pack, pack_digest, propose


VALID_USAGE = {"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 30}


class DeltaProposer:
    def __init__(self, response, usage=VALID_USAGE, during_call=None):
        self.response = response
        self.usage = usage
        self.during_call = during_call
        self.prompt = None

    def advise(self, policy, model, workspace, prompt, timeout, log, role):
        self.prompt = prompt
        if self.during_call:
            self.during_call()
        return {"returncode": 0, "reason": None, "completed": True,
                "message": self.response if isinstance(self.response, str) else json.dumps(self.response),
                "usage": self.usage, "cost_usd": .01}


class ProposalDeltaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = copy_pack(ASSETS / "packs" / "backend", self.root / "source")
        self.fixture = create(self.root / "fixture")
        self.evidence = [{"task_id": "development", "task_sha256": "development", "status": "failed",
                          "attempts": [], "task": {"prompt": "Handle empty pages"}}]
        self.destination = self.root / "candidate"

    def propose(self, adapter):
        return propose(self.source, self.destination, self.evidence, self.fixture / "repo",
                       load_policy(), "strong", adapter=adapter)

    def delta(self, operation="append", old="", new="\nCheck empty pages."):
        return {"operation": operation, "old": old, "new": new,
                "rationale": "The development failure omitted an empty page case."}

    def test_append_preserves_existing_bytes_and_records_edit(self):
        original = b"Preserve the API contract.\r\nKeep compatibility.\r\n"
        (self.source / "instructions.md").write_bytes(original)
        before = pack_digest(self.source)
        delta = self.delta(new="\r\nCheck empty pages.\r\n")
        adapter = DeltaProposer(delta)
        result = self.propose(adapter)
        self.assertEqual((self.destination / "instructions.md").read_bytes(), original + delta["new"].encode())
        self.assertEqual(pack_digest(self.source), before)
        self.assertEqual(result["delta"], delta)
        self.assertEqual(read(self.destination / "proposal.json")["delta"], delta)
        self.assertEqual((self.source / "pack.toml").read_bytes(), (self.destination / "pack.toml").read_bytes())
        self.assertIn("<instructions_json>", adapter.prompt)
        self.assertIn("<read_only_skill_context>", adapter.prompt)

    def test_replace_preserves_unrelated_guidance(self):
        original = "Preserve API contracts.\nCheck pages.\nKeep compatibility.\n"
        (self.source / "instructions.md").write_text(original)
        self.propose(DeltaProposer(self.delta("replace", "Check pages.", "Check empty and final pages.")))
        self.assertEqual((self.destination / "instructions.md").read_text(),
                         "Preserve API contracts.\nCheck empty and final pages.\nKeep compatibility.\n")

    def test_noop_leaves_instructions_byte_identical(self):
        original = b"Keep existing guidance.\r\n"
        (self.source / "instructions.md").write_bytes(original)
        result = self.propose(DeltaProposer(self.delta("noop", "", "")))
        self.assertEqual((self.destination / "instructions.md").read_bytes(), original)
        self.assertEqual(result["source_pack_sha256"], result["candidate_pack_sha256"])

    def test_missing_nonunique_and_overlapping_targets_rejected(self):
        for original, old in (("First rule.", "Missing rule."), ("Rule. Rule.", "Rule."), ("aaa", "aa")):
            with self.subTest(original=original):
                (self.source / "instructions.md").write_text(original)
                with self.assertRaisesRegex(ValueError, "exactly once"):
                    self.propose(DeltaProposer(self.delta("replace", old, "Replacement.")))
                self.assertFalse(self.destination.exists())

    def test_malformed_or_unbounded_edits_rejected(self):
        invalid = ["Full replacement text", [], {**self.delta(), "extra": "unexpected"},
                   {**self.delta(), "rationale": " "}, {**self.delta(), "old": None},
                   self.delta("delete"), self.delta("append", "not empty"),
                   self.delta("append", "", " "), self.delta("noop", "", "change"),
                   self.delta("append", "", "x" * 2001), self.delta("replace", "x" * 2001, "new")]
        for response in invalid:
            with self.subTest(response=str(response)[:80]):
                with self.assertRaises(ValueError):
                    self.propose(DeltaProposer(response))
                self.assertFalse(self.destination.exists())

    def test_unknown_or_malformed_usage_rejected_and_artifacts_retained(self):
        values = (None, {}, [], dict(VALID_USAGE, output_tokens=-1), dict(VALID_USAGE, input_tokens=True),
                  dict(VALID_USAGE, cached_input_tokens=101),
                  {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0})
        for usage in values:
            with self.subTest(usage=usage):
                with self.assertRaisesRegex(ValueError, "valid measured usage"):
                    self.propose(DeltaProposer(self.delta(), usage=usage))
                self.assertFalse(self.destination.exists())
        logs = list((self.root / ".harness" / "proposals").glob("*/result.json"))
        self.assertEqual(len(logs), len(values))
        self.assertTrue(all(path.with_name("prompt.txt").is_file() for path in logs))

    def test_final_instruction_budget_rejected_before_copy(self):
        (self.source / "instructions.md").write_text("x" * 5900)
        with self.assertRaisesRegex(ValueError, "exceed 6000"):
            self.propose(DeltaProposer(self.delta(new="y" * 101)))
        self.assertFalse(self.destination.exists())

    def test_source_mutation_invalidates_proposed_delta(self):
        def mutate():
            (self.source / "instructions.md").write_text("Changed concurrently.\n")
        with self.assertRaisesRegex(ValueError, "Source pack changed"):
            self.propose(DeltaProposer(self.delta(), during_call=mutate))
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
