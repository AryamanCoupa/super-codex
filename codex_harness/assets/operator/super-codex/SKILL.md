---
name: super-codex
description: Follow the session's SuperCodex answer routing, discover relevant skills and verify results; support direct native work when routing is explicitly disabled.
---

Follow the session mode and the current request's routing instructions. In a default SuperCodex session, a UserPromptSubmit hook supplies an exact `answer --prompt-file` command for each user message. Execute that command before independently browsing, answering or editing source, then inspect its receipt and report the actual result with its source links and verification limits. The private prompt file preserves the user's original text; do not substitute a summary. Loading skills or listing commands does not satisfy routing. An initial request supplied at launch also needs one delegated run; bootstrap initialization itself is not a user task.

When `--no-prompt-hook` was explicitly selected, or this operator skill is used in ordinary Codex without session routing, complete authorized work directly with the current tools. Do not invent a hook, require a receipt for native work or start a child model merely because a skill is available. In either mode, preserve the current authentication, permissions, user constraints and higher-priority instructions. A worker with `SUPERCODEX_WORKER=1` follows its existing assignment and never routes recursively.

Use `skill-discovery` for each materially new task to choose the smallest useful set from both the native session's available skills and the bundled catalog below. Honor explicitly named skills. Read the selected instructions at their advertised paths or resources, reuse unchanged instructions already read, and briefly announce the skill names being applied. Do not repeat discovery for every follow-up or read every skill. The catalog gives exact installed paths; do not assume the current working directory contains the package. Read any selected task pack's instructions as well. A skill provides a procedure, not credentials or permission to perform unrelated actions.

If the descriptions do not make the choice clear, use the absolute launcher shown below with `skills --search "short task keywords"`, then inspect promising matches. This searches only bundled names and descriptions by keyword; it does not search third-party skills or guarantee suitability. A no-match result does not prevent ordinary native work. Follow `skill-discovery` for other advertised catalogs without installing or downloading anything automatically.

{{SUPER_CODEX_SKILLS}}

For research, start with `research-with-sources` and the relevant service skill. Use connections actually available to the executing role and their advertised discovery/initialization tools. The outer native operator's integrations are not automatically available to a managed child. Search and follow pagination before claiming a complete inventory; distinguish inaccessible results from absent results. Give concrete findings with source links, and state retrieval limits. If a routed command fails, inspect its receipt and report the failure rather than silently replacing it with native research. For an outer sandbox or process-permission denial, use the host's normal approval flow for the same command when permitted; do not weaken sandbox or approval settings. Missing service credentials require their normal setup, not a larger model or invented findings.

For coding, use `plan-and-context` for scope, `debug-with-evidence` for a defect, and `verify-changes` before completion. In a routed session, let the managed command inspect, implement and verify under its contract; the outer operator must not bypass a failed run with direct source edits. In skills-only native mode, inspect repository instructions and the current diff, make the smallest coherent change and run meaningful checks directly. Preserve unrelated and concurrent work in either case. Report actual checks and outcomes; native checks are not a managed receipt. Git cleanliness requirements apply to managed coding, not ordinary research or all native edits.

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

`answer "PROMPT"` is the noninteractive managed request used by default session routing and can also be run directly. It uses buffered Codex exec; do not claim that child answer text streams before completion. `start --managed --no-stream --task TASK_FILE --repo REPO --config WORKER_POLICY` uses an explicit coding contract and the existing exec authentication path. `run` returns a patch for review; the managed controller can apply a passing patch after source/base checks. Preserve the exact command supplied by the hook and its policy/tool selections. Source-state, authentication and budget requirements still apply. Do not discard or commit unrelated changes to satisfy them, weaken permissions, or silently relabel a blocked managed run as native success.

When creating a managed task, specify a concrete prompt, executable check commands as argv arrays, protected tests and any required setup. Check that tests collect meaningful assertions. For a regression, use `baseline_must_fail` when the original behavior should fail. Inspect the resulting receipt, checks and patch before claiming managed success; distinguish `harness_run`, `verified` and `applied`. Unknown usage or prices stay unknown. Native operator inference is separate from managed-run accounting.

For recurring task families, use `pack list`, `pack inspect` and `pack suggest` to discover a reusable harness. `evaluate-harness` and `curate-learning-data` cover development evidence, fresh holdouts and promotion. `select-experiment` covers optional parallel candidates, learned routing, retrieval, ACE/GEPA, recursion and local fine-tuning. Change one method at a time and count failed attempts and tuning spend. Availability of a technique does not mean it ran or improved this result.

When initialization provides no user task, say the session is ready and wait. When it includes a request, follow the bootstrap's routing mode and apply relevant skills; merely reading the bootstrap or listing commands does not complete it.

If `SUPERCODEX_WORKER=1` is inherited, you are already inside a managed run. Follow its assigned contract and budget. Native tools needed for that assignment remain usable within their permissions, but do not invoke `answer`, start nested model jobs, mutate task packs, or clear the marker. Read-only CLI discovery and diagnostics are allowed; return proposed additional runs or experiments to the parent in your handoff.
