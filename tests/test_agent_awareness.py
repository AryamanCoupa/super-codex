import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from codex_harness.agent_tools import bundled_skills, invocation, worker_context
from codex_harness.codex import CodexAdapter
from codex_harness.config import load_policy


class AgentAwarenessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="supercodex agent test ")
        self.root = Path(self.temp.name)
        self.workspace = self.root / "foreign working directory"
        self.workspace.mkdir()
        self.child = self.root / "fake child.py"
        self.policy = load_policy(overrides={"codex_command": [sys.executable, str(self.child)],
                                             "model": "offline"})

    def tearDown(self):
        self.temp.cleanup()

    def script(self, body):
        self.child.write_text("import json, os, subprocess, sys\nfrom pathlib import Path\n"
                              + "prompt = sys.stdin.read()\n" + body + "\n"
                              + "print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':json.dumps(info)}}))\n"
                              + "print(json.dumps({'type':'turn.completed','usage':{'input_tokens':20,'cached_input_tokens':0,'output_tokens':10}}))\n")

    def test_every_model_role_receives_discovery_and_exact_saved_prompt(self):
        self.script("info = {'prompt': prompt, 'worker': os.environ.get('SUPERCODEX_WORKER'), "
                    "'sandbox': sys.argv[sys.argv.index('--sandbox') + 1]}")
        adapter = CodexAdapter()
        original_environment = os.environ.get("SUPERCODEX_WORKER")
        for role in ("implement", "plan", "review", "prepare"):
            with self.subTest(role=role):
                log = self.root / f"{role}.log"
                task_prompt = f"Perform {role} on the scoped task."
                if role == "implement":
                    result = adapter.run(self.policy, "offline", self.workspace, task_prompt, {}, 15, log)
                else:
                    result = adapter.advise(self.policy, "offline", self.workspace, task_prompt, 15, log, role)
                self.assertTrue(result["completed"], result)
                received = json.loads(result["message"])
                expected = worker_context() + "\n\n" + task_prompt
                self.assertEqual(received["prompt"], expected)
                self.assertEqual(received["worker"], "1")
                self.assertEqual(received["sandbox"], "workspace-write" if role == "implement" else "read-only")
                self.assertEqual(log.with_name(f"{role}.effective-prompt.txt").read_text(), expected)
                self.assertEqual(result["effective_prompt_sha256"], hashlib.sha256(expected.encode()).hexdigest())
                self.assertEqual(result["cli_context_sha256"], hashlib.sha256(worker_context().encode()).hexdigest())
                self.assertIn("skill-discovery", received["prompt"])
                self.assertIn("output JSON schema", received["prompt"])
                for row in bundled_skills():
                    self.assertIn(row["name"], received["prompt"])
                    self.assertIn(row["description"], received["prompt"])
                    self.assertIn(row["path"], received["prompt"])
                    body = Path(row["path"]).read_text().split("---", 2)[2].strip()
                    self.assertNotIn(body, received["prompt"])
        self.assertEqual(os.environ.get("SUPERCODEX_WORKER"), original_environment)
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_child_can_discover_cli_from_foreign_cwd_but_cannot_nest_work(self):
        launch = repr(invocation())
        # A missing task deliberately prevents model execution even if the guard regresses.
        # The expected worker-specific error proves the guard acts before task loading.
        self.script(
            f"launch = {launch}\n"
            "def call(args):\n"
            "    p = subprocess.run(launch + args, capture_output=True, text=True, timeout=10)\n"
            "    return {'code': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}\n"
            "catalog = call(['commands', '--json'])\n"
            "skills = call(['skills', '--search', 'github repositories', '--json'])\n"
            "skill = call(['skills', 'skill-discovery'])\n"
            "nested = call(['run', 'missing-task.json', '--repo', '.', '--output', 'nested-runs'])\n"
            "answer = call(['answer', 'nested request', '--repo', '.'])\n"
            "mutation = call(['fixtures', 'nested-fixtures'])\n"
            "info = {'catalog': catalog, 'skills': skills, 'skill': skill, 'nested': nested, 'answer': answer, 'mutation': mutation, "
            "'created': Path('nested-runs').exists() or Path('nested-fixtures').exists()}"
        )
        result = CodexAdapter().run(self.policy, "offline", self.workspace, "Inspect available commands.",
                                   {}, 30, self.root / "discovery.log")
        self.assertTrue(result["completed"], result)
        report = json.loads(result["message"])
        self.assertEqual(report["catalog"]["code"], 0, report["catalog"])
        catalog = json.loads(report["catalog"]["stdout"])
        self.assertIn("experimental", json.dumps(catalog))
        self.assertEqual(report["skills"]["code"], 0, report["skills"])
        self.assertEqual(json.loads(report["skills"]["stdout"])["skills"][0]["name"], "github-context")
        self.assertEqual(report["skill"]["code"], 0, report["skill"])
        self.assertIn("name: skill-discovery", report["skill"]["stdout"])
        for key in ("nested", "answer", "mutation"):
            self.assertEqual(report[key]["code"], 2, report[key])
            self.assertIn("worker", report[key]["stderr"].casefold())
        self.assertFalse(report["created"])


if __name__ == "__main__":
    unittest.main()
