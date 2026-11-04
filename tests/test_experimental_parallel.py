import copy
import threading
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

from codex_harness.config import ASSETS, load_policy, load_task, read
from codex_harness.codex import CodexAdapter
from codex_harness.demo import create
from codex_harness.experimental.parallel import best_of_n, teams
from codex_harness.runner import git


class Analyst:
    def __init__(self, invalid=False, edit=False):
        self.invalid = invalid
        self.edit = edit
        self.calls = []
        self.lock = threading.Lock()

    def advise(self, policy, model, workspace, prompt, timeout, log, role):
        with self.lock:
            self.calls.append({"workspace": workspace, "prompt": prompt, "model": model, "timeout": timeout})
        if self.edit:
            (workspace / "unauthorized.txt").write_text("Changed by a read-only analyst")
        return {"returncode": 0, "reason": None, "completed": True,
                "message": "Inspect stats.py: mean() divides by length; the empty-input contract needs a guard.",
                "usage": None if self.invalid else {"input_tokens": 80, "cached_input_tokens": 20, "output_tokens": 20},
                "cost_usd": .01}


class ParallelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.fixture = create(self.root / "fixtures")
        self.repo = self.fixture / "repo"
        self.task = load_task(self.fixture / "mean.json")
        self.policy = load_policy(overrides={"codex_command": ["echo"], "max_attempts": 2,
                                             "cheap_attempts": 2, "attempt_timeout_seconds": 5})
        self.output = self.root / "experiment"
        self.calls = []
        self.lock = threading.Lock()
        self.active = self.peak = 0

    def tearDown(self):
        self.temp.cleanup()

    def candidate(self, repo, task, policy, output, pack=None, mcp=None, **kwargs):
        label = kwargs["label"]
        with self.lock:
            self.calls.append((task, policy, kwargs))
            self.active += 1
            self.peak = max(self.peak, self.active)
        time.sleep(.02)
        with self.lock:
            self.active -= 1
        number = int(label.split("-")[-1]) if label.startswith("candidate-") else 1
        directory = output / label
        directory.mkdir(parents=True)
        (directory / "accepted.patch").write_text(f"verified patch {label}")
        return {"id": label, "label": label, "status": "passed", "tokens": 150 - 10 * number,
                "cost_usd": .1, "base_commit": kwargs["revision"], "artifact_directory": str(directory)}

    def call_best(self, **kwargs):
        with patch("codex_harness.experimental.parallel.run", side_effect=self.candidate):
            return best_of_n(self.repo, self.task, self.policy, self.output, **kwargs)

    def test_best_selects_verified_candidate_and_counts_all_spending(self):
        result = self.call_best(candidates=3, concurrency=2)
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["selected_run_id"], "candidate-3")
        self.assertEqual(result["accounting"]["tokens"], 390)
        self.assertAlmostEqual(result["accounting"]["cost_usd"], .3)
        self.assertEqual(Path(result["accepted_patch"]).read_text(), "verified patch candidate-3")
        self.assertEqual(self.peak, 2)
        self.assertEqual(len({kwargs["revision"] for _, _, kwargs in self.calls}), 1)
        self.assertEqual(git(self.repo, "status", "--porcelain"), b"")
        self.assertEqual(read(self.output / "experiment.json"), result)

    def test_failed_candidates_are_charged_and_never_selected(self):
        original = self.candidate
        def some_fail(*args, **kwargs):
            result = original(*args, **kwargs)
            if kwargs["label"] == "candidate-3":
                result["status"] = "failed"
            return result
        with patch("codex_harness.experimental.parallel.run", side_effect=some_fail):
            result = best_of_n(self.repo, self.task, self.policy, self.output)
        self.assertEqual(result["selected_run_id"], "candidate-2")
        self.assertEqual(result["accounting"]["tokens"], 390)

    def test_unknown_usage_stops_future_batches_and_selection(self):
        original = self.candidate
        def unknown(*args, **kwargs):
            result = original(*args, **kwargs)
            result["tokens"] = None
            return result
        with patch("codex_harness.experimental.parallel.run", side_effect=unknown):
            result = best_of_n(self.repo, self.task, self.policy, self.output, candidates=4, concurrency=2)
        self.assertEqual(result["status"], "usage_unknown")
        self.assertEqual(len(self.calls), 2)
        self.assertIsNone(result["accepted_patch"])
        self.assertIsNone(result["accounting"]["tokens"])

    def test_shared_limit_stops_between_batches_retains_verified_result(self):
        result = self.call_best(candidates=4, concurrency=2, max_total_tokens=200)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(result["termination_reason"], "budget_exhausted")
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["accounting"]["tokens"], 270)

    def test_preflight_rejects_unbounded_fanout_or_unpriced_dollars(self):
        for args in ({"candidates": 17}, {"concurrency": 5}, {"selection_metric": "usd"}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.call_best(**args)
            self.assertFalse(self.output.exists())
        self.assertFalse(self.calls)

    def test_nonignored_source_output_rejected_before_any_call(self):
        self.output = self.repo / "artifacts"
        with self.assertRaisesRegex(ValueError, "not safely ignored"):
            self.call_best()
        self.assertFalse(self.output.exists())

    def test_unreturned_candidate_does_not_disappear_from_accounting(self):
        with patch("codex_harness.experimental.parallel.run", side_effect=RuntimeError("in-flight failure")):
            result = best_of_n(self.repo, self.task, self.policy, self.output, candidates=3, concurrency=2)
        self.assertEqual(result["status"], "usage_unknown")
        self.assertEqual(len(result["records"]), 2)
        self.assertIsNone(result["accounting"]["tokens"])
        self.assertFalse((self.output / "accepted.patch").exists())

    def test_interrupt_drains_inflight_work_and_preserves_unknown_record(self):
        original = self.candidate
        def interrupted(*args, **kwargs):
            if kwargs["label"] == "candidate-1":
                raise KeyboardInterrupt()
            return original(*args, **kwargs)
        with patch("codex_harness.experimental.parallel.run", side_effect=interrupted):
            result = best_of_n(self.repo, self.task, self.policy, self.output, candidates=4, concurrency=2)
        self.assertEqual(result["status"], "interrupted")
        self.assertEqual(self.active, 0)
        self.assertEqual(len(result["records"]), 2)
        self.assertIsNone(result["accepted_patch"])

    def test_interrupt_during_submission_drains_started_work_and_marks_usage_unknown(self):
        submit = ThreadPoolExecutor.submit
        def interrupted_submit(executor, *args, **kwargs):
            submit(executor, *args, **kwargs)
            raise KeyboardInterrupt()
        with patch("codex_harness.experimental.parallel.run", side_effect=self.candidate), \
                patch.object(ThreadPoolExecutor, "submit", interrupted_submit):
            result = best_of_n(self.repo, self.task, self.policy, self.output, candidates=4)
        self.assertEqual(result["status"], "interrupted")
        self.assertEqual(self.active, 0)
        self.assertEqual(len(self.calls), 1)
        self.assertIsNone(result["accounting"]["tokens"])
        self.assertIsNone(result["accepted_patch"])

    def test_team_uses_separate_analyst_clones_and_accounts_for_coordinator(self):
        adapter = Analyst()
        with patch("codex_harness.experimental.parallel.run", side_effect=self.candidate):
            result = teams(self.repo, self.task, self.policy, self.output, adapter=adapter,
                           specialist_model="cheap", coordinator_model="strong", concurrency=2)
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(len(adapter.calls), 4)
        self.assertEqual(len({row["workspace"] for row in adapter.calls}), 4)
        self.assertEqual([row["model"] for row in adapter.calls].count("cheap"), 3)
        self.assertEqual(adapter.calls[-1]["model"], "strong")
        self.assertEqual(len(self.calls), 1)
        self.assertIn("Coordinator advice", self.calls[0][2]["extra_context"])
        self.assertEqual(result["accounting"]["tokens"], 540)
        self.assertEqual(git(self.repo, "status", "--porcelain"), b"")

    def test_unknown_or_writing_specialist_prevents_implementation(self):
        for index, adapter in enumerate((Analyst(invalid=True), Analyst(edit=True))):
            output = self.root / f"team-{index}"
            with patch("codex_harness.experimental.parallel.run", side_effect=self.candidate):
                result = teams(self.repo, self.task, self.policy, output, adapter=adapter, concurrency=1)
            self.assertIn(result["status"], {"usage_unknown", "analysis_failed"})
            self.assertIsNone(result["accepted_patch"])
        self.assertFalse(self.calls)

    def test_team_budget_accounts_for_analysis_before_worker_launch(self):
        with patch("codex_harness.experimental.parallel.run", side_effect=self.candidate):
            result = teams(self.repo, self.task, self.policy, self.output, adapter=Analyst(),
                           concurrency=1, max_total_tokens=150)
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertEqual(result["accounting"]["tokens"], 200)
        self.assertFalse(self.calls)

    def test_real_runner_candidates_use_normal_subprocess_and_verifier(self):
        policy = load_policy(overrides={"codex_command": [__import__("sys").executable, str(ASSETS / "fake_codex.py")],
                                        "model": "simulator", "max_attempts": 2, "cheap_attempts": 2})
        result = best_of_n(self.repo, self.task, policy, self.output, candidates=2, concurrency=2)
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(len(result["records"]), 2)
        self.assertEqual(result["accounting"]["tokens"], 520)
        self.assertTrue(all(row["status"] == "passed" for row in result["records"]))
        self.assertIn("stats.py", Path(result["accepted_patch"]).read_text())
        self.assertEqual(git(self.repo, "status", "--porcelain"), b"")

    def test_real_team_implementer_verifies_advice_in_fresh_clone(self):
        policy = load_policy(overrides={"codex_command": [__import__("sys").executable, str(ASSETS / "fake_codex.py")],
                                        "model": "simulator", "max_attempts": 2, "cheap_attempts": 2})
        adapter = Analyst()
        adapter.run = CodexAdapter().run
        result = teams(self.repo, self.task, policy, self.output, adapter=adapter, concurrency=2)
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["accounting"]["tokens"], 560)
        self.assertEqual(len(result["records"]), 4)
        self.assertEqual(result["records"][-1]["extra_context_sha256"], result["advice_sha256"])
        self.assertIn("stats.py", Path(result["accepted_patch"]).read_text())
        self.assertEqual(git(self.repo, "status", "--porcelain"), b"")


if __name__ == "__main__":
    unittest.main()
