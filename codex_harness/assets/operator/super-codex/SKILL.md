---
name: super-codex
description: Discover and apply relevant SuperCodex skills in the current session, verify results and respect explicitly selected managed answer routing.
---

Apply relevant skills to the user's actual task in the current Codex session. The default SuperCodex skills hook provides a small shortlist from bundled metadata and reminds you to read and use appropriate instructions. Treat matches as candidates, check the full available catalog when needed, and use judgment about fit. Follow the chosen procedure with existing tools and report the actual outcome; listing or reading a skill alone does not complete the task. No child `answer` command, per-turn prompt copy or managed receipt is required by this default workflow.

Follow the mode selected in the bootstrap. `--prompt-hook skills` is the default; `--prompt-hook off` or `--no-prompt-hook` keeps bootstrap guidance without per-turn reminders. When `--prompt-hook answer` was explicitly selected and the current turn supplies an exact `answer --prompt-file` command, execute that command and inspect its receipt before reporting the result. Preserve its exact prompt, selected policy and tools; do not silently replace a failed managed request with native work. Outside that explicit mode, use native tools directly. In all modes preserve authentication, permissions, user constraints and higher-priority instructions. A worker with `SUPERCODEX_WORKER=1` follows its assignment and never routes recursively.

Use `skill-discovery` for each materially new task to choose the smallest useful set from both the native session's available skills and the bundled catalog below. Honor explicitly named skills. Read the selected instructions at their advertised paths or resources, reuse unchanged instructions already read, and briefly announce the skill names being applied. Do not repeat discovery for every follow-up or read every skill. The catalog gives exact installed paths; do not assume the current working directory contains the package. Read any selected task pack's instructions as well. A skill provides a procedure, not credentials or permission to perform unrelated actions.

If the descriptions do not make the choice clear, use the absolute launcher shown below with `skills --search "short task keywords"`, then inspect promising matches. This searches only bundled names and descriptions by keyword; it does not search third-party skills or guarantee suitability. A no-match result does not prevent ordinary native work. Follow `skill-discovery` for other advertised catalogs without installing or downloading anything automatically.

{{SUPER_CODEX_SKILLS}}

For research, start with `research-with-sources` and the relevant service skill. Use connections available in the current session and their advertised discovery/initialization tools. Search and follow pagination before claiming a complete inventory; distinguish inaccessible results from absent results. Give concrete findings with source links and retrieval limits. When an explicit managed request is used, remember that outer native integrations are not automatically available to its child. Use the host's normal approval flow for actual permission needs; do not weaken sandbox or approval settings. Missing service credentials require their normal setup, not a larger model or invented findings.

For coding, use `plan-and-context` for scope, `debug-with-evidence` for a defect, and `verify-changes` before completion. Read the selected instructions and perform their relevant steps: inspect the current diff, reproduce or inspect the failure, make a scoped repair and verify behavior. Preserve unrelated and concurrent work. If explicit answer routing is active, let the managed command implement and verify under its contract rather than bypassing a failed run with direct source edits. Report actual checks and outcomes; native checks are not a managed receipt. Git cleanliness requirements apply to managed coding, not ordinary research or all native edits.

Use `browser-verify` when browser behavior or appearance is part of acceptance. Use `economical-delegation` to assess multi-agent work or stronger reasoning when independent subtasks, complexity or failures justify it. If delegation helps and tools are available, give workers bounded assignments and check their results; merely mentioning multi-agent work is not using it. Respect the user's model choices and budget. A small task may need one direct tool call and no plan or delegation. Do not load every skill, spawn workers for every question or apply every technique to every task.

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

`answer "PROMPT"` is an optional noninteractive managed request, also used by explicit `--prompt-hook answer` sessions. It uses buffered Codex exec; do not claim child answer text streams before completion. `start --managed --no-stream --task TASK_FILE --repo REPO --config WORKER_POLICY` uses an explicit coding contract and the existing exec authentication path. `run` returns a patch for review; the managed controller can apply a passing patch after source/base checks. Source-state, authentication and budget requirements apply to these selected workflows. Do not discard unrelated changes to satisfy them, weaken permissions or relabel a blocked managed run as native success.

When creating a managed task, specify a concrete prompt, executable check commands as argv arrays, protected tests and any required setup. Check that tests collect meaningful assertions. For a regression, use `baseline_must_fail` when the original behavior should fail. Inspect the resulting receipt, checks and patch before claiming managed success; distinguish `harness_run`, `verified` and `applied`. Unknown usage or prices stay unknown. Native operator inference is separate from managed-run accounting.

For recurring task families, use `pack list`, `pack inspect` and `pack suggest` to discover a reusable harness. `evaluate-harness` and `curate-learning-data` cover development evidence, fresh holdouts and promotion. `select-experiment` covers optional parallel candidates, learned routing, retrieval, ACE/GEPA, recursion and local fine-tuning. Change one method at a time and count failed attempts and tuning spend. Availability of a technique does not mean it ran or improved this result.

When initialization provides no user task, say the session is ready and wait. When it includes a request, follow the bootstrap's routing mode and apply relevant skills; merely reading the bootstrap or listing commands does not complete it.

If `SUPERCODEX_WORKER=1` is inherited, you are already inside a managed run. Follow its assigned contract and budget. Native tools needed for that assignment remain usable within their permissions, but do not invoke `answer`, start nested model jobs, mutate task packs, or clear the marker. Read-only CLI discovery and diagnostics are allowed; return proposed additional runs or experiments to the parent in your handoff.
