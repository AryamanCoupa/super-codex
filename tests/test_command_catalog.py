import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from codex_harness.cli import build_parser, main
from codex_harness.command_catalog import catalog


class CommandCatalogTests(unittest.TestCase):
    def test_inventory_covers_every_executable_parser_and_roundtrips_usage_arguments(self):
        parser = build_parser()
        leaves = {}

        def walk(current, path=()):
            children = [action for action in current._actions if isinstance(action, argparse._SubParsersAction)]
            if not children:
                leaves[path] = current
            for action in children:
                for name, child in action.choices.items():
                    walk(child, (*path, name))

        walk(parser)
        inventory = json.loads(json.dumps(catalog(parser)))
        self.assertEqual({tuple(item["path"]) for item in inventory["commands"]}, set(leaves))
        for item in inventory["commands"]:
            current = leaves[tuple(item["path"])]
            self.assertEqual(item["usage"], current.format_usage().strip())
            self.assertEqual({argument["name"] for argument in item["arguments"]},
                             {action.dest for action in current._actions if action.help != argparse.SUPPRESS})
        run = next(item for item in inventory["commands"] if item["path"] == ["run"])
        repo = next(item for item in run["arguments"] if item["name"] == "repo")
        self.assertTrue(repo["required"])
        self.assertEqual(repo["flags"], ["--repo"])
        mcp = next(item for item in run["arguments"] if item["name"] == "mcp")
        self.assertTrue(mcp["repeatable"])

    def test_new_command_is_discoverable_without_catalog_registration(self):
        parser = build_parser()
        subcommands = next(action for action in parser._actions if isinstance(action, argparse._SubParsersAction))
        added = subcommands.add_parser("future-command", help="A dynamically added command")
        added.add_argument("--mode", choices=["quick", "full"], default="quick")
        result = catalog(parser, ["future-command"])
        self.assertEqual(len(result["commands"]), 1)
        self.assertEqual(result["commands"][0]["description"], "A dynamically added command")
        mode = next(item for item in result["commands"][0]["arguments"] if item["name"] == "mode")
        self.assertEqual(mode["choices"], ["quick", "full"])
        self.assertEqual(mode["default"], "quick")

    def test_nested_scope_and_unknown_command_are_handled_without_execution(self):
        parser = build_parser()
        result = catalog(parser, ["experimental", "router"])
        self.assertEqual({tuple(row["path"]) for row in result["commands"]},
                         {("experimental", "router", "train"), ("experimental", "router", "choose")})
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = main(["commands", "missing-command", "--json"])
        self.assertEqual(status, 2)
        self.assertFalse(out.getvalue())
        self.assertIn("Unknown command path", err.getvalue())

    def test_module_inventory_and_leaf_help_work_from_another_directory(self):
        source = Path(__file__).resolve().parents[1]
        env = {**os.environ, "PYTHONPATH": str(source)}
        with tempfile.TemporaryDirectory() as directory:
            def invoke(*arguments):
                result = subprocess.run([sys.executable, "-m", "codex_harness", *arguments],
                                        cwd=directory, env=env, capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout
            inventory = json.loads(invoke("commands", "--json"))
            self.assertTrue(any(row["path"] == ["experimental", "finetune", "train"] for row in inventory["commands"]))
            actual_help = invoke("experimental", "router", "train", "--help")
            discovered_help = invoke("commands", "experimental", "router", "train")
            self.assertEqual(actual_help.rstrip(), discovered_help.rstrip())
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
