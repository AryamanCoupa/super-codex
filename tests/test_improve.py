import copy
import json
import tempfile
import unittest
from pathlib import Path

from codex_harness.cli import pack_path
from codex_harness.config import load_policy
from codex_harness.demo import create
from codex_harness.improve import copy_pack, fingerprint, pack_digest, promote, promotion_gate, propose, register, rollback
from codex_harness.runner import save


class Proposer:
    def advise(self, *args):
        return {"returncode": 0, "reason": None, "completed": True,
                "message": json.dumps({"operation": "append", "old": "", "new": "For pagination defects, check empty pages and the final partial page against the endpoint contract.",
                                       "rationale": "The development case failed on a pagination boundary."}),
                "usage": {"input_tokens": 100, "cached_input_tokens": 0, "output_tokens": 30}, "cost_usd": .01}


class ImprovementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = copy_pack(pack_path("backend"), self.root / "base")
        self.candidate = copy_pack(self.source, self.root / "candidate")
        (self.candidate / "instructions.md").write_text("Check the endpoint's empty-page contract.\n")
        self.proposal = {"source_pack_sha256": pack_digest(self.source), "candidate_pack_sha256": pack_digest(self.candidate),
                         "development_task_hashes": ["development"]}
        save(self.candidate / "proposal.json", self.proposal)
        row = {"task_sha256": "holdout", "base_commit": "abc", "policy": {"model": "small"},
               "status": "passed", "cost_usd": 1.0, "tokens": 100, "mcp_sha256": "tools",
               "codex_version": "test codex 1", "platform": "test platform", "python": "3.11"}
        self.baseline = [dict(row, id=f"baseline-{i}", pack_sha256=pack_digest(self.source)) for i in range(10)]
        self.trials = [dict(row, id=f"candidate-{i}", pack_sha256=pack_digest(self.candidate), cost_usd=.8) for i in range(10)]

    def tearDown(self):
        self.temp.cleanup()

    def test_lower_cost_promotes_and_first_promotion_rolls_back(self):
        registry = self.root / "registry"
        original = register(self.source, registry)
        release = promote(self.candidate, registry, self.baseline, self.trials)
        self.assertEqual(pack_path(str(registry)), release)
        self.assertEqual(pack_digest(release), pack_digest(self.candidate))
        self.assertEqual(rollback(registry), original)
        self.assertEqual(pack_path(str(registry)), original)

    def test_quality_gain_can_spend_more_when_explicit(self):
        self.baseline[0]["status"] = "failed"
        for row in self.trials:
            row["cost_usd"] = 1.2
        with self.assertRaisesRegex(ValueError, "cost ratio"):
            promotion_gate(self.candidate, self.baseline, self.trials)
        result = promotion_gate(self.candidate, self.baseline, self.trials, max_cost_ratio=1.3)
        self.assertEqual(result["candidate_successes"], 10)

    def test_regression_is_rejected_even_when_cheaper(self):
        self.trials[0]["status"] = "failed"
        with self.assertRaisesRegex(ValueError, "regresses"):
            promotion_gate(self.candidate, self.baseline, self.trials)

    def test_holdout_leakage_is_rejected(self):
        self.proposal["development_task_hashes"] = ["holdout"]
        save(self.candidate / "proposal.json", self.proposal)
        with self.assertRaisesRegex(ValueError, "overlaps"):
            promotion_gate(self.candidate, self.baseline, self.trials)

    def test_renamed_development_prompt_cannot_be_a_promotion_holdout(self):
        self.proposal["development_prompt_hashes"] = [fingerprint("previous training task")]
        save(self.candidate / "proposal.json", self.proposal)
        for row in self.trials:
            row["task"] = {"prompt": " PREVIOUS   training TASK "}
        with self.assertRaisesRegex(ValueError, "normalized development"):
            promotion_gate(self.candidate, self.baseline, self.trials)

    def test_external_advice_must_match_between_promotion_variants(self):
        self.trials[0]["extra_context_sha256"] = "unmatched external advice"
        with self.assertRaisesRegex(ValueError, "matching"):
            promotion_gate(self.candidate, self.baseline, self.trials)

    def test_cli_discovery_context_must_match_and_cannot_mix_with_legacy_trials(self):
        for row in self.trials:
            row["agent_cli_context_sha256"] = "cli-context-a"
        with self.assertRaisesRegex(ValueError, "matching"):
            promotion_gate(self.candidate, self.baseline, self.trials)
        for row in self.baseline:
            row["agent_cli_context_sha256"] = "cli-context-a"
        promotion_gate(self.candidate, self.baseline, self.trials)
        self.trials[0]["agent_cli_context_sha256"] = "cli-context-b"
        with self.assertRaisesRegex(ValueError, "matching"):
            promotion_gate(self.candidate, self.baseline, self.trials)

    def test_changed_candidate_is_rejected(self):
        (self.candidate / "instructions.md").write_text("Another change")
        with self.assertRaisesRegex(ValueError, "changed after"):
            promotion_gate(self.candidate, self.baseline, self.trials)

    def test_unknown_price_and_infrastructure_fail_closed(self):
        self.trials[0]["cost_usd"] = None
        with self.assertRaisesRegex(ValueError, "Missing measured cost"):
            promotion_gate(self.candidate, self.baseline, self.trials)
        self.trials[0]["status"] = "infrastructure_error"
        with self.assertRaisesRegex(ValueError, "infrastructure"):
            promotion_gate(self.candidate, self.baseline, self.trials, metric="tokens")

    def test_repetition_and_policy_must_match(self):
        with self.assertRaisesRegex(ValueError, "at least"):
            promotion_gate(self.candidate, self.baseline, self.trials[:1])
        self.trials[0]["policy"] = {"model": "other"}
        with self.assertRaisesRegex(ValueError, "matching"):
            promotion_gate(self.candidate, self.baseline, self.trials)

    def test_no_improvement_is_rejected(self):
        for row in self.trials:
            row["cost_usd"] = 1.0
        with self.assertRaisesRegex(ValueError, "No observed improvement"):
            promotion_gate(self.candidate, self.baseline, self.trials)

    def test_quality_floor_and_finite_limits(self):
        for row in self.baseline + self.trials:
            row["status"] = "failed"
        with self.assertRaisesRegex(ValueError, "minimum"):
            promotion_gate(self.candidate, self.baseline, self.trials)
        with self.assertRaisesRegex(ValueError, "Positive"):
            promotion_gate(self.candidate, self.baseline, self.trials, max_cost_ratio=float("nan"))

    def test_registry_cannot_be_nested_inside_pack(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            register(self.source, self.source / "registry")

    def test_comparison_rejects_changed_environment_and_missing_metadata(self):
        for field in ("mcp_sha256", "codex_version", "platform", "python"):
            trials = copy.deepcopy(self.trials)
            trials[0][field] = "different"
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "matching"):
                promotion_gate(self.candidate, self.baseline, trials)
        self.trials[0].pop("codex_version")
        with self.assertRaisesRegex(ValueError, "metadata"):
            promotion_gate(self.candidate, self.baseline, self.trials)

    def test_verifier_errors_are_not_quality_failures(self):
        self.baseline[0]["status"] = "verification_error"
        with self.assertRaisesRegex(ValueError, "infrastructure"):
            promotion_gate(self.candidate, self.baseline, self.trials)

    def test_duplicate_trials_are_not_independent_runs(self):
        self.trials[1] = dict(self.trials[0])
        with self.assertRaisesRegex(ValueError, "distinct"):
            promotion_gate(self.candidate, self.baseline, self.trials)

    def test_promotion_requires_registered_matching_baseline(self):
        registry = self.root / "registry"
        with self.assertRaisesRegex(ValueError, "Register"):
            promote(self.candidate, registry, self.baseline, self.trials)
        unrelated = copy_pack(self.source, self.root / "unrelated")
        (unrelated / "instructions.md").write_text("Different task family")
        register(unrelated, registry)
        before = (registry / "active.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "source baseline"):
            promote(self.candidate, registry, self.baseline, self.trials)
        self.assertEqual((registry / "active.json").read_bytes(), before)

    def test_model_proposal_changes_only_candidate_instructions(self):
        fixture = create(self.root / "fixture")
        dest = self.root / "proposal"
        before = pack_digest(self.source)
        evidence = {"task_id": "development", "task_sha256": "development", "status": "failed", "attempts": [], "task": {}}
        result = propose(self.source, dest, [evidence], fixture / "repo", load_policy(), "strong", adapter=Proposer())
        self.assertEqual(pack_digest(self.source), before)
        self.assertEqual(result["source_pack_sha256"], before)
        self.assertEqual((dest / "pack.toml").read_bytes(), (self.source / "pack.toml").read_bytes())
        self.assertIn("pagination", (dest / "instructions.md").read_text())
        self.assertEqual(result["usage"]["output_tokens"], 30)


if __name__ == "__main__":
    unittest.main()
