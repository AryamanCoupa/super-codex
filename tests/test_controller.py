import contextlib
import io
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from codex_harness.cli import build_parser
from codex_harness.controller import execute_turn, handle, prepare
from codex_harness.runner import git


class ControllerTests(unittest.TestCase):
    def setUp(self):
        research = patch("codex_harness.controller.resolve_research", return_value={})
        research.start()
        self.addCleanup(research.stop)
        self.temp = tempfile.TemporaryDirectory(prefix="supercodex controller ")
        self.root = Path(self.temp.name)
        self.repo = self.root / "source"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        git(self.repo, "config", "user.email", "test@example.invalid")
        git(self.repo, "config", "user.name", "Test")
        (self.repo / "code.py").write_text("value = 1\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "baseline")
        self.policy_file = self.root / "policy.json"
        self.policy_file.write_text(json.dumps({"model": "cheap", "max_tokens": 1000,
                                                "run_timeout_seconds": 300,
                                                "prices": {"cheap": {"input": 1, "cached_input": 1, "output": 1}}}))
        self.task = {"id": "fix-value", "prompt": "Set value to two", "checks": [["python", "-m", "unittest"]],
                     "setup": [], "protected_paths": ["tests"], "baseline_must_fail": False}

    def tearDown(self):
        self.temp.cleanup()

    def args(self, *extra):
        return build_parser().parse_args(["start", "--repo", str(self.repo), "--config", str(self.policy_file),
                                         "--output-root", str(self.root / "artifacts"), *extra])

    def plan(self, *extra):
        plan = prepare(self.args(*extra))
        plan["folder"].mkdir(parents=True)
        return plan

    def advisor(self, kind="task", task=None, apply_patch=True, **overrides):
        response = {"message": json.dumps({"kind": kind, "answer": "Prepared from existing checks",
                                            "task": (task or self.task) if kind == "task" else None,
                                            "apply_patch": apply_patch}),
                    "usage": {"input_tokens": 100, "output_tokens": 20, "cached_input_tokens": 0},
                    "cost_usd": .00012, "completed": True, "returncode": 0, "reason": None, "events": []}
        response.update(overrides)
        adapter = Mock()
        adapter.advise.return_value = response
        return adapter

    def runner(self, status="passed", source_changed=False, usage_complete=True):
        def invoke(repo, task, policy, output, **kwargs):
            folder = output / "sample-run"
            folder.mkdir(parents=True)
            base = git(repo, "rev-parse", "HEAD").decode().strip()
            content = b"diff --git a/code.py b/code.py\n--- a/code.py\n+++ b/code.py\n@@ -1 +1 @@\n-value = 1\n+value = 2\n"
            if status == "passed":
                (folder / "accepted.patch").write_bytes(content)
            if source_changed:
                (repo / "code.py").write_text("user concurrent change\n")
            result = {"id": "sample-run", "artifact_directory": str(folder), "base_commit": base,
                      "status": status, "tokens": 230 if usage_complete else None, "known_tokens": 230,
                      "cost_usd": .00023, "usage_complete": usage_complete, "cost_complete": True,
                      "attempts": [{"model": "cheap", "checks": [{"argv": task["checks"][0], "returncode": 0}],
                                    "passed": status == "passed"}], "advisories": [], "baseline": []}
            (folder / "result.json").write_text(json.dumps(result))
            return result
        return Mock(side_effect=invoke)

    def turn(self, plan=None, **kwargs):
        with contextlib.redirect_stderr(io.StringIO()):
            return execute_turn(plan or self.plan(), request="Fix the value; preserve compatibility", **kwargs)

    def test_prepare_uses_worker_model_for_preparation_and_disables_inherited_configuration(self):
        config = json.loads(self.policy_file.read_text())
        config.update(planner_model="expensive", inherit_user_config=True)
        self.policy_file.write_text(json.dumps(config))
        plan = prepare(self.args())
        self.assertEqual(plan["preview"]["operator_model"], "cheap")
        self.assertFalse(plan["policy"]["inherit_user_config"])
        self.assertEqual(plan["preview"]["mode"], "managed")
        self.assertEqual(plan["preview"]["prompt_hook"], {"requested": False, "status": "not_applicable"})
        self.assertTrue(plan["preview"]["harness_enforced"])
        self.assertEqual(prepare(self.args("--operator-model", "custom"))["preview"]["operator_model"], "custom")
        self.assertFalse((self.root / "artifacts").exists())

    def test_operator_prices_required_for_dollar_budget(self):
        config = json.loads(self.policy_file.read_text())
        config.update(max_cost_usd=.5)
        self.policy_file.write_text(json.dumps(config))
        with self.assertRaisesRegex(ValueError, "preparation/operator"):
            prepare(self.args("--operator-model", "unpriced"))

    def test_prepare_run_apply_receipt_and_combined_budgets(self):
        plan = self.plan()
        plan["policy"]["max_cost_usd"] = .5
        adapter, runner = self.advisor(), self.runner()
        receipt = self.turn(plan, adapter=adapter, run_fn=runner)
        self.assertEqual(receipt["status"], "applied")
        self.assertTrue(receipt["verified"] and receipt["harness_run"] and receipt["applied"])
        self.assertEqual((self.repo / "code.py").read_text(), "value = 2\n")
        self.assertEqual(receipt["totals"]["tokens"], 350)
        self.assertAlmostEqual(receipt["totals"]["cost_usd"], .00035)
        worker_policy = runner.call_args.args[2]
        self.assertEqual(worker_policy["max_tokens"], 880)
        self.assertAlmostEqual(worker_policy["max_cost_usd"], .49988)
        self.assertLess(worker_policy["run_timeout_seconds"], 300)
        self.assertIn("Fix the value; preserve compatibility", receipt["task"]["prompt"])
        self.assertNotEqual(adapter.advise.call_args.args[2], self.repo)
        self.assertEqual(adapter.advise.call_args.args[-1], "prepare")
        self.assertFalse(adapter.advise.call_args.args[0]["inherit_user_config"])
        self.assertEqual(json.loads(Path(receipt["receipt_path"]).read_text()), receipt)
        self.assertEqual(stat.S_IMODE(Path(receipt["receipt_path"]).stat().st_mode), 0o600)

    def test_research_connections_are_separate_from_worker_connections(self):
        plan = self.plan()
        plan["research_mcp"] = {"lookup": {"url": "https://example.invalid/read", "enabled_tools": ["search"]}}
        plan["mcp"] = {"build": {"command": "build-tools"}}
        adapter, runner = self.advisor(), self.runner()
        adapter.advise.return_value["events"] = [
            {"type": "item.completed", "item": {"type": "mcp_tool_call", "server": "lookup", "tool": "search", "status": "completed", "arguments": {"private": "not in summary"}}}]
        receipt = self.turn(plan, adapter=adapter, run_fn=runner, patch_only=True)
        self.assertEqual(adapter.advise.call_args.kwargs["mcp"], plan["research_mcp"])
        self.assertEqual(runner.call_args.kwargs["mcp"], plan["mcp"])
        self.assertEqual(receipt["research_mcp_names"], ["lookup"])
        self.assertEqual(receipt["preparation"]["tool_calls"], [{"server": "lookup", "tool": "search", "status": "completed"}])
        self.assertNotIn("research_mcp", runner.call_args.args[2])

    def test_patch_only_flag_and_prepared_user_restriction_prevent_apply(self):
        for by_flag in (True, False):
            with self.subTest(flag=by_flag):
                receipt = self.turn(adapter=self.advisor(apply_patch=by_flag), run_fn=self.runner(), patch_only=by_flag)
                self.assertEqual(receipt["status"], "passed")
                self.assertFalse(receipt["applied"])
                self.assertTrue(receipt["patch_only"])
                self.assertEqual((self.repo / "code.py").read_text(), "value = 1\n")

    def test_explicit_task_skips_preparation(self):
        file = self.root / "task.json"
        file.write_text(json.dumps(self.task))
        adapter = self.advisor()
        receipt = self.turn(adapter=adapter, run_fn=self.runner(), task_file=file, patch_only=True)
        adapter.advise.assert_not_called()
        self.assertIsNone(receipt["preparation"])
        self.assertEqual(receipt["totals"]["tokens"], 230)

    def test_advisory_answer_does_not_claim_harness_run(self):
        runner = self.runner()
        receipt = self.turn(adapter=self.advisor(kind="answer", apply_patch=False), run_fn=runner)
        self.assertEqual(receipt["status"], "advisory")
        self.assertFalse(receipt["harness_run"] or receipt["verified"] or receipt["applied"])
        runner.assert_not_called()
        self.assertEqual(receipt["totals"]["tokens"], 120)

    def startup_failure(self, log_text, **overrides):
        response = {"completed": False, "returncode": 1, "message": "", "usage": None,
                    "cost_usd": None, "reason": None, "transport": "exec", "events": []}
        response.update(overrides)
        adapter = self.advisor(**response)
        def fail(*args, **kwargs):
            Path(args[5]).write_text(log_text)
            return dict(response)
        adapter.advise.side_effect = fail
        return adapter

    def test_exact_premodel_permission_failure_has_host_approval_guidance_without_retry(self):
        log_text = ("WARNING: proceeding, even though we could not create PATH aliases: Operation not permitted (os error 1)\n"
                    "Error: failed to initialize in-process app-server client: Operation not permitted (os error 1)\n")
        plan = self.plan()
        adapter, runner = self.startup_failure(log_text), self.runner()
        receipt = self.turn(plan, adapter=adapter, run_fn=runner)
        self.assertEqual(receipt["status"], "preparation_failed")
        self.assertEqual(receipt["preparation"]["failure_kind"], "startup_permission_denied")
        self.assertIn("request approval to retry the same SuperCodex command", receipt["reason"])
        self.assertIn("Preserve the child Codex sandbox", receipt["reason"])
        self.assertFalse(receipt["harness_run"] or receipt["verified"] or receipt["applied"])
        self.assertIsNone(receipt["totals"]["tokens"])
        self.assertEqual(adapter.advise.call_count, 1)
        runner.assert_not_called()
        self.assertEqual(json.loads(Path(receipt["receipt_path"]).read_text()), receipt)
        self.assertFalse(plan["policy"]["inherit_user_config"])

    def test_permission_diagnostic_does_not_misclassify_later_events_usage_or_other_transports(self):
        log_text = "Error: failed to initialize in-process app-server client: Operation not permitted (os error 1)\n"
        cases = [
            {"events": [{"type": "thread.started"}]},
            {"usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}},
            {"transport": "app-server"},
            {"message": "A model response exists"},
            {"reason": "timeout"},
        ]
        for overrides in cases:
            with self.subTest(overrides=overrides):
                adapter, runner = self.startup_failure(log_text, **overrides), self.runner()
                receipt = self.turn(adapter=adapter, run_fn=runner)
                self.assertNotIn("failure_kind", receipt["preparation"])
                self.assertNotIn("request approval", receipt["reason"])
                self.assertEqual(adapter.advise.call_count, 1)
                runner.assert_not_called()

    def test_other_startup_errors_keep_generic_failure_without_exposing_log_content(self):
        for log_text in ("Operation not permitted while accessing a provider\n",
                         "WARNING: proceeding, even though we could not create PATH aliases: Operation not permitted (os error 1)\n",
                         "Error: private fixture connection detail\n"):
            with self.subTest(log_text=log_text):
                runner = self.runner()
                receipt = self.turn(adapter=self.startup_failure(log_text), run_fn=runner)
                self.assertEqual(receipt["status"], "preparation_failed")
                self.assertNotIn("failure_kind", receipt["preparation"])
                self.assertIn("Inspect", receipt["reason"])
                self.assertNotIn("private fixture", receipt["reason"])
                self.assertNotIn("request approval", receipt["reason"])
                runner.assert_not_called()

    def uncommitted_source(self, name, initialize=False):
        self.repo = self.root / name
        self.repo.mkdir()
        (self.repo / "private-notes.txt").write_text("Do not copy unrelated directory contents.\n")
        if initialize:
            git(self.repo, "init", "-q")

    def test_research_from_nongit_directory_uses_empty_private_workspace(self):
        self.uncommitted_source("ordinary directory")
        adapter, runner = self.advisor(kind="answer", apply_patch=False), self.runner()
        receipt = self.turn(adapter=adapter, run_fn=runner)
        self.assertEqual(receipt["status"], "advisory")
        self.assertEqual(receipt["source_context"]["kind"], "not_git")
        self.assertIsNone(receipt["base_commit"])
        self.assertFalse(receipt["harness_run"] or receipt["verified"] or receipt["applied"])
        self.assertEqual(receipt["totals"]["tokens"], 120)
        runner.assert_not_called()
        workspace = adapter.advise.call_args.args[2]
        self.assertNotEqual(workspace, self.repo)
        self.assertEqual(git(workspace, "ls-files"), b"")
        self.assertEqual(git(workspace, "rev-parse", "HEAD").decode().strip(), receipt["preparation_base_commit"])
        self.assertIn("no files from the selected directory were copied", adapter.advise.call_args.args[3])
        self.assertEqual(list(self.repo.iterdir()), [self.repo / "private-notes.txt"])
        self.assertEqual((self.repo / "private-notes.txt").read_text(), "Do not copy unrelated directory contents.\n")

    def test_research_from_unborn_git_does_not_create_user_commit(self):
        self.uncommitted_source("unborn repository", initialize=True)
        before_head = (self.repo / ".git/HEAD").read_bytes()
        adapter, runner = self.advisor(kind="answer", apply_patch=False), self.runner()
        receipt = self.turn(adapter=adapter, run_fn=runner)
        self.assertEqual(receipt["status"], "advisory")
        self.assertEqual(receipt["source_context"]["kind"], "unborn")
        self.assertIsNone(receipt["base_commit"])
        runner.assert_not_called()
        self.assertEqual((self.repo / ".git/HEAD").read_bytes(), before_head)
        self.assertFalse((self.repo / ".git/index").exists())
        with self.assertRaises(RuntimeError):
            git(self.repo, "rev-parse", "--verify", "HEAD^{commit}")
        self.assertEqual(git(adapter.advise.call_args.args[2], "ls-files"), b"")

    def test_prepared_coding_task_without_source_commit_has_actionable_block(self):
        for initialize in (False, True):
            with self.subTest(git_initialized=initialize):
                self.uncommitted_source(f"coding directory {initialize}", initialize=initialize)
                adapter, runner = self.advisor(), self.runner()
                receipt = self.turn(adapter=adapter, run_fn=runner)
                self.assertEqual(receipt["status"], "blocked")
                self.assertIn("--repo /path/to/project", receipt["reason"])
                self.assertIn("clean, committed Git checkout", receipt["reason"])
                self.assertNotIn("fatal:", receipt["reason"])
                self.assertFalse(receipt["harness_run"] or receipt["applied"])
                self.assertEqual(receipt["totals"]["tokens"], 120)
                runner.assert_not_called()
                self.assertTrue((self.repo / "private-notes.txt").is_file())

    def test_explicit_task_without_source_commit_blocks_before_model_preparation(self):
        file = self.root / "explicit-task.json"
        file.write_text(json.dumps(self.task))
        for initialize in (False, True):
            with self.subTest(git_initialized=initialize):
                self.uncommitted_source(f"explicit directory {initialize}", initialize=initialize)
                adapter, runner = self.advisor(), self.runner()
                receipt = self.turn(adapter=adapter, run_fn=runner, task_file=file)
                self.assertEqual(receipt["status"], "blocked")
                self.assertIn("--repo /path/to/project", receipt["reason"])
                self.assertIsNone(receipt["preparation"])
                self.assertEqual(receipt["totals"]["tokens"], 0)
                adapter.advise.assert_not_called()
                runner.assert_not_called()

    def test_dirty_checkout_still_allows_advisory_on_committed_snapshot(self):
        (self.repo / "code.py").write_text("pending user work\n")
        adapter, runner = self.advisor(kind="answer", apply_patch=False), self.runner()
        receipt = self.turn(adapter=adapter, run_fn=runner)
        self.assertEqual(receipt["status"], "advisory")
        self.assertTrue(receipt["source_context"]["dirty"])
        self.assertEqual((adapter.advise.call_args.args[2] / "code.py").read_text(), "value = 1\n")
        self.assertEqual((self.repo / "code.py").read_text(), "pending user work\n")
        runner.assert_not_called()

    def test_invalid_response_and_missing_checks_block_before_runner(self):
        invalid_task = {**self.task, "checks": []}
        for adapter in (self.advisor(message="not json"), self.advisor(task=invalid_task),
                        self.advisor(task={**self.task, "checks": [["true"]]})):
            with self.subTest(response=adapter.advise.return_value["message"]):
                runner = self.runner()
                receipt = self.turn(adapter=adapter, run_fn=runner)
                self.assertEqual(receipt["status"], "blocked")
                self.assertTrue(Path(receipt["receipt_path"]).is_file())
                runner.assert_not_called()

    def test_pack_gates_cannot_be_removed_by_preparation(self):
        pack = self.root / "pack"
        pack.mkdir()
        (pack / "pack.toml").write_text('name = "guarded"\n[task]\nchecks = [["python", "check_contract.py"]]\n'
                                        'setup = [["python", "setup_test.py"]]\nprotected_paths = ["contracts"]\n'
                                        'baseline_must_fail = true\n')
        receipt = self.turn(self.plan("--pack", str(pack)), adapter=self.advisor(), run_fn=self.runner(), patch_only=True)
        self.assertEqual(receipt["task"]["checks"], [["python", "check_contract.py"], ["python", "-m", "unittest"]])
        self.assertEqual(receipt["task"]["setup"], [["python", "setup_test.py"]])
        self.assertEqual(receipt["task"]["protected_paths"], ["contracts", "tests"])
        self.assertTrue(receipt["task"]["baseline_must_fail"])

    def test_unknown_preparation_usage_and_exhausted_budget_stop_next_model_stage(self):
        cases = [(self.advisor(usage=None), "usage_unknown"),
                 (self.advisor(usage={"input_tokens": 1000, "output_tokens": 1}), "budget_exhausted")]
        for adapter, status in cases:
            with self.subTest(status=status):
                runner = self.runner()
                receipt = self.turn(adapter=adapter, run_fn=runner)
                self.assertEqual(receipt["status"], status)
                runner.assert_not_called()

    def test_generated_tasks_protect_existing_conventional_tests_but_explicit_task_owns_its_gates(self):
        paths = ["tests/contract.py", "test/test_case.rb", "src/__tests__/feature.ts", "test_value.py",
                 "value_test.py", "src/feature.spec.ts", "src/feature.test.jsx"]
        for name in paths + ["src/runtime.py"]:
            path = self.repo / name
            path.parent.mkdir(exist_ok=True, parents=True)
            path.write_text("# fixture\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "add committed tests")
        unprotected = {**self.task, "protected_paths": []}
        receipt = self.turn(adapter=self.advisor(task=unprotected), run_fn=self.runner(), patch_only=True)
        self.assertEqual(set(receipt["task"]["protected_paths"]), set(paths))
        explicit = self.root / "explicit.json"
        explicit.write_text(json.dumps(unprotected))
        receipt = self.turn(adapter=self.advisor(), run_fn=self.runner(), task_file=explicit, patch_only=True)
        self.assertEqual(receipt["task"]["protected_paths"], [])

    def test_missing_accepted_artifact_is_not_reported_as_verified(self):
        runner = self.runner()
        invoke = runner.side_effect
        def missing(*args, **kwargs):
            result = invoke(*args, **kwargs)
            (Path(result["artifact_directory"]) / "accepted.patch").unlink()
            return result
        runner.side_effect = missing
        receipt = self.turn(adapter=self.advisor(), run_fn=runner)
        self.assertEqual(receipt["status"], "infrastructure_error")
        self.assertFalse(receipt["verified"] or receipt["applied"])

    def test_unknown_preparation_cost_stops_when_dollar_budget_is_set(self):
        plan = self.plan()
        plan["policy"]["max_cost_usd"] = .5
        runner = self.runner()
        receipt = self.turn(plan, adapter=self.advisor(cost_usd=None), run_fn=runner)
        self.assertEqual(receipt["status"], "usage_unknown")
        self.assertIsNone(receipt["totals"]["cost_usd"])
        runner.assert_not_called()

    def test_dirty_source_cannot_enter_coding_run(self):
        (self.repo / "code.py").write_text("pending user work\n")
        runner = self.runner()
        receipt = self.turn(adapter=self.advisor(), run_fn=runner)
        self.assertEqual(receipt["status"], "blocked")
        self.assertIn("dirty", receipt["reason"])
        runner.assert_not_called()
        self.assertEqual((self.repo / "code.py").read_text(), "pending user work\n")

    def test_failed_verification_or_concurrent_edit_never_applies_patch(self):
        receipt = self.turn(adapter=self.advisor(), run_fn=self.runner(status="failed"))
        self.assertEqual(receipt["status"], "failed")
        self.assertFalse(receipt["verified"] or receipt["applied"])
        self.assertEqual((self.repo / "code.py").read_text(), "value = 1\n")
        receipt = self.turn(adapter=self.advisor(), run_fn=self.runner(source_changed=True))
        self.assertEqual(receipt["status"], "apply_blocked")
        self.assertTrue(receipt["verified"])
        self.assertFalse(receipt["applied"])
        self.assertEqual((self.repo / "code.py").read_text(), "user concurrent change\n")

    def test_missing_worker_usage_preserves_patch_without_applying(self):
        receipt = self.turn(adapter=self.advisor(), run_fn=self.runner(usage_complete=False))
        self.assertEqual(receipt["status"], "usage_unknown")
        self.assertTrue(receipt["verified"])
        self.assertFalse(receipt["applied"])
        self.assertIsNone(receipt["totals"]["tokens"])

    def test_interrupted_apply_does_not_claim_source_was_unchanged(self):
        actual_run = subprocess.run

        def interrupt_after_application(argv, *args, **kwargs):
            result = actual_run(argv, *args, **kwargs)
            if "apply" in argv and "--check" not in argv:
                raise KeyboardInterrupt()
            return result

        with patch("codex_harness.controller.subprocess.run", side_effect=interrupt_after_application):
            receipt = self.turn(adapter=self.advisor(), run_fn=self.runner())
        self.assertEqual(receipt["status"], "interrupted")
        self.assertEqual((self.repo / "code.py").read_text(), "value = 2\n")
        self.assertIsNone(receipt["applied"])
        self.assertEqual(receipt["application_status"], "unknown")
        self.assertIn("Inspect git status and diff", receipt["reason"])
        self.assertEqual(json.loads(Path(receipt["receipt_path"]).read_text()), receipt)

    def test_interrupted_preparation_writes_unknown_accounting_receipt(self):
        adapter = self.advisor()
        adapter.advise.side_effect = KeyboardInterrupt()
        receipt = self.turn(adapter=adapter, run_fn=self.runner())
        self.assertEqual(receipt["status"], "interrupted")
        self.assertFalse(receipt["totals"]["usage_complete"])
        self.assertTrue(Path(receipt["receipt_path"]).is_file())

    def test_preparer_modification_is_rejected(self):
        adapter = self.advisor()
        response = adapter.advise.return_value
        def mutate(*args):
            (args[2] / "code.py").write_text("improper modification\n")
            return response
        adapter.advise.side_effect = mutate
        runner = self.runner()
        receipt = self.turn(adapter=adapter, run_fn=runner)
        self.assertEqual(receipt["status"], "integrity_failed")
        runner.assert_not_called()
        self.assertEqual((self.repo / "code.py").read_text(), "value = 1\n")

    def test_dry_run_has_no_model_or_filesystem_side_effects(self):
        with patch("codex_harness.controller.CodexAdapter") as adapter, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(handle(self.args("fix value", "--dry-run")), 0)
        self.assertEqual(json.loads(output.getvalue())["mode"], "managed")
        self.assertFalse((self.root / "artifacts").exists())
        adapter.assert_not_called()

    def test_prompt_and_task_are_mutually_exclusive(self):
        with self.assertRaisesRegex(ValueError, "either"):
            prepare(self.args("fix value", "--task", "task.json"))

    def test_repl_requires_terminal_only_when_no_task_or_prompt(self):
        with patch("codex_harness.controller.sys.stdin.isatty", return_value=False):
            with self.assertRaisesRegex(ValueError, "requires a terminal"):
                handle(self.args())
        self.assertFalse((self.root / "artifacts").exists())


if __name__ == "__main__":
    unittest.main()
