---
name: github-context
description: Retrieve the GitHub issue, pull request, or source context needed for a coding task through its configured MCP server.
---

Retrieve the specific repository/ref and relevant issue or pull request. Follow pagination and distinguish missing content from empty content. Record the source URL and commit when available. Fetch only files needed for the task. Do not publish comments, push branches, or edit issues unless the user explicitly requests those actions.

If a custom gateway is configured, use its operation discovery tools before invoking an operation. Multiplexed tool names do not tell you whether an operation writes data. Prefer the user's chosen integration; otherwise use the configured GitHub server.
