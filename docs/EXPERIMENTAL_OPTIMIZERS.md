# Experimental ACE and upstream GEPA

Both workflows generate **candidates**, not active releases. They reuse Codex authentication and the existing clean-clone verifier. Every paid stage is recorded. Token/dollar limits are checked between stages and can overshoot within a stage. Neither workflow changes model weights, acceptance tests, MCP configuration or model policy.

## ACE: structured evolving playbooks

[ACE](https://arxiv.org/html/2510.04618v1) separates generation, reflection and curation, using incremental bullet updates to preserve useful context. Its benchmark results depend on reliable feedback and domain; blindly accumulating advice can hurt. SuperCodex provides a **local ACE variant**, not the authors' exact experimental reproduction. The distinction is explicit: generator trajectories come from existing SuperCodex runs; deduplication and retrieval use lexical overlap rather than semantic embeddings.

The implemented cycle is:

1. Validate development-record task/pack fingerprints and reject infrastructure outcomes.
2. Give generator outcomes to a separate read-only reflector. It returns reusable insights and evidence-linked helpful/harmful feedback on existing bullet IDs.
3. Give the reflection to a separate read-only curator. It proposes bounded add/update/remove operations. Existing unrelated bullets remain intact.
4. Apply operations deterministically. Preserve stable IDs and provenance, deduplicate overlapping bullets, rank by feedback, and prune to bullet/context budgets. One run cannot vote repeatedly for the same bullet.
5. Render the playbook into a new pack and write `proposal.json`. The original instructions remain the base. Evaluate the candidate on untouched tasks before promotion.

CLI, using real development results created with the source pack:

```bash
super-codex experimental ace .harness/packs/api \
  --from-runs .harness/development-runs --repo /path/to/development-repo \
  --output .harness/experiments/ace-001 --config balanced \
  --model gpt-6.1-sol --rounds 1 --max-calls 4 --max-total-tokens 120000

# Optional selective retrieval instead of injecting the entire rendered playbook:
super-codex experimental run task.json --repo /path/to/repo \
  --pack .harness/packs/api \
  --ace-playbook .harness/experiments/ace-001/playbook.json \
  --output .harness/runs/ace-assisted
```

Equivalent Python API:

```python
from pathlib import Path
from codex_harness.config import load_policy, read
from codex_harness.experimental.ace import ace_update, ace_context

pack = Path(".harness/packs/api")
result = ace_update(
    pack, [read(".harness/runs/DEV_RUN/result.json")],
    "/path/to/development-repo", ".harness/experiments/ace-001",
    policy=load_policy("balanced", pack), model="gpt-6.1-sol",
    max_tokens=120_000, max_calls=4, rounds=1,
    max_bullets=30, max_context_chars=4_000,
)
print(result["status"], result["accounting"])

# Relevant bounded memory can also be inspected separately.
if result["status"] == "candidate_requires_holdout_evaluation":
    selected = ace_context(
        Path(result["candidate"]) / "ace-playbook.json",
        "Fix cursor pagination", max_chars=2_000,
    )
    print(selected)
```

The normal candidate contains its bounded rendered playbook, so using `run --pack CANDIDATE` needs no extra hook. `ace_context` provides selective retrieval for separate experiments. Its counters record model-attributed usefulness, not verified causal effects or calibrated confidence. An improved pack still must pass the independent quality/cost gate. Keep the original development records, and rotate holdouts after observing their results.

For the next ACE cycle, use the previous candidate or its promoted release as the source pack. Its stored playbook must reconstruct those exact source instructions; an unrelated playbook cannot replace the original guidance. Development task hashes and normalized prompt hashes accumulate across cycles. Selective retrieval rejects a playbook learned from the current prompt, including case/whitespace-renamed copies, or from any task in `run --exclude-suite`. Python callers can supply `exclude_task_hashes` and `exclude_prompt_hashes` to `ace_context`. Legacy or hand-authored playbooks without learning metadata cannot provide this provenance check; regenerate learned playbooks from retained evidence.

## GEPA: the real upstream search engine

SuperCodex calls **`gepa.optimize` from the optional upstream package**, tested with `gepa==0.1.4`. It enables the upstream Pareto candidate selector, reflective mutation and merge proposals. A custom adapter evaluates each instruction candidate through the existing Codex runner and executable acceptance checks. The reflection model is a Codex read-only session; LiteLLM or a second API credential is not required.

API references were verified against [upstream `api.py`](https://github.com/gepa-ai/gepa/blob/main/src/gepa/api.py), [the adapter protocol](https://github.com/gepa-ai/gepa/blob/main/src/gepa/core/adapter.py) and the installed 0.1.4 package. The implementation uses the genuine search engine; benchmark scores from the [GEPA paper](https://arxiv.org/abs/2507.19457) are not claimed for this integration.

Install the optional dependency:

```bash
python -m pip install 'super-codex-harness[gepa]'
# From a checkout: python -m pip install '.[gepa]'
```

Create separate `train.json`, `validation.json` and optional `holdout.json` files. Each contains a nonempty `tasks` array only; GEPA manages sampling, so these files do not contain `variants` or `repeat`:

```json
{
  "tasks": [
    {"repo": "/path/to/repo", "task": "tasks/unique-task.json", "revision": "HEAD"}
  ]
}
```

Paths resolve relative to each suite file, and revisions are frozen before the experiment. Use distinct real tasks in each split. The program rejects identical or case/whitespace-renamed prompts across splits; semantic duplication still requires curation. Keep held-out tasks/solutions out of repositories the reflection model can inspect.

```bash
super-codex experimental gepa .harness/packs/api \
  --train-suite train.json --validation-suite validation.json \
  --holdout-suite holdout.json --repo /path/to/development-repo \
  --output .harness/experiments/gepa-001 --config balanced \
  --reflection-model gpt-6.1-sol --max-metric-calls 20 \
  --max-reflection-calls 8 --max-total-tokens 1000000 --timeout-seconds 3600
```

Equivalent Python API:

```python
from pathlib import Path
from codex_harness.config import load_policy
from codex_harness.experimental.gepa import optimize_pack

pack = Path(".harness/packs/api")
result = optimize_pack(
    pack, "train.json", "validation.json",
    "/path/to/development-repo", ".harness/experiments/gepa-001",
    policy=load_policy("balanced", pack), reflection_model="gpt-6.1-sol",
    holdout_suite="holdout.json",  # checked for overlap, never executed or supplied to GEPA
    max_metric_calls=20, max_reflection_calls=8,
    max_tokens=1_000_000, timeout=3_600, seed=42,
)
print(result["status"], result["accounting"])
```

The metric is verified pass/fail. Costs remain fully recorded; the independent promotion gate decides whether a quality improvement is worth its cost. Search validation scores are **development feedback**, so they are not unbiased test accuracy. Both train and validation identities are written to the candidate's `development_task_hashes` and `development_prompt_hashes`, together with inherited development history; neither split can later pass as a fresh promotion holdout. The optional holdout suite is checked for overlap, including historical prompt identities, but its records never enter GEPA's evaluator or reflection prompt.

Metric calls and reflection calls have separate caps. A strict cap can stop a GEPA batch before it starts; a stopped experiment reports that status without presenting an unfinished selection as an approved candidate. Unknown usage and infrastructure failures stop search. Audit files retain every completed rollout and failed/reflection spending. The source pack and active registry are unchanged.

## Evaluate and promote

For either method, run the original pack and final candidate on a new holdout suite with matching policy, tools, commits, checks, environment and repetition counts. Use the [manual comparison and promotion workflow](TASK_PACKS.md#manual-proposal-and-promotion). Register the original baseline before promotion. The existing gate checks exact source/candidate hashes, no development overlap, no per-task regression, a quality floor, and a cost/quality improvement. These experimental generators do not manage the normal optimizer's consumed-holdout history; curate cross-experiment reuse yourself.

Use a new output directory outside the source pack and outside target repositories unless explicitly Git-ignored. Keep raw artifacts private until reviewed: prompts, code, command logs and development examples can contain sensitive material.

## What was verified

Offline tests cover ACE feedback/provenance, incremental curation, duplicate-vote prevention, lexical retrieval, pruning, invalid outputs and budget stops. GEPA contract tests exercise the adapter and split separation. An optional test uses the real 0.1.4 engine with offline fake rollouts: it invokes reflection, evaluates a new candidate and updates its Pareto frontier. This proves integration behavior, not live model-quality gains. The optional test is skipped when GEPA is absent.
