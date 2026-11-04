import importlib.util
import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from codex_harness.config import ASSETS, load_policy, read
from codex_harness.demo import create
from codex_harness.experimental.gepa import optimize_pack
from codex_harness.improve import copy_pack, fingerprint, pack_digest
from codex_harness.runner import save


@dataclass
class Batch:
    outputs: list
    scores: list
    trajectories: list | None = None


class Reflector:
    def __init__(self):
        self.prompts = []

    def advise(self, policy, model, workspace, prompt, timeout, log, role):
        self.prompts.append(prompt)
        return {"returncode": 0, "completed": True, "reason": None,
                "message": "```\nCheck empty input before arithmetic.\n```", "cost_usd": .01,
                "usage": {"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 30}}


class FakeEngine:
    EvaluationBatch = Batch

    def optimize(self, **kwargs):
        self.arguments = kwargs
        adapter = kwargs["adapter"]
        old = adapter.evaluate(kwargs["valset"], kwargs["seed_candidate"])
        train = adapter.evaluate(kwargs["trainset"], kwargs["seed_candidate"], capture_traces=True)
        feedback = adapter.make_reflective_dataset(kwargs["seed_candidate"], train, ["instructions"])
        kwargs["reflection_lm"](json.dumps(feedback))
        candidate = {"instructions": "Check empty input before arithmetic."}
        new = adapter.evaluate(kwargs["valset"], candidate)
        return SimpleNamespace(best_candidate=candidate, val_aggregate_scores=[old.scores[0], new.scores[0]],
                               candidates=[kwargs["seed_candidate"], candidate], parents=[[None], [0]])


class GepaTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = copy_pack(ASSETS / "packs" / "backend", self.root / "pack")
        self.fixture = create(self.root / "fixture")
        self.paths = []
        for split, name in (("train", "mean"), ("validation", "slug"), ("holdout", "chunks")):
            path = self.fixture / f"{split}.json"
            save(path, {"tasks": [{"repo": "repo", "task": f"{name}.json"}]})
            self.paths.append(path)
        self.reflector, self.engine, self.calls = Reflector(), FakeEngine(), []

    def tearDown(self):
        self.temporary.cleanup()

    def fake_run(self, repo, task, policy, output, pack, **kwargs):
        self.calls.append(task)
        success = (pack / "instructions.md").read_text() == "Check empty input before arithmetic."
        return {"id": f"run-{len(self.calls)}", "status": "passed" if success else "failed", "tokens": 200,
                "cost_usd": .02, "attempts": [], "pack_sha256": pack_digest(pack),
                "artifact_directory": str(output / f"run-{len(self.calls)}")}

    def optimize(self, **kwargs):
        args = {"policy": load_policy(), "reflection_model": "strong", "adapter": self.reflector,
                "gepa_module": self.engine, "holdout_suite": self.paths[2], "max_metric_calls": 6}
        args.update(kwargs)
        with patch("codex_harness.experimental.gepa.run", side_effect=self.fake_run):
            return optimize_pack(self.source, self.paths[0], self.paths[1], self.fixture / "repo", self.root / "output", **args)

    def test_public_engine_contract_produces_separate_holdout_candidate(self):
        result = self.optimize()
        self.assertEqual(result["status"], "candidate_requires_holdout_evaluation", result)
        self.assertEqual(result["metric_calls"], 3)
        self.assertEqual(result["accounting"]["tokens"], 730)
        self.assertEqual(len(self.reflector.prompts), 1)
        self.assertEqual(self.engine.arguments["candidate_selection_strategy"], "pareto")
        self.assertTrue(self.engine.arguments["use_merge"])
        self.assertEqual({task["id"] for task in self.calls}, {"mean", "slug"})
        proposal = read(Path(result["candidate"]) / "proposal.json")
        self.assertEqual(len(proposal["development_task_hashes"]), 2)
        self.assertEqual(len(proposal["development_prompt_hashes"]), 2)
        self.assertNotIn("chunks", json.dumps(self.reflector.prompts))
        self.assertFalse(result["reserved_holdout_executed"])

    def test_leaked_or_renamed_prompt_rejected_before_engine(self):
        task = read(self.fixture / "mean.json")
        task["id"], task["prompt"] = "renamed", task["prompt"].upper()
        save(self.fixture / "slug.json", task)
        with self.assertRaisesRegex(ValueError, "disjoint"):
            self.optimize()
        self.assertFalse(self.calls)

    def test_historical_development_prompt_cannot_be_a_renamed_holdout(self):
        task = read(self.fixture / "chunks.json")
        save(self.source / "proposal.json", {"development_task_hashes": ["a" * 64],
             "development_prompt_hashes": [fingerprint(" ".join(task["prompt"].casefold().split()))]})
        with self.assertRaisesRegex(ValueError, "historical development"):
            self.optimize()
        self.assertFalse(self.calls)

    def test_proposal_preserves_historical_task_and_prompt_hashes(self):
        save(self.source / "proposal.json", {"development_task_hashes": ["a" * 64],
             "development_prompt_hashes": ["b" * 64], "development_task_ids": ["previous"]})
        result = self.optimize()
        self.assertEqual(result["status"], "candidate_requires_holdout_evaluation", result)
        proposal = read(Path(result["candidate"]) / "proposal.json")
        self.assertEqual(len(proposal["development_task_hashes"]), 3)
        self.assertEqual(len(proposal["development_prompt_hashes"]), 3)
        self.assertIn("a" * 64, proposal["development_task_hashes"])
        self.assertIn("b" * 64, proposal["development_prompt_hashes"])

    def test_budget_stops_without_emitting_unevaluated_candidate(self):
        result = self.optimize(max_tokens=150)
        self.assertEqual(result["status"], "budget_stopped")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(result["accounting"]["tokens"], 200)
        self.assertFalse((self.root / "output" / "candidate").exists())

    def test_infrastructure_does_not_become_quality_signal(self):
        original = self.fake_run
        def failure(*args, **kwargs):
            row = original(*args, **kwargs)
            row["status"] = "verification_error"
            return row
        self.fake_run = failure
        result = self.optimize()
        self.assertEqual(result["status"], "rejected")
        self.assertIn("infrastructure", result["reason"])
        self.assertFalse(self.reflector.prompts)

    def test_unknown_accounting_stops(self):
        original = self.fake_run
        def unknown(*args, **kwargs):
            row = original(*args, **kwargs)
            row["tokens"] = None
            return row
        self.fake_run = unknown
        result = self.optimize()
        self.assertEqual(result["status"], "budget_stopped")
        self.assertIsNone(result["accounting"]["tokens"])

    @unittest.skipUnless(importlib.util.find_spec("gepa"), "Optional upstream GEPA package not installed")
    def test_real_upstream_pareto_engine_with_offline_rollouts(self):
        import gepa
        result = self.optimize(gepa_module=gepa)
        self.assertEqual(result["status"], "candidate_requires_holdout_evaluation", result)
        self.assertGreaterEqual(result["candidates_explored"], 2)
        self.assertLessEqual(result["metric_calls"], 6)
        self.assertEqual((Path(result["candidate"]) / "instructions.md").read_text(), "Check empty input before arithmetic.")


if __name__ == "__main__":
    unittest.main()
