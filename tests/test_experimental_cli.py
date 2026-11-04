import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_harness.cli import main
from codex_harness.config import ASSETS, load_policy, load_task, read
from codex_harness.demo import create
from codex_harness.experimental.memory import build_memory
from codex_harness.experimental.routing import route
from codex_harness.improve import fingerprint
from codex_harness.runner import run, save


class ExperimentalCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.fixture = create(self.root / "fixture")
        self.repo = self.fixture / "repo"
        self.config = self.root / "policy.json"
        save(self.config, {"codex_command": [sys.executable, str(ASSETS / "fake_codex.py")],
                           "model": "simulator", "max_attempts": 2})

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, arguments):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(arguments)
        return code, json.loads(out.getvalue()) if out.getvalue().strip() else {}, err.getvalue()

    def task_args(self, action):
        return ["experimental", action, str(self.fixture / "mean.json"), "--repo", str(self.repo),
                "--config", str(self.config), "--output", str(self.root / action)]

    def test_feature_inventory_and_actual_parallel_cli(self):
        code, inventory, _ = self.invoke(["experimental", "list"])
        self.assertEqual(code, 0)
        self.assertEqual(len(inventory["features"]), 8)
        code, output, error = self.invoke(self.task_args("best-of-n") + ["--candidates", "2", "--concurrency", "2"])
        self.assertEqual(code, 0, error)
        self.assertEqual(output["status"], "passed")
        self.assertEqual(output["accounting"]["tokens"], 520)
        self.assertTrue(Path(output["accepted_patch"]).is_file())
        self.assertNotIn("records", output)
        self.assertEqual(len(read(self.root / "best-of-n" / "experiment.json")["records"]), 2)

    def test_retrieval_and_ace_context_are_composed_into_real_verified_run(self):
        task = load_task(self.fixture / "mean.json")
        task["id"], task["prompt"] = "previous-mean", "Repair stats.mean empty input using the existing contract."
        previous = run(self.repo, task, load_policy(self.config), self.root / "past")
        self.assertEqual(previous["status"], "passed")
        index, book = self.root / "memory.json", self.root / "book.json"
        build_memory([previous], index)
        save(book, {"schema_version": 1, "bullets": [{"id": "b-0123456789ab", "text": "Check stats.mean empty input and negative values.",
                                                     "helpful": 2, "harmful": 0, "tags": ["mean"], "evidence_ids": [previous["id"]]}]})
        code, output, error = self.invoke(self.task_args("run") + ["--memory", str(index), "--ace-playbook", str(book)])
        self.assertEqual(code, 0, error)
        row = read(Path(output["artifact_directory"]) / "result.json")
        self.assertEqual(row["status"], "passed")
        self.assertTrue(row["experimental"]["retrieval"]["matches"])
        self.assertEqual(row["experimental"]["ace_bullet_ids"], ["b-0123456789ab"])
        prompt = (Path(row["artifact_directory"]) / "attempt-1" / "prompt.txt").read_text()
        self.assertIn("Retrieved prior successful-run metadata", prompt)
        self.assertIn("b-0123456789ab", prompt)

    def test_explicit_model_cannot_silently_be_overwritten_by_router(self):
        code, _, error = self.invoke(self.task_args("run") + ["--router", "unused.json", "--model", "chosen"])
        self.assertEqual(code, 2)
        self.assertIn("Choose --router", error)

    def test_router_context_matches_real_memory_and_playbook_prompt_before_selection(self):
        task = load_task(self.fixture / "mean.json")
        task["id"], task["prompt"] = "prior-mean", "Repair stats.mean empty input using the existing contract."
        previous = run(self.repo, task, load_policy(self.config), self.root / "past")
        self.assertEqual(previous["status"], "passed")
        memory, playbook, router_path = self.root / "memory.json", self.root / "book.json", self.root / "router.json"
        build_memory([previous], memory)
        save(playbook, {"schema_version": 1, "bullets": [{"id": "b-0123456789ab",
             "text": "Check stats.mean empty input and negative values.", "helpful": 2, "harmful": 0,
             "tags": ["mean"], "evidence_ids": [previous["id"]]}]})

        def runtime_context(record):
            return {**{key: record[key] for key in ("base_commit", "pack_sha256", "context_sha256", "agent_cli_context_sha256", "mcp_sha256",
                                                    "codex_version", "platform", "python")},
                    "policy_sha256": fingerprint({k: v for k, v in record["policy"].items() if k != "model"})}

        # A fitted-score fixture strongly prefers cheap when its runtime context matches.
        # The real router and real runner determine whether composition changes that support.
        router = {"schema_version": 1, "kind": "quality-cost-router", "models": {"cheap": "simulator", "strong": "strong-simulator"},
                  "vocabulary": ["mean"], "idf": [1.0], "weights": [0.0], "bias": 10.0,
                  "training_vectors": [[1.0]], "contexts": [runtime_context(previous)]}
        save(router_path, router)
        args = self.task_args("run") + ["--memory", str(memory), "--ace-playbook", str(playbook), "--router", str(router_path)]
        with patch("codex_harness.experimental.routing.route", wraps=route) as selection:
            code, output, error = self.invoke(args)
        self.assertEqual(code, 0, error)
        record = read(Path(output["artifact_directory"]) / "result.json")
        self.assertEqual(record["policy"]["model"], "strong-simulator")
        self.assertFalse(record["experimental"]["routing"]["cheap_selected"])
        self.assertIn("context differs", " ".join(record["experimental"]["routing"]["reasons"]))
        self.assertEqual(selection.call_args.kwargs["expected_context"]["context_sha256"], record["context_sha256"])
        self.assertEqual(selection.call_args.kwargs["expected_context"]["agent_cli_context_sha256"], record["agent_cli_context_sha256"])
        self.assertNotEqual(record["context_sha256"], previous["context_sha256"])

        # When the same composed context is present in comparison evidence, cheap routing is allowed.
        router["contexts"] = [runtime_context(record)]
        save(router_path, router)
        args[args.index("--output") + 1] = str(self.root / "matched-context")
        code, output, error = self.invoke(args)
        self.assertEqual(code, 0, error)
        matched = read(Path(output["artifact_directory"]) / "result.json")
        self.assertEqual(matched["context_sha256"], record["context_sha256"])
        self.assertEqual(matched["policy"]["model"], "simulator")
        self.assertTrue(matched["experimental"]["routing"]["cheap_selected"])


if __name__ == "__main__":
    unittest.main()
