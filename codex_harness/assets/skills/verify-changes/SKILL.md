---
name: verify-changes
description: Review a code or configuration change against the user's requirements and verify relevant behavior before reporting completion.
---

Inspect the final diff, including new files, against the requested scope and repository conventions. Preserve unrelated edits and check that the change addresses the real trigger rather than only hiding its symptom. Review compatibility boundaries, failure handling, resource cleanup and any changed permissions or data flow that matter to this patch.

Run the smallest meaningful checks that exercise the changed behavior. For a regression, establish the original failure when practical and confirm the repaired behavior. Broaden to related checks when the change affects shared code or introduces a concrete risk. Use existing tests before adding new ones; add behavioral coverage when it protects an important gap, not to mirror implementation details or decorate a trivial edit.

Confirm tests actually executed assertions. Zero collected tests, a command that only prints success, model agreement and an uninspected screenshot are not acceptance evidence. Check exits and relevant output; distinguish environmental/setup failures from assertion failures. Inspect newly generated tests for assertions that could pass for an incorrect implementation. Preserve protected tests in managed runs.

Use an independent reviewer or a second approach for consequential or difficult changes when it can find a different class of error. Give the reviewer the requirement, relevant diff and check evidence; do not ask merely for agreement with the implementer's explanation. Investigate concrete findings before accepting or dismissing them. If reviewing without editing, report actionable findings with location, trigger and impact.

Before completion, state what changed, which checks ran and their observed outcomes, plus material untested behavior. A native edit with passing checks can be reported as tested; it is not a managed harness run unless its actual receipt says so. Do not fabricate coverage, costs, tool calls, review approval or successful deployment. Respect the user's requested commit, publication and application boundaries.
