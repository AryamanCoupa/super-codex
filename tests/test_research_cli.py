"""Offline real-process research tests; the stand-in never contacts an MCP server."""

import json
import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

from codex_harness.runner import git


class ResearchCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="supercodex research cli ")
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "research directory"
        self.source.mkdir()
        self.original = "Unrelated local notes must stay outside research workspaces.\n"
        (self.source / "notes.txt").write_text(self.original)
        self.artifacts = self.root / "artifacts"
        self.capture = self.root / "invocations.jsonl"
        self.config_home = self.root / "private config"
        (self.config_home / "super-codex").mkdir(parents=True)
        (self.config_home / "super-codex/research.toml").write_text(
            '[mcp_servers.repository-search]\n'
            'url = "https://example.invalid/mcp"\n'
            'enabled_tools = ["search_repositories"]\n'
        )
        self.fake = self.root / "fake research codex.py"
        self.fake.write_text(
            "import json, os, subprocess, sys\nfrom pathlib import Path\n"
            f"capture = Path({str(self.capture)!r})\n"
            "argv = sys.argv[1:]\n"
            "if '--version' in argv:\n"
            "    print('offline-research-fixture 1')\n    raise SystemExit(0)\n"
            "workspace = Path(argv[argv.index('-C') + 1])\n"
            "prompt = sys.stdin.read()\n"
            "base = subprocess.check_output(['git', '-C', str(workspace), 'rev-parse', '--verify', 'HEAD^{commit}']).decode().strip()\n"
            "tracked = subprocess.check_output(['git', '-C', str(workspace), 'ls-files']).decode()\n"
            "with capture.open('a') as stream:\n"
            "    stream.write(json.dumps({'argv': argv, 'cwd': str(Path.cwd()), 'workspace': str(workspace),\n"
            "        'base': base, 'tracked': tracked, 'prompt': prompt,\n"
            "        'source_notes_copied': (workspace / 'notes.txt').exists(),\n"
            "        'worker_marker': os.environ.get('SUPERCODEX_WORKER')}) + '\\n')\n"
            "message = json.dumps({'kind': 'answer', 'answer': 'Fixture search found example/demo.',\n"
            "                      'apply_patch': False, 'task': None})\n"
            "print(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'I will search the selected connection.'}}))\n"
            "print(json.dumps({'type': 'item.completed', 'item': {'type': 'mcp_tool_call',\n"
            "    'server': 'repository-search', 'tool': 'search_repositories', 'status': 'completed',\n"
            "    'arguments': {'query': 'demo'}, 'result': {'names': ['example/demo']}}}))\n"
            "print(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': message}}))\n"
            "print(json.dumps({'type': 'turn.completed', 'usage':\n"
            "    {'input_tokens': 100, 'cached_input_tokens': 20, 'output_tokens': 30}}))\n"
        )
        self.policy = self.root / "policy.json"
        self.policy.write_text(json.dumps({
            "model": "research-fixture", "escalation_model": None,
            "codex_command": [sys.executable, str(self.fake)],
            "max_attempts": 1, "max_tokens": 1000, "run_timeout_seconds": 30,
            "attempt_timeout_seconds": 15,
            "prices": {"research-fixture": {"input": 1, "cached_input": .5, "output": 2}},
        }))

    def tearDown(self):
        self.temp.cleanup()

    def invoke_research(self):
        launcher = Path(__file__).resolve().parents[1] / "codex_harness/launch.py"
        env = {**os.environ, "XDG_CONFIG_HOME": str(self.config_home)}
        env.pop("SUPERCODEX_WORKER", None)
        result = subprocess.run(
            [sys.executable, str(launcher), "Find the repositories named demo in the example organization.",
             "--no-stream", "--config", str(self.policy), "--output-root", str(self.artifacts)],
            cwd=self.source, env=env, text=True, capture_output=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        receipts = list(self.artifacts.glob("sessions/*/turns/0001/receipt.json"))
        self.assertEqual(len(receipts), 1, result.stdout + result.stderr)
        receipt = json.loads(receipts[0].read_text())
        calls = [json.loads(line) for line in self.capture.read_text().splitlines()]
        self.assertEqual(len(calls), 1, "Research must not start a coding worker or native fallback")
        call = calls[0]
        self.assertEqual(call["argv"][0], "exec")
        self.assertEqual(call["argv"][call["argv"].index("--sandbox") + 1], "read-only")
        self.assertIn("--ignore-user-config", call["argv"])
        self.assertEqual(Path(call["argv"][call["argv"].index("--output-schema") + 1]).name, "prepare.schema.json")
        self.assertEqual(call["worker_marker"], "1")
        self.assertEqual(call["cwd"], call["workspace"])
        self.assertNotEqual(Path(call["workspace"]), self.source)
        self.assertEqual(call["tracked"], "")
        self.assertFalse(call["source_notes_copied"])
        self.assertEqual(call["base"], receipt["preparation_base_commit"])
        self.assertIn("no files from the selected directory were copied", call["prompt"])
        overrides = [call["argv"][index + 1] for index, value in enumerate(call["argv"][:-1]) if value == "-c"]
        mcp_options = [tomllib.loads(value)["mcp_servers"] for value in overrides if value.startswith("mcp_servers.")]
        self.assertEqual(mcp_options, [{"repository-search": {
            "url": "https://example.invalid/mcp", "enabled_tools": ["search_repositories"], "required": True}}])
        self.assertEqual(receipt["status"], "advisory")
        self.assertEqual(receipt["research_mcp_names"], ["repository-search"])
        self.assertEqual(receipt["mcp_names"], [])
        self.assertEqual(receipt["preparation"]["tool_calls"], [{
            "server": "repository-search", "tool": "search_repositories", "status": "completed"}])
        self.assertFalse(receipt["harness_run"] or receipt["verified"] or receipt["applied"])
        self.assertIsNone(receipt["base_commit"])
        self.assertEqual(receipt["totals"]["tokens"], 130)
        self.assertAlmostEqual(receipt["totals"]["cost_usd"], .00015)
        self.assertEqual((self.source / "notes.txt").read_text(), self.original)
        self.assertIn("not a verified coding run", result.stdout)
        self.assertNotIn("opening Codex", result.stderr)
        return receipt

    def test_plain_research_from_ordinary_directory_uses_private_default_mcp(self):
        receipt = self.invoke_research()
        self.assertEqual(receipt["source_context"]["kind"], "not_git")
        self.assertEqual(sorted(path.name for path in self.source.iterdir()), ["notes.txt"])
        self.assertFalse((self.source / ".git").exists())

    def test_plain_research_from_unborn_git_preserves_source_without_commit(self):
        git(self.source, "init", "-q")
        before_head = (self.source / ".git/HEAD").read_bytes()
        receipt = self.invoke_research()
        self.assertEqual(receipt["source_context"]["kind"], "unborn")
        self.assertEqual((self.source / ".git/HEAD").read_bytes(), before_head)
        self.assertFalse((self.source / ".git/index").exists())
        self.assertEqual(sorted(path.name for path in self.source.iterdir()), [".git", "notes.txt"])
        with self.assertRaises(RuntimeError):
            git(self.source, "rev-parse", "--verify", "HEAD^{commit}")


if __name__ == "__main__":
    unittest.main()
