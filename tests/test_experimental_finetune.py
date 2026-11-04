import copy
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from codex_harness.config import load_policy, load_task, read
from codex_harness.demo import CASES, create
from codex_harness.experimental.finetune import export_dataset, train_lora
from codex_harness.improve import fingerprint
from codex_harness.runner import run, save


class Teacher:
    def __init__(self, name):
        self.name = name

    def run(self, policy, model, workspace, prompt, mcp, timeout, log):
        case = CASES[self.name]
        (workspace / case[4]).write_text(case[1])
        return {"returncode": 0, "reason": None, "completed": True, "message": "Completed scoped repair",
                "events": [], "usage": {"input_tokens": 100, "cached_input_tokens": 0, "output_tokens": 25},
                "cost_usd": .01}


def dependencies():
    calls = {"train": 0, "evaluate": 0, "save": 0, "tokenizer_save": 0}

    class Dataset:
        @staticmethod
        def from_list(rows):
            return copy.deepcopy(rows)

    class Tokenizer:
        eos_token, pad_token = "<EOS>", None

        @classmethod
        def from_pretrained(cls, model, **kwargs):
            calls["tokenizer_load"] = (model, kwargs)
            return cls()

        def __call__(self, text, **kwargs):
            return {"input_ids": list(range(len(text)))}

        def save_pretrained(self, destination):
            calls["tokenizer_save"] += 1
            (Path(destination) / "tokenizer_config.json").write_text("{}")

    class Callback:
        pass

    class Config:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class Trainer:
        def __init__(self, **kwargs):
            calls["trainer_kwargs"] = kwargs

        def train(self):
            calls["train"] += 1
            for step in range(calls["trainer_kwargs"]["args"].max_steps):
                control = SimpleNamespace(should_training_stop=False)
                for callback in calls["trainer_kwargs"]["callbacks"]:
                    callback.on_step_end(None, SimpleNamespace(global_step=step+1), control)
                if control.should_training_stop:
                    break
            return SimpleNamespace(metrics={"train_loss": .5})

        def evaluate(self):
            calls["evaluate"] += 1
            return {"eval_loss": .6}

        def save_model(self, destination):
            calls["save"] += 1
            Path(destination).mkdir(parents=True)
            (Path(destination) / "adapter_config.json").write_text("{}")

    return (Dataset, Tokenizer, Callback, Config, Config, Trainer), calls


class FineTuneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared = tempfile.TemporaryDirectory()
        cls.fixture = create(Path(cls.shared.name) / "fixture")
        policy = load_policy(overrides={"model": "teacher", "max_attempts": 1,
                                        "codex_command": [sys.executable, "-c", "print('offline-teacher')"]})
        cls.verified = []
        for name in CASES:
            row = run(cls.fixture / "repo", load_task(cls.fixture / f"{name}.json"), policy,
                      cls.fixture / "runs", adapter=Teacher(name))
            if row["status"] != "passed":
                raise AssertionError(row)
            cls.verified.append(row)

    @classmethod
    def tearDownClass(cls):
        cls.shared.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.records = [copy.deepcopy(row) for row in self.verified]
        self.dataset = self.root / "dataset"

    def tearDown(self):
        self.temp.cleanup()

    def export(self, records=None, **kwargs):
        return export_dataset(self.records if records is None else records, self.dataset, min_tasks=2, **kwargs)

    def samples(self):
        return [json.loads(line) for name in ("train", "validation")
                for line in (self.dataset / f"{name}.jsonl").read_text().splitlines()]

    def test_export_uses_original_source_revision_and_verified_patch(self):
        manifest = self.export()
        self.assertEqual(sum(manifest["counts"].values()), 3)
        self.assertEqual(self.dataset.stat().st_mode & 0o777, 0o700)
        for row in self.samples():
            record = next(r for r in self.records if r["id"] == row["metadata"]["run_id"])
            case = CASES[record["task_id"]]
            context = json.loads(row["prompt"].split("\n", 1)[1])
            self.assertEqual(context["original_files"], [{"path": case[4], "before": case[0]}])
            self.assertEqual(row["completion"], (Path(record["artifact_directory"]) / "accepted.patch").read_text())
            self.assertIn("+", row["completion"])

    def test_renamed_normalized_prompt_cannot_cross_data_splits(self):
        self.records[1]["task"]["prompt"] = self.records[0]["task"]["prompt"].upper().replace(" ", "   ")
        self.records[1]["task_sha256"] = fingerprint(self.records[1]["task"])
        result = self.export()
        self.assertEqual(sum(result["counts"].values()), 2)
        self.assertEqual(result["rejected"]["duplicate_task"], 1)
        identities = [row["metadata"]["prompt_group"] for row in self.samples()]
        self.assertEqual(len(set(identities)), len(identities))

    def test_identical_solution_under_a_different_prompt_is_deduplicated(self):
        alias = copy.deepcopy(self.records[0])
        alias["id"] = "same-patch-different-task"
        alias["task_id"] = alias["task"]["id"] = "alias"
        alias["task"]["prompt"] = "A separately phrased request for the same mean behavior"
        alias["task_sha256"] = fingerprint(alias["task"])
        result = self.export(self.records + [alias])
        self.assertEqual(sum(result["counts"].values()), 3)
        self.assertEqual(result["rejected"]["duplicate_task"], 1)

    def test_heldout_hashes_are_excluded_before_export(self):
        excluded = self.records[0]["task_sha256"]
        result = self.export(exclude_task_hashes=[excluded])
        self.assertEqual(result["rejected"]["heldout"], 1)
        self.assertNotIn(excluded, [row["metadata"]["task_sha256"] for row in self.samples()])

    def test_invalid_verification_and_changed_accepted_patch_are_excluded(self):
        self.records[0]["attempts"][-1]["checks"][0]["returncode"] = 1
        result = self.export()
        self.assertEqual(result["rejected"]["not_verified"], 1)
        self.dataset = self.root / "tampered-patch-data"
        rows = [copy.deepcopy(row) for row in self.verified]
        copied = self.root / "copied-run"
        shutil.copytree(rows[0]["artifact_directory"], copied)
        rows[0]["artifact_directory"] = str(copied)
        (copied / "accepted.patch").write_text("different patch")
        result = self.export(rows)
        self.assertEqual(result["rejected"]["patch_mismatch_or_empty"], 1)

    def test_incomplete_checks_and_inconsistent_required_review_are_not_verified(self):
        self.records[0]["task"]["checks"].append(["additional-acceptance-check"])
        self.records[0]["task_sha256"] = fingerprint(self.records[0]["task"])
        result = self.export()
        self.assertEqual(result["rejected"]["not_verified"], 1)
        self.dataset = self.root / "bad-review"
        rows = [copy.deepcopy(row) for row in self.verified]
        rows[0]["policy"]["reviewer_model"] = "reviewer"
        rows[0]["attempts"][-1]["review"] = {"verdict": "pass", "findings": ["Still broken"]}
        result = self.export(rows)
        self.assertEqual(result["rejected"]["not_verified"], 1)

    def test_oversized_patch_or_source_is_rejected_instead_of_truncated(self):
        with self.assertRaisesRegex(ValueError, "distinct verified tasks"):
            self.export(max_patch_chars=5)
        self.assertFalse(self.dataset.exists())
        with self.assertRaisesRegex(ValueError, "context_too_large"):
            self.export(max_context_chars=1)
        self.assertFalse(self.dataset.exists())

    def test_changed_dataset_hash_is_rejected_before_loading_training_dependencies(self):
        self.export()
        path = self.dataset / "train.jsonl"
        path.write_text(path.read_text() + "\n")
        with patch("codex_harness.experimental.finetune._dependencies") as deps:
            with self.assertRaisesRegex(ValueError, "changed after export"):
                train_lora(self.dataset, "local-model", self.root / "adapter")
        deps.assert_not_called()
        self.assertFalse((self.root / "adapter").exists())

    def test_duplicate_solution_in_updated_manifest_is_still_rejected(self):
        self.export()
        first = json.loads((self.dataset / "train.jsonl").read_text().splitlines()[0])
        first["metadata"]["prompt_group"] = "different-group"
        path = self.dataset / "validation.jsonl"
        path.write_text(path.read_text() + json.dumps(first) + "\n")
        manifest = read(self.dataset / "dataset.json")
        manifest["files"][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        save(self.dataset / "dataset.json", manifest)
        with patch("codex_harness.experimental.finetune._dependencies") as deps:
            with self.assertRaisesRegex(ValueError, "Duplicate solution"):
                train_lora(self.dataset, "local-model", self.root / "adapter")
        deps.assert_not_called()

    def test_completion_hash_mismatch_is_rejected_even_with_updated_file_manifest(self):
        self.export()
        path = self.dataset / "train.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[0]["completion"] += "not the originally verified patch\n"
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        manifest = read(self.dataset / "dataset.json")
        manifest["files"][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        save(self.dataset / "dataset.json", manifest)
        with patch("codex_harness.experimental.finetune._dependencies") as deps:
            with self.assertRaisesRegex(ValueError, "recorded verified completion"):
                train_lora(self.dataset, "local-model", self.root / "adapter")
        deps.assert_not_called()

    def test_local_sft_wrapper_trains_evaluates_and_saves_adapter_without_hub_upload(self):
        self.export()
        deps, calls = dependencies()
        with patch("codex_harness.experimental.finetune._dependencies", return_value=deps):
            result = train_lora(self.dataset, "local-model", self.root / "training", revision="pinned-revision",
                                max_steps=3, max_length=10_000, use_cpu=True)
        self.assertEqual(result["status"], "trained", result)
        self.assertEqual((calls["train"], calls["evaluate"], calls["save"], calls["tokenizer_save"]), (1, 1, 1, 1))
        self.assertEqual(calls["tokenizer_load"], ("local-model", {"revision": "pinned-revision", "trust_remote_code": False}))
        args = calls["trainer_kwargs"]["args"]
        self.assertEqual(args.max_steps, 3)
        self.assertEqual(args.report_to, "none")
        self.assertFalse(args.push_to_hub)
        self.assertTrue(args.completion_only_loss)
        self.assertFalse(args.packing)
        self.assertEqual(calls["trainer_kwargs"]["peft_config"].target_modules, "all-linear")
        self.assertEqual(calls["trainer_kwargs"]["peft_config"].r, 8)
        self.assertTrue(all(row["completion"].endswith("<EOS>") for row in calls["trainer_kwargs"]["train_dataset"]))
        self.assertIsNone(result["hardware_cost_usd"])
        self.assertEqual(read(self.root / "training" / "training.json")["status"], "trained")

    def test_long_tokenized_example_stops_before_trainer_instead_of_truncating(self):
        self.export()
        deps, calls = dependencies()
        with patch("codex_harness.experimental.finetune._dependencies", return_value=deps):
            result = train_lora(self.dataset, "local-model", self.root / "training", max_length=1)
        self.assertEqual(result["status"], "error")
        self.assertIn("exceeds max_length", result["error"])
        self.assertEqual(calls["train"], 0)
        self.assertNotIn("trainer_kwargs", calls)
        self.assertFalse((self.root / "training" / "adapter").exists())


if __name__ == "__main__":
    unittest.main()
