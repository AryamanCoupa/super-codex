# Experimental independent candidates and specialist teams

These workflows are opt-in experiments. Both preserve the ordinary runner's protected checks and clean-clone verification. Their extra calls are included in experiment accounting. Neither workflow automatically applies patches to your checkout or merges independently generated patches.

The rationale is conditional: [multi-agent research](https://www.anthropic.com/research/multi-agent-research-system) supports parallel exploration when subtasks can be separated, while emphasizing coordination/token overhead and the difficulty of tightly coupled coding. [Test-time compute research](https://arxiv.org/html/2408.03314v1) motivates adaptive computation, but its mathematical reasoning results do not establish the benefit of independent coding candidates. Measure these workflows against the ordinary runner on your own tasks.

## Independent candidates: best-of-N

`best_of_n` starts N independent runner trials from the same frozen Git commit, task, pack, base policy and MCP configuration. Each trial has its own worker and verifier clones. Remaining shared wall time can shorten a later trial's timeouts, which are recorded in its effective policy. Policy-controlled repairs may happen inside a trial. Candidates run in batches of at most `concurrency`; defaults are three candidates and two concurrent trials. Caps are sixteen candidates and four concurrent trials.

```bash
super-codex experimental best-of-n task.json --repo /path/to/repo \
  --pack backend --config balanced --candidates 3 --concurrency 2 \
  --selection-metric tokens --max-total-tokens 500000 \
  --output /path/outside/repo/experiment-001
```

Only results passing the configured checks and any required review can be selected. The selector chooses the passing result with the lowest measured token usage or estimated dollar cost, using candidate order to break ties. It never uses majority voting, a model's self-confidence or test pass counts to accept a failed patch. All unsuccessful candidates remain in the experiment cost.

Python API example, using an existing task and clean repository:

```python
from codex_harness.config import load_policy, load_task
from codex_harness.experimental.parallel import best_of_n
from codex_harness.packs import resolve_pack

pack = resolve_pack("backend")
result = best_of_n(
    "/path/to/repo", load_task("task.json", pack),
    load_policy("balanced", pack), "/path/outside/repo/experiment-001",
    pack=pack, candidates=3, concurrency=2,
    selection_metric="tokens", max_total_tokens=500_000,
)
print(result["status"], result["accounting"], result["accepted_patch"])
```

This example invokes your configured model. Token count is the default **explicit proxy**, not a dollar estimate; it is not interchangeable across models. For dollar selection, set `selection_metric="usd"` and provide complete per-model rates in the policy. `max_total_cost_usd` requires rates for every model that could run, including planners, reviewers and escalation.

The top-level `accepted.patch` is a copy of the selected runner's verified patch. A result can be `passed` with `termination_reason="budget_exhausted"` or `"timeout"` when an earlier candidate already passed and the experiment stopped before launching further batches. Check both fields and actual totals. Missing usage, interruption or an invalid selected artifact prevents automatic selection; per-run artifacts remain available for inspection.

## Read-only cheap specialists, optional stronger coordination

`teams` decomposes research into three default roles: implementation localization, behavioral contracts, and test gaps. Each specialist receives a separate clone and returns bounded findings. A changed tracked/untracked source file fails the specialist's integrity check. Specialists do not edit the implementation or receive pack MCP servers.

An optional coordinator inspects the repository and synthesizes the independent reports into one short plan. Without a coordinator, reports are combined deterministically. One ordinary implementer then receives the advice and makes the change; external verification remains authoritative. This makes a useful cheap-worker experiment without introducing concurrent edits or an automatic patch merger.

```python
from codex_harness.experimental.parallel import teams

result = teams(
    "/path/to/repo", load_task("task.json", pack),
    load_policy("balanced", pack), "/path/outside/repo/team-001",
    pack=pack, specialist_model="gpt-6-luna",
    coordinator_model="gpt-6.1-sol", concurrency=2,
    max_total_tokens=500_000,
)
```

Use model identifiers available to your account. The named examples follow the existing project policies. Omitting `specialist_model` uses the policy's model; omitting `coordinator_model` avoids an extra synthesis call. If the policy also enables a planner, that additional planning stage still runs and is charged; compare whether both stages add value.

```bash
super-codex experimental teams task.json --repo /path/to/repo \
  --pack backend --config balanced --specialist-model gpt-6-luna \
  --coordinator-model gpt-6.1-sol --concurrency 2 \
  --max-total-tokens 500000 --output /path/outside/repo/team-001
```

Use `--specialists specialists.json` to load custom roles in the same structure shown below.

Custom specialists use one to eight entries with exactly `name` and `focus` fields:

```python
specialists = [
    {"name": "api-contract", "focus": "Trace response fields and compatibility constraints for the requested endpoint."},
    {"name": "storage-contract", "focus": "Inspect repository data-access invariants relevant to this change."},
]
```

Names must be unique and `coordinator` is reserved. Focus text is limited to 2,000 characters, each specialist report to 1,500, and coordinator output to 4,000. Advice is labeled untrusted and capped at 12,000 characters before reaching the implementer. A missing/failed/unauditable specialist result stops the workflow before implementation. The team does not infer that agreement between specialists proves correctness.

## Budgets, artifacts and comparison

Both APIs require a fresh output directory. Artifact locations inside the source repository must be explicitly Git-ignored. Selected pack skills are snapshotted into the experiment. `experiment.json` records the frozen commit, task/policy, limits, stage outcomes, total/known token and dollar usage, and patch selection. Analysis prompts and raw model results are retained privately; inspect them before publishing.

Limits are soft between batches or model stages because usage arrives after inference. A batch can overshoot by all of its already-launched work. Every runner also has its own timeout and token/cost limits. Once a shared budget or unknown accounting is observed, no further batch starts. On interruption the executor cancels work that has not started and drains current calls under their existing timeouts before returning, so it does not abandon model subprocesses. This is bounded cleanup, not immediate remote-inference cancellation. Git preparation has separate timeouts and can extend the nominal experiment deadline.

Evaluate total cost per successful task, latency distributions, first-attempt results and human-reviewed correctness. Compare N=1 against higher N; compare a normal worker against specialists alone, specialists plus coordination, and a strong single model. Independent repetitions across held-out tasks remain necessary. The included offline integration tests establish orchestration and accounting, not live-model accuracy or cost savings.
