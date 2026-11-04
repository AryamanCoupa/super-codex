import tempfile
import unittest
from pathlib import Path

from scripts.check_release import check_release


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "codex_harness").mkdir()
        (self.root / "pyproject.toml").write_text('[project]\nname = "super-codex-harness"\nversion = "0.4.0"\n')
        self.init = self.root / "codex_harness/__init__.py"
        self.init.write_text('__version__ = "0.4.0"\n')

    def tearDown(self):
        self.temp.cleanup()

    def test_matching_stable_tag_identifies_built_version(self):
        self.assertEqual(check_release(self.root, "v0.4.0"), "0.4.0")

    def test_tag_or_runtime_version_mismatch_cannot_publish(self):
        with self.assertRaisesRegex(ValueError, "match exactly"):
            check_release(self.root, "v0.4.1")
        self.init.write_text('__version__ = "0.3.1"\n')
        with self.assertRaisesRegex(ValueError, "match exactly"):
            check_release(self.root, "v0.4.0")

    def test_prerelease_and_malformed_tags_cannot_be_published_as_stable(self):
        for tag in ("0.4.0", "v0.4.0rc1", "v0.4.0-beta.1", "v00.4.0", "v0.4.0\n", "v0.4.0;echo wrong"):
            with self.subTest(tag=tag), self.assertRaisesRegex(ValueError, "stable versions"):
                check_release(self.root, tag)


if __name__ == "__main__":
    unittest.main()
