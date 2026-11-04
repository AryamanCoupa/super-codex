import contextlib
import fcntl
import io
import json
import os
import pty
import select
import signal
import stat
import subprocess
import sys
import tempfile
import termios
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_harness.cli import build_parser
from codex_harness.session import handle, prepare


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="supercodex session ")
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "target project"
        self.repo.mkdir()
        (self.repo / "existing.txt").write_text("Keep this checkout unchanged.\n")
        self.output = self.root / "session artifacts"

    def tearDown(self):
        self.temp.cleanup()

    def args(self, *extra):
        return build_parser().parse_args(["start", "--native", "--repo", str(self.repo),
                                         "--output-root", str(self.output), *extra])

    def test_model_policy_selection_and_independent_operator_override(self):
        cases = [
            ((), "gpt-6-luna", "gpt-6-luna"),
            (("--config", "architect"), "gpt-6.1-sol", "gpt-6-luna"),
            (("--config", "architect", "--model", "custom-worker"), "custom-worker", "custom-worker"),
            (("--config", "architect", "--model", "custom-worker", "--operator-model", "custom-operator"),
             "custom-operator", "custom-worker"),
        ]
        for options, operator, worker in cases:
            with self.subTest(options=options):
                plan = prepare(self.args(*options))
                self.assertEqual(plan["preview"]["operator_model"], operator)
                self.assertEqual(plan["policy"]["model"], worker)
                self.assertEqual(plan["argv"][plan["argv"].index("--model") + 1], operator)
        self.assertFalse(self.output.exists())

    def test_pack_skills_policy_and_mcp_reach_operator_and_worker_defaults(self):
        pack = self.root / "dedicated pack"
        pack.mkdir()
        (pack / "pack.toml").write_text('name = "local"\nskills = ["debug-with-evidence"]\n[policy]\nmodel = "pack-worker"\nmax_tokens = 777\n')
        (pack / "instructions.md").write_text("Preserve this project's pagination invariant.")
        (pack / "mcp.toml").write_text('[mcp_servers.shared]\ncommand = "old-server"\n[mcp_servers.pack-only]\ncommand = "pack-server"\n')
        extra = self.root / "private-mcp.json"
        secret = "test-private-mcp-value"
        extra.write_text(json.dumps({"mcp_servers": {"shared": {"url": "https://example.invalid/mcp", "http_headers": {"Authorization": secret}}}}))
        plan = prepare(self.args("--pack", str(pack), "--mcp", "github", "--mcp-config", str(extra)))
        self.assertEqual(plan["policy"]["max_tokens"], 777)
        self.assertEqual(plan["policy"]["model"], "pack-worker")
        self.assertEqual(plan["preview"]["operator_model"], "pack-worker")
        overridden = prepare(self.args("--pack", str(pack), "--config", "balanced"))
        self.assertEqual(overridden["policy"]["model"], "gpt-6-luna")
        self.assertEqual(set(plan["mcp"]), {"shared", "pack-only", "github"})
        self.assertEqual(plan["mcp"]["shared"]["url"], "https://example.invalid/mcp")
        self.assertNotIn("command", plan["mcp"]["shared"])
        self.assertIn("pagination invariant", plan["prompt"])
        self.assertIn('skill name="debug-with-evidence"', plan["prompt"])
        self.assertIn("worker-policy.json", plan["prompt"])
        self.assertIn("worker-mcp.json", plan["prompt"])
        self.assertIn(str(pack), plan["prompt"])
        self.assertTrue(any(secret in value for value in plan["argv"]))
        self.assertNotIn(secret, json.dumps(plan["preview"]))
        self.assertNotIn(secret, plan["prompt"])

    def test_native_user_configuration_and_permission_settings_are_not_replaced(self):
        plan = prepare(self.args("--config", "accuracy", "--no-alt-screen"))
        argv = plan["argv"]
        self.assertNotIn("exec", argv)
        self.assertNotIn("--ignore-user-config", argv)
        self.assertNotIn("--sandbox", argv)
        self.assertNotIn("--ask-for-approval", argv)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", argv)
        self.assertNotIn("--dangerously-bypass-hook-trust", argv)
        overrides = [argv[index + 1] for index, value in enumerate(argv[:-1]) if value == "-c"]
        self.assertFalse(any(value.startswith(("developer_instructions=", "model_instructions_file=", "approval_policy=")) for value in overrides))
        self.assertIn("--no-alt-screen", argv)
        self.assertEqual(argv[argv.index("--add-dir") + 1], str(plan["folder"]))
        self.assertEqual(argv[-2], "--")
        self.assertEqual(argv[-1], plan["initial_prompt"])
        self.assertIn(str(plan["folder"] / "bootstrap.txt"), plan["initial_prompt"])
        self.assertNotEqual(plan["initial_prompt"], plan["prompt"])

    def test_local_provider_flags_and_literal_task_are_preserved(self):
        config = self.root / "local.json"
        config.write_text(json.dumps({"model": "local-model", "local_provider": "ollama"}))
        task = "Fix the literal string $(touch should-not-exist); preserve its quotes: 'x'."
        plan = prepare(self.args(task, "--config", str(config)))
        self.assertIn("--oss", plan["argv"])
        self.assertEqual(plan["argv"][plan["argv"].index("--local-provider") + 1], "ollama")
        self.assertIn(task, plan["prompt"])
        self.assertNotIn(task, plan["argv"][-1])
        self.assertFalse((self.root / "should-not-exist").exists())

    def test_dry_run_does_not_write_or_launch_and_redacts_mcp_values(self):
        config = self.root / "mcp.json"
        secret = "do-not-print-this-test-token"
        config.write_text(json.dumps({"mcp_servers": {"remote": {"url": "https://example.invalid", "bearer_token_env_var": secret}}}))
        with patch("codex_harness.session.subprocess.call") as launch, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(handle(self.args("--dry-run", "--mcp-config", str(config))), 0)
        launch.assert_not_called()
        self.assertFalse(self.output.exists())
        preview = json.loads(out.getvalue())
        self.assertEqual(preview["repo"], str(self.repo))
        self.assertNotIn(secret, out.getvalue())

    def test_nonterminal_and_missing_executable_fail_before_writing(self):
        with patch("codex_harness.session.sys.stdin.isatty", return_value=False):
            with self.assertRaisesRegex(ValueError, "requires a terminal"):
                handle(self.args())
        self.assertFalse(self.output.exists())
        config = self.root / "missing-cli.json"
        config.write_text(json.dumps({"codex_command": [str(self.root / "does-not-exist")]}))
        with patch("codex_harness.session.sys.stdin.isatty", return_value=True), patch("codex_harness.session.sys.stdout.isatty", return_value=True):
            with self.assertRaisesRegex(ValueError, "executable was not found"):
                handle(self.args("--config", str(config)))
        self.assertFalse(self.output.exists())

    def test_real_terminal_child_inherits_handles_environment_and_exit_status(self):
        fake = self.root / "native standin.py"
        fake.write_text('''import json, os, sys
from pathlib import Path
argv = sys.argv[1:]
folder = Path(argv[argv.index("--add-dir") + 1])
policy = json.loads((folder / "worker-policy.json").read_text())
bootstrap = (folder / "bootstrap.txt").read_text()
print("NATIVE_TUI_READY", flush=True)
received = sys.stdin.readline().strip()
capture = {"argv": argv, "cwd": str(Path.cwd()), "stdin_tty": sys.stdin.isatty(),
           "stdout_tty": sys.stdout.isatty(), "inherited": os.environ.get("SUPERCODEX_TEST_NATIVE"),
           "worker_marker": os.environ.get("SUPERCODEX_WORKER"), "worker_model": policy["model"],
           "received": received, "mcp_exists": (folder / "worker-mcp.json").is_file(), "bootstrap": bootstrap}
(folder / "native-capture.json").write_text(json.dumps(capture))
print("NATIVE_TUI_DONE", flush=True)
sys.exit(7)
''')
        config = self.root / "native policy.json"
        config.write_text(json.dumps({"model": "test-worker", "codex_command": [sys.executable, str(fake)]}))
        foreign = self.root / "foreign working directory"
        foreign.mkdir()
        launch = Path(__file__).resolve().parents[1] / "codex_harness/launch.py"
        unwanted = self.root / "shell-expanded"
        task = f'Inspect the literal $(touch "{unwanted}"); do not evaluate it.'
        command = [sys.executable, str(launch), "--native", task, "--repo", str(self.repo), "--config", str(config),
                   "--output-root", str(self.output), "--operator-model", "test-operator"]
        env = {**os.environ, "SUPERCODEX_TEST_NATIVE": "native-config-marker"}
        env.pop("SUPERCODEX_WORKER", None)
        master, slave = pty.openpty()
        process = subprocess.Popen(command, cwd=foreign, env=env, stdin=slave, stdout=slave, stderr=slave,
                                   start_new_session=True, preexec_fn=lambda: fcntl.ioctl(0, termios.TIOCSCTTY, 0))
        os.close(slave)
        output = bytearray()
        sent = False
        deadline = time.monotonic() + 15
        try:
            while time.monotonic() < deadline:
                readable, _, _ = select.select([master], [], [], .1)
                if readable:
                    try:
                        chunk = os.read(master, 65536)
                    except OSError:
                        break
                    if not chunk:
                        break
                    output.extend(chunk)
                    if not sent and b"NATIVE_TUI_READY" in output:
                        os.write(master, b"terminal-input-check\n")
                        sent = True
                if process.poll() is not None and not readable:
                    break
            self.assertEqual(process.wait(timeout=2), 7, output.decode(errors="replace"))
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            os.close(master)
        self.assertTrue(sent)
        self.assertIn(b"NATIVE_TUI_DONE", output)
        sessions = list((self.output / "sessions").iterdir())
        self.assertEqual(len(sessions), 1)
        folder = sessions[0]
        capture = json.loads((folder / "native-capture.json").read_text())
        self.assertEqual(capture["cwd"], str(self.repo))
        self.assertTrue(capture["stdin_tty"] and capture["stdout_tty"])
        self.assertEqual(capture["inherited"], "native-config-marker")
        self.assertIsNone(capture["worker_marker"])
        self.assertEqual(capture["received"], "terminal-input-check")
        self.assertEqual(capture["worker_model"], "test-worker")
        self.assertTrue(capture["mcp_exists"])
        self.assertIn(task, capture["bootstrap"])
        self.assertIn(str(folder / "bootstrap.txt"), capture["argv"][-1])
        self.assertNotIn(task, capture["argv"][-1])
        self.assertEqual(capture["argv"][capture["argv"].index("--model") + 1], "test-operator")
        self.assertFalse(unwanted.exists())
        self.assertEqual(json.loads((folder / "exit.json").read_text())["returncode"], 7)
        self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o700)
        for name in ("worker-policy.json", "worker-mcp.json", "bootstrap.txt", "session.json"):
            self.assertEqual(stat.S_IMODE((folder / name).stat().st_mode), 0o600)
        self.assertEqual([path.name for path in self.repo.iterdir()], ["existing.txt"])
        self.assertEqual((self.repo / "existing.txt").read_text(), "Keep this checkout unchanged.\n")


if __name__ == "__main__":
    unittest.main()
