import sys
import tempfile
import unittest
from pathlib import Path

from codex_harness.config import ASSETS, load_policy, load_task
from codex_harness.demo import create
from codex_harness.runner import git, run


class OutputDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.fixture = create(self.root / "fixture")
        self.repo = self.fixture / "repo"
        self.task = load_task(self.fixture / "mean.json")
        self.policy = load_policy(overrides={
            "codex_command": [sys.executable, str(ASSETS / "fake_codex.py")],
            "max_attempts": 2,
        })

    def run_task(self, output):
        return run(self.repo, self.task, self.policy, output)

    def ignore_outputs(self):
        (self.repo / ".gitignore").write_text("__pycache__/\n.harness/\n")
        git(self.repo, "add", ".gitignore")
        git(self.repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "-c", "commit.gpgsign=false", "commit", "-qm", "Ignore local artifacts")

    def test_unignored_output_rejected_before_any_artifacts(self):
        output = self.repo / ".harness" / "runs"
        with self.assertRaisesRegex(ValueError, "Use --output.*outside"):
            self.run_task(output)
        self.assertFalse((self.repo / ".harness").exists())
        self.assertEqual(git(self.repo, "status", "--porcelain"), b"")

    def test_source_root_and_git_metadata_are_not_output_directories(self):
        for output in (self.repo, self.repo / ".git" / "runs"):
            with self.subTest(output=output):
                with self.assertRaisesRegex(ValueError, "Use --output"):
                    self.run_task(output)
        self.assertFalse((self.repo / ".git" / "runs").exists())
        self.assertEqual(git(self.repo, "status", "--porcelain"), b"")

    def test_new_and_existing_ignored_directory_support_repeated_runs(self):
        self.ignore_outputs()
        output = self.repo / ".harness"
        self.assertFalse(output.exists())
        for _ in range(2):
            result = self.run_task(output)
            self.assertEqual(result["status"], "passed")
            self.assertTrue((Path(result["artifact_directory"]) / "accepted.patch").exists())
            self.assertEqual(git(self.repo, "status", "--porcelain"), b"")

    def test_external_output_allowed_and_source_preserved(self):
        result = self.run_task(self.root / "runs")
        self.assertEqual(result["status"], "passed")
        self.assertEqual(git(self.repo, "status", "--porcelain"), b"")

    def test_external_symlink_into_source_does_not_bypass_check(self):
        alias = self.root / "alias"
        alias.symlink_to(self.repo)
        with self.assertRaisesRegex(ValueError, "Use --output"):
            self.run_task(alias / ".harness")
        self.assertFalse((self.repo / ".harness").exists())

    def test_external_output_does_not_bypass_dirty_source_check(self):
        (self.repo / "stats.py").write_text("# uncommitted user work\n")
        with self.assertRaisesRegex(ValueError, "dirty"):
            self.run_task(self.root / "runs")
        self.assertFalse((self.root / "runs").exists())


if __name__ == "__main__":
    unittest.main()
