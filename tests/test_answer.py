"""Exact-message routing and offline process coverage for the answer command."""

import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from codex_harness.answer import handle, register_parser
from codex_harness.runner import git


class AnswerInputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="supercodex answer ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.parser = argparse.ArgumentParser()
        register_parser(self.parser.add_subparsers(dest="action", required=True))

    def args(self, *values):
        return self.parser.parse_args(["answer", *values])

    def test_exact_quoted_message_uses_managed_exec_and_preserves_configuration(self):
        message = '  ai news about "small models"\nDo not execute $(touch unwanted) or `commands`.  '
        args = self.args(message, "--repo", str(self.root), "--pack", "backend",
                         "--config", "economy", "--mcp", "github", "--research-mcp", "playwright",
                         "--output-root", str(self.root / "outputs"))
        with patch("codex_harness.controller.handle", return_value=7) as controller:
            self.assertEqual(handle(args), 7)
        received = controller.call_args.args[0]
        self.assertIs(received, args)
        self.assertEqual(received.prompt, message)
        self.assertTrue(received.answer_mode and received.managed and received.no_stream)
        self.assertFalse(received.native or received.no_alt_screen)
        self.assertIsNone(received.task)
        self.assertIsNone(received.answer_context)
        self.assertEqual(received.config, "economy")
        self.assertEqual(received.pack, "backend")
        self.assertEqual(received.mcp, ["github"])
        self.assertEqual(received.research_mcp, ["playwright"])
        self.assertFalse((self.root / "outputs").exists())

    def test_files_preserve_unicode_newlines_and_separate_context(self):
        prompt = 'What about "café"?\r\nKeep the quoted text: """hello"""\n'
        context = 'Previous question: AI models\nPrevious answer: reviewed examples.\n'
        prompt_file, context_file = self.root / "prompt.txt", self.root / "context.txt"
        prompt_file.write_bytes(prompt.encode("utf-8"))
        context_file.write_bytes(context.encode("utf-8"))
        args = self.args("--prompt-file", str(prompt_file), "--context-file", str(context_file), "--dry-run")
        with patch("codex_harness.controller.handle", return_value=0) as controller:
            self.assertEqual(handle(args), 0)
        received = controller.call_args.args[0]
        self.assertEqual(received.prompt, prompt)
        self.assertEqual(received.answer_context, context)
        self.assertTrue(received.dry_run)

    def test_missing_or_conflicting_message_sources_are_rejected_by_parser(self):
        for values in ((), ("hello", "--prompt-file", "message.txt")):
            with self.subTest(values=values), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.args(*values)

    def test_invalid_prompt_inputs_do_not_reach_controller(self):
        path = self.root / "invalid.txt"
        cases = ((b" \n", "empty"), (b"null\x00byte", "NUL"), (b"\xff", "UTF-8"),
                 (b"x" * 1_000_001, "limit"))
        for content, expected in cases:
            path.write_bytes(content)
            with self.subTest(expected=expected), patch("codex_harness.controller.handle") as controller:
                with self.assertRaisesRegex(ValueError, expected):
                    handle(self.args("--prompt-file", str(path)))
                controller.assert_not_called()
        for message, expected in ((" \n", "empty"), ("\0", "NUL"), ("x" * 1_000_001, "limit")):
            with self.subTest(expected=expected), patch("codex_harness.controller.handle") as controller:
                with self.assertRaisesRegex(ValueError, expected):
                    handle(self.args(message))
                controller.assert_not_called()

    def test_invalid_context_and_missing_files_are_rejected_before_execution(self):
        path = self.root / "context.txt"
        for content, expected in ((b"", "empty"), (b"\0", "NUL"), (b"\xff", "UTF-8"),
                                  (b"x" * 64_001, "limit")):
            path.write_bytes(content)
            with self.subTest(expected=expected), patch("codex_harness.controller.handle") as controller:
                with self.assertRaisesRegex(ValueError, expected):
                    handle(self.args("follow up", "--context-file", str(path)))
                controller.assert_not_called()
        for path in (self.root / "absent.txt", self.root):
            with self.subTest(path=path), patch("codex_harness.controller.handle") as controller:
                with self.assertRaisesRegex(ValueError, "regular file"):
                    handle(self.args("--prompt-file", str(path)))
                controller.assert_not_called()


class AnswerCLIProcessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="supercodex answer process ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.repo = self.root / "ordinary directory"
        self.repo.mkdir()
        (self.repo / "notes.txt").write_text("Unrelated user file.\n")
        self.artifacts = self.root / "artifacts"
        self.capture = self.root / "capture.json"
        self.fake = self.root / "fake codex.py"
        self.fake.write_text(
            "import json, os, sys\nfrom pathlib import Path\n"
            "argv = sys.argv[1:]\n"
            "if '--version' in argv:\n    print('offline-answer-fixture 1')\n    raise SystemExit(0)\n"
            "assert argv[0] == 'exec', 'answer must not open another interactive operator'\n"
            "prompt = sys.stdin.read()\n"
            f"Path({str(self.capture)!r}).write_text(json.dumps({{'argv':argv,'prompt':prompt,'worker':os.environ.get('SUPERCODEX_WORKER')}}))\n"
            "answer = json.dumps({'kind':'answer','answer':'Offline news fixture with a source: https://example.invalid/news', 'apply_patch':False,'task':None})\n"
            "print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':answer}}))\n"
            "print(json.dumps({'type':'turn.completed','usage':{'input_tokens':40,'cached_input_tokens':10,'output_tokens':20}}))\n"
        )
        self.policy = self.root / "policy.json"
        self.policy.write_text(json.dumps({
            "model": "answer-fixture", "escalation_model": None,
            "codex_command": [sys.executable, str(self.fake)], "max_attempts": 1,
            "max_tokens": 1000, "attempt_timeout_seconds": 10, "run_timeout_seconds": 20,
            "prices": {"answer-fixture": {"input": 1, "cached_input": .5, "output": 2}},
        }))
        self.launcher = Path(__file__).resolve().parents[1] / "codex_harness/launch.py"
        self.env = {**os.environ, "XDG_CONFIG_HOME": str(self.root / "empty-config")}
        self.env.pop("SUPERCODEX_WORKER", None)

    def invoke(self, *arguments, worker=False):
        environment = dict(self.env)
        if worker:
            environment["SUPERCODEX_WORKER"] = "1"
        return subprocess.run(
            [sys.executable, str(self.launcher), "answer", *arguments,
             "--repo", str(self.repo), "--config", str(self.policy), "--output-root", str(self.artifacts)],
            cwd=self.root, env=environment, text=True, capture_output=True, timeout=25,
        )

    def test_research_message_goes_through_real_managed_process_and_receipt(self):
        request = 'ai news\nInclude "models" and literal $(touch unwanted).'
        prompt_file = self.root / "prompt.txt"
        prompt_file.write_text(request)
        context = self.root / "context.txt"
        context.write_text("Earlier scope: public model releases, not private organization updates.")
        result = self.invoke("--prompt-file", str(prompt_file), "--context-file", str(context))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        capture = json.loads(self.capture.read_text())
        self.assertEqual(capture["argv"][0], "exec")
        self.assertEqual(capture["worker"], "1")
        self.assertIn(request, capture["prompt"])
        self.assertIn(context.read_text(), capture["prompt"])
        self.assertIn('web_search="live"', capture["argv"])
        self.assertEqual(capture["argv"][capture["argv"].index("--sandbox") + 1], "read-only")
        paths = list(self.artifacts.glob("sessions/*/turns/0001/receipt.json"))
        self.assertEqual(len(paths), 1, result.stdout + result.stderr)
        receipt = json.loads(paths[0].read_text())
        self.assertEqual(receipt["request"], request)
        self.assertEqual(receipt["entrypoint"], "answer")
        self.assertEqual(receipt["status"], "advisory")
        self.assertFalse(receipt["harness_run"] or receipt["verified"] or receipt["applied"])
        self.assertEqual(receipt["totals"]["tokens"], 60)
        self.assertIn("Offline news fixture", result.stdout)
        self.assertIn("Receipt:", result.stdout)
        self.assertEqual(sorted(path.name for path in self.repo.iterdir()), ["notes.txt"])
        self.assertFalse((self.root / "unwanted").exists())

    def test_coding_message_still_uses_independent_checks_before_source_application(self):
        original = "def answer():\n    return 0\n"
        (self.repo / "value.py").write_text(original)
        (self.repo / "tests").mkdir()
        (self.repo / "tests/test_value.py").write_text(
            "import unittest\nfrom value import answer\nclass Checks(unittest.TestCase):\n"
            "    def test_answer(self):\n        self.assertEqual(answer(), 42)\n")
        git(self.repo, "init", "-q")
        git(self.repo, "add", ".")
        git(self.repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "-c", "commit.gpgsign=false", "commit", "-qm", "Fixture")
        task = {"id": "answer-fixture", "prompt": "Make answer return 42.",
                "checks": [["{python}", "-m", "unittest", "discover", "-s", "tests"]],
                "setup": [], "protected_paths": ["tests"], "baseline_must_fail": True}
        self.fake.write_text(
            "import json, sys\nfrom pathlib import Path\n"
            "argv = sys.argv[1:]\n"
            "if '--version' in argv:\n    print('offline-answer-fixture 1')\n    raise SystemExit(0)\n"
            "assert argv[0] == 'exec'\n"
            "prompt = sys.stdin.read()\n"
            "workspace = Path(argv[argv.index('-C') + 1])\n"
            f"source = Path({str(self.repo)!r})\n"
            f"assert (source / 'value.py').read_text() == {original!r}\n"
            "assert workspace != source\n"
            "if '--output-schema' in argv:\n"
            f"    message = json.dumps({{'kind':'task','answer':'Run the regression test.','apply_patch':True,'task':{task!r}}})\n"
            "else:\n"
            "    (workspace / 'value.py').write_text('def answer():\\n    return 42\\n')\n"
            "    message = 'Candidate ready for independent verification.'\n"
            "print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':message}}))\n"
            "print(json.dumps({'type':'turn.completed','usage':{'input_tokens':40,'cached_input_tokens':10,'output_tokens':20}}))\n"
        )
        request = "Make answer() return 42 and check it."
        result = self.invoke(request)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        paths = list(self.artifacts.glob("sessions/*/turns/0001/receipt.json"))
        self.assertEqual(len(paths), 1)
        receipt = json.loads(paths[0].read_text())
        self.assertEqual(receipt["request"], request)
        self.assertEqual(receipt["entrypoint"], "answer")
        self.assertEqual(receipt["status"], "applied")
        self.assertTrue(receipt["harness_run"] and receipt["verified"] and receipt["applied"])
        self.assertEqual(receipt["totals"]["tokens"], 120)
        run = json.loads(Path(receipt["run"]["result_path"]).read_text())
        self.assertEqual(run["baseline"][0]["returncode"], 1)
        self.assertEqual(run["attempts"][0]["checks"][0]["returncode"], 0)
        self.assertEqual((self.repo / "value.py").read_text(), "def answer():\n    return 42\n")

    def test_dry_run_and_worker_recursion_guard_make_no_model_call(self):
        result = self.invoke("ai news", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        preview = json.loads(result.stdout)
        self.assertEqual(preview["mode"], "managed")
        self.assertEqual(preview["transport"], "exec")
        self.assertFalse(self.artifacts.exists())
        self.assertFalse(self.capture.exists())
        blocked = self.invoke("ai news", worker=True)
        self.assertEqual(blocked.returncode, 2, blocked.stdout + blocked.stderr)
        self.assertIn("Managed worker cannot launch nested", blocked.stderr)
        self.assertFalse(self.artifacts.exists())
        self.assertFalse(self.capture.exists())


if __name__ == "__main__":
    unittest.main()
