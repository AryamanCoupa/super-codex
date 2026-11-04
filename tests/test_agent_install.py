import contextlib
import io
import json
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_harness.agent_tools import install_skill, invocation
from codex_harness.cli import main
from codex_harness.config import ASSETS
from codex_harness.demo import create
from codex_harness.runner import save


class AgentInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="supercodex agent ")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_project_skill_launcher_discovers_commands_from_another_directory(self):
        project = self.root / "project with spaces"
        project.mkdir()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["agent", "install", "--repo", str(project)]), 0)
        skill = project / ".agents/skills/super-codex/SKILL.md"
        text = skill.read_text()
        command = shlex.split(text.split("```bash\n", 1)[1].split("\n", 1)[0])
        result = subprocess.run([*command, "--json"], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        paths = {tuple(row["path"]) for row in json.loads(result.stdout)["commands"]}
        self.assertIn(("agent", "install"), paths)
        self.assertIn(("experimental", "finetune", "train"), paths)
        self.assertIn(("pack", "optimize"), paths)

    def test_user_scope_and_idempotent_install_without_touching_real_home(self):
        with patch("codex_harness.agent_tools.Path.home", return_value=self.root), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["agent", "install", "--user"]), 0)
        destination = self.root / ".agents/skills/super-codex"
        self.assertEqual(install_skill(destination)["status"], "unchanged")

    def test_update_preserves_user_edits_and_unknown_skills(self):
        destination = self.root / "skill"
        install_skill(destination)
        before = (destination / "SKILL.md").read_text()
        with patch("codex_harness.agent_tools.skill_text", return_value=before + "\nUpdated guidance.\n"):
            with self.assertRaisesRegex(ValueError, "--update"):
                install_skill(destination)
            self.assertEqual(install_skill(destination, update=True)["status"], "installed")
        (destination / "SKILL.md").write_text("User-edited instructions")
        with self.assertRaisesRegex(ValueError, "local edits"):
            install_skill(destination, update=True)
        self.assertEqual((destination / "SKILL.md").read_text(), "User-edited instructions")
        unknown = self.root / "unmanaged"
        unknown.mkdir()
        (unknown / "SKILL.md").write_text("Existing skill")
        with self.assertRaisesRegex(ValueError, "not a managed"):
            install_skill(unknown, update=True)

    def test_installer_refuses_symlinked_destination(self):
        actual = self.root / "actual"
        actual.mkdir()
        link = self.root / "skill-link"
        link.symlink_to(actual, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            install_skill(link)
        self.assertEqual(list(actual.iterdir()), [])

    def test_absolute_launcher_runs_task_in_other_repo_from_foreign_cwd(self):
        fixture = create(self.root / "target repository")
        working = self.root / "operator directory"
        working.mkdir()
        policy = self.root / "simulation.json"
        save(policy, {"model": "simulator", "max_attempts": 2,
                      "codex_command": [sys.executable, str(ASSETS / "fake_codex.py")]})
        # -I removes PYTHONPATH and cwd import support: launch.py must locate its own package.
        argv = invocation()
        result = subprocess.run([argv[0], "-I", argv[1], "run", str(fixture / "mean.json"),
            "--repo", str(fixture / "repo"), "--config", str(policy), "--output", str(self.root / "runs")],
            cwd=working, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads(result.stdout)
        self.assertEqual(record["status"], "passed")
        self.assertTrue((Path(record["artifact_directory"]) / "accepted.patch").exists())
        self.assertIn("return sum(values)", (fixture / "repo/stats.py").read_text())


if __name__ == "__main__":
    unittest.main()
