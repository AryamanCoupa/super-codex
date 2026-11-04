---
name: debug-with-evidence
description: Diagnose a reproducible code defect from failing tests or runtime logs and produce a focused repair.
---

Use the failing input to locate the violated invariant. Inspect the implementation and one nearby caller before changing code. Check boundary cases implied by the contract, not just the supplied example. Preserve protected acceptance tests. Add a regression test in an allowed location when the existing checks do not express the defect. Report the command and observed result; distinguish unrun checks from passing checks.

When another attempt failed, use its concrete feedback to change the approach. A repeated failure with unchanged code is evidence to stop or escalate, not to repeat the same edit.
