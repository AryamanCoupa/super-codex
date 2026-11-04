# Measure accuracy, cost and reliability

Optimize success subject to your real constraints. A cheaper failed patch is not a saving. The default comparison is **total spending across all runs / successful runs**; if no run succeeds, this is undefined. Missing prices remain unknown.

## Suite format

All paths resolve relative to the suite JSON. Policies are merged over the defaults and the variant's pack policy:

```json
{
  "repeat": 5,
  "seed": 42,
  "tasks": [
    {"repo": "../target", "task": "tasks/pagination.json", "revision": "COMMIT_SHA"},
    {"repo": "../target", "task": "tasks/validation.json", "revision": "COMMIT_SHA"}
  ],
  "variants": [
    {"name": "cheap-single", "pack": "../packs/api", "policy": {"max_attempts": 1}},
    {"name": "cheap-repair", "pack": "../packs/api", "policy": {"max_attempts": 3}},
    {"name": "architect", "pack": "../packs/api", "policy": {"planner_model": "gpt-6.1-sol", "max_attempts": 3}},
    {"name": "strong-baseline", "pack": "../packs/api", "policy": {"model": "gpt-6.1-sol", "max_attempts": 1}}
  ]
}
```

Freeze commits before running. Each trial gets a fresh clone; variants are interleaved in seeded order to reduce ordering effects. Within a trial, repairs share the candidate workspace and get fresh Codex sessions with compact feedback. This is not independent candidate sampling. The CLI enforces `--max-runs` (default 100) against the planned suite size; each run has its own budgets. There is no single hard suite-wide dollar cap.

## Dataset design

Start with real issues you understand and independent checks you trust. Cover the task families you actually perform: regression repair, a feature with precise acceptance criteria, cross-file behavior, a browser interaction, and a difficult reasoning case if relevant. Include meaningful edge cases. Reserve tasks before tuning. The generated mean/slug/chunks fixtures are diagnostic examples, not human-validated representative quality evidence.

Keep a development set for instruction changes, a holdout set for promotion, and an audit set for repeated optimization. Protect against semantic duplicates and remembered patches, not just duplicate IDs. The built-in gate blocks exact task-hash overlap and normalized prompt overlap when development provenance is available; it cannot detect all contamination. Add hidden checks in a genuinely isolated external grader if you need a credible public benchmark.

`pack optimize` additionally detects normalized prompt overlap and records consumed holdout prompts in its registry. It requires at least three distinct prompts by default, because ten repetitions of one task do not provide diversity. Manual `eval`/`promote` calls do not manage this history; maintain separate datasets yourself. See [the dedicated-pack workflow](TASK_PACKS.md).

## Verify the verifier

Run a known incorrect implementation against the checks and confirm it fails for the expected reason. Cover boundary behavior and meaningful invariants; consider property-based, differential or mutation checks where the repository supports them. Review generated assertions and reference implementations independently. Stronger inputs exposed false positives in [EvalPlus](https://arxiv.org/html/2305.01210v1); simply increasing sample count against inadequate tests does not establish correctness.

Automatic pack proposals cannot change checks or model policy. Keep test-quality improvements separate so that before/after scores still measure the same task contract.

## Metrics and their interpretation

- `pass_rate`: fraction of complete trials passing all configured checks and required review.
- `first_attempt_successes`: successes before external repair. One Codex attempt may itself involve many internal model/tool turns.
- `cost_per_success_usd`: total estimated cost, including failed trials, divided by successes.
- `mean_tokens`: input plus output across implementation and advisor stages; cached input is already part of input and is not counted twice.
- `mean_seconds`: end-to-end run time including setup and verification.
- `statuses`: distinguish test failure, stall, budget exhaustion, timeout, integrity rejection, model/CLI failure, and infrastructure problems.
- `wilson_95_interval`: descriptive binomial interval. Heterogeneous or repeated tasks violate simple independence assumptions; use task-cluster bootstrap or paired analysis for formal public claims.

Reports do not call sequential repairs `pass@k`, do not discard expensive failed runs, and do not treat unknown costs as zero. A reviewer passing a patch is an extra signal, not proof of correctness. Inspect results manually for requirements that tests do not encode.

## Price configuration

Add your current rates to a private policy:

```toml
max_cost_usd = 2.0
[prices."YOUR_MODEL_ID"]
input = 1.0
cached_input = 0.1
output = 4.0
```

These numbers are **illustrative, not current model prices**. Provide rates for all selected implementation, planner, escalation and reviewer models when using a dollar budget. The simple estimate is `(uncached_input × input_rate + cached_input × cached_rate + output × output_rate) / 1,000,000`. It omits separate cache-write/tool/provider charges and subscription credit rules. Use provider billing records for financial reconciliation.

Budgets are checked before each new model stage. A long Codex turn can overshoot; `budget_overrun` records observed excess. Terminating a local process cannot guarantee remote inference has already stopped billing. Use provider-side controls where hard financial limits matter.

## Ablation sequence

Measure a strong baseline and cheap baseline first. Then add exactly one change: a task pack, repair, escalation, planning, or review. For pack promotion, keep the model policy fixed so attribution is meaningful. Compare on untouched tasks, include tuning expenses, and keep only changes with useful measured quality/cost behavior. Prefer a simpler workflow when performance is indistinguishable.

The [experimental commands](EXPERIMENTS.md) extend this sequence to sampling, specialists, learned routing, memory, ACE/GEPA, recursion and local training. Run these commands explicitly; the ordinary `eval` suite does not dispatch experimental workflows. Its per-run report format does not automatically aggregate specialist/optimizer/training overhead, so use each experiment's audit totals as well. A best-of-N success is one experiment outcome, not N independent user-task successes. Router validation is retrospective and uncalibrated; GEPA validation guides search and therefore is development data. Fine-tuning validation loss requires a separate downstream coding evaluation. Keep external advice identical in paired pack comparisons, and reserve new tasks for final claims.
