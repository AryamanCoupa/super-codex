---
name: super-codex
description: Operate the local SuperCodex harness when asked to run a coding task through it, choose a dedicated task pack, compare model cost and accuracy, or improve a reusable harness from verified evidence.
---

Use the installed CLI as the execution interface. It works from any directory using this exact launcher; preserve quoting:

```bash
{{SUPER_CODEX_COMMAND}} commands
```

Start with the compact `commands` list, then inspect the relevant leaf with `commands run` or `commands experimental best-of-n`. Append `--json` when structured argument metadata is useful. The complete `commands --json` catalog is available for automation but is large; avoid loading it all into routine model context. Discover live commands before choosing flags, so upgrades do not leave you using a stale reference. Discovery makes no model calls.

For an ordinary coding request, use the default controlled entry point (`start "TASK" --repo REPO`) or provide a reviewed contract (`start --task TASK_FILE --repo REPO`). It performs preparation, a verified run, and checked application; add `--patch-only` when the user wants a patch for review. The controller will stop on missing checks, invalid preparation or insufficient accounting rather than fall back to direct edits. `--native` is an explicitly advisory Codex interface and cannot enforce harness use. A skill loaded into an ordinary Codex session is also guidance, not execution enforcement.

Act as the top-level operator within the user's task and spending constraints. Inspect the target repository and define a task JSON with a concrete prompt, executable `checks` as argv arrays, and protected tests. Use `baseline_must_fail` for a regression whose original code should fail. Resolve task, repository, pack, suite and artifact paths explicitly; checks execute inside disposable clones. The source must be a clean committed Git checkout. Do not discard or commit unrelated user changes to make it clean.

Minimal task shape (replace the prompt and check with this repository's actual acceptance criteria):

```json
{"id":"scoped-fix","prompt":"Describe the required behavior and boundaries.","checks":[["{python}","-m","unittest","discover","-s","tests"]],"protected_paths":["tests"],"baseline_must_fail":false}
```

Check that the command runs meaningful assertions, not an empty test collection. Optional `setup` uses the same list-of-argv-arrays format for reproducible dependencies. `{python}` is the harness interpreter. A JSON/TOML policy passed with `--config` can set `max_tokens`, `max_cost_usd` and `run_timeout_seconds`; token/dollar limits are soft between model stages. For preset-specific overrides, inspect its packaged TOML before creating a custom policy; do not invent undocumented command-line flags.

Use `pack list`, `pack inspect` and `pack suggest` to discover a suitable dedicated harness, then use it with `start --task TASK --repo REPO --pack PACK`, or with the lower-level `run TASK --repo REPO --pack PACK --output OUTPUT`. An output directory outside the source keeps generated artifacts separate. Use actual checks for this repository; copied sample commands are not acceptance criteria. Use the controller receipt, `report` and saved result/check/patch artifacts to assess completion. A passed patch remains in `accepted.patch`. The controller applies it only after source/base checks unless `--patch-only` was selected; lower-level `run` leaves the source unchanged. After application, the user must review and commit intended changes before another coding run. Never commit or discard unrelated work to make the source clean.

Report what actually ran: preparation, worker attempts, deterministic checks, configured planning/review, repairs or escalation, and whether the patch was applied. Listing commands or describing capabilities does not establish harness execution. Advisory research answers are not verified coding runs. Do not claim all available techniques were used or that quality/cost improved without measured comparison. Preparation and execution share a per-task budget in the controller; native operator spending remains outside child-run accounting.

For recurring task families, use `pack create` and the measured `learn`/`propose`/`optimize`/`promote` lifecycle, with separate development and holdout tasks. Registry release, inspection and rollback commands are discoverable in `commands pack`. Keep the active pack unless its candidate meets the gates. Do not weaken checks or reuse development answers as holdouts.

For an observed failure that warrants more computation, inspect `experimental list` and the chosen command's help. Select independent candidates for verifiable alternatives; specialists or recursion for separable questions; routing and memory when matched verified data exists; ACE/GEPA for reusable guidance; local fine-tuning only with suitable data and compute. Count all attempts and optimization spend, treat unknown cost as unknown, and add one method at a time. Optional dependencies may need installation before GEPA or training can execute. Do not enable every experiment for every task.

Select MCP presets and custom configurations only when relevant. `mcp` prints configuration; it does not authenticate or connect services. Follow the user's authorization for external actions. Command discovery itself does not grant permissions or spending authorization. An explicitly requested run can proceed without asking for permission again merely because this skill is active.

If `SUPERCODEX_WORKER=1` is inherited, you are already inside a managed run. Use read-only discovery and diagnostics; return proposed additional runs or changes to the parent in your handoff. Do not start nested model jobs or clear the marker: their spending would escape the parent accounting. Use the top-level experimental commands for accounted delegation.
