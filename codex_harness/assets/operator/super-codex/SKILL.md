---
name: super-codex
description: Discover and use relevant available skills for native research, coding and verification; select optional task packs, managed runs or experiments when they help the request.
---

Work in the current Codex session with its existing tools, authentication, context and permissions. Choose the relevant skills below and complete the user's request directly. Research can use connected MCP tools or browsing; coding can use native editing and meaningful checks. An `answer` command, another model process, a clean Git commit or a managed receipt is not a prerequisite for ordinary work. Do not route every message through a child CLI or wait for a wrapper before using an available tool.

Use `skill-discovery` for each materially new task to choose the smallest useful set from both the native session's available skills and the bundled catalog below. Honor explicitly named skills. Read the selected instructions at their advertised paths or resources, reuse unchanged instructions already read, and briefly announce the skill names being applied. Do not repeat discovery for every follow-up or read every skill. The catalog gives exact installed paths; do not assume the current working directory contains the package. Read any selected task pack's instructions as well. A skill provides a procedure, not credentials or permission to perform unrelated actions.

If the descriptions do not make the choice clear, use the absolute launcher shown below with `skills --search "short task keywords"`, then inspect promising matches. This searches only bundled names and descriptions by keyword; it does not search third-party skills or guarantee suitability. A no-match result does not prevent ordinary native work. Follow `skill-discovery` for other advertised catalogs without installing or downloading anything automatically.

{{SUPER_CODEX_SKILLS}}

For research, start with `research-with-sources` and the relevant service skill. Use the user's selected connection and its advertised discovery/initialization tools. Search and follow pagination before claiming a complete inventory; distinguish inaccessible results from absent results. Give concrete findings with source links, and state retrieval limits. If one optional harness command fails, the existing native tools remain available within the user's scope. Explain a real authentication or permissions failure without inventing findings or weakening permission settings.

For coding, inspect repository instructions and the current diff first. Use `plan-and-context` for scope, `debug-with-evidence` for a defect, and `verify-changes` before completion. Native edits are allowed when the user asks for a change. Preserve unrelated and concurrent work, make the smallest coherent change, and verify the behavior that matters. Report the actual checks and their outcomes; do not claim a managed run or receipt when only native tools ran. Git cleanliness requirements belong to particular managed commands, not to ordinary research or all native edits.

Use `browser-verify` when a browser interaction or appearance is part of acceptance. Use `economical-delegation` before choosing extra agents or a stronger model. A small task may need one direct tool call and no plan or delegation. Do not load every skill, spawn workers for every question, or apply every available research technique to a single task.

The CLI remains available when the user asks for its workflow or the task benefits from isolated verification, measured model comparisons, repeated task packs or durable run artifacts. Discover the relevant command before choosing flags:

```bash
{{SUPER_CODEX_COMMAND}} commands
{{SUPER_CODEX_COMMAND}} skills
{{SUPER_CODEX_COMMAND}} skills --search "github repositories"
{{SUPER_CODEX_COMMAND}} skills github-context
{{SUPER_CODEX_COMMAND}} commands run
{{SUPER_CODEX_COMMAND}} commands pack
{{SUPER_CODEX_COMMAND}} experimental list
```

`skills` lists the bundled catalog, `skills --search "keywords"` filters its names and descriptions, and `skills NAME` reads one complete skill without a model call. Load individual command help rather than the complete JSON command catalog unless automation needs it. Finding a skill is different from reading and applying its instructions; none of those alone completes the user's task. Preserve the bootstrap's repository, policy, pack, tool and output defaults when selecting a CLI workflow; do not silently change budgets.

`answer "PROMPT"` is an optional noninteractive managed request. `start --managed --no-stream --task TASK_FILE --repo REPO --config WORKER_POLICY` uses an explicit coding contract and the existing exec authentication path. `run` returns a patch for review; the managed controller can apply a passing patch after source/base checks. Use these only when selected for the task, not as a mandatory prelude to research or native editing. Their source-state, authentication and budget requirements still apply. Do not discard or commit unrelated changes to satisfy them. If the user explicitly requested enforced execution, a blocked run must be reported rather than silently relabeled as a native success.

When creating a managed task, specify a concrete prompt, executable check commands as argv arrays, protected tests and any required setup. Check that tests collect meaningful assertions. For a regression, use `baseline_must_fail` when the original behavior should fail. Inspect the resulting receipt, checks and patch before claiming managed success; distinguish `harness_run`, `verified` and `applied`. Unknown usage or prices stay unknown. Native operator inference is separate from managed-run accounting.

For recurring task families, use `pack list`, `pack inspect` and `pack suggest` to discover a reusable harness. `evaluate-harness` and `curate-learning-data` cover development evidence, fresh holdouts and promotion. `select-experiment` covers optional parallel candidates, learned routing, retrieval, ACE/GEPA, recursion and local fine-tuning. Change one method at a time and count failed attempts and tuning spend. Availability of a technique does not mean it ran or improved this result.

When initialization provides no user task, say the session is ready and wait. When it includes a request, choose the relevant skills and do the work; merely reading the bootstrap or listing commands does not complete it.

If `SUPERCODEX_WORKER=1` is inherited, you are already inside a managed run. Follow its assigned contract and budget. Native tools needed for that assignment remain usable within their permissions, but do not invoke `answer`, start nested model jobs, mutate task packs, or clear the marker. Read-only CLI discovery and diagnostics are allowed; return proposed additional runs or experiments to the parent in your handoff.
