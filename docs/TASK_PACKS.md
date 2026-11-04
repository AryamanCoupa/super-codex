# Dedicated harnesses and controlled self-improvement

A task pack is a reusable workflow for a task family, such as API pagination bugs or React form accessibility. Keep the one-off request in `task.json`; put recurring constraints, tools, skills and verified command defaults in the pack. Do not encode one benchmark's solution as reusable guidance.

```text
my-pack/
  pack.toml          # name, version, skills, matching hints, task defaults and policy
  instructions.md    # short guidance for recurring work
  task.example.json  # editable example when created with --task or --prompt
  mcp.toml           # optional Codex MCP tables
  skills/            # local skill directories
  evidence/          # optional development archive; never injected automatically
```

Precedence: built-in policy → pack policy → CLI config → explicit model override. Task JSON overrides pack task defaults. Arrays replace arrays. An explicit `--mcp` preset or `--mcp-config` entry replaces the same-named server in the pack. No global Codex settings are modified.

## Find a pack before creating one

```bash
super-codex pack list
super-codex pack list --root ./team-packs --root ./team-registries --json
super-codex pack inspect frontend
super-codex pack suggest dev-task.json --repo /path/to/development-repo
super-codex pack suggest --prompt "Fix loading states in a React form" --repo /path/to/repo
```

`list` includes the three bundled packs: `backend`, `frontend`, and `issue-to-patch`. Without `--root`, it also searches `.harness/packs` and `.harness/registries` relative to your current directory. An explicit `--root` replaces these local search roots; bundled packs remain visible. Roots may be a pack, a registry, or a directory containing packs/registries. Discovery is bounded to direct children and does not scan an entire checkout. A registry entry shows its active release and retains the registry path as the reusable selector.

`inspect` reports skills, MCP server names, task defaults, policy and context size. `suggest` uses task words, project manifests and pack matching hints; it does not invoke a model. Scores are transparent heuristics, not calibrated accuracy estimates. Results explain why a pack matched and whether creating a dedicated pack merits an experiment. Supply `--root` to include packs stored elsewhere.

To include previous results, add `--from-runs .harness/runs`. Repeated matching task failures or exhausted run budgets can trigger an experiment suggestion. Setup and infrastructure errors do not trigger this learning suggestion. Historical task details are checked when available; legacy results with only task IDs provide weaker evidence. Suggestions never promote a pack or change the active release.

## Build a dedicated pack

Use a working directory outside the target repository for the examples below. Alternatively, explicitly Git-ignore artifact directories inside the target repository before running, and keep the checkout clean. Runs and optimization reject output paths that would make the source checkout dirty.

```bash
super-codex pack create .harness/packs/my-api --from backend \
  --task dev-task.json --repo /path/to/development-repo
super-codex pack inspect .harness/packs/my-api
super-codex pack suggest dev-task.json --repo /path/to/development-repo
```

`create` requires an explicit `--from` template. It copies instructions, selected skills and MCP configuration. It copies check/setup commands only when supplied in your task file; it does not assume a template's example commands work in your repository. With `--prompt` instead of `--task`, the generated `task.example.json` has empty checks and deliberately cannot run until you add real acceptance commands. Creation does not execute or certify those commands.

Edit `instructions.md` for recurring constraints. Edit `pack.toml` to select skills, tools, policy and task defaults. The inherited `match.family` helps reuse a customized template; add `match.task_keywords` and exact repository-relative `match.repo_files` for more specific suggestions. These are matching hints, not model instructions. Task-specific text stays in the example task rather than being permanently appended to instructions.

An acceptance task might contain:

```json
{
  "id": "api-pagination-dev",
  "prompt": "Preserve the API contract when the final result page is empty.",
  "checks": [["python", "-m", "pytest", "tests/test_pagination.py"]],
  "protected_paths": ["tests", "pyproject.toml"]
}
```

Replace that example command with the repository's actual workflow. A custom skill has `skills/<name>/SKILL.md` with `name` and `description` YAML frontmatter and concise instructions. Local skills override bundled skills of the same name. The loader includes selected skill text in the prompt; it does not install anything into `~/.codex`. Referenced resources stay in the pack, so include relevant content in instructions or commit needed project resources into the worker's target repository.

Protect acceptance tests, test-runner configuration and files whose changes could invalidate checks. Nested `.codex`, `.agents`, `AGENTS.md` and `.gitmodules` changes are always rejected. For tasks intentionally editing these, use a separately reviewed workflow. `pack fork SOURCE DESTINATION` remains available for an exact editable copy, including the source's command defaults; review those commands before use.

## Run it and collect real development evidence

Register the finalized baseline, then run development tasks using that exact registered pack:

```bash
super-codex pack register .harness/packs/my-api --registry .harness/registries/api
super-codex run dev-task.json --repo /path/to/development-repo \
  --pack .harness/registries/api --output .harness/runs
```

Use the resulting `.harness/runs/RUN_ID/result.json` in the next step. Optimization requires a complete task record and a pack hash matching the current baseline. Results from a different pack, incomplete summaries, or old results after a pack change do not qualify. Use actual run artifacts rather than fabricated evidence. To keep a separate review archive, use `pack learn .harness/packs/my-api --from-result PATH/result.json`; this does not change instructions or automatically feed an optimizer. Keep registry releases immutable and collect evidence against a newly registered/versioned baseline when changing their configuration.

## One bounded improvement experiment

Self-improvement means measured changes to task instructions. It does not train model weights or allow the model to change its evaluator. `pack optimize` makes one paid proposal, compares it with the baseline, and promotes only if the executable gate passes. It can initialize an empty registry itself; explicit registration above makes collecting evidence against the active baseline clearer.

Create `holdout.json` with fresh tasks that were not used in development or a previous optimization. Paths resolve relative to the suite file; absolute paths also work. This example has three distinct prompts, repeated four times: 12 runs per variant and 24 total, within the default 40-run limit.

```json
{
  "repeat": 4,
  "seed": 42,
  "tasks": [
    {"repo": "/path/to/holdout-repo", "task": "holdout/empty-page.json", "revision": "HEAD"},
    {"repo": "/path/to/holdout-repo", "task": "holdout/cursor-boundary.json", "revision": "HEAD"},
    {"repo": "/path/to/holdout-repo", "task": "holdout/partial-page.json", "revision": "HEAD"}
  ]
}
```

Each task file needs its own real request and acceptance checks. Three renamed copies of the same prompt do not provide task diversity. Keep holdout tasks and their solutions out of the development evidence and the repository the proposer can inspect; a separate holdout repository helps enforce this boundary. Curate semantic overlap as well as exact text overlap.

```bash
super-codex pack optimize .harness/registries/api \
  --from-result .harness/runs/DEV_RUN_ID/result.json \
  --holdout holdout.json --repo /path/to/development-repo \
  --registry .harness/registries/api \
  --output .harness/experiments/api-001 \
  --model gpt-6.1-sol --cost-metric tokens
```

The example explicitly uses token count as a cost proxy. Tokens are not dollars and are not interchangeable across different models. For a dollar-based experiment, configure current input/cached-input/output prices for every worker, planner, reviewer, escalation and proposal model used, pass that file with `--config`, and use `--cost-metric usd`. The default USD gate refuses unknown prices. `--max-total-cost-usd` adds an optional experiment spending limit and also requires complete pricing.

The loop performs the following steps:

1. Validate development provenance and untouched holdouts, freeze repository commits and the baseline policy/checks, and acquire a registry lock.
2. Ask a model for one structured instruction delta using development evidence in a read-only disposable clone. Keep policy, checks, skills and tools fixed. Reject an invalid or unchanged proposal before spending on holdout runs.
3. Reserve the holdout prompt hashes in the registry, then run baseline/candidate pairs in randomized order on the same tasks and revisions. Preserve all trial records and proposal accounting.
4. Apply the quality/cost gate. If it passes, store a versioned release and update the active pointer. Otherwise, retain the existing active release and record the reason in `optimization.json`.

The output directory must be new and outside the source pack and registry. For every source repository, artifact locations must be outside it or explicitly ignored by Git. Clean committed repositories are required. Reusing an old output directory is refused.

Defaults are at most 40 evaluation runs, at least 10 runs per variant, at least three distinct holdout prompts and a **soft total limit of 1,000,000 tokens**, including the proposal and evaluation. Limits are checked between the proposal and complete run stages; one stage can overshoot. Per-run policy limits still apply. Unknown usage stops further calls. Accounting includes failed trials but excludes the development runs already collected; include that earlier spend when estimating the optimization's total benefit.

Promotion requires matching task/revision/policy/repetition sets and exact pack hashes, no development overlap, no setup/accounting/launch errors, no per-task success-count regression, at least 80% candidate success, no increased measured cost by default, and either higher observed success or lower cost. `--max-cost-ratio 1.5` allows 50% more cost when justified by improved success. These are empirical gates, not proof of statistical significance or universal improvement.

Once holdout evaluation can begin, the registry records the prompts as consumed. Rejected, interrupted and budget-limited experiments still consume reserved holdouts. A later `optimize` call against that registry requires fresh tasks. Hashes catch identical prompts and changes limited to task IDs, case or whitespace; they do not detect all semantic duplicates. Keep an additional untouched audit set for repeated optimization.

Use the registry for subsequent work and roll back when necessary:

```bash
super-codex run next-task.json --repo /path/to/repo --pack .harness/registries/api
super-codex pack rollback .harness/registries/api
```

Rollback switches current and previous release pointers. It does not clear consumed holdout history. The tool refuses to overwrite releases, but manual filesystem changes remain outside this guarantee.

Version 0.2 snapshots selected bundled skill assets into releases and fingerprints their effective content consistently with local copies. Register a fresh self-contained baseline in a new registry and re-run development/holdout comparisons created by 0.1; do not edit old result hashes to fit the new scheme. This keeps package upgrades from silently changing a registered pack's skill text.

## Manual proposal and promotion

The lower-level commands remain available when you want to inspect and evaluate stages separately:

```bash
super-codex pack propose .harness/registries/api .harness/candidates/api-001 \
  --repo /path/to/development-repo \
  --from-result .harness/runs/DEV_RUN_ID/result.json --model gpt-6.1-sol
super-codex eval baseline-holdout.json --output .harness/manual-baseline-001
super-codex eval candidate-holdout.json --output .harness/manual-candidate-001
super-codex pack promote .harness/candidates/api-001 \
  --baseline-runs .harness/manual-baseline-001 \
  --candidate-runs .harness/manual-candidate-001 \
  --registry .harness/registries/api --cost-metric tokens
```

Create the two `eval` suite files using the [evaluation format](EVALUATION.md): use identical held-out tasks, revisions, policies and repetition counts, with one variant pointing to the baseline registry and the other to the candidate. Inspect `instructions.md` and `proposal.json` before evaluation. Proposal metadata records pack hashes, development hashes, usage and cost. Raw proposal artifacts are retained under `.harness/proposals` beside the candidate's parent directory, including failed proposals when accounting is available.

Manual `propose`/`eval`/`promote` does **not** maintain the automatic optimizer's consumed-holdout history, diversity preflight, aggregate experiment budget or registry lock. Its promotion gate checks the submitted records, but you must track cross-experiment holdout reuse yourself. Prefer `optimize` when those controls should be enforced together.

There is no background daemon or automatically enabled schedule. Each `optimize` invocation attempts one candidate; it does not keep searching until something passes. The reflective update is inspired by research rather than a reproduction of GEPA or DSPy. Review local artifacts before sharing them: task prompts, model events and raw command logs can contain secrets or proprietary code.
