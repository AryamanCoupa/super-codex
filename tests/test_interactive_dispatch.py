import contextlib
import io
import json
import os
import sys
import unittest
from unittest.mock import patch

from codex_harness import __version__
from codex_harness.cli import main


class InteractiveDispatchTests(unittest.TestCase):
    def test_no_arguments_launch_session_and_preserve_caller_argv(self):
        supplied = []
        with patch("codex_harness.session.handle", return_value=17) as launch:
            self.assertEqual(main(supplied), 17)
        self.assertEqual(supplied, [])
        self.assertEqual(launch.call_args.args[0].action, "start")
        self.assertIsNone(launch.call_args.args[0].prompt)

    def test_process_argv_defaults_to_interactive_and_keeps_quoted_prompt_intact(self):
        prompt = "Fix pagination; preserve the existing API."
        supplied = ["sc", prompt, "--repo", "/project with spaces", "--pack", "backend"]
        with patch.object(sys, "argv", supplied), patch("codex_harness.session.handle", return_value=0) as launch:
            self.assertEqual(main(), 0)
        args = launch.call_args.args[0]
        self.assertEqual(args.prompt, prompt)
        self.assertEqual(args.repo, "/project with spaces")
        self.assertEqual(args.pack, "backend")
        self.assertEqual(supplied[0], "sc")
        self.assertEqual(len(supplied), 6)

    def test_option_first_and_explicit_start_use_same_parser(self):
        supplied = ["--repo", "/another/project", "--config", "architect", "--dry-run"]
        with patch("codex_harness.session.handle", return_value=0) as launch:
            self.assertEqual(main(supplied), 0)
            implicit = vars(launch.call_args.args[0])
            self.assertEqual(main(["start", *supplied]), 0)
            explicit = vars(launch.call_args.args[0])
        self.assertEqual(implicit, explicit)
        self.assertEqual(supplied[0], "--repo")

    def test_existing_commands_are_dispatched_without_opening_codex(self):
        with contextlib.redirect_stdout(io.StringIO()) as out, patch("codex_harness.session.handle") as launch:
            self.assertEqual(main(["commands", "--json"]), 0)
        self.assertIn(["start"], [row["path"] for row in json.loads(out.getvalue())["commands"]])
        launch.assert_not_called()
        with contextlib.redirect_stdout(io.StringIO()) as out, patch("codex_harness.session.handle") as launch:
            self.assertEqual(main(["experimental", "list"]), 0)
        self.assertTrue(json.loads(out.getvalue())["experimental"])
        launch.assert_not_called()

    def test_help_and_version_never_launch_a_session(self):
        for arguments in (["--help"], ["-h"], ["start", "--help"], ["--version"], ["-V"]):
            with self.subTest(arguments=arguments), contextlib.redirect_stdout(io.StringIO()) as out:
                with patch("codex_harness.session.handle") as launch, self.assertRaises(SystemExit) as stop:
                    main(arguments)
                self.assertEqual(stop.exception.code, 0)
                launch.assert_not_called()
                if arguments[0] in {"--version", "-V"}:
                    self.assertIn(__version__, out.getvalue())

    def test_worker_cannot_bypass_nested_session_guard_through_default_or_explicit_dispatch(self):
        for arguments in ([], ["start"], ["fix a bug"]):
            with self.subTest(arguments=arguments), patch.dict(os.environ, {"SUPERCODEX_WORKER": "1"}):
                with contextlib.redirect_stderr(io.StringIO()) as err, patch("codex_harness.session.handle") as launch:
                    self.assertEqual(main(arguments), 2)
                self.assertIn("Managed worker", err.getvalue())
                launch.assert_not_called()

    def test_reserved_command_name_can_be_used_as_prompt_with_explicit_start(self):
        with patch("codex_harness.session.handle", return_value=0) as launch:
            self.assertEqual(main(["start", "run"]), 0)
        self.assertEqual(launch.call_args.args[0].prompt, "run")


if __name__ == "__main__":
    unittest.main()
