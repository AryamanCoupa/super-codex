import json
import tempfile
import unittest
from pathlib import Path

from codex_harness.config import ASSETS, load_policy, load_task
from codex_harness.demo import CASES, create
from codex_harness.experimental.recursive import recursive_run
from codex_harness.improve import copy_pack, pack_digest
from codex_harness.runner import git, run


class RecursiveAdapter:
    def __init__(self, responses, usage=True, edit=False):
        self.responses = iter(responses)
        self.usage, self.edit = usage, edit
        self.models, self.prompts = [], []

    def result(self, message):
        return {"returncode": 0, "completed": True, "reason": None, "message": message,
                "usage": {"input_tokens": 50, "cached_input_tokens": 0, "output_tokens": 10} if self.usage else None,
                "cost_usd": .001 if self.usage else None, "events": []}

    def advise(self, policy, model, workspace, prompt, timeout, log, role):
        self.models.append(model)
        if self.edit:
            (workspace / "stats.py").write_text("changed")
        return self.result(json.dumps(next(self.responses)))

    def run(self, policy, model, workspace, prompt, mcp, timeout, log):
        self.models.append(model)
        self.prompts.append(prompt)
        (workspace / "stats.py").write_text(CASES["mean"][1])
        return self.result("Fixed empty mean")


class RecursiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.fixture = create(self.root / "fixture")
        self.repo = self.fixture / "repo"
        self.task = load_task(self.fixture / "mean.json")
        self.policy = load_policy(overrides={"model": "cheap", "codex_command": ["git"], "max_attempts": 1})

    def tearDown(self):
        self.temp.cleanup()

    def experiment(self, adapter, **kwargs):
        return recursive_run(self.repo, self.task, self.policy, self.root / "experiment", adapter=adapter, **kwargs)

    def test_recursive_child_evidence_reaches_verified_worker_and_counts_all_calls(self):
        adapter = RecursiveAdapter([
            {"action": "read", "path": "stats.py"},
            {"action": "delegate", "question": "Find the empty-input boundary", "paths": ["stats.py"]},
            {"action": "answer", "answer": "stats.mean divides by len(values); empty values need None."},
            {"action": "answer", "answer": "Handle empty input in stats.mean; preserve other values."}])
        report = self.experiment(adapter, root_model="strong", child_model="cheap", max_calls=4)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(adapter.models, ["strong", "strong", "cheap", "strong", "cheap"])
        self.assertEqual(report["tokens"], 300)
        self.assertAlmostEqual(report["cost_usd"], .005)
        self.assertIn("experimental_advice", adapter.prompts[0])
        self.assertTrue(Path(report["accepted_patch"]).exists())
        self.assertEqual(git(self.repo, "status", "--porcelain"), b"")

    def test_global_call_cap_stops_recursion(self):
        adapter = RecursiveAdapter([{"action": "read", "path": "stats.py"}])
        result = self.experiment(adapter, max_calls=1)
        self.assertEqual(result["status"], "call_limit")
        self.assertEqual(len(adapter.models), 1)
        self.assertNotIn("accepted_patch", result)

    def test_depth_cap_cannot_be_bypassed_with_children(self):
        adapter = RecursiveAdapter([{"action": "delegate", "question": "one", "paths": ["stats.py"]},
                                    {"action": "delegate", "question": "two", "paths": ["stats.py"]}])
        self.assertEqual(self.experiment(adapter, max_depth=1)["status"], "depth_limit")

    def test_unknown_usage_stops_before_worker(self):
        adapter = RecursiveAdapter([{"action": "answer", "answer": "Fix it"}], usage=False)
        result = self.experiment(adapter)
        self.assertEqual(result["status"], "usage_unknown")
        self.assertIsNone(result["tokens"])
        self.assertEqual(len(adapter.models), 1)

    def test_verified_worker_with_unknown_usage_is_not_automatically_accepted(self):
        class UnknownWorker(RecursiveAdapter):
            def run(self, *args):
                result = super().run(*args)
                result.update(usage=None, cost_usd=None)
                return result
        adapter = UnknownWorker([{"action": "answer", "answer": "Guard empty stats.mean input."}])
        result = self.experiment(adapter)
        self.assertEqual(result["worker"]["status"], "passed")
        self.assertEqual(result["status"], "usage_unknown")
        self.assertIsNone(result["tokens"])
        self.assertEqual(result["known_tokens"], 60)
        self.assertNotIn("accepted_patch", result)

    def test_pack_mutation_during_analysis_cannot_change_worker_instructions(self):
        source = copy_pack(ASSETS / "packs" / "backend", self.root / "source-pack")
        initial = "Preserve the original verified pagination invariant.\n"
        (source / "instructions.md").write_text(initial)
        initial_digest = pack_digest(source)
        adapter = RecursiveAdapter([{"action": "answer", "answer": "Guard empty stats.mean input."}])
        original_advise = adapter.advise
        def mutate_source(*args):
            (source / "instructions.md").write_text("Unreviewed source instructions changed during analysis.\n")
            return original_advise(*args)
        adapter.advise = mutate_source
        result = self.experiment(adapter, pack=source)
        self.assertEqual(result["status"], "passed", result)
        self.assertNotEqual(pack_digest(source), initial_digest)
        self.assertEqual(result["pack_sha256"], initial_digest)
        self.assertEqual(result["worker"]["pack_sha256"], initial_digest)
        self.assertIn(initial, adapter.prompts[0])
        self.assertNotIn("Unreviewed source instructions", adapter.prompts[0])

    def test_output_inside_pack_rejected_before_model_or_artifacts(self):
        source = copy_pack(ASSETS / "packs" / "backend", self.root / "source-pack")
        output = source / "experiment"
        adapter = RecursiveAdapter([{"action": "answer", "answer": "No model call expected"}])
        with self.assertRaisesRegex(ValueError, "outside the source pack"):
            recursive_run(self.repo, self.task, self.policy, output, pack=source, adapter=adapter)
        self.assertEqual(adapter.models, [])
        self.assertFalse(output.exists())

    def test_analyzer_edits_rejected(self):
        adapter = RecursiveAdapter([{"action": "answer", "answer": "Fixed"}], edit=True)
        self.assertEqual(self.experiment(adapter)["status"], "integrity_failed")

    def test_outside_file_and_oversized_advice_rejected(self):
        adapter = RecursiveAdapter([{"action": "read", "path": "../../secret"}])
        self.assertEqual(self.experiment(adapter)["status"], "error")
        with self.assertRaisesRegex(ValueError, "12,000"):
            run(self.repo, self.task, self.policy, self.root / "runs", extra_context="x"*12001)
        self.assertFalse((self.root / "runs").exists())


if __name__ == "__main__":
    unittest.main()
