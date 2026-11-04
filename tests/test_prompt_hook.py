import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from codex_harness.prompt_hook import HOOK_KEY, MAX_CONTEXT_BYTES, hook_overrides, route
import codex_harness.prompt_hook as prompt_hook


class PromptHookTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="sc prompt hook ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.output = self.root / "answers"
        self.routing = self.root / "session-routing.json"
        self.argv = [sys.executable, "/fixture launcher/launch.py", "answer", "--repo", "/fixture project",
                     "--output-root", str(self.output)]
        self.bootstrap = "Initialize this exact fixture bootstrap."
        self.routing.write_text(json.dumps({"answer_argv": self.argv, "output_root": str(self.output),
            "bootstrap_prompt_sha256": hashlib.sha256(self.bootstrap.encode()).hexdigest()}))
        self.environment = patch.dict(os.environ)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        os.environ.pop("SUPERCODEX_WORKER", None)

    def event(self, prompt):
        return {"hook_event_name": "UserPromptSubmit", "prompt": prompt,
                "session_id": "thread-1", "turn_id": "turn-1", "cwd": "/fixture"}

    def test_prompt_is_preserved_exactly_without_interpolating_shell_syntax(self):
        text = 'ai news "quoted"\n$(touch should-not-exist); `echo unwanted`\nUnicode café 🐈'
        with patch("codex_harness.prompt_hook.subprocess.Popen") as launch:
            output = route(self.event(text), self.routing)
        launch.assert_not_called()
        context = output["hookSpecificOutput"]["additionalContext"]
        command = shlex.split(context.splitlines()[1])
        self.assertEqual(command[:len(self.argv)], self.argv)
        self.assertNotIn(text, context)
        prompt = Path(command[command.index("--prompt-file") + 1])
        recent = Path(command[command.index("--context-file") + 1])
        self.assertEqual(prompt.read_text(), text)
        self.assertEqual(json.loads(recent.read_text()), {"recent_turns": []})
        self.assertEqual(stat.S_IMODE(prompt.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(recent.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(prompt.parent.stat().st_mode), 0o700)
        self.assertIn("Before native browsing", context)
        self.assertIn("Do not silently bypass", context)

    def test_bootstrap_and_managed_workers_do_not_route_recursively(self):
        self.assertEqual(route(self.event(self.bootstrap), self.routing), {})
        with patch.dict(os.environ, {"SUPERCODEX_WORKER": "1"}):
            self.assertEqual(route(None, self.root / "missing-config.json"), {})
        self.assertFalse((self.root / "messages").exists())

    def test_each_message_gets_an_independent_private_capture(self):
        route(self.event("ai news"), self.routing)
        route(self.event("which affects developers?"), self.routing)
        prompts = list((self.root / "messages").glob("*.prompt.txt"))
        self.assertEqual(len(prompts), 2)
        self.assertEqual({path.read_text() for path in prompts}, {"ai news", "which affects developers?"})

    def test_context_is_recent_bounded_and_excludes_reasoning_and_tool_payloads(self):
        for index in range(8):
            folder = self.output / "sessions" / f"s{index}" / "turns" / "0001"
            folder.mkdir(parents=True)
            path = folder / "receipt.json"
            path.write_text(json.dumps({"request": f"request {index}", "answer": "é" * 3500,
                                        "status": "advisory", "reasoning": "secret-reasoning",
                                        "preparation": {"events": ["private-tool-payload"]}}))
            os.utime(path, (index + 1, index + 1))
        output = route(self.event("continue"), self.routing)
        command = shlex.split(output["hookSpecificOutput"]["additionalContext"].splitlines()[1])
        path = Path(command[command.index("--context-file") + 1])
        content = path.read_text()
        self.assertLessEqual(len(content.encode()), MAX_CONTEXT_BYTES)
        rows = json.loads(content)["recent_turns"]
        self.assertLessEqual(len(rows), 6)
        self.assertEqual(rows[-1]["request"], "request 7")
        self.assertTrue(all(set(row) == {"request", "answer", "status"} for row in rows))
        self.assertNotIn("request 0", content)
        self.assertNotIn("secret-reasoning", content)
        self.assertNotIn("private-tool-payload", content)

    def test_symlinked_message_storage_is_rejected(self):
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        (self.root / "messages").symlink_to(elsewhere, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            route(self.event("query"), self.routing)
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_untrusted_long_receipt_status_is_bounded(self):
        folder = self.output / "sessions" / "s1" / "turns" / "0001"
        folder.mkdir(parents=True)
        (folder / "receipt.json").write_text(json.dumps({"request": "question", "answer": "answer",
                                                        "status": "x" * 200_000}))
        output = route(self.event("follow-up"), self.routing)
        command = shlex.split(output["hookSpecificOutput"]["additionalContext"].splitlines()[1])
        content = Path(command[command.index("--context-file") + 1]).read_bytes()
        self.assertLessEqual(len(content), MAX_CONTEXT_BYTES)
        self.assertEqual(len(json.loads(content)["recent_turns"][0]["status"]), 80)

    def test_cli_blocks_invalid_or_oversized_payload_without_echoing_it(self):
        argv = [sys.executable, str(Path(prompt_hook.__file__)), "--session", str(self.routing)]
        for payload in (b'{"prompt":"private-fragment",invalid}', b"x" * 1_000_001):
            result = subprocess.run(argv, input=payload, env=os.environ, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, b"")
            self.assertIn(b"could not route", result.stderr)
            self.assertNotIn(b"private-fragment", result.stderr)
        with patch.dict(os.environ, {"SUPERCODEX_WORKER": "1"}):
            result = subprocess.run(argv, input=b"not json", env=os.environ, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), {})


FAKE_PREFLIGHT = r'''
import json, os, sys, time, tomllib
from pathlib import Path
root = Path(__file__).parent
(root / 'pid').write_text(str(os.getpid()))
overrides = [sys.argv[i + 1] for i, value in enumerate(sys.argv[:-1]) if value == '-c']
configuration = next(tomllib.loads(value) for value in overrides if value.startswith('hooks.UserPromptSubmit='))
command = configuration['hooks']['UserPromptSubmit'][0]['hooks'][0]['command']
with (root / 'capture.json').open('w') as capture:
    json.dump({'home': os.environ['CODEX_HOME'], 'has_api_key': 'OPENAI_API_KEY' in os.environ,
               'argv': sys.argv[1:], 'worker': os.environ.get('SUPERCODEX_WORKER')}, capture)
for line in sys.stdin:
    request = json.loads(line)
    assert request['method'] not in ('turn/start', 'thread/start')
    if request['method'] == 'initialize':
        print(json.dumps({'id': 1, 'result': {'userAgent': 'fixture'}}), flush=True)
    elif request['method'] == 'hooks/list':
        if (root / 'hang').exists():
            time.sleep(30)
        hook = {'key': '/<session-flags>/config.toml:user_prompt_submit:0:0',
                'source': 'sessionFlags', 'handlerType': 'command', 'eventName': 'userPromptSubmit',
                'command': command, 'enabled': True, 'currentHash': 'sha256:' + 'a' * 64}
        if (root / 'wrong-hook').exists():
            hook['command'] = 'unrelated command'
        print(json.dumps({'id': 2, 'result': {'data': [{'errors': [], 'hooks': [hook]}]}}), flush=True)
'''


class HookPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="sc hook preflight ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.script = self.root / "fake codex.py"
        self.script.write_text(FAKE_PREFLIGHT)
        self.command = [sys.executable, str(self.script)]

    def test_only_exact_owned_hook_receives_scoped_trust_and_no_auth_or_model_call(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fixture-secret"}):
            args = hook_overrides(self.command, self.root / "session-routing.json")
        self.assertEqual(args[0::2], ["-c", "-c"])
        definition = tomllib.loads(args[1])["hooks"]["UserPromptSubmit"]
        trusted = tomllib.loads(args[3])["hooks"]["state"]
        self.assertEqual(trusted, {HOOK_KEY: {"trusted_hash": "sha256:" + "a" * 64}})
        self.assertIn("--session", definition[0]["hooks"][0]["command"])
        captured = json.loads((self.root / "capture.json").read_text())
        self.assertFalse(captured["has_api_key"])
        self.assertEqual(captured["worker"], "1")
        self.assertIn("app-server", captured["argv"])
        self.assertFalse(Path(captured["home"]).exists())
        self.assertNotIn("dangerously", str(args))

    def test_unexpected_hook_cannot_be_trusted(self):
        (self.root / "wrong-hook").touch()
        with self.assertRaisesRegex(ValueError, "--no-prompt-hook"):
            hook_overrides(self.command, self.root / "session-routing.json")

    def test_timeout_stops_probe_and_does_not_silently_disable_routing(self):
        (self.root / "hang").touch()
        with self.assertRaisesRegex(ValueError, "Cannot enable"):
            hook_overrides(self.command, self.root / "session-routing.json", timeout=.3)
        pid = int((self.root / "pid").read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)


if __name__ == "__main__":
    unittest.main()
