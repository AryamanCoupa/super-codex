# Codex, skills, MCP and future providers

## Codex setup

SuperCodex reuses Codex authentication; it does not copy credentials into a repository. Managed invocations ignore the user's `config.toml` by default, but this is not a guarantee that every global skill, managed policy or project instruction is absent. Audit those sources for reproducible benchmarks. With the lower-level `run` command, `inherit_user_config = true` in a private local policy enables existing MCP/provider configuration, whose contents then affect the run.

The default `sc` controller always disables inherited user configuration for preparation and workers, even if a supplied policy requests it. Configure integrations explicitly through the selected pack, `--mcp` or `--mcp-config`. Read-only preparation receives no task MCP servers; selected integrations are available to the implementation worker. This avoids treating a local read-only sandbox as permission to make remote writes. Explicit `sc --native` instead preserves native interactive configuration and remains advisory; see [the mode distinction](AGENT_USAGE.md#explicit-native-codex-mode).

The adapter uses `codex exec --json --ephemeral --sandbox workspace-write`, passes prompts through stdin, and sets `approval_policy="never"`. Commands requiring an interactive escalation fail in automation. It does not use the dangerous sandbox-bypass flag. Advisors use `read-only`. Project instructions remain subject to Codex's trust/loading behavior. [Official configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).

## Playwright

```bash
super-codex mcp playwright
npx -y @playwright/mcp@0.0.84 --help
```

The preset pins the upstream package version, runs headlessly and uses `--isolated` so sessions do not share browser profiles. Node 18+ and a compatible installed browser are needed. For fully repeatable evaluation, install/package a pinned dependency tree and browser image ahead of time; a pinned npx package alone is not a complete environment lock. See [upstream installation and browser options](https://github.com/microsoft/playwright-mcp).

Browser MCP interactions support exploration and UI evidence. Make meaningful deterministic Playwright tests part of `checks` for acceptance. The browser server itself has network access; the Codex shell sandbox is not a policy boundary around remote/browser tools.

## GitHub

The preset uses the [official remote read-only endpoint](https://github.com/github/github-mcp-server/blob/main/docs/remote-server.md) and a small tool allow-list. Set `GITHUB_MCP_TOKEN` in your shell using a token with access only to the repositories you need. Do not put it in task files, packs or committed TOML. MCP authentication and account policies may require additional setup. The project does not create issues, comments, pull requests or pushes automatically.

## Atlassian

The preset uses `https://mcp.atlassian.com/v2/mcp` with a narrow set of read/search tools. Complete OAuth using Codex before an unattended run. To register and sign in explicitly:

```bash
codex mcp add atlassian --url https://mcp.atlassian.com/v2/mcp
codex mcp login atlassian
```

These commands change your Codex connection configuration; SuperCodex only prints or passes configuration unless you run them yourself. OAuth requires browser interaction and may require organization approval. Confirm the current [tool catalog](https://support.atlassian.com/atlassian-ai-gateway/docs/supported-tools/) and [server setup](https://atlassian.github.io/atlassian-mcp-server/) for your deployment. Servers can evolve tool names; a required server startup failure should be fixed as configuration, not retried with a bigger model.

## Custom servers

Copy `codex_harness/assets/mcp/custom.example.toml` to an ignored `custom.local.toml`. Replace the endpoint, bearer-token environment variable and allow-list with your server's configuration:

```bash
super-codex run task.json --repo /path/to/repo --mcp-config custom.local.toml
```

TOML must contain `[mcp_servers.<name>]` tables. Stdio command/args and HTTP URL settings are passed to Codex without a shell. Use references to environment variables rather than literal credentials. If a server multiplexes read and write operations behind one tool name, a tool-name allow-list does **not** make it read-only. Use server-side permission controls and appropriate credentials.

Only task-selected servers are included by SuperCodex. A server marked `required=true` must initialize. Existing inherited configurations and managed policies can add other behavior, which should be audited for benchmarks. Advisors receive no task-pack MCP presets; inherited global tools remain subject to your Codex settings.

## Skills

Five bundled skills cover evidence-driven debugging, browser verification, GitHub context, Atlassian requirements, and harness evaluation. Packs select the skills they need. To use a skill directly in Codex outside the wrapper, copy its directory into your repository's supported skills location according to your Codex version. Installation into a user's global environment is intentionally explicit.

## Open models

`codex_harness/assets/policies/open-model.example.toml` activates Codex's `--oss --local-provider ollama` path. `lmstudio` is the other accepted value. Supply an installed model name and verify tool/reasoning support. These paths are structurally supported but not live-tested here; there is no claim of parity with hosted Codex. A future provider can implement the adapter's `run`/`advise` contract without changing verification or pack promotion.

## Observability

Local JSON/JSONL is the default; no telemetry is uploaded automatically. If you add Langfuse or another tracing backend, send sanitized run IDs, phase/model names, usage, latency and scores, then opt in separately to prompt/code capture. Do not assume that `.gitignore` redacts logs. Raw artifacts can contain source code, private URLs, tool output and credentials printed by target programs.
