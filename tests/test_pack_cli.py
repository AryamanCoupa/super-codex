import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_harness.cli import main


class PackCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(arg) for arg in args])
        return code, out.getvalue(), err.getvalue()

    def write_task(self, filename="task.json", **overrides):
        value = {"id": "react-page", "prompt": "Fix loading UI in a React page", **overrides}
        path = self.root / filename
        path.write_text(json.dumps(value))
        return path

    def test_list_custom_root_json_and_human_output(self):
        packs = self.root / "packs"
        packs.mkdir()
        code, _, err = self.invoke("pack", "create", packs / "checkout-ui", "--from", "frontend")
        self.assertEqual(code, 0, err)
        code, output, err = self.invoke("pack", "list", "--root", packs, "--json")
        self.assertEqual(code, 0, err)
        found = json.loads(output)
        custom = next(row for row in found if row["name"] == "checkout-ui")
        self.assertEqual(custom["source"], "custom")
        self.assertEqual(custom["selector"], str(packs / "checkout-ui"))
        self.assertIn("backend", [row["name"] for row in found])
        code, output, _ = self.invoke("pack", "list", "--root", packs)
        self.assertEqual(code, 0)
        self.assertIn("checkout-ui [custom]", output)
        self.assertIn("tools=playwright", output)

    def test_suggest_accepts_task_file_or_prompt(self):
        task = self.write_task()
        code, file_output, err = self.invoke("pack", "suggest", task)
        self.assertEqual(code, 0, err)
        code, prompt_output, err = self.invoke("pack", "suggest", "--prompt", "Fix loading UI in a React page")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(file_output)["recommended_pack"], "frontend")
        self.assertEqual(json.loads(file_output)["suggestions"], json.loads(prompt_output)["suggestions"])

    def test_create_then_inspect_preserves_explicit_task_checks(self):
        task = self.write_task(checks=[["npm", "run", "test:acceptance"]])
        destination = self.root / "checkout-ui"
        code, output, err = self.invoke("pack", "create", destination, "--from", "frontend", "--task", task)
        self.assertEqual(code, 0, err)
        created = json.loads(output)
        code, output, err = self.invoke("pack", "inspect", destination)
        self.assertEqual(code, 0, err)
        inspected = json.loads(output)
        self.assertEqual(created["path"], inspected["path"])
        self.assertEqual(inspected["task_defaults"]["checks"], [["npm", "run", "test:acceptance"]])
        self.assertFalse(inspected["needs_checks"])
        code, output, err = self.invoke("pack", "suggest", task, "--root", destination)
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(output)["recommended_pack"], str(destination))

    def test_incomplete_checks_prevent_run_before_agent_or_artifacts(self):
        destination = self.root / "checkout-ui"
        code, _, err = self.invoke("pack", "create", destination, "--from", "frontend", "--prompt", "Fix loading UI")
        self.assertEqual(code, 0, err)
        output_dir = self.root / "runs"
        with patch("codex_harness.cli.run") as run:
            code, _, err = self.invoke("run", destination / "task.example.json", "--pack", destination,
                                       "--repo", self.root, "--output", output_dir)
        self.assertEqual(code, 2)
        self.assertIn("At least one check is required", err)
        run.assert_not_called()
        self.assertFalse(output_dir.exists())

    def test_suggest_rejects_ambiguous_or_missing_task_input(self):
        task = self.write_task()
        code, _, err = self.invoke("pack", "suggest", task, "--prompt", "Something else")
        self.assertEqual(code, 2)
        self.assertIn("not both", err)
        code, _, err = self.invoke("pack", "suggest")
        self.assertEqual(code, 2)
        self.assertIn("Supply a task", err)

    def test_historical_budget_exhaustion_suggests_experiment_but_not_other_tasks(self):
        task = self.write_task()
        task_data = json.loads(task.read_text())
        results = self.root / "runs"
        for index in range(2):
            directory = results / str(index)
            directory.mkdir(parents=True)
            (directory / "result.json").write_text(json.dumps({"task_id": task_data["id"],
                "task": task_data, "status": "budget_exhausted"}))
        code, output, err = self.invoke("pack", "suggest", task, "--from-runs", results)
        self.assertEqual(code, 0, err)
        recommendation = json.loads(output)
        self.assertTrue(recommendation["create_recommended"])
        self.assertEqual(recommendation["matching_result_statuses"], {"budget_exhausted": 2})
        task_data["prompt"] = "Fix a different React dialog"
        task.write_text(json.dumps(task_data))
        code, output, err = self.invoke("pack", "suggest", task, "--from-runs", results)
        self.assertEqual(code, 0, err)
        recommendation = json.loads(output)
        self.assertFalse(recommendation["create_recommended"])
        self.assertEqual(recommendation["matching_result_statuses"], {})


if __name__ == "__main__":
    unittest.main()
