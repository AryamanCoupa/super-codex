import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from codex_harness.agent_tools import bundled_skills
from codex_harness import skill_hook


class SkillReminderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="sc skill reminder ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.environment = patch.dict(os.environ)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        os.environ.pop("SUPERCODEX_WORKER", None)
        self.catalog = {row["name"]: row for row in bundled_skills()}

    def event(self, prompt):
        return {"hook_event_name": "UserPromptSubmit", "prompt": prompt,
                "transcript_path": str(self.root / "must-not-read.jsonl")}

    def context(self, prompt):
        result = skill_hook.remind(self.event(prompt))
        self.assertEqual(result["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        return result["hookSpecificOutput"]["additionalContext"]

    def test_two_tasks_receive_relevant_paths_without_prompt_exposure_or_processes(self):
        with patch("subprocess.Popen") as launch, patch("socket.create_connection") as network:
            debug = self.context('debug failing tests; private-marker-1 "$(touch unwanted)"')
            research = self.context("latest AI news private-marker-2")
        launch.assert_not_called()
        network.assert_not_called()
        self.assertIn(self.catalog["debug-with-evidence"]["path"], debug)
        self.assertNotIn(self.catalog["research-with-sources"]["path"], debug)
        self.assertIn(self.catalog["research-with-sources"]["path"], research)
        self.assertNotIn(self.catalog["debug-with-evidence"]["path"], research)
        for context in (debug, research):
            self.assertIn(self.catalog["skill-discovery"]["path"], context)
            self.assertIn(self.catalog["verify-changes"]["path"], context)
            self.assertNotIn("private-marker", context)
            self.assertNotIn("touch unwanted", context)
            self.assertNotIn("must-not-read.jsonl", context)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_shortlist_is_bounded_and_guidance_preserves_native_work(self):
        context = self.context("debug browser github atlassian research delegation")
        self.assertLessEqual(context.count("\n  Read: "), 2 + skill_hook.MAX_TOPIC_SKILLS)
        self.assertIn("matches keywords only", context)
        self.assertIn("current Codex session", context)
        self.assertIn("No answer command", context)
        self.assertIn("permission controls", context)
        self.assertIn("adds value", context)
        self.assertIn("confirm readiness and wait", context)
        for row in self.catalog.values():
            body = Path(row["path"]).read_text().split("---", 2)[2].strip()
            self.assertNotIn(body, context)

    def test_unmatched_and_filler_prompts_keep_discovery_without_inventing_topics(self):
        for prompt in ("zyzzyvaquantum", "can you please help me"):
            with self.subTest(prompt=prompt):
                context = self.context(prompt)
                self.assertIn("No bundled topic match", context)
                self.assertEqual(context.count("\n  Read: "), 2)

    def test_managed_worker_skips_catalog_and_payload(self):
        with patch.dict(os.environ, {"SUPERCODEX_WORKER": "1"}), \
                patch("codex_harness.skill_hook.bundled_skills", side_effect=AssertionError("Unexpected read")):
            self.assertEqual(skill_hook.remind(None), {})

    def invoke(self, payload, **environment):
        command = shlex.split(skill_hook.hook_definition()["UserPromptSubmit"][0]["hooks"][0]["command"])
        return subprocess.run(command, input=payload, cwd=self.root,
                              env={**os.environ, **environment}, capture_output=True, timeout=5)

    def test_invalid_payloads_do_not_block_or_echo_prompt_data(self):
        cases = [b'{"prompt":"private-fragment",invalid}', b"[]",
                 json.dumps({"hook_event_name": "Other", "prompt": "private-fragment"}).encode(),
                 json.dumps(self.event(123)).encode(),
                 json.dumps(self.event("private-fragment\0")).encode(),
                 b"x" * (skill_hook.MAX_INPUT_BYTES + 1)]
        for payload in cases:
            with self.subTest(size=len(payload)):
                result = self.invoke(payload)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), {})
                self.assertIn(b"reminder unavailable", result.stderr)
                self.assertNotIn(b"private-fragment", result.stderr)
        worker = self.invoke(b"invalid", SUPERCODEX_WORKER="1")
        self.assertEqual(worker.returncode, 0)
        self.assertEqual(json.loads(worker.stdout), {})
        self.assertEqual(worker.stderr, b"")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_absolute_isolated_entrypoint_ignores_foreign_imports_and_writes_no_files(self):
        malicious = self.root / "codex_harness"
        malicious.mkdir()
        (malicious / "__init__.py").write_text("raise RuntimeError('Untrusted working directory import')\n")
        before = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))
        result = self.invoke(json.dumps(self.event("latest AI news private-question")).encode(),
                             PYTHONPATH=str(self.root), PATH="")
        self.assertEqual(result.returncode, 0, result.stderr)
        context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn(self.catalog["research-with-sources"]["path"], context)
        self.assertNotIn("private-question", context)
        self.assertEqual(sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*")), before)


class SkillReminderRegistrationTests(unittest.TestCase):
    def test_only_owned_inspected_hook_is_trusted_with_isolated_absolute_launcher(self):
        digest = "sha256:" + "a" * 64
        with patch("codex_harness.skill_hook._inspect_hook", return_value=digest) as inspect:
            args = skill_hook.hook_overrides(["fixture-codex"])
        definition = skill_hook.hook_definition()
        inspect.assert_called_once_with(["fixture-codex"], definition, 10)
        self.assertEqual(args[0::2], ["-c", "-c"])
        configured = tomllib.loads(args[1])["hooks"]["UserPromptSubmit"]
        self.assertEqual(configured, definition["UserPromptSubmit"])
        trusted = tomllib.loads(args[3])["hooks"]["state"]
        self.assertEqual(trusted, {skill_hook.HOOK_KEY: {"trusted_hash": digest}})
        command = shlex.split(configured[0]["hooks"][0]["command"])
        self.assertTrue(Path(command[0]).is_absolute())
        self.assertEqual(command[1:3], ["-I", "-B"])
        self.assertEqual(Path(command[3]), Path(skill_hook.__file__).resolve())
        self.assertEqual(len(command), 4)
        self.assertEqual(configured[0]["hooks"][0]["statusMessage"], "Selecting SuperCodex skills")

    def test_registration_error_is_reported_without_trust_bypass(self):
        with patch("codex_harness.skill_hook._inspect_hook", side_effect=PermissionError("Operation not permitted")):
            with self.assertRaisesRegex(ValueError, "skill reminder"):
                skill_hook.hook_overrides(["fixture-codex"])


if __name__ == "__main__":
    unittest.main()
