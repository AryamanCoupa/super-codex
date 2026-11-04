import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_harness.cli import pack_path
from codex_harness.config import ASSETS, load_task, read
from codex_harness.codex import CodexAdapter
from codex_harness.demo import create
from codex_harness.improve import copy_pack, fingerprint, pack_digest
from codex_harness.optimize import optimize
from codex_harness.runner import save


class Proposer:
    def __init__(self, usage=True, unchanged=None):
        self.calls = 0
        self.usage = usage
        self.unchanged = unchanged
        self.prompts = []

    def advise(self, policy, model, repo, prompt, timeout, log, role):
        self.calls += 1
        self.prompts.append(prompt)
        delta = {"operation": "noop" if self.unchanged else "append", "old": "",
                 "new": "" if self.unchanged else "\nFor collection edge cases, check empty input before applying arithmetic.\n",
                 "rationale": "Development evidence shows an unhandled empty-input case."}
        return {"returncode": 0, "reason": None, "completed": True, "message": json.dumps(delta),
                "usage": {"input_tokens": 100, "cached_input_tokens": 50, "output_tokens": 30} if self.usage else None,
                "cost_usd": 0.01}


class OptimizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = copy_pack(ASSETS / "packs" / "backend", self.root / "pack")
        self.fixture = create(self.root / "fixture")
        task = load_task(self.fixture / "mean.json", self.source)
        self.evidence = [{"id": "dev-1", "task_id": task["id"], "task": task, "task_sha256": fingerprint(task),
                          "pack_sha256": pack_digest(self.source), "status": "failed", "attempts": []}]
        self.suite = self.fixture / "holdout.json"
        save(self.suite, {"tasks": [{"repo": "repo", "task": "slug.json"},
                                   {"repo": "repo", "task": "chunks.json"}]})
        self.registry = self.root / "registry"
        self.output = self.root / "cycle"
        self.proposer = Proposer()
        self.calls = []

    def tearDown(self):
        self.temp.cleanup()

    def fake_run(self, repo, task, policy, output, pack, **kwargs):
        self.calls.append((task, kwargs))
        label = kwargs["label"]
        return {"id": f"run-{len(self.calls)}", "task_id": task["id"], "task": copy.deepcopy(task), "task_sha256": fingerprint(task),
                "pack_sha256": pack_digest(pack), "policy": policy, "base_commit": kwargs["revision"],
                "mcp_sha256": "same-tools", "codex_version": "fake-cli-1", "platform": "test-os", "python": "3.11",
                "status": "passed", "label": label,
                "tokens": 100 if label == "baseline" else 80, "cost_usd": .1 if label == "baseline" else .08,
                "artifact_directory": str(output / f"run-{len(self.calls)}")}

    def call(self, **overrides):
        args = {"min_runs": 2, "min_distinct_tasks": 2, "max_runs": 4,
                "cost_metric": "tokens", "adapter": self.proposer}
        args.update(overrides)
        with patch("codex_harness.optimize.run", side_effect=self.fake_run):
            return optimize(self.source, self.evidence, self.suite, self.fixture / "repo",
                            self.registry, self.output, **args)

    def test_full_cycle_promotes_with_total_accounting_and_frozen_pairs(self):
        result = self.call()
        self.assertEqual(result["status"], "promoted", result)
        self.assertEqual(result["accounting"]["tokens"], 490)
        self.assertAlmostEqual(result["accounting"]["cost_usd"], .37)
        self.assertEqual(result["accounting"]["proposal"]["tokens"], 130)
        self.assertEqual(result["accounting"]["evaluation"]["tokens"], 360)
        self.assertEqual(result["accounting"]["evaluation_runs"], 4)
        self.assertEqual(pack_path(str(self.registry)), Path(result["release"]))
        self.assertTrue(read(self.registry / "active.json")["previous"])
        self.assertFalse((self.registry / ".optimize.lock").exists())
        self.assertEqual(read(self.output / "optimization.json"), result)
        revisions = {kwargs["revision"] for _, kwargs in self.calls}
        self.assertEqual(len(revisions), 1)
        self.assertNotIn(load_task(self.fixture / "slug.json")["prompt"], self.proposer.prompts[0])
        self.assertNotIn(load_task(self.fixture / "chunks.json")["prompt"], self.proposer.prompts[0])

    def test_missing_or_wrong_evidence_provenance_rejected_before_model(self):
        self.evidence[0].pop("pack_sha256")
        with self.assertRaisesRegex(ValueError, "pack hash"):
            self.call()
        self.assertEqual(self.proposer.calls, 0)
        self.assertFalse(self.output.exists())

    def test_renamed_development_prompt_is_not_fresh_holdout(self):
        task = copy.deepcopy(self.evidence[0]["task"])
        task["id"] = "renamed"
        task["prompt"] = "  " + task["prompt"].upper().replace(" ", "   ") + "\n"
        save(self.fixture / "slug.json", task)
        with self.assertRaisesRegex(ValueError, "overlaps development"):
            self.call()
        self.assertEqual(self.proposer.calls, 0)

    def test_repeats_do_not_satisfy_diversity(self):
        save(self.suite, {"repeat": 2, "tasks": [{"repo": "repo", "task": "slug.json"}]})
        with self.assertRaisesRegex(ValueError, "distinct holdout"):
            self.call()
        self.assertEqual(self.proposer.calls, 0)

    def test_run_cap_preflight(self):
        with self.assertRaisesRegex(ValueError, "above max_runs"):
            self.call(max_runs=3)
        self.assertEqual(self.proposer.calls, 0)

    def test_nonignored_artifacts_rejected_before_model_or_writes(self):
        self.output = self.fixture / "repo" / "optimization"
        with self.assertRaisesRegex(ValueError, "not safely ignored"):
            self.call()
        self.assertEqual(self.proposer.calls, 0)
        self.assertFalse(self.output.exists())
        self.output = self.root / "outside"
        self.registry = self.fixture / "repo" / "registry"
        with self.assertRaisesRegex(ValueError, "not safely ignored"):
            self.call()
        self.assertFalse(self.registry.exists())

    def test_usd_requires_prices_before_model(self):
        with self.assertRaisesRegex(ValueError, "explicit prices"):
            self.call(cost_metric="usd")
        self.assertEqual(self.proposer.calls, 0)

    def test_unknown_proposal_usage_stops_without_holdout_calls(self):
        self.proposer.usage = False
        result = self.call()
        self.assertEqual(result["status"], "usage_unknown")
        self.assertEqual(self.calls, [])
        self.assertIsNone(result["accounting"]["tokens"])
        self.assertFalse((self.registry / "holdout-history.json").exists())
        self.assertEqual(pack_digest(pack_path(str(self.registry))), pack_digest(self.source))

    def test_invalid_proposal_still_accounts_for_model_spend(self):
        class InvalidProposer(Proposer):
            def advise(self, *args):
                result = super().advise(*args)
                result["message"] = "not a structured edit"
                return result

        result = self.call(adapter=InvalidProposer())
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["accounting"]["tokens"], 130)
        self.assertEqual(result["accounting"]["cost_usd"], .01)
        self.assertEqual(self.calls, [])
        self.assertFalse((self.registry / "holdout-history.json").exists())

    def test_budget_includes_proposal_and_stops_at_stage_boundary(self):
        result = self.call(max_total_tokens=200)
        self.assertEqual(result["status"], "budget_exceeded")
        self.assertEqual(len(self.calls), 1)
        self.assertGreater(result["accounting"]["tokens"], 200)
        self.assertTrue(result["budget_overrun"])
        self.assertEqual(pack_digest(pack_path(str(self.registry))), pack_digest(self.source))

    def test_noop_proposal_does_not_spend_holdout(self):
        self.proposer.unchanged = (self.source / "instructions.md").read_text()
        result = self.call()
        self.assertEqual(result["status"], "rejected")
        self.assertIn("no instruction change", result["reason"])
        self.assertEqual(self.calls, [])
        self.assertFalse((self.registry / "holdout-history.json").exists())

    def test_regression_rejected_and_holdout_cannot_be_reused(self):
        original = self.fake_run

        def regression(*args, **kwargs):
            row = original(*args, **kwargs)
            if kwargs["label"] == "candidate":
                row["status"] = "failed"
            return row

        self.fake_run = regression
        result = self.call()
        self.assertEqual(result["status"], "rejected")
        self.assertIn("regresses", result["reason"])
        self.assertEqual(pack_digest(pack_path(str(self.registry))), pack_digest(self.source))
        self.output = self.root / "again"
        with self.assertRaisesRegex(ValueError, "earlier optimization"):
            self.call()
        self.assertEqual(self.proposer.calls, 1)

    def test_interrupt_saves_audit_and_releases_lock(self):
        def interrupted(*args, **kwargs):
            raise KeyboardInterrupt

        self.fake_run = interrupted
        result = self.call()
        self.assertEqual(result["status"], "interrupted")
        self.assertEqual(read(self.output / "optimization.json")["status"], "interrupted")
        self.assertFalse((self.registry / ".optimize.lock").exists())
        self.assertTrue((self.registry / "holdout-history.json").exists())
        self.assertIsNone(result["accounting"]["tokens"])

    def test_real_runner_with_offline_cli_keeps_equivalent_candidate_inactive(self):
        class OfflineAdapter(Proposer):
            run = CodexAdapter.run

        config = self.root / "offline.json"
        save(config, {"model": "simulator", "codex_command": [sys.executable, str(ASSETS / "fake_codex.py")],
                      "prices": {"simulator": {"input": 0, "cached_input": 0, "output": 0}}})
        result = optimize(self.source, self.evidence, self.suite, self.fixture / "repo", self.registry,
                          self.output, config=config, min_runs=2, min_distinct_tasks=2, max_runs=4,
                          cost_metric="tokens", adapter=OfflineAdapter())
        self.assertEqual(result["status"], "rejected", result)
        self.assertIn("No observed improvement", result["reason"])
        self.assertEqual(result["accounting"]["evaluation_runs"], 4)
        self.assertEqual(result["accounting"]["tokens"], 1170)
        self.assertTrue(all(row["status"] == "passed" for row in result["results"]))
        self.assertEqual(pack_digest(pack_path(str(self.registry))), pack_digest(self.source))

    def test_active_registry_change_prevents_promotion(self):
        original = self.fake_run

        def mutate_registry(*args, **kwargs):
            result = original(*args, **kwargs)
            (pack_path(str(self.registry)) / "instructions.md").write_text("Changed concurrently")
            return result

        self.fake_run = mutate_registry
        result = self.call()
        self.assertEqual(result["status"], "rejected")
        self.assertIn("registry or source changed", result["reason"])


if __name__ == "__main__":
    unittest.main()
