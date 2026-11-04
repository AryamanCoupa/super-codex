# Codex, skills, MCP and future providers

## Codex setup

SuperCodex reuses Codex authentication; it does not copy credentials into a repository. Managed invocations ignore the user's `config.toml` by default, but this is not a guarantee that every global skill, managed policy or project instruction is absent. Audit those sources for reproducible benchmarks. With the lower-level `run` command, `inherit_user_config = true` in a private local policy enables existing MCP/provider configuration, whose contents then affect the run.

In 0.5.6, default `sc` opens native Codex with per-turn skill reminders and preserves configured integrations/authentication. The operator reads and applies relevant GitHub, Atlassian, browser or research skills using available tools directly. The reminder does not call a model or require an `answer` command. `--prompt-hook off` keeps bootstrap guidance without reminders; `--prompt-hook answer`, `sc --managed` and direct `answer` explicitly select managed execution with separately configured child integrations. See [the mode distinction](AGENT_USAGE.md).

The optional managed exec adapter uses `codex exec --json --ephemeral --sandbox workspace-write`, passes prompts through stdin, and sets `approval_policy="never"`. Commands requiring an interactive escalation fail in automation. It does not use the dangerous sandbox-bypass flag. Advisors use `read-only`. Project instructions remain subject to Codex's trust/loading behavior. [Official configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).

## Research from any directory

Native research works from any directory using the existing Codex connection permissions. It does not require a committed source snapshot. For example, ask `sc` to find matching repositories; the GitHub skill guides actual tool discovery, search scope, pagination and evidence reporting. Skills cannot create access to repositories that the connected account cannot see.

The following settings apply only to explicit managed research through `answer`, `--managed` or `--prompt-hook answer`. In a directory without Git commits, that controller creates an empty private workspace for preparation without copying the selected directory's files or initializing it. Managed coding remains gated on a clean committed target selected with `--repo`.

Select research presets explicitly; the GitHub example still requires the token described below:

```bash
sc --managed --no-stream --research-mcp github "Find repositories matching my query"
sc --managed --no-stream --research-mcp atlassian "Find the issue and its linked specification"
sc --managed --no-stream --research-mcp-config /path/to/private-research.toml "Research this question"
```

`--research-mcp` is repeatable. A preset replaces a same-named server from the research file. These flags configure the managed controller or are forwarded by explicit `--prompt-hook answer`; default skills mode and off mode reject them and use existing native connections or `--mcp`. Worker `--mcp` selections do not automatically become managed research connections.

To reuse selected connections with `sc --managed --no-stream`, create `research.toml` under `${XDG_CONFIG_HOME:-~/.config}/super-codex/`. Managed preparation reads this file only when it exists; `--research-mcp-config` selects a different file instead. Default native `sc` already uses ordinary Codex connections. Keep the research file private and outside public repositories. It can reference a server already configured in Codex:

```toml
# The name must match a server in your local Codex config.toml.
[existing_mcp_servers.github]
enabled_tools = ["search_repositories", "get_file_contents"]
```

References read only the named connection from `$CODEX_HOME/config.toml`, or `~/.codex/config.toml` when `CODEX_HOME` is unset. Its configuration is copied in memory and the explicit tool allow-list is applied; the original file is not changed. This does not enable blanket user configuration, plugins or every native MCP server. Use actual tool names supported by the selected server.

Managed preparation cannot show interactive approval prompts. When you explicitly authorize an individual read tool to run unattended, a reference can override that tool's approval mode without changing native settings:

```toml
[existing_mcp_servers.github.tools.search_repositories]
approval_mode = "approve"
```

Overrides must name an enabled tool. `approve` skips that tool's approval prompt; it does not grant service access or override managed requirements. Other tools retain their existing settings. Do not use this for a broad dispatcher unless every exposed operation is appropriate for unattended use. See the [official MCP configuration examples](https://learn.chatgpt.com/docs/extend/mcp).

Alternatively, define a connection directly:

```toml
[mcp_servers.github]
url = "https://api.githubcopilot.com/mcp/readonly"
bearer_token_env_var = "GITHUB_MCP_TOKEN"
enabled_tools = ["search_repositories", "get_file_contents"]
required = true
```

Custom and referenced connections require a nonempty `enabled_tools` list. Use environment-variable references instead of literal credentials. Configuration does not create authentication or grant repository access; complete the server's authentication separately. `sc --managed --dry-run` previews selected research server names without making model calls or printing connection values.

The controller requires each selected research server to be ready at startup. Server names must use letters, numbers, underscores or hyphens so Codex's dotted command-line settings preserve the exact connection name.

Preparation requests read/search operations and records actual MCP calls in its receipt. Its local read-only sandbox does **not** prevent remote writes. A multiplexed tool can expose read and write operations behind one name, so an allow-list alone is not an operation-level permission boundary. Use server-side restrictions and appropriately scoped credentials. The GitHub preset uses its remote read-only endpoint; other custom and browser integrations need their own controls. Research answers remain advisory and do not claim independently verified coding results.

## Playwright

```bash
super-codex mcp playwright
npx -y @playwright/mcp@0.0.84 --help
```

The preset pins the upstream package version, runs headlessly and uses `--isolated` so sessions do not share browser profiles. Node 18+ and a compatible installed browser are needed. For fully repeatable evaluation, install/package a pinned dependency tree and browser image ahead of time; a pinned npx package alone is not a complete environment lock. See [upstream installation and browser options](https://github.com/microsoft/playwright-mcp).

Browser MCP interactions support exploration and UI evidence. Make meaningful deterministic Playwright tests part of `checks` for acceptance. The browser server itself has network access; the Codex shell sandbox is not a policy boundary around remote/browser tools.

## GitHub

The preset uses the [official remote read-only endpoint](https://github.com/github/github-mcp-server/blob/main/docs/remote-server.md) and a small tool allow-list, including `search_repositories`. Set `GITHUB_MCP_TOKEN` in your shell using a token with access only to the repositories you need. Do not put it in task files, packs or committed TOML. MCP authentication and account policies may require additional setup. The project does not create issues, comments, pull requests or pushes automatically.

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

Only explicitly selected servers are supplied by SuperCodex to each phase. A server marked `required=true` must initialize. Preparation can receive the research configuration described above; planners and reviewers receive no MCP presets from the harness. Managed policies and instruction sources can still affect Codex behavior and should be audited for benchmarks.

## Skills

Twelve bundled task skills cover skill discovery, research, planning, debugging, verification, economical delegation, browser work, GitHub/Atlassian context, evaluation, experiment selection and learning-data curation. Inspect them with `sc skills`, search bundled names/descriptions with `sc skills --search "GitHub repositories"`, or read one with `sc skills github-context`. Search also supports `--json` and makes no model calls. It is a keyword shortlist, not a search of third-party skills or a guarantee that the first result fits the task.

Native `sc` supplies the full catalog and a per-turn shortlist in default skills mode. `skill-discovery` directs the operator to consider both bundled and native session skills, read relevant instructions and apply them with existing tools. The shortlist is keyword-based and does not guarantee suitability; an empty result does not rule out an installed/project skill. Discovery does not install additional skills or start model jobs. Packs select skills in their manifest. Ordinary Codex sessions can load the same catalog via `sc agent install --user`; installing that skill alone does not register a hook. See [skill coverage and installation](AGENT_USAGE.md). Skills do not install or authorize the services they describe.

## Open models

`codex_harness/assets/policies/open-model.example.toml` activates Codex's `--oss --local-provider ollama` path. `lmstudio` is the other accepted value. Supply an installed model name and verify tool/reasoning support. These paths are structurally supported but not live-tested here; there is no claim of parity with hosted Codex. A future provider can implement the adapter's `run`/`advise` contract without changing verification or pack promotion.

## Observability

Local JSON/JSONL is the default; no telemetry is uploaded automatically. If you add Langfuse or another tracing backend, send sanitized run IDs, phase/model names, usage, latency and scores, then opt in separately to prompt/code capture. Do not assume that `.gitignore` redacts logs. Raw artifacts can contain source code, private URLs, tool output and credentials printed by target programs.
