"""Every shipped skill must be usable from the native operator catalog."""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from codex_harness.agent_tools import bundled_skills, skill_text
from codex_harness.config import ASSETS


class SkillCatalogTests(unittest.TestCase):
    def test_catalog_covers_packaged_skills_with_readable_absolute_paths(self):
        expected = {path.resolve() for path in (ASSETS / "skills").glob("*/SKILL.md")}
        rows = bundled_skills()
        self.assertTrue(expected)
        self.assertEqual({Path(row["path"]) for row in rows}, expected)
        self.assertEqual(len(rows), len(expected))
        names = [row["name"] for row in rows]
        self.assertEqual(len(names), len(set(names)))
        for row in rows:
            with self.subTest(name=row["name"]):
                path = Path(row["path"])
                self.assertTrue(path.is_absolute())
                self.assertEqual(path.name, "SKILL.md")
                self.assertEqual(row["name"], path.parent.name)
                self.assertTrue(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", row["name"]))
                text = path.read_text(encoding="utf-8")
                self.assertTrue(text.startswith("---\n"))
                frontmatter, body = text.split("---", 2)[1:]
                self.assertRegex(frontmatter, r"(?m)^name:\s*" + re.escape(row["name"]) + r"\s*$")
                self.assertTrue(row["description"].strip())
                self.assertIn(row["description"], frontmatter)
                self.assertTrue(body.strip())

    def test_operator_renders_catalog_without_inlining_every_skill_body(self):
        operator = skill_text()
        self.assertNotIn("{{SUPER_CODEX_SKILLS}}", operator)
        self.assertNotIn("{{SUPER_CODEX_COMMAND}}", operator)
        for row in bundled_skills():
            with self.subTest(name=row["name"]):
                self.assertIn(row["name"], operator)
                self.assertIn(row["description"], operator)
                self.assertIn(row["path"], operator)
                body = Path(row["path"]).read_text(encoding="utf-8").split("---", 2)[2].strip()
                self.assertNotIn(body, operator, "Read skill instructions on demand instead of stuffing every body into startup")

    def test_skill_cli_lists_and_reads_from_another_directory_even_for_managed_workers(self):
        launcher = Path(__file__).resolve().parents[1] / "codex_harness/launch.py"
        env = {**os.environ, "SUPERCODEX_WORKER": "1"}
        rows = bundled_skills()
        selected = rows[0]
        with tempfile.TemporaryDirectory(prefix="supercodex skill discovery ") as directory:
            def invoke(*args):
                return subprocess.run([sys.executable, str(launcher), *args], cwd=directory,
                                      env=env, text=True, capture_output=True, timeout=10)

            listing = invoke("skills", "--json")
            self.assertEqual(listing.returncode, 0, listing.stderr)
            self.assertEqual(json.loads(listing.stdout), {"skills": rows})

            content = invoke("skills", selected["name"])
            self.assertEqual(content.returncode, 0, content.stderr)
            self.assertEqual(content.stdout.rstrip(), Path(selected["path"]).read_text().rstrip())

            metadata = invoke("skills", selected["name"], "--json")
            self.assertEqual(metadata.returncode, 0, metadata.stderr)
            self.assertEqual(json.loads(metadata.stdout), {"skills": [selected]})

            discovery = invoke("commands", "skills", "--json")
            self.assertEqual(discovery.returncode, 0, discovery.stderr)
            self.assertEqual(json.loads(discovery.stdout)["commands"][0]["path"], ["skills"])

            missing = invoke("skills", "../operator/super-codex")
            self.assertEqual(missing.returncode, 2)
            self.assertIn("Unknown bundled skill", missing.stderr)
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
