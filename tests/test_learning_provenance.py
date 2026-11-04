import tempfile
import unittest
from pathlib import Path

from codex_harness.config import ASSETS, load_policy, read
from codex_harness.demo import create
from codex_harness.improve import copy_pack, development_history, fingerprint, pack_digest, propose, register
from codex_harness.runner import save
from test_improve import Proposer


class LearningProvenanceTests(unittest.TestCase):
    def test_ancestry_survives_fork_register_and_another_optimizer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = copy_pack(ASSETS / "packs" / "backend", root / "learned")
            prior = {"development_task_hashes": ["old-task"], "development_task_ids": ["old-id"],
                     "development_prompt_hashes": [fingerprint("old training prompt")]}
            save(source / "proposal.json", prior)
            fork = copy_pack(source, root / "fork")
            self.assertEqual(pack_digest(fork), pack_digest(source))
            release = register(fork, root / "registry")
            self.assertIn("old-task", development_history(release)["development_task_hashes"])
            fixture = create(root / "fixture")
            record = {"task_id": "new-id", "task_sha256": "new-task", "status": "failed", "attempts": [],
                      "task": {"prompt": " New TRAINING prompt "}}
            metadata = propose(release, root / "new-candidate", [record], fixture / "repo", load_policy(), "strong", Proposer())
            self.assertEqual(set(metadata["development_task_hashes"]), {"old-task", "new-task"})
            self.assertEqual(set(metadata["development_prompt_hashes"]),
                             {fingerprint("old training prompt"), fingerprint("new training prompt")})
            self.assertEqual(read(root / "new-candidate" / "proposal.json"), metadata)

    def test_provenance_rejects_malformed_inherited_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save(root / "proposal.json", {"development_task_hashes": "not-an-array"})
            with self.assertRaisesRegex(ValueError, "provenance"):
                development_history(root)


if __name__ == "__main__":
    unittest.main()
