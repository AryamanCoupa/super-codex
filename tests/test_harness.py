import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from codex_harness.cli import main, pack_path
from codex_harness.codex import CodexAdapter, command, estimate_cost, parse_events, mcp_override
from codex_harness.config import ASSETS, load_policy, load_task, read, toml_value
from codex_harness.demo import CASES, create
from codex_harness.process import execute
from codex_harness.report import summarize, wilson
from codex_harness.runner import git, protected_changes, run


class ScriptedAdapter:
    def __init__(self, actions, usage=True, completed=True):
        self.actions = iter(actions)
        self.models = []
        self.usage = usage
        self.completed = completed
        self.prompts = []

    def run(self, policy, model, workspace, prompt, mcp, timeout, log):
        self.models.append(model)
        self.prompts.append(prompt)
        next(self.actions)(workspace)
        return {"returncode": 0, "reason": None, "completed": self.completed,
                "usage": {"input_tokens": 100, "cached_input_tokens": 10, "output_tokens": 20} if self.usage else None,
                "cost_usd": 0.01 if self.usage else None, "message": "handoff", "events": [], "seconds": 0}


class AdvisorAdapter(ScriptedAdapter):
    def __init__(self, actions, replies):
        super().__init__(actions)
        self.replies = iter(replies)
        self.roles = []

    def advise(self, policy, model, workspace, prompt, timeout, log, role):
        self.roles.append((role, model))
        return {"returncode": 0, "reason": None, "completed": True,
                "usage": {"input_tokens": 100, "cached_input_tokens": 0, "output_tokens": 20},
                "cost_usd": .02, "message": next(self.replies), "events": [], "seconds": 0}


def repair(workspace):
    (workspace / "stats.py").write_text(CASES["mean"][1])


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.fixture = create(self.root / "fixture")
        self.repo = self.fixture / "repo"
        self.task = load_task(self.fixture / "mean.json")
        self.policy = load_policy(overrides={"codex_command": [sys.executable, str(ASSETS / "fake_codex.py")],
                                             "model": "cheap", "escalation_model": "strong",
                                             "cheap_attempts": 1, "max_attempts": 3})

    def tearDown(self):
        self.temp.cleanup()

    def run_task(self, adapter=None, **kwargs):
        return run(self.repo, self.task, self.policy, self.root / "runs", adapter=adapter, **kwargs)

    def test_empty_unittest_collection_blocks_before_model_execution(self):
        self.task["checks"] = [["{python}", "-m", "unittest", "discover", "-s", "tests", "-p", "missing_*.py"]]
        self.task["baseline_must_fail"] = False
        adapter = ScriptedAdapter([])
        result = self.run_task(adapter)
        self.assertEqual(result["status"], "baseline_error")
        self.assertEqual(result["baseline"][0]["reason"], "no_tests")
        self.assertEqual(adapter.models, [])

    def test_interrupted_worker_and_planner_preserve_unknown_spend(self):
        class InterruptedAdapter:
            def run(self, *args):
                raise KeyboardInterrupt()

            def advise(self, *args):
                raise KeyboardInterrupt()

        for planner in (None, "strong"):
            with self.subTest(planner=planner):
                self.policy["planner_model"] = planner
                result = self.run_task(InterruptedAdapter())
                self.assertEqual(result["status"], "interrupted")
                self.assertFalse(result["usage_complete"] or result["cost_complete"])
                self.assertIsNone(result["tokens"])
                self.assertIsNone(result["cost_usd"])
                saved = json.loads((Path(result["artifact_directory"]) / "result.json").read_text())
                self.assertFalse(saved["usage_complete"])

    def test_real_subprocess_demo_repairs_and_preserves_source(self):
        before = git(self.repo, "rev-parse", "HEAD")
        result = self.run_task(CodexAdapter())
        self.assertEqual(result["status"], "passed")
        self.assertEqual(len(result["attempts"]), 2)
        self.assertFalse(result["attempts"][0]["passed"])
        self.assertEqual(result["tokens"], 260)
        self.assertIsNone(result["cost_usd"])
        self.assertTrue((Path(result["artifact_directory"]) / "accepted.patch").exists())
        self.assertEqual(git(self.repo, "status", "--porcelain"), b"")
        self.assertEqual(before, git(self.repo, "rev-parse", "HEAD"))

    def test_escalation_after_failed_verification(self):
        adapter = ScriptedAdapter([lambda w: None, repair])
        result = self.run_task(adapter)
        self.assertEqual(adapter.models, ["cheap", "strong"])
        self.assertEqual(result["status"], "passed")

    def test_stall_allows_planned_strong_escalation(self):
        self.policy["cheap_attempts"] = 2
        adapter = ScriptedAdapter([lambda w: None, lambda w: None, repair])
        result = self.run_task(adapter)
        self.assertEqual(adapter.models, ["cheap", "cheap", "strong"])
        self.assertEqual(result["status"], "passed")

    def test_planner_handoff_and_total_accounting(self):
        self.policy["planner_model"] = "planner"
        adapter = AdvisorAdapter([repair], ["Inspect stats.mean; handle empty input."])
        result = self.run_task(adapter)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["tokens"], 240)
        self.assertAlmostEqual(result["cost_usd"], .03)
        self.assertIn("handle empty input", adapter.prompts[0])
        self.assertEqual(adapter.roles, [("plan", "planner")])

    def test_review_failure_triggers_repair(self):
        self.policy["reviewer_model"] = "reviewer"
        adapter = AdvisorAdapter([repair, repair], [json.dumps({"verdict": "fail", "findings": ["Inspect negative values."]}),
                                                   json.dumps({"verdict": "pass", "findings": []})])
        result = self.run_task(adapter)
        self.assertEqual(result["status"], "passed")
        self.assertFalse(result["attempts"][0]["passed"])
        self.assertTrue(result["attempts"][0]["tests_passed"])
        self.assertEqual(result["tokens"], 480)
        self.assertIn("negative values", adapter.prompts[1])

    def test_invalid_review_fails_closed(self):
        self.policy["reviewer_model"] = "reviewer"
        adapter = AdvisorAdapter([repair], ['{"verdict":"pass","findings":["bug"]}'])
        result = self.run_task(adapter)
        self.assertEqual(result["status"], "review_invalid")
        self.assertFalse((Path(result["artifact_directory"]) / "accepted.patch").exists())

    def test_budget_must_cover_required_review(self):
        self.policy.update({"reviewer_model": "reviewer", "max_tokens": 100})
        result = self.run_task(AdvisorAdapter([repair], []))
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertFalse(result["attempts"][0]["passed"])

    def test_planner_budget_prevents_worker(self):
        self.policy.update({"planner_model": "planner", "max_tokens": 100})
        adapter = AdvisorAdapter([], ["Small plan"])
        result = self.run_task(adapter)
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertEqual(adapter.models, [])

    def test_protected_test_cannot_be_weakened(self):
        def tamper(w):
            repair(w)
            (w / "tests/test_mean.py").write_text("# no tests\n")
        result = self.run_task(ScriptedAdapter([tamper]))
        self.assertEqual(result["status"], "integrity_failed")

    def test_deleted_protected_file_rejected(self):
        result = self.run_task(ScriptedAdapter([lambda w: (w / "tests/test_mean.py").unlink()]))
        self.assertEqual(result["status"], "integrity_failed")

    def test_new_file_is_in_patch_and_verifier(self):
        def action(w):
            repair(w)
            (w / "new_module.py").write_text("VALUE = 1\n")
        result = self.run_task(ScriptedAdapter([action]))
        self.assertEqual(result["status"], "passed")
        patch = (Path(result["artifact_directory"]) / "accepted.patch").read_text()
        self.assertIn("new_module.py", patch)

    def test_agent_commit_is_still_compared_to_original_base(self):
        def commit(w):
            repair(w)
            git(w, "add", "-A")
            git(w, "-c", "user.name=test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false", "commit", "-qm", "agent commit")
        result = self.run_task(ScriptedAdapter([commit]))
        self.assertEqual(result["status"], "passed")
        self.assertIn("stats.py", result["attempts"][0]["changed_files"])

    def test_symlink_candidate_rejected(self):
        result = self.run_task(ScriptedAdapter([lambda w: (w / "escape").symlink_to("/tmp")]))
        self.assertEqual(result["status"], "integrity_failed")

    def test_missing_usage_stops_retries(self):
        result = self.run_task(ScriptedAdapter([lambda w: None], usage=False))
        self.assertEqual(result["status"], "usage_unknown")
        self.assertIsNone(result["cost_usd"])
        self.assertIsNone(result["tokens"])

    def test_agent_error_is_not_repaired_with_bigger_model(self):
        result = self.run_task(ScriptedAdapter([lambda w: None], completed=False))
        self.assertEqual(result["status"], "agent_error")
        self.assertEqual(len(result["attempts"]), 1)

    def test_token_budget_prevents_next_attempt(self):
        self.policy["max_tokens"] = 100
        result = self.run_task(ScriptedAdapter([lambda w: None]))
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertEqual(len(result["attempts"]), 1)

    def test_cost_budget_prevents_next_attempt(self):
        self.policy["max_cost_usd"] = .005
        result = self.run_task(ScriptedAdapter([lambda w: None]))
        self.assertEqual(result["status"], "budget_exhausted")

    def test_stall_detection(self):
        result = self.run_task(ScriptedAdapter([lambda w: None, lambda w: None]))
        self.assertEqual(result["status"], "stalled")

    def test_baseline_false_positive(self):
        repair(self.repo)
        git(self.repo, "add", ".")
        git(self.repo, "-c", "user.name=test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false", "commit", "-qm", "already fixed")
        result = self.run_task(ScriptedAdapter([]))
        self.assertEqual(result["status"], "invalid_baseline")
        self.assertEqual(result["attempts"], [])

    def test_dirty_source_rejected(self):
        repair(self.repo)
        with self.assertRaisesRegex(ValueError, "dirty"):
            self.run_task()

    def test_setup_error_is_separate(self):
        self.task["setup"] = [[sys.executable, "-c", "raise SystemExit(1)"]]
        result = self.run_task(ScriptedAdapter([]))
        self.assertEqual(result["status"], "setup_failed")

    def test_fork_and_evidence_leave_active_instructions_unchanged(self):
        path = self.root / "custom"
        self.assertEqual(main(["pack", "fork", "backend", str(path)]), 0)
        before = (path / "instructions.md").read_bytes()
        result = self.run_task(ScriptedAdapter([repair]))
        self.assertEqual(main(["pack", "learn", str(path), "--from-result", str(Path(result["artifact_directory"]) / "result.json")]), 0)
        self.assertEqual(before, (path / "instructions.md").read_bytes())
        self.assertTrue((path / "skills/debug-with-evidence/SKILL.md").exists())


class UnitTests(unittest.TestCase):
    def test_usage_and_cached_cost(self):
        usage = {"input_tokens": 100, "cached_input_tokens": 80, "output_tokens": 10}
        out = "warning\n" + json.dumps({"type": "turn.completed", "usage": usage})
        self.assertEqual(parse_events(out)["usage"], usage)
        self.assertAlmostEqual(estimate_cost(usage, {"input": 2, "cached_input": .5, "output": 10}), .00018)

    def test_failed_turn_not_success(self):
        self.assertFalse(parse_events('{"type":"turn.failed"}')["completed"])
        self.assertIsNone(parse_events('{"type":"turn.completed"}')["usage"])

    def test_invalid_usage_not_zero(self):
        event = {"type": "turn.completed", "usage": {"input_tokens": -1, "cached_input_tokens": 0, "output_tokens": 3}}
        self.assertIsNone(parse_events(json.dumps(event))["usage"])

    def test_missing_price_is_unknown(self):
        self.assertIsNone(estimate_cost({"input_tokens": 1}, None))
        with self.assertRaisesRegex(ValueError, "Dollar budgets"):
            load_policy(overrides={"max_cost_usd": 1})

    def test_invalid_limits(self):
        for key, value in [("max_attempts", 0), ("max_tokens", -1), ("attempt_timeout_seconds", float("nan"))]:
            with self.assertRaises(ValueError):
                load_policy(overrides={key: value})

    def test_shell_argv_and_safe_flags(self):
        policy = load_policy()
        argv = command(policy, "model", Path("/tmp/has spaces"), {"docs": {"url": "https://example.invalid/mcp"}})
        self.assertIn("--ignore-user-config", argv)
        self.assertIn("workspace-write", argv)
        self.assertIn("/tmp/has spaces", argv)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", argv)
        self.assertEqual(argv[-1], "-")

    def test_advisor_uses_read_only_sandbox_and_review_schema(self):
        argv = command(load_policy(), "strong", Path("/tmp"), {}, role="review")
        self.assertEqual(argv[argv.index("--sandbox") + 1], "read-only")
        self.assertIn("--output-schema", argv)

    def test_mcp_cli_key_preserves_server_name_without_literal_quotes(self):
        value = mcp_override("repo-search", {"url": "https://example.invalid/mcp"})
        self.assertEqual(value.split("=", 1)[0].split("."), ["mcp_servers", "repo-search"])
        for invalid in ('"repo-search"', 'repo.search', 'server name'):
            with self.subTest(name=invalid), self.assertRaisesRegex(ValueError, "MCP server names"):
                mcp_override(invalid, {})

    def test_progress_commentary_does_not_corrupt_structured_final_response(self):
        payload = '{"kind":"answer","answer":"Done","task":null,"apply_patch":false}'
        events = [{"type": "item.completed", "item": {"type": "agent_message", "text": text}}
                  for text in ("I will inspect the available evidence.", payload)]
        events.append({"type": "turn.completed", "usage": {"input_tokens": 10, "cached_input_tokens": 0, "output_tokens": 5}})
        result = parse_events("\n".join(json.dumps(event) for event in events))
        self.assertEqual(result["message"], payload)
        self.assertEqual(result["events"], events)
        self.assertTrue(result["completed"])

    def test_preparation_uses_readonly_sandbox_and_packaged_contract_schema(self):
        argv = command(load_policy(), "small", Path("/tmp"), {}, role="prepare")
        self.assertEqual(argv[argv.index("--sandbox") + 1], "read-only")
        self.assertIn("--ignore-user-config", argv)
        schema = json.loads(Path(argv[argv.index("--output-schema") + 1]).read_text())
        self.assertEqual(set(schema["required"]), {"kind", "answer", "apply_patch", "task"})
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["kind"]["enum"], ["task", "answer", "blocked"])

    def test_toml_serialization(self):
        import tomllib
        value = {"args": ["a b", 'quote"'], "enabled": True}
        self.assertEqual(tomllib.loads("a=" + toml_value(value))["a"], value)

    def test_timeout_and_output_limits(self):
        result = execute([sys.executable, "-c", "import time; time.sleep(10)"], Path.cwd(), .1)
        self.assertEqual(result["reason"], "timeout")
        result = execute([sys.executable, "-c", "print('x'*10000)"], Path.cwd(), 3, max_bytes=100)
        self.assertEqual(result["reason"], "output_limit")
        self.assertLessEqual(len(result["output"]), 100)

    def test_timeout_covers_stdin_backpressure(self):
        result = execute([sys.executable, "-c", "import time; time.sleep(10)"], Path.cwd(), .1, stdin="a" * 1_000_000)
        self.assertEqual(result["reason"], "timeout")

    def test_protected_globs_and_nested_instructions(self):
        self.assertEqual(protected_changes(["tests/a.py", "src/AGENTS.md", "foo.py"], ["tests"]), ["tests/a.py", "src/AGENTS.md"])

    def test_reports_include_failure_spend(self):
        rows = [{"label": "a", "status": state, "attempts": [], "seconds": 2, "tokens": 10,
                 "cost_usd": 1, "base_commit": "abc"} for state in ["passed", "failed"]]
        stats = summarize(rows)["a"]
        self.assertEqual(stats["cost_per_success_usd"], 2)
        rows[1]["cost_usd"] = None
        self.assertIsNone(summarize(rows)["a"]["cost_per_success_usd"])
        self.assertLess(wilson(1, 2)[0], .5)
        self.assertGreater(wilson(1, 2)[1], .5)

    def test_all_pack_and_mcp_toml_parse(self):
        for path in ASSETS.rglob("*.toml"):
            self.assertIsInstance(read(path), dict)
        self.assertTrue(pack_path("frontend"))
        self.assertEqual(load_policy("architect")["planner_model"], "gpt-6.1-sol")


if __name__ == "__main__":
    unittest.main()
