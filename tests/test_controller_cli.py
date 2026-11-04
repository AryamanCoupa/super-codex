"""Exercise the strict entry point with real processes, clones and checks, offline."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from codex_harness.runner import git


class ControllerCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="supercodex controller cli ")
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "target project"
        self.repo.mkdir()
        (self.repo / "value.py").write_text("def answer():\n    return 0\n")
        (self.repo / "tests").mkdir()
        (self.repo / "tests/test_value.py").write_text(
            "import unittest\nfrom value import answer\n"
            "class AnswerTests(unittest.TestCase):\n"
            "    def test_answer(self):\n        self.assertEqual(answer(), 42)\n"
        )
        git(self.repo, "init", "-q")
        git(self.repo, "add", ".")
        git(self.repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "-c", "commit.gpgsign=false", "commit", "-qm", "Fixture")
        self.base = git(self.repo, "rev-parse", "HEAD")
        self.original = (self.repo / "value.py").read_text()
        self.capture = self.root / "calls.jsonl"
        self.artifacts = self.root / "artifacts"
        self.fake = self.root / "fake codex.py"
        self.task = {
            "id": "answer-fix", "prompt": "Make answer() return 42.",
            "checks": [["{python}", "-m", "unittest", "discover", "-s", "tests"]],
            "setup": [], "protected_paths": ["tests"], "baseline_must_fail": True,
        }
        self.task_file = self.root / "task.json"
        self.task_file.write_text(json.dumps(self.task))
        self.policy = self.root / "policy.json"
        self.policy.write_text(json.dumps({
            "model": "fixture-model", "escalation_model": None,
            "codex_command": [sys.executable, str(self.fake)],
            "max_attempts": 1, "cheap_attempts": 1, "max_tokens": 1000,
            "max_cost_usd": 1, "run_timeout_seconds": 60,
            "attempt_timeout_seconds": 15, "check_timeout_seconds": 15,
            "prices": {"fixture-model": {"input": 1, "cached_input": .5, "output": 2}},
        }))
        self.write_fake(42)

    def tearDown(self):
        self.temp.cleanup()

    def write_fake(self, candidate_value):
        self.fake.write_text(
            "import json, os, sys\nfrom pathlib import Path\n"
            f"source = Path({str(self.repo)!r})\n"
            f"capture = Path({str(self.capture)!r})\n"
            f"task = {self.task!r}\n"
            "if '--version' in sys.argv:\n"
            "    print('offline-controller-fixture 1')\n    raise SystemExit(0)\n"
            "workspace = Path(sys.argv[sys.argv.index('-C') + 1])\n"
            "prompt = sys.stdin.read()\n"
            "preparing = ('--output-schema' in sys.argv and "
            "Path(sys.argv[sys.argv.index('--output-schema') + 1]).name == 'prepare.schema.json')\n"
            "with capture.open('a') as stream:\n"
            "    stream.write(json.dumps({'role': 'prepare' if preparing else 'worker',\n"
            "        'argv': sys.argv[1:], 'workspace': str(workspace), 'prompt': prompt,\n"
            "        'source_before': (source / 'value.py').read_text(),\n"
            "        'worker_marker': os.environ.get('SUPERCODEX_WORKER')}) + '\\n')\n"
            "if preparing:\n"
            "    message = json.dumps({'kind': 'task', 'answer': '', 'apply_patch': True, 'task': task})\n"
            "    usage = {'input_tokens': 100, 'cached_input_tokens': 20, 'output_tokens': 20}\n"
            "else:\n"
            f"    (workspace / 'value.py').write_text('def answer():\\n    return {candidate_value}\\n')\n"
            "    message = 'Candidate ready for independent verification.'\n"
            "    usage = {'input_tokens': 200, 'cached_input_tokens': 40, 'output_tokens': 30}\n"
            "print(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': message}}))\n"
            "print(json.dumps({'type': 'turn.completed', 'usage': usage}))\n"
        )

    def invoke(self, *args):
        launcher = Path(__file__).resolve().parents[1] / "codex_harness/launch.py"
        env = dict(os.environ)
        env.pop("SUPERCODEX_WORKER", None)
        result = subprocess.run(
            [sys.executable, str(launcher), *args, "--repo", str(self.repo),
             "--config", str(self.policy), "--output-root", str(self.artifacts)],
            cwd=self.root, env=env, text=True, capture_output=True, timeout=45,
        )
        receipts = list(self.artifacts.glob("sessions/*/turns/0001/receipt.json"))
        self.assertEqual(len(receipts), 1, result.stdout + result.stderr)
        receipt = json.loads(receipts[0].read_text())
        calls = [json.loads(line) for line in self.capture.read_text().splitlines()]
        return result, receipt, calls

    def test_default_prompt_runs_preparation_verifier_and_only_then_applies(self):
        result, receipt, calls = self.invoke("Make answer() return 42.")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([call["role"] for call in calls], ["prepare", "worker"])
        self.assertTrue(all(call["source_before"] == self.original for call in calls))
        self.assertTrue(all(call["worker_marker"] == "1" for call in calls))
        prepare_argv = calls[0]["argv"]
        self.assertEqual(prepare_argv[prepare_argv.index("--sandbox") + 1], "read-only")
        self.assertIn("--ignore-user-config", prepare_argv)
        self.assertNotEqual(calls[0]["workspace"], str(self.repo))
        self.assertNotEqual(calls[1]["workspace"], str(self.repo))
        self.assertEqual(receipt["status"], "applied")
        self.assertTrue(receipt["harness_run"] and receipt["verified"] and receipt["applied"])
        self.assertEqual(receipt["totals"]["tokens"], 350)
        self.assertAlmostEqual(receipt["totals"]["cost_usd"], .00037)
        run = json.loads(Path(receipt["run"]["result_path"]).read_text())
        self.assertEqual(run["policy"]["max_tokens"], 880)
        self.assertLess(run["policy"]["run_timeout_seconds"], 60)
        self.assertEqual(run["baseline"][0]["returncode"], 1)
        self.assertEqual(run["attempts"][0]["checks"][0]["returncode"], 0)
        self.assertEqual((self.repo / "value.py").read_text(), "def answer():\n    return 42\n")
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), self.base)
        self.assertIn(b"value.py", git(self.repo, "status", "--porcelain"))

    def test_failed_verification_keeps_source_unchanged(self):
        self.write_fake(41)
        result, receipt, calls = self.invoke("Make answer() return 42.")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([call["role"] for call in calls], ["prepare", "worker"])
        self.assertTrue(receipt["harness_run"])
        self.assertFalse(receipt["verified"] or receipt["applied"])
        self.assertEqual(receipt["totals"]["tokens"], 350)
        self.assertEqual((self.repo / "value.py").read_text(), self.original)
        self.assertEqual(git(self.repo, "status", "--porcelain"), b"")
        run = json.loads(Path(receipt["run"]["result_path"]).read_text())
        self.assertEqual(run["attempts"][0]["checks"][0]["returncode"], 1)
        self.assertFalse((Path(run["artifact_directory"]) / "accepted.patch").exists())

    def test_explicit_task_skips_preparation_and_patch_only_preserves_source(self):
        result, receipt, calls = self.invoke("--task", str(self.task_file), "--patch-only")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([call["role"] for call in calls], ["worker"])
        self.assertTrue(receipt["harness_run"] and receipt["verified"])
        self.assertFalse(receipt["applied"])
        self.assertEqual(receipt["totals"]["tokens"], 230)
        self.assertAlmostEqual(receipt["totals"]["cost_usd"], .00024)
        self.assertEqual((self.repo / "value.py").read_text(), self.original)
        self.assertEqual(git(self.repo, "status", "--porcelain"), b"")
        patch = Path(receipt["run"]["artifact_directory"]) / "accepted.patch"
        self.assertIn("return 42", patch.read_text())


if __name__ == "__main__":
    unittest.main()
