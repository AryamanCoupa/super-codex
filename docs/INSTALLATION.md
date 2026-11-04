# Install SuperCodex without cloning the repository

Install a published release directly with pipx, then run `sc` from any project. pipx manages an isolated Python environment and exposes the CLI commands on your PATH; it accepts wheel and archive URLs. [Official pipx documentation](https://pipx.pypa.io/stable/).

Packages are distributed through [AryamanCoupa/super-codex Releases](https://github.com/AryamanCoupa/super-codex/releases). Use a version with completed release assets. The package is not published to PyPI; do not use `pipx install super-codex-harness` yet. Maintainers can follow [the release guide](RELEASING.md) to publish new versions.

This checkout contains the **unreleased 0.5.6 development build**. Its native Codex interface loads the operator, bundled skills and a lightweight per-turn skill reminder. Test it with `pipx install --force .` from this checkout, or `pipx install --force /absolute/path/to/a/built.whl`. Published examples below intentionally select 0.5.0; do not use a 0.5.6 download URL until its assets exist. Version 0.5.0 starts the managed controller by default and lacks the later mode selectors.

## Prerequisites

- Python **3.11 or newer**, Git, and pipx.
- Codex CLI installed on your PATH, with normal Codex authentication. Local checks use Codex 0.164.0. Hook reminders need compatible UserPromptSubmit support; if skills-hook inspection is unavailable, startup warns and uses bootstrap guidance. Explicit answer routing requires compatible hooks. SuperCodex does not install Codex or provide model access.
- macOS or Linux. Native Windows is unsupported; running under WSL remains unverified.

On macOS with Homebrew, install pipx with:

```bash
brew install pipx
pipx ensurepath
```

On Linux, use your distribution's pipx package or another method in the [official pipx installation guide](https://pipx.pypa.io/stable/how-to/install-pipx.html), then run `pipx ensurepath`. Reopen your terminal after PATH changes. If pipx selects a Python older than 3.11, add `--python python3.11` to the install command, or supply the absolute path to a supported interpreter.

## Install a released version

Install the published `v0.5.0` release wheel:

```bash
pipx install "https://github.com/AryamanCoupa/super-codex/releases/download/v0.5.0/super_codex_harness-0.5.0-py3-none-any.whl"
pipx ensurepath
```

This installs `sc`, `supercodex`, `super-codex` and `ch`. You do not need a local source checkout. Python and the prerequisite tools are still required; the wheel is an installable Python package, not a standalone native executable.

Check the installation from a new terminal:

```bash
sc --version
sc doctor
codex login                 # only if Codex is not already authenticated
sc demo --output /tmp/supercodex-demo-01
```

The demo is offline and makes no model calls; choose a new output directory each time. `doctor` checks local prerequisites, not model access or MCP authentication.

Then open your project:

```bash
cd /path/to/your-project
sc
# Or supply a task immediately:
supercodex "Fix the pagination bug and verify the edge cases"
```

In the 0.5.6 development build, `sc` opens the real Codex terminal with normal layout, streaming and authentication. A private bootstrap supplies the operator, selected pack/policy defaults and skill catalog. The default `skills` hook suggests up to three keyword-matched skills per message and tells Codex to read and apply relevant instructions in the current session. Research uses existing web/MCP tools; coding edits and runs checks directly. The hook makes no model calls, saves no per-turn prompt copies and requires no managed receipt. Reading guidance alone does not establish task completion.

Use `sc skills` to list the twelve bundled task skills, `sc skills --search "GitHub repositories"` to search their names/descriptions, `sc skills github-context` to read one skill, or `sc skills --json` for catalog metadata. Search also accepts `--json`. These inspection commands make no model calls. The search covers bundled metadata only, so no match does not mean a relevant native or project skill is unavailable. See [skill selection and coverage](AGENT_USAGE.md#bundled-skill-coverage).

```bash
# Default native work:
sc "Research current AI news with sources"
sc "Find repositories matching my query"
sc --prompt-hook skills             # default: apply relevant skills in native Codex
sc --prompt-hook answer             # opt in to exact-prompt managed routing
sc --prompt-hook off                # bootstrap guidance without per-turn reminders
sc --no-prompt-hook                 # alias for --prompt-hook off

# Optional managed workflows in the 0.5.6 development build:
sc answer "Research this question"
sc answer --prompt-file /path/to/message.txt --context-file /path/to/relevant-context.txt
sc answer "Fix the pagination bug and verify its contract" --pack backend
sc --managed "Fix the pagination bug and verify its contract"
sc --managed --task /path/to/task.json --patch-only
sc answer --research-mcp github "Find repositories matching my query"
```

`answer` remains an optional noninteractive controller entry point, also used by explicit `--prompt-hook answer`. It uses buffered Codex exec and accepts a quoted prompt or UTF-8 `--prompt-file` plus separate bounded context. Managed questions produce advisory receipts. Managed coding prepares a task, runs isolated workers/checks and applies only a passing patch to a clean checkout at the original commit. `--patch-only` preserves the patch for review; `start --managed --task` skips preparation for a reviewed contract. Default skill reminders require none of these extra calls or receipts. [Modes, skills and accounting](AGENT_USAGE.md#run-with-sc).

Native research can use the connections already available in Codex, without a clean Git checkout or a child process. The GitHub, Atlassian and research skills explain tool discovery, source verification, pagination and access limits. Separately selected `--research-mcp` or private research configuration is needed only for explicit managed research. Managed preparation from a directory without commits uses an empty private workspace and does not inspect that directory's files. [Research connection setup](INTEGRATIONS.md#research-from-any-directory).

`--native` remains an alias for the default 0.5.6 interface. On `start`, `--task`, `--patch-only` and `--no-stream` select managed mode for compatibility and conflict with explicit `--native`. Research flags belong to `--prompt-hook answer`, `answer` or `start --managed`; skills/off modes use native Codex connections or `--mcp`. A quoted task in native mode opens an interactive session; use `sc answer "PROMPT"` for a noninteractive request.

## Install from a published tag before a wheel is available

A GitHub source archive is another no-clone option:

```bash
pipx install "https://github.com/AryamanCoupa/super-codex/archive/refs/tags/v0.5.0.zip"
```

The tag must exist and contain this Python package. pipx downloads the archive and builds it in its own environment; build dependencies may be downloaded. A tagged wheel is preferable when the release already provides one. Use a versioned tag rather than a moving branch for repeatable installation.

## Upgrade or return to a previous version

Use the URL of the desired published release with `--force`. Replace both version components below when choosing another release:

```bash
pipx install --force "https://github.com/AryamanCoupa/super-codex/releases/download/v0.5.0/super_codex_harness-0.5.0-py3-none-any.whl"
sc --version
```

For an installation from a versioned URL, do not expect `pipx upgrade` to discover another GitHub release automatically: select the new release URL explicitly. The same command with a previous release URL selects that older version. These operations affect the installed application, not your project repositories or saved harness artifacts. See [pipx's install/upgrade options](https://pipx.pypa.io/stable/reference/cli.html).

Exit an already running Codex session, then start `sc` again after upgrading. Use `/quit` to leave a managed controller prompt. A running process keeps its old implementation; installing a new wheel does not update that session in place.

The default 0.5.6 interface uses Codex's streaming and direct tools. Per-turn skill reminders add guidance, not an extra model call. Native answers/checks remain native evidence. Explicit answer routing uses buffered child output while the outer UI still streams; child receipts exclude the outer operator's inference cost. Skills and hooks guide the model rather than guaranteeing compliance or better accuracy.

The launcher uses one local app-server inspection, without a model turn, to validate its exact owned hook and supply session-scoped trust. Existing user hooks and global settings remain unchanged. In default skills mode, failed inspection produces a visible warning and startup continues with bootstrap guidance; runtime reminder failures are nonblocking diagnostics. Explicit answer mode instead stops when registration fails. `--prompt-hook off` and its `--no-prompt-hook` alias skip registration. Dry runs start no hook/model process and write no files. Skill files stay in the installed package rather than being copied into the target checkout.

An explicit `sc --managed` session streams public response deltas and tool activity through Codex app-server. Preparation's internal task JSON stays hidden; a quiet model or tool produces a waiting notice after ten seconds. Use `sc --managed --no-stream` for buffered exec if your Codex version or authentication is incompatible. The live interface was checked against Codex CLI 0.164.0; older versions may need an upgrade.

The managed live transport uses a temporary Codex home to exclude inherited MCP servers, hooks and settings. It uses file-based access credentials or provider environment variables; valid refresh tokens are never copied, and the native login is not changed. If authentication expires, refresh it through normal Codex and restart the managed request, or use `--managed --no-stream`. Keyring-only authentication and MCP OAuth credential stores are currently unsupported by this isolated live transport. These limitations do not change the default native interface's existing Codex authentication. Configuring a server still does not grant access automatically.

If you separately installed the operator skill for ordinary Codex sessions, refresh its managed copy after an upgrade:

```bash
sc agent install --user --update
```

This is unnecessary for sessions launched with `sc`, which load current packaged guidance directly, or for `answer` and `sc --managed`, which use the installed controller implementation. Locally edited skills are preserved by refusing to overwrite them.

## Optional experimental dependencies

The core package has no runtime Python dependencies. Only install extra packages for experiments you intend to use. Add them to the same pipx environment as the CLI:

```bash
# Upstream GEPA engine used by this release:
pipx inject super-codex-harness "gepa==0.1.4"

# Optional local training stack; downloads substantial dependencies:
pipx inject super-codex-harness "trl==1.17.1" "peft==0.21.0"
```

Dependency versions above match the 0.5.6 development build. Follow the target release's instructions when upgrading. [pipx CLI reference](https://pipx.pypa.io/stable/reference/cli.html), [experiment guide and training limitations](EXPERIMENTS.md).

Playwright, GitHub, Atlassian and custom MCP services have their own runtime/authentication requirements. Configure only the services needed for your task using [the integrations guide](INTEGRATIONS.md); installing the CLI does not connect those accounts automatically.

## Troubleshooting and removal

If the command is not found, run `pipx ensurepath`, reopen the terminal, and inspect `pipx list`. On the default macOS/Linux installation, `~/.local/bin/sc --version` can test the executable directly. If the download returns 404, check the tag and asset filename on the [Releases page](https://github.com/AryamanCoupa/super-codex/releases); a newly pushed tag may still be building its packages.

After upgrading, restart `sc` and refresh a separately installed operator skill with `sc agent install --user --update`; running sessions retain old instructions. Version 0.5.5 defaulted to `answer` routing. Version 0.5.6 defaults to native skill reminders and leaves that behavior available through `--prompt-hook answer`. A skills-hook warning means bootstrap guidance remains available; it does not trigger a child answer job. Use `--prompt-hook off` to disable reminders explicitly.

If an explicitly selected answer/managed request reports `Operation not permitted` during child startup, inspect its receipt and use the host's normal approval flow for the same command when available. Service credentials are a separate requirement. Do not disable sandboxing or approvals, silently substitute native work or claim the failed managed request succeeded. Default skills mode avoids that child execution path.

If an explicitly selected managed coding task reports a dirty source, inspect `git status` and commit only your intended changes or choose a clean checkout. If preparation cannot identify meaningful checks, supply a reviewed task JSON or dedicated pack. Inspect the receipt for the exact reason. Native skill-driven coding can work in an existing checkout while preserving unrelated edits; it does not require changing user work to satisfy managed-run prerequisites.

The local development build includes the 0.5.1 fix for managed research from directories without Git commits. If an older running session reports `fatal: Needed a single revision` for a research question, install this checkout and restart it; the published 0.5.0 wheel does not include that fix. Managed coding still needs `--repo /path/to/a/clean-committed-project`. A missing research connection is a separate setup issue; configure it using [the integrations guide](INTEGRATIONS.md#research-from-any-directory).

Remove the application with:

```bash
pipx uninstall super-codex-harness
```

Project changes, saved sessions under `~/.local/state/super-codex`, and a separately installed operator skill remain in place. Remove those separately only if you no longer need them.
