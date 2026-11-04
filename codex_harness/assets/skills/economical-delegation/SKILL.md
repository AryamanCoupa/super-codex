---
name: economical-delegation
description: Choose useful multi-agent work, bounded smaller-model delegation or stronger reasoning from task difficulty and observed evidence, while controlling total cost and checking results.
---

Begin with the current session and the simplest method that can satisfy the task. Do not spawn a model just to wrap a tool call, repeat a known answer or access tools already connected here. Respect the user's model choices and budget. When model selection is unavailable, do not pretend a cheaper model was used.

Use multi-agent work when subtasks are bounded, have clear input/output contracts and can be checked by the coordinator. Good candidates include independent file inspection, extracting facts from specified sources, a narrowly scoped repair with tests or reviewing a separate failure risk. If it adds value and delegation tools are available, actually assign the work, collect the results and integrate verified findings. Provide the relevant context and constraints, not the entire conversation. Assign file ownership or read-only scope so workers do not overwrite each other.

Parallelize independent work when the expected benefit exceeds coordination and duplicated-context cost. Keep one owner for integrating edits, reconciling conflicting evidence and running final checks. Avoid several workers producing the same uncheckable answer; majority agreement does not establish correctness. Count all candidates, failed attempts, verification and coordinator effort when comparing cost.

Use stronger reasoning when a task requires difficult decomposition, cross-cutting design or resolution of conflicting evidence, or when a cheaper attempt has failed for a model-related reason. Supply the concrete failure and a compact handoff. Do not escalate an authentication, missing-tool or broken-environment problem as if a larger model could fix access. Stop repeated attempts that add no new evidence and resolve the actual blocker.

For recurring tasks, compare a cheap baseline, selective escalation and a strong baseline under the same acceptance criteria before claiming savings. Use `evaluate-harness` or `select-experiment` when a measured CLI workflow is useful. Keep unknown usage/prices unknown and include tuning spend. More agents or a larger model is an option, not an accuracy guarantee.

If `SUPERCODEX_WORKER=1` is inherited, do not launch further model jobs or clear the marker. Complete the assigned subtask within the parent budget and return a recommendation if more work is needed. The top-level operator owns additional runs and experiments.
