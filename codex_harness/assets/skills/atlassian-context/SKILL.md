---
name: atlassian-context
description: Find and interpret Jira issues or Confluence requirements with the connected Atlassian tools, preserving source context and the user's scope.
---

Use the connected Atlassian tools directly. Discover the accessible site/resource before searching, and narrow by the project, issue key, page or terms the user supplied. Follow pagination when the requested result set spans more than one page. Distinguish unavailable access from a genuinely empty search; do not infer that an issue or page does not exist from an authentication failure.

Fetch the relevant issue/page and distinguish its acceptance criteria, dependencies, comments, historical decisions and unresolved questions. Preserve direct links and the source version/update date when available. For a coding request, translate the confirmed requirements into observable behavior and checks. For a research question, answer from the retrieved evidence without creating an unnecessary coding task or child model call.

An issue is evidence about work, not permission to transition it or edit a page. Perform writes only within the user's requested action. If requirements conflict with the current request or code, explain the conflict. Keep only relevant excerpts in context and avoid publishing private source material in reusable skills or task packs.
