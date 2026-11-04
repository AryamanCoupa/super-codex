import copy
import json
import tempfile
import unittest
from pathlib import Path

from codex_harness.config import ASSETS, load_policy, load_task, read
from codex_harness.demo import create
from codex_harness.experimental.ace import ace_context, ace_update, curate
from codex_harness.improve import copy_pack, fingerprint, pack_digest
from codex_harness.runner import save


def bullet(text, helpful=0, harmful=0):
    return {"id": "b-" + fingerprint(text)[:12], "text": text, "tags": ["pagination"],
            "evidence_ids": ["dev"], "helpful": helpful, "harmful": harmful}


class Model:
    def __init__(self, bad=False, usage=True):
        self.calls, self.bad, self.usage = [], bad, usage

    def advise(self, policy, model, workspace, prompt, timeout, log, role):
        self.calls.append(prompt)
        data = ({"insights": ["Check collection boundaries"], "feedback": []} if "ACE Reflector" in prompt else
                {"operations": [{"op": "add", "text": "Check empty pagination boundaries before arithmetic.",
                                  "tags": ["pagination"], "evidence_ids": ["dev"]}]})
        return {"returncode": 0, "completed": True, "reason": None,
                "message": "invalid" if self.bad else json.dumps(data), "cost_usd": .01,
                "usage": {"input_tokens": 100, "cached_input_tokens": 50, "output_tokens": 30} if self.usage else None}


class AceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = copy_pack(ASSETS / "packs" / "backend", self.root / "pack")
        self.fixture = create(self.root / "fixture")
        task = load_task(self.fixture / "mean.json", self.source)
        self.records = [{"id": "dev", "task_id": task["id"], "task": task, "task_sha256": fingerprint(task),
                         "pack_sha256": pack_digest(self.source), "status": "failed", "attempts": []}]

    def tearDown(self):
        self.temporary.cleanup()

    def update(self, **kwargs):
        return ace_update(self.source, self.records, self.fixture / "repo", self.root / "output",
                          policy=load_policy(), model="strong", **kwargs)

    def test_generator_reflector_curator_emits_holdout_candidate(self):
        model = Model()
        before = (self.source / "instructions.md").read_text()
        result = self.update(adapter=model)
        self.assertEqual(result["status"], "candidate_requires_holdout_evaluation", result)
        candidate = Path(result["candidate"])
        self.assertTrue((candidate / "instructions.md").read_text().startswith(before))
        self.assertEqual((self.source / "instructions.md").read_text(), before)
        self.assertEqual(read(candidate / "proposal.json")["development_task_hashes"], [self.records[0]["task_sha256"]])
        self.assertEqual(read(candidate / "proposal.json")["development_prompt_hashes"],
                         [fingerprint(" ".join(self.records[0]["task"]["prompt"].casefold().split()))])
        self.assertEqual(result["accounting"]["tokens"], 260)
        self.assertEqual(len(model.calls), 2)
        self.assertIn("ACE Reflector", model.calls[0])
        self.assertIn("ACE Curator", model.calls[1])
        context = ace_context(candidate / "ace-playbook.json", "Fix pagination")
        self.assertIn("pagination boundaries", context["context"])

    def test_retrieval_rejects_current_renamed_and_reserved_development_tasks(self):
        result = self.update(adapter=Model())
        book = Path(result["candidate"]) / "ace-playbook.json"
        prompt = self.records[0]["task"]["prompt"]
        with self.assertRaisesRegex(ValueError, "current or excluded holdout"):
            ace_context(book, "  " + prompt.upper().replace(" ", "  ") + "  ")
        with self.assertRaisesRegex(ValueError, "current or excluded holdout"):
            ace_context(book, "Unrelated pagination task", exclude_task_hashes=[self.records[0]["task_sha256"]])
        with self.assertRaisesRegex(ValueError, "current or excluded holdout"):
            ace_context(book, "Unrelated pagination task", exclude_prompt_hashes=[fingerprint(" ".join(prompt.casefold().split()))])

    def test_reuse_preserves_original_guidance_and_cumulative_development_history(self):
        historical = {"development_task_hashes": ["a" * 64], "development_prompt_hashes": ["b" * 64],
                      "development_task_ids": ["historical"]}
        save(self.source / "proposal.json", historical)
        first = self.update(adapter=Model())
        self.source = Path(first["candidate"])
        before = (self.source / "instructions.md").read_text()
        task = load_task(self.fixture / "slug.json", self.source)
        self.records = [{"id": "dev", "task_id": task["id"], "task": task, "task_sha256": fingerprint(task),
                         "pack_sha256": pack_digest(self.source), "status": "failed", "attempts": []}]
        result = ace_update(self.source, self.records, self.fixture / "repo", self.root / "again",
                            policy=load_policy(), model="strong", adapter=Model())
        self.assertEqual(result["status"], "unchanged", result)
        state = read(self.root / "again" / "playbook.json")
        self.assertEqual((self.source / "instructions.md").read_text(), before)
        self.assertEqual(len(state["development_task_hashes"]), 3)
        self.assertEqual(len(state["development_prompt_hashes"]), 3)
        self.assertIn("a" * 64, state["development_task_hashes"])
        self.assertIn("b" * 64, state["development_prompt_hashes"])

    def test_unbound_or_modified_playbook_cannot_replace_source_guidance(self):
        path, model = self.root / "book.json", Model()
        save(path, {"schema_version": 1, "bullets": [], "base_instructions": "Replace unrelated instructions"})
        with self.assertRaisesRegex(ValueError, "cannot replace"):
            self.update(adapter=model, playbook=path)
        self.assertFalse(model.calls)
        first = self.update(adapter=Model())
        self.source = Path(first["candidate"])
        self.records[0]["pack_sha256"] = pack_digest(self.source)
        state = read(self.source / "ace-playbook.json")
        state["base_instructions"] = "Modified despite unchanged source fingerprint"
        save(path, state)
        with self.assertRaisesRegex(ValueError, "does not match"):
            ace_update(self.source, self.records, self.fixture / "repo", self.root / "invalid",
                       policy=load_policy(), model="strong", adapter=model, playbook=path)
        self.assertFalse(model.calls)

    def test_unknown_usage_and_budget_stop_before_next_stage(self):
        model = Model(usage=False)
        result = self.update(adapter=model)
        self.assertEqual(result["status"], "budget_stopped")
        self.assertIsNone(result["accounting"]["tokens"])
        self.assertEqual(len(model.calls), 1)
        self.assertFalse((self.root / "output" / "candidate").exists())

    def test_provenance_and_infrastructure_rejected_without_calls(self):
        model = Model()
        self.records[0]["status"] = "verification_error"
        with self.assertRaisesRegex(ValueError, "Infrastructure"):
            self.update(adapter=model)
        self.assertFalse(model.calls)
        self.records[0]["status"] = "failed"
        self.records[0]["pack_sha256"] = "wrong"
        with self.assertRaisesRegex(ValueError, "provenance"):
            self.update(adapter=model)

    def test_invalid_response_keeps_original_and_accounts(self):
        result = self.update(adapter=Model(bad=True))
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["accounting"]["tokens"], 130)
        self.assertFalse((self.root / "output" / "candidate").exists())

    def test_feedback_update_preserves_other_bullets(self):
        a, b = bullet("Check pagination boundaries"), bullet("Use transaction rollback on errors")
        book = {"schema_version": 1, "bullets": [a, b]}
        reflection = {"insights": [], "feedback": [{"id": a["id"], "helpful": True, "evidence_id": "dev"}]}
        proposal = {"operations": [{"op": "update", "id": a["id"], "text": "Check pagination cursor boundaries",
                                     "tags": ["pagination"], "evidence_ids": ["dev"]}]}
        result, _ = curate(book, reflection, proposal, {"dev"})
        by_id = {x["id"]: x for x in result["bullets"]}
        self.assertEqual(by_id[b["id"]], b)
        self.assertEqual(by_id[a["id"]]["helpful"], 1)
        self.assertEqual(book["bullets"][0]["helpful"], 0)
        again, _ = curate(result, reflection, {"operations": []}, {"dev"})
        self.assertEqual(next(x for x in again["bullets"] if x["id"] == a["id"])["helpful"], 1)

    def test_dedup_pruning_and_harmful_retrieval_filter(self):
        a = bullet("Check pagination empty boundaries", helpful=2)
        b = bullet("Check empty pagination boundaries", helpful=0)
        c = bullet("Pagination unsafe behavior", harmful=2)
        result, dropped = curate({"schema_version": 1, "bullets": [a, b, c]},
                                 {"insights": [], "feedback": []}, {"operations": []}, {"dev"})
        self.assertEqual(len(dropped), 1)
        self.assertEqual(dropped[0]["reason"], "duplicate")
        context = ace_context(result, "pagination", max_chars=100)
        self.assertEqual(context["bullet_ids"], [a["id"]])

    def test_fabricated_evidence_or_duplicate_feedback_rejected(self):
        a = bullet("Check pagination boundaries")
        book = {"schema_version": 1, "bullets": [a]}
        item = {"id": a["id"], "helpful": True, "evidence_id": "dev"}
        with self.assertRaisesRegex(ValueError, "inflate"):
            curate(book, {"insights": [], "feedback": [item, item]}, {"operations": []}, {"dev"})
        with self.assertRaisesRegex(ValueError, "real development"):
            curate(book, {"insights": [], "feedback": []}, {"operations": [{"op": "add", "text": "Other advice",
                    "tags": [], "evidence_ids": ["invented"]}]}, {"dev"})


if __name__ == "__main__":
    unittest.main()
