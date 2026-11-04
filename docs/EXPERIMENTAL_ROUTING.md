# Experimental learned routing and trajectory retrieval

Both capabilities are explicit local experiments. They make no model calls while fitting or retrieving. They can be composed with a real coding run through `experimental run`, whose normal clean-clone verifier still decides whether a patch passes.

## Fit a router from controlled comparisons

The router fits a TF-IDF logistic classifier. Its target is whether the cheaper model matched or exceeded the stronger model's observed success rate without higher measured cost on the same task. This is an actual fitted classifier, not a keyword rule. It is a small local experiment inspired by [RouteLLM](https://arxiv.org/html/2406.18665v2), not an implementation or reproduction of RouteLLM's preference-trained routers.

Collect ordinary `eval` records for two **single-model** variants, using the same pack, checks, revision, tool configuration, runtime metadata and repetition counts. Give the variants different `policy.model` values. Disable planner, reviewer and escalation roles in these comparisons so the outcomes can be attributed to the declared model. The comparison policy otherwise must match exactly, including limits and price tables. Include real failing cases and successes.

```bash
super-codex experimental router train \
  --from-runs .harness/router-comparisons --output .harness/router.json \
  --cheap-model YOUR_CHEAP_MODEL --strong-model YOUR_STRONG_MODEL \
  --cost-metric tokens
super-codex experimental router choose task.json --router .harness/router.json
```

Use current explicit prices and `--cost-metric usd` for monetary comparisons. Token count is a proxy; model token prices need not be equal. Every usable trial must have known finite cost under the selected metric. Historical collection spending, including excluded records where known, is recorded separately from estimated routing cost.

Defaults require eight distinct task prompts and at least two prompt groups in each target class. Repeated trials and renamed task IDs do not create diversity. Duplicate run IDs are rejected. Unusable infrastructure/accounting outcomes exclude the paired task; differences in tools, revisions, policy or repetition counts are rejected rather than attributed to the model.

Training and validation split by normalized prompt identity, keeping repeated and renamed tasks together. Vocabulary and weights are fitted only on the training subset. The fixed-threshold validation report compares the router with always-cheap and always-strong choices using the recorded trials. It is a retrospective estimate; it does not include a new live routed experiment. Scores are **uncalibrated**, and semantic duplicates can still leak across text-based splits. Use an untouched audit suite before trusting quality or savings claims.

The default cheap-model threshold is 0.8. Low lexical similarity or insufficient fitted support falls back to the configured strong model. The composed execution path checks recorded context metadata; direct `router choose` is an inspection operation unless that metadata is supplied. A stronger-model fallback does not guarantee correctness.

## Retrieve compact successful trajectories

Trajectory memory performs BM25 retrieval over prior task text and changed filenames. It stores task/check hashes, base revision, pack identity, source run IDs, and a compact sequence of attempted changes and check outcomes. A passing status alone is insufficient: the final recorded verifier checks must all have passed. Failed examples, invalid task hashes and failed required reviews are excluded.

```bash
super-codex experimental memory build \
  --from-runs .harness/development-runs --output .harness/memory.json
super-codex experimental memory query task.json \
  --index .harness/memory.json --repo /path/to/repo --pack .harness/packs/my-api
```

By default, the index excludes raw events, test output, patch bodies and model handoffs. The Python API's `include_handoffs=True` explicitly retains a bounded final handoff; treat that model-authored text as untrusted advice even when the associated patch passed checks. Inspect it for sensitive content before sharing. Index files are created privately and never overwritten.

Retrieval excludes the current task's exact hash and normalized prompt, checks pack identity, and requires the same frozen base revision. Stale revision reuse is an explicit API/CLI opt-in and is marked in every returned match. A fixed character budget includes complete provenance records; it never truncates an example mid-record. Pass holdout task and normalized-prompt hashes as exclusions, or use the CLI's holdout-suite exclusion option. Lexical similarity is not proof of relevance, and text hashes do not detect every semantic duplicate.

This implements a compact, provenance-aware retrieval experiment informed by [ExpeL](https://arxiv.org/html/2308.10144v1). It does not claim ExpeL's learned insights, dense-retrieval method or benchmark gains.

## Compose and evaluate

```bash
super-codex experimental run task.json --repo /path/to/repo \
  --pack .harness/packs/my-api --router .harness/router.json \
  --memory .harness/memory.json --output .harness/routed-runs
```

The selected model and retrieved advice remain inputs to the existing verified coding loop. Record the router and context hashes with each result. Compare four variants on fresh tasks: fixed model without memory, routing alone, memory alone, and both together. Count all data-collection, failed-run, tuning and inference spending. Change one component at a time before attributing a gain.

For integrations, `routing.train_router(...)` writes a new artifact; `routing.route(...)` returns a model decision and its reasons. `memory.build_memory(...)` writes the local index; `memory.retrieve(...)` returns bounded `context` and source matches. The runtime can pass that text as `runner.run(..., extra_context=...)` without bypassing protected checks.
