---
name: debug-with-evidence
description: Diagnose a reproducible code defect from failing tests or runtime logs and produce a focused repair.
---

Reproduce the reported failure when practical, or inspect the exact error, input and environment evidence when reproduction is unavailable. State the behavior that should hold and identify which observation contradicts it. Inspect the relevant implementation and a nearby caller before editing. Check boundary cases implied by the contract, not just the supplied example.

Form one testable cause and use a targeted read, trace or check to distinguish it from alternatives. Preserve the user's existing changes and any protected acceptance tests. Make a focused repair, then rerun the failing case and nearby meaningful checks. Add a regression test when existing assertions do not express the defect; do not weaken tests to accommodate the bug. For unrelated pre-existing failures, report the evidence and keep the repair scope clear.

Report the actual command and observed result; distinguish unrun checks from passing checks. A plausible explanation without a successful check remains a hypothesis. Use the current session's tools; a nested harness process is optional unless the user selected that workflow.

When another attempt failed, use its concrete feedback to change the approach. A repeated failure with unchanged evidence is a reason to inspect the assumption, obtain missing context or choose a stronger reviewer, not to repeat the same edit indefinitely. Separate infrastructure/authentication failures from code defects before spending on another model attempt.
