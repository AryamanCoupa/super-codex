---
name: evaluate-harness
description: Compare task-pack or model-policy changes using repeated, fixed-revision coding trials and explicit quality and cost metrics.
---

Keep training/development examples separate from the final holdout tasks. Freeze task prompts, acceptance checks, base revisions, dependencies, MCP capabilities and timeouts before comparing variants. Change one factor at a time. Include failed runs in spending and status counts. Report first-attempt and eventual success separately. Independent repeated trials are different from sequential repairs; do not call repairs pass@k. Inspect failure artifacts before editing a pack. Propose a small change, evaluate it on development tasks, then confirm it on untouched holdouts before promotion.

Synthetic demo runs validate orchestration only. Do not report them as model performance. Unknown usage or prices remain unknown, never zero.

Check the verifier before optimizing the agent: show that representative wrong implementations fail, and validate any reference outputs independently. Generated tests are proposed evidence until their assertions are reviewed. Keep verifier changes in a separate experiment from instruction changes.

For recurring tasks, use `pack suggest` to inspect available specialization and `pack optimize` for one bounded instruction experiment. Preserve unrelated learned guidance with a small edit. Use fresh holdouts after observing evaluation feedback, count proposal/evaluation spending, and compare tool/runtime metadata. A rejected candidate is evidence to inspect, not permission to keep tuning against the same holdout.
