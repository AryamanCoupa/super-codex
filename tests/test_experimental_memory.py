import copy
import json
import tempfile
import unittest
from pathlib import Path

from codex_harness.experimental.memory import build_memory, prompt_hash, retrieve
from codex_harness.improve import fingerprint


def example(name, prompt, *, revision="commit-a", pack="pack-a", status="passed"):
    task = {"id": name, "prompt": prompt, "checks": [["python", "-m", "unittest"]], "protected_paths": ["tests"]}
    return {"id": f"run-{name}", "task_id": name, "task": task, "task_sha256": fingerprint(task),
            "base_commit": revision, "pack_sha256": pack, "status": status, "policy": {"model": "cheap"},
            "attempts": [{"model": "cheap", "passed": status == "passed", "changed_files": ["api/pagination.py"],
                          "message": "PRIVATE_HANDOFF", "checks": [{"returncode": 0, "reason": None,
                                                                      "output": "PRIVATE_LOG"}]}]}


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.index_path = self.root / "memory.json"
        self.rows = [example("empty", "Fix pagination empty page handling"),
                     example("stale", "Fix pagination cursor handling", revision="older-commit"),
                     example("other", "Fix pagination response validation", pack="other-pack"),
                     example("date", "Fix timezone datetime conversion")]
        self.task = {"id": "new", "prompt": "Fix pagination of the final partial page", "checks": [["test"]]}

    def tearDown(self):
        self.temp.cleanup()

    def test_retrieves_bounded_verified_metadata_with_revision_and_pack_filters(self):
        index = build_memory(self.rows, self.index_path)
        self.assertEqual(len(index["entries"]), 4)
        result = retrieve(self.index_path, self.task, base_commit="commit-a", pack_sha256="pack-a", max_chars=2000)
        self.assertEqual(result["matches"][0]["run_ids"], ["run-empty"])
        self.assertEqual(result["skipped"]["stale_revision"], 1)
        self.assertEqual(result["skipped"]["different_pack"], 1)
        self.assertLessEqual(len(result["context"]), 2000)
        self.assertIn("api/pagination.py", result["context"])
        self.assertNotIn("PRIVATE_HANDOFF", self.index_path.read_text())
        self.assertNotIn("PRIVATE_LOG", self.index_path.read_text())
        self.assertEqual(self.index_path.stat().st_mode & 0o777, 0o600)

    def test_current_prompt_is_excluded_even_when_renamed_or_reformatted(self):
        index = build_memory(self.rows, self.index_path)
        renamed = dict(self.rows[0]["task"], id="renamed", prompt="  FIX  PAGINATION empty PAGE handling\n")
        result = retrieve(index, renamed, base_commit="commit-a", pack_sha256="pack-a")
        self.assertNotIn("run-empty", json.dumps(result["matches"]))
        self.assertEqual(result["skipped"]["current_or_excluded_task"], 1)

    def test_explicit_holdout_exclusion_applies_at_build_and_query(self):
        excluded = self.rows[0]["task_sha256"]
        index = build_memory(self.rows, self.index_path, exclude_task_hashes=[excluded])
        self.assertEqual(index["skipped_records"]["excluded_task"], 1)
        self.assertNotIn(excluded, [entry["task_sha256"] for entry in index["entries"]])
        plain = build_memory(self.rows, self.root / "all.json")
        result = retrieve(plain, self.task, base_commit="commit-a", pack_sha256="pack-a", exclude_task_hashes=[excluded])
        self.assertNotIn(excluded, [entry["task_sha256"] for entry in result["matches"]])

    def test_normalized_holdout_exclusion_and_index_integrity(self):
        excluded = prompt_hash(self.rows[0]["task"])
        index = build_memory(self.rows, self.index_path, exclude_prompt_hashes=[excluded])
        self.assertEqual(index["skipped_records"]["excluded_prompt"], 1)
        self.assertNotIn(excluded, [entry["prompt_sha256"] for entry in index["entries"]])
        index["entries"][0]["prompt"] = "Changed after indexing"
        with self.assertRaisesRegex(ValueError, "changed after indexing"):
            retrieve(index, self.task, base_commit="commit-a", pack_sha256="pack-a")

    def test_stale_retrieval_requires_explicit_opt_in_and_marks_entries(self):
        index = build_memory(self.rows, self.index_path)
        result = retrieve(index, self.task, base_commit="fresh-commit", pack_sha256="pack-a")
        self.assertEqual(result["context"], "")
        permitted = retrieve(index, self.task, base_commit="fresh-commit", pack_sha256="pack-a", allow_stale=True)
        self.assertTrue(permitted["matches"])
        self.assertTrue(all(entry["stale_revision"] for entry in permitted["matches"]))

    def test_failed_or_false_success_cannot_become_memory(self):
        bad = copy.deepcopy(self.rows[:1])
        bad[0]["attempts"][0]["checks"][0]["returncode"] = 1
        with self.assertRaisesRegex(ValueError, "No externally verified"):
            build_memory(bad, self.index_path)
        bad[0]["attempts"][0]["checks"][0]["returncode"] = 0
        bad[0]["task"]["prompt"] = "Changed after run"
        with self.assertRaisesRegex(ValueError, "No externally verified"):
            build_memory(bad, self.index_path)
        self.assertFalse(self.index_path.exists())

    def test_repeated_successes_do_not_dominate_search(self):
        repeat = copy.deepcopy(self.rows[0])
        repeat["id"] = "repeat-empty"
        index = build_memory([self.rows[0], repeat], self.index_path)
        self.assertEqual(len(index["entries"]), 1)
        self.assertEqual(set(index["entries"][0]["run_ids"]), {"run-empty", "repeat-empty"})
        with self.assertRaisesRegex(ValueError, "distinct"):
            build_memory([self.rows[0], self.rows[0]], self.root / "duplicate.json")

    def test_optional_handoff_and_context_budget_never_truncate_provenance(self):
        index = build_memory(self.rows[:1], self.index_path, include_handoffs=True)
        result = retrieve(index, self.task, base_commit="commit-a", pack_sha256="pack-a", max_chars=256)
        self.assertEqual(result["context"], "")
        self.assertEqual(result["skipped"]["context_budget"], 1)
        result = retrieve(index, self.task, base_commit="commit-a", pack_sha256="pack-a")
        self.assertIn("PRIVATE_HANDOFF", result["context"])
        with self.assertRaises(FileExistsError):
            build_memory(self.rows, self.index_path)


if __name__ == "__main__":
    unittest.main()
