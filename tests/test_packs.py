import json
import tempfile
import unittest
from pathlib import Path

from codex_harness.config import load_task, read
from codex_harness.improve import register
from codex_harness.packs import create_pack, discover_packs, inspect_pack, resolve_pack, suggest_packs


class PackUsabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()

    def tearDown(self):
        self.temp.cleanup()

    def test_bundled_inspection_exposes_tools_without_server_secrets(self):
        details = inspect_pack("frontend")
        self.assertEqual(details["mcp_servers"], ["playwright"])
        self.assertIn("browser-verify", details["skills"])
        self.assertEqual(details["source"], "bundled")
        self.assertNotIn("args", json.dumps(details))

    def test_discovery_lists_custom_packs_and_active_registry(self):
        packs = self.root / "packs"
        packs.mkdir()
        created = create_pack("backend", packs / "service-api", task="Fix pagination in the Python API")
        registry = self.root / "registry"
        active = register(Path(created["path"]), registry)
        found = discover_packs([packs, registry])
        self.assertEqual({row["name"] for row in found}, {"backend", "frontend", "issue-to-patch", "service-api"})
        releases = [row for row in found if row["source"] == "registry"]
        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0]["path"], str(active))
        self.assertEqual(releases[0]["selector"], str(registry))
        self.assertEqual(resolve_pack(registry), active)

    def test_invalid_registry_is_reported_without_hiding_valid_packs(self):
        registry = self.root / "broken"
        registry.mkdir()
        (registry / "active.json").write_text('{"current":"../../elsewhere"}')
        found = discover_packs([self.root])
        self.assertEqual(len([row for row in found if row["available"]]), 3)
        invalid = next(row for row in found if row["name"] == "broken")
        self.assertFalse(invalid["available"])
        self.assertIn("identifier", invalid["error"])

    def test_registry_cannot_escape_via_symlink(self):
        custom = self.root / "custom"
        create_pack("backend", custom)
        registry = self.root / "registry"
        (registry / "releases").mkdir(parents=True)
        release = "release-" + "a" * 16
        (registry / "releases" / release).symlink_to(custom, target_is_directory=True)
        (registry / "active.json").write_text(json.dumps({"current": release}))
        with self.assertRaisesRegex(ValueError, "inside"):
            resolve_pack(registry)

    def test_suggest_uses_task_and_actual_manifest_evidence(self):
        repo = self.root / "repo"
        repo.mkdir()
        (repo / "package.json").write_text(json.dumps({"dependencies": {"react": "1"}}))
        recommendation = suggest_packs("Fix the page loading UI", repo=repo)
        self.assertEqual(recommendation["recommended_pack"], "frontend")
        self.assertIn("react", " ".join(recommendation["suggestions"][0]["reasons"]))
        self.assertIn("not measured accuracy", recommendation["method"])
        self.assertFalse(recommendation["create_recommended"])

    def test_local_family_pack_is_suggested_for_reuse(self):
        pack = self.root / "service-api"
        create_pack("backend", pack, task="Fix the Python API")
        recommendation = suggest_packs("Fix the Python API", roots=[pack])
        self.assertEqual(recommendation["recommended_pack"], str(pack))
        self.assertIn("local pack", recommendation["creation_reason"])

    def test_uncertain_task_suggests_creation_without_guessing_template(self):
        recommendation = suggest_packs("Improve the compiler register allocation")
        self.assertIsNone(recommendation["recommended_pack"])
        self.assertTrue(recommendation["create_recommended"])

    def test_repeated_task_failures_suggest_experiment_not_infrastructure_learning(self):
        task = {"id": "page-bug", "prompt": "Fix React page"}
        infra = [{"task_id": "page-bug", "status": "infrastructure_error"}] * 3
        self.assertFalse(suggest_packs(task, records=infra)["create_recommended"])
        failures = [{"task_id": "page-bug", "status": "failed"}] * 2
        recommendation = suggest_packs(task, records=failures)
        self.assertTrue(recommendation["create_recommended"])
        self.assertEqual(recommendation["matching_result_statuses"], {"failed": 2})
        self.assertIn("experiment", recommendation["creation_reason"])
        unrelated = [{"task_id": "different", "status": "failed"}] * 2
        self.assertFalse(suggest_packs(task, records=unrelated)["create_recommended"])

    def test_created_pack_preserves_skills_and_requires_explicit_checks(self):
        destination = self.root / "custom-ui"
        metadata = create_pack("frontend", destination, task="Improve empty state")
        self.assertTrue(metadata["needs_checks"])
        self.assertTrue((destination / "skills" / "browser-verify" / "SKILL.md").is_file())
        self.assertTrue((destination / "mcp.toml").is_file())
        self.assertNotIn("checks", read(destination / "pack.toml")["task"])
        with self.assertRaisesRegex(ValueError, "check is required"):
            load_task(destination / "task.example.json", destination)
        self.assertNotIn("Improve empty state", (destination / "instructions.md").read_text())

    def test_creation_copies_user_checks_and_can_run_task_loader(self):
        destination = self.root / "custom-api"
        task = {"id": "api-contract", "prompt": "Fix the API contract", "checks": [["python", "check.py"]]}
        metadata = create_pack("backend", destination, task=task)
        self.assertFalse(metadata["needs_checks"])
        loaded = load_task(destination / "task.example.json", destination)
        self.assertEqual(loaded["checks"], task["checks"])

    def test_invalid_creation_does_not_leave_partial_pack(self):
        destination = self.root / "custom"
        with self.assertRaisesRegex(ValueError, "argv"):
            create_pack("backend", destination, task={"prompt": "Fix API", "checks": ["pytest"]})
        self.assertFalse(destination.exists())
        source = resolve_pack("backend")
        with self.assertRaisesRegex(ValueError, "outside"):
            create_pack(source, source / "nested")


if __name__ == "__main__":
    unittest.main()
