import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_harness.config import ASSETS
from codex_harness.improve import copy_pack, pack_digest, register
from codex_harness.runner import pack_context


class PackSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assets = self.root / "assets"
        shutil.copytree(ASSETS, self.assets)
        for module in ("codex_harness.runner.ASSETS", "codex_harness.improve.ASSETS"):
            patcher = patch(module, self.assets)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.source = self.assets / "packs" / "backend"
        self.skill = self.assets / "skills" / "debug-with-evidence"

    def test_bundled_pack_and_fork_have_same_context_and_digest(self):
        references = self.skill / "references"
        references.mkdir()
        (references / "example.txt").write_text("Reusable skill resource.\n")
        forked = copy_pack(self.source, self.root / "forked")
        self.assertEqual(pack_context(self.source), pack_context(forked))
        self.assertEqual(pack_digest(self.source), pack_digest(forked))
        self.assertEqual((forked / "skills" / "debug-with-evidence" / "references" / "example.txt").read_text(),
                         "Reusable skill resource.\n")

    def test_registered_release_is_independent_of_bundle_changes(self):
        release = register(self.source, self.root / "registry")
        before_context, before_digest = pack_context(release), pack_digest(release)
        original = self.skill / "SKILL.md"
        original.write_text(original.read_text() + "\nChanged in a later bundle.\n")
        self.assertTrue((release / "skills" / "debug-with-evidence" / "SKILL.md").is_file())
        self.assertEqual(pack_context(release), before_context)
        self.assertEqual(pack_digest(release), before_digest)
        self.assertNotEqual(pack_digest(self.source), before_digest)

    def test_partial_local_skill_override_fails_before_copy_or_registration(self):
        partial = self.source / "skills" / "debug-with-evidence"
        partial.mkdir(parents=True)
        (partial / "notes.txt").write_text("Incomplete local override")
        for operation in (lambda: pack_context(self.source),
                          lambda: copy_pack(self.source, self.root / "forked"),
                          lambda: register(self.source, self.root / "registry")):
            with self.assertRaisesRegex(ValueError, "must contain SKILL.md"):
                operation()
        self.assertFalse((self.root / "forked").exists())
        self.assertFalse((self.root / "registry" / "active.json").exists())

    def test_symlinked_bundled_skill_resource_rejected_before_copy(self):
        (self.skill / "linked.txt").symlink_to(self.source / "instructions.md")
        with self.assertRaisesRegex(ValueError, "symlinks"):
            copy_pack(self.source, self.root / "forked")
        self.assertFalse((self.root / "forked").exists())

    def test_symlinked_local_skill_rejected(self):
        (self.source / "skills").mkdir()
        (self.source / "skills" / "debug-with-evidence").symlink_to(self.skill)
        with self.assertRaisesRegex(ValueError, "symlinks"):
            register(self.source, self.root / "registry")
        self.assertFalse((self.root / "registry" / "active.json").exists())


if __name__ == "__main__":
    unittest.main()
