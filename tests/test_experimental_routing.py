import copy
import tempfile
import unittest
from pathlib import Path

from codex_harness.experimental.routing import route, train_router
from codex_harness.improve import fingerprint


def data():
    rows = []
    for easy in (True, False):
        for index in range(4):
            name = f"{'easy' if easy else 'hard'}-{index}"
            prompt = ("Routine formatting whitespace cleanup" if easy else "Complex concurrency deadlock transaction isolation")
            prompt += f" distinctive_{name.replace('-', '_')}"
            task = {"id": name, "prompt": prompt, "checks": [["python", "-m", "unittest"]]}
            for model in ("cheap", "strong"):
                passed = easy or model == "strong"
                rows.append({"id": f"run-{name}-{model}", "task_id": name, "task": task,
                             "task_sha256": fingerprint(task), "policy": {"model": model, "max_attempts": 1},
                             "base_commit": "commit-a", "pack_sha256": "pack-a", "context_sha256": "context-a",
                             "mcp_sha256": "tools-a", "codex_version": "codex-test-1", "platform": "test-os", "python": "3.11",
                             "status": "passed" if passed else "failed", "cost_usd": 1 if model == "cheap" else 4,
                             "tokens": 100 if model == "cheap" else 200,
                             "attempts": [{"model": model, "passed": passed,
                                           "checks": [{"returncode": 0 if passed else 1, "reason": None}]}]})
    return rows


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "router.json"
        self.rows = data()

    def tearDown(self):
        self.temp.cleanup()

    def train(self, rows=None, **kwargs):
        return train_router(self.rows if rows is None else rows, self.path,
                            cheap_model="cheap", strong_model="strong", **kwargs)

    def test_fit_learns_different_model_choices_and_reports_holdout_costs(self):
        router = self.train()
        easy = route(self.path, {"prompt": "Routine formatting whitespace cleanup new module"})
        hard = route(router, {"prompt": "Complex concurrency deadlock transaction isolation issue"})
        self.assertEqual(easy["model"], "cheap")
        self.assertEqual(hard["model"], "strong")
        self.assertGreater(easy["score"], hard["score"])
        self.assertTrue(any(abs(weight) > .1 for weight in router["weights"]))
        comparison = router["validation"]["comparisons"]
        self.assertEqual(comparison["router"]["mean_success"], 1)
        self.assertLess(comparison["router"]["total_mean_cost"], comparison["always_strong"]["total_mean_cost"])
        self.assertEqual(comparison["always_cheap"]["mean_success"], .5)
        self.assertEqual(router["source_data_accounting"]["total_cost"], 40)
        self.assertFalse(set(router["training_run_ids"]) & set(router["validation_run_ids"]))

    def test_prompt_groups_do_not_leak_across_train_and_validation(self):
        duplicate_pair = [copy.deepcopy(row) for row in self.rows[:2]]
        for row in duplicate_pair:
            row["id"] += "-renamed"
            row["task"]["id"] += "-renamed"
            row["task"]["prompt"] = "  " + row["task"]["prompt"].upper().replace(" ", "   ")
            row["task_sha256"] = fingerprint(row["task"])
        router = self.train(self.rows + duplicate_pair)
        self.assertFalse(set(router["training_prompt_hashes"]) & set(router["validation_prompt_hashes"]))
        original_hash = self.rows[0]["task_sha256"]
        renamed_hash = duplicate_pair[0]["task_sha256"]
        self.assertEqual(original_hash in router["training_task_hashes"], renamed_hash in router["training_task_hashes"])
        for row in self.rows:
            if row["task_sha256"] in router["validation_task_hashes"]:
                marker = row["task"]["prompt"].split()[-1]
                self.assertNotIn(marker, router["vocabulary"])

    def test_unknown_vocabulary_and_changed_context_fall_back(self):
        router = self.train()
        absent = route(router, {"prompt": "zebra lunar geology"})
        self.assertEqual(absent["model"], "strong")
        self.assertEqual(absent["similarity"], 0)
        changed = route(router, {"prompt": "Routine formatting whitespace cleanup"}, expected_context={"base_commit": "new"})
        self.assertEqual(changed["model"], "strong")
        self.assertTrue(changed["context_checked"])
        matched = route(router, {"prompt": "Routine formatting whitespace cleanup"}, expected_context={"base_commit": "commit-a", "pack_sha256": "pack-a"})
        self.assertEqual(matched["model"], "cheap")
        with self.assertRaisesRegex(ValueError, "known nonempty"):
            route(router, {"prompt": "routine formatting"}, expected_context={"unrecognized": None})

    def test_unmatched_settings_and_repeated_record_ids_are_rejected(self):
        self.rows[0]["mcp_sha256"] = "different-tools"
        with self.assertRaisesRegex(ValueError, "matched"):
            self.train()
        self.rows = data()
        with self.assertRaisesRegex(ValueError, "distinct"):
            self.train(self.rows + [self.rows[0]])
        self.assertFalse(self.path.exists())

    def test_discovery_context_is_matched_in_training_and_prediction(self):
        for row in self.rows:
            row["agent_cli_context_sha256"] = "cli-context-a"
        self.rows[0]["agent_cli_context_sha256"] = "cli-context-b"
        with self.assertRaisesRegex(ValueError, "matched"):
            self.train()
        self.rows[0]["agent_cli_context_sha256"] = "cli-context-a"
        router = self.train()
        task = {"prompt": "Routine formatting whitespace cleanup"}
        self.assertEqual(route(router, task, expected_context={"agent_cli_context_sha256": "cli-context-a"})["model"], "cheap")
        self.assertEqual(route(router, task, expected_context={"agent_cli_context_sha256": "cli-context-b"})["model"], "strong")
        for context in router["contexts"]:
            context.pop("agent_cli_context_sha256")
        self.assertEqual(route(router, task, expected_context={"agent_cli_context_sha256": "cli-context-a"})["model"], "strong")

    def test_mixed_models_and_unknown_cost_are_rejected(self):
        self.rows[0]["policy"]["planner_model"] = "strong"
        with self.assertRaisesRegex(ValueError, "single-model"):
            self.train()
        self.rows = data()
        self.rows[0]["cost_usd"] = None
        with self.assertRaisesRegex(ValueError, "known finite"):
            self.train()
        router = self.train(cost_metric="tokens")
        self.assertEqual(router["cost_metric"], "tokens")

    def test_infrastructure_failure_excludes_entire_paired_task(self):
        self.rows[0]["status"] = "verification_error"
        router = self.train(min_tasks=4)
        self.assertEqual(router["excluded_records"]["unusable_quality_outcome"], 1)
        self.assertEqual(router["excluded_records"]["paired_task_has_unusable_outcome"], 1)
        self.assertNotIn(self.rows[0]["task_sha256"], router["training_task_hashes"] + router["validation_task_hashes"])

    def test_training_requires_diversity_and_both_outcome_classes(self):
        with self.assertRaisesRegex(ValueError, "distinct matched"):
            self.train(self.rows[:4])
        for row in self.rows:
            row["status"] = "passed"
            row["attempts"][0]["passed"] = True
            row["attempts"][0]["checks"][0]["returncode"] = 0
        with self.assertRaisesRegex(ValueError, "each outcome class"):
            self.train()

    def test_artifact_cannot_be_overwritten_and_invalid_weights_rejected(self):
        router = self.train()
        with self.assertRaises(FileExistsError):
            self.train()
        router["weights"][0] = float("nan")
        with self.assertRaisesRegex(ValueError, "Malformed"):
            route(router, {"prompt": "routine formatting"})


if __name__ == "__main__":
    unittest.main()
