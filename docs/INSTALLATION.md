# Install SuperCodex without cloning the repository

Install a published release directly with pipx, then run `sc` from any project. pipx manages an isolated Python environment and exposes the CLI commands on your PATH; it accepts wheel and archive URLs. [Official pipx documentation](https://pipx.pypa.io/stable/).

Packages are distributed through [AryamanCoupa/super-codex Releases](https://github.com/AryamanCoupa/super-codex/releases). Use a version with completed release assets. The package is not published to PyPI; do not use `pipx install super-codex-harness` yet. Maintainers can follow [the release guide](RELEASING.md) to publish new versions.

This checkout contains the **unreleased 0.5.5 development build**. Its native Codex interface loads the operator skill, a catalog of task skills and a per-message hook that directs requests through `answer`. Test it with `pipx install --force .` from this checkout, or `pipx install --force /absolute/path/to/a/built.whl`. The published examples below intentionally select 0.5.0; do not use a 0.5.5 download URL until its assets exist. Version 0.5.0 starts the managed controller by default and has neither the later `answer` command nor the `--managed` selector.

## Prerequisites

- Python **3.11 or newer**, Git, and pipx.
- Codex CLI installed on your PATH, with your normal Codex authentication. Local checks use Codex 0.164.0. Default 0.5.5 startup needs compatible UserPromptSubmit hooks and hook inspection; `--no-prompt-hook` explicitly skips that requirement. SuperCodex does not install Codex or provide model access.
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

In the 0.5.5 development build, `sc` opens the real Codex terminal with its normal layout and authentication. A private bootstrap supplies the operator skill, selected pack/policy defaults and task-skill catalog. Each user message receives a hook-supplied `answer --prompt-file` command preserving the original text, and the operator must run it and inspect its receipt. A quoted initial request routes once; startup without a task simply waits. The native interface streams its own responses, while delegated `answer` currently uses buffered exec and returns its text after the child process completes. `skill-discovery` remains available within the selected workflow.

Use `sc skills` to list the twelve bundled task skills, `sc skills --search "GitHub repositories"` to search their names/descriptions, `sc skills github-context` to read one skill, or `sc skills --json` for catalog metadata. Search also accepts `--json`. These inspection commands make no model calls. The search covers bundled metadata only, so no match does not mean a relevant native or project skill is unavailable. See [skill selection and coverage](AGENT_USAGE.md#bundled-skill-coverage).

```bash
# Default native interface with per-message answer routing:
sc "Research current AI news with sources"
sc "Find repositories matching my query"
sc --research-mcp github "Find repositories matching my query"
sc --no-prompt-hook                 # skills-only native tools, no answer routing

# Optional managed workflows in the 0.5.5 development build:
sc answer "Research this question"
sc answer --prompt-file /path/to/message.txt --context-file /path/to/relevant-context.txt
sc answer "Fix the pagination bug and verify its contract" --pack backend
sc --managed "Fix the pagination bug and verify its contract"
sc --managed --task /path/to/task.json --patch-only
sc answer --research-mcp github "Find repositories matching my query"
```

`answer` is the noninteractive controller entry point used by default routing and can also be run directly. It accepts a quoted prompt or UTF-8 `--prompt-file` and separate bounded `--context-file` input. Managed questions produce advisory receipts. Managed coding prepares a task, runs isolated workers and checks, then applies only a passing patch to a clean checkout at the original commit. `--patch-only` preserves the patch for review; `start --managed --task` skips model preparation for a reviewed contract. `--no-prompt-hook` selects skills-only native work without these delegated calls. [Modes, skills and accounting](AGENT_USAGE.md#run-with-sc).

Delegated research uses separately selected `--research-mcp` settings or the private research configuration, including when invoked by the hook. Outer native connections are not automatically inherited by the managed child. GitHub, Atlassian and research skills explain discovery, source verification, pagination and access limits. Preparation from a directory without commits uses an empty private workspace and does not inspect that directory's files. With `--no-prompt-hook`, research uses ordinary Codex connections directly. [Research connection setup](INTEGRATIONS.md#research-from-any-directory).

`--native` remains an explicit alias for the default 0.5.5 interface, including its hook. On `start`, `--task`, `--patch-only` and `--no-stream` also select managed mode for compatibility; they cannot be combined with explicit `--native`. Research flags configure delegated requests in the default hooked interface or can be passed to `answer` and `start --managed`; they conflict with `--no-prompt-hook`. A quoted task in native mode still opens an interactive session; use `sc answer "PROMPT"` for a noninteractive single request.

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

The default 0.5.5 interface uses Codex's own terminal streaming around delegated `answer` calls. Those child calls currently buffer output. Routing adds model work beyond the native operator, whose inference cost is not included in the child receipt. Skills-only `--no-prompt-hook` uses native tools directly and does not produce managed receipts. Hook instructions guide the model; actual command results establish whether routing was followed.

The 0.5.5 launcher inspects the exact owned hook with a local app-server process, without a model turn, and registers its definition and matching trust hash only for the session. Existing user hooks and global configuration remain unchanged. Failed inspection stops launch visibly; choose `--no-prompt-hook` explicitly for skills-only startup. Dry runs do not inspect hooks, start hook/model processes or write files. No skill files are copied into the target checkout by `sc`; catalog paths point into the installed package.

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

Dependency versions above match the 0.5.5 development build. Follow the target release's instructions when upgrading. [pipx CLI reference](https://pipx.pypa.io/stable/reference/cli.html), [experiment guide and training limitations](EXPERIMENTS.md).

Playwright, GitHub, Atlassian and custom MCP services have their own runtime/authentication requirements. Configure only the services needed for your task using [the integrations guide](INTEGRATIONS.md); installing the CLI does not connect those accounts automatically.

## Troubleshooting and removal

If the command is not found, run `pipx ensurepath`, reopen the terminal, and inspect `pipx list`. On the default macOS/Linux installation, `~/.local/bin/sc --version` can test the executable directly. If the download returns 404, check the tag and asset filename on the [Releases page](https://github.com/AryamanCoupa/super-codex/releases); a newly pushed tag may still be building its packages.

After upgrading, restart `sc` and refresh any separately installed operator skill with `sc agent install --user --update`; running sessions retain their old bootstrap. Version 0.5.4 used skills-only startup, while 0.5.5 restores per-message `answer` routing. If hook inspection fails, use a compatible Codex installation or explicitly start `sc --no-prompt-hook` for skills-only work.

If a delegated request reports `Operation not permitted` during child startup, inspect its receipt. The outer host sandbox may require its normal approval flow to execute that same command; service authentication is a separate requirement. The hook grants no extra access and does not disable sandbox or approval settings. Report the blocker when approval is unavailable. Do not silently substitute native work or describe the failed request as completed.

If a managed coding task reports a dirty source, including one routed by the hook, inspect `git status` and commit only your intended changes or choose a clean checkout. If preparation cannot identify meaningful checks, supply a reviewed task JSON or dedicated pack. Inspect the receipt for the exact reason. Explicit skills-only native coding can work in an existing checkout while preserving unrelated edits; do not alter unrelated work merely to satisfy managed prerequisites.

The local development build includes the 0.5.1 fix for managed research from directories without Git commits. If an older running session reports `fatal: Needed a single revision` for a research question, install this checkout and restart it; the published 0.5.0 wheel does not include that fix. Managed coding still needs `--repo /path/to/a/clean-committed-project`. A missing research connection is a separate setup issue; configure it using [the integrations guide](INTEGRATIONS.md#research-from-any-directory).

Remove the application with:

```bash
pipx uninstall super-codex-harness
```

Project changes, saved sessions under `~/.local/state/super-codex`, and a separately installed operator skill remain in place. Remove those separately only if you no longer need them.
