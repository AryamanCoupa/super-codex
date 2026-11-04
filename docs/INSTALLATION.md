# Install SuperCodex without cloning the repository

Install a published release directly with pipx, then run `sc` from any project. pipx manages an isolated Python environment and exposes the CLI commands on your PATH; it accepts wheel and archive URLs. [Official pipx documentation](https://pipx.pypa.io/stable/).

Packages are distributed through [AryamanCoupa/super-codex Releases](https://github.com/AryamanCoupa/super-codex/releases). Use a version with completed release assets. The package is not published to PyPI; do not use `pipx install super-codex-harness` yet. Maintainers can follow [the release guide](RELEASING.md) to publish new versions.

## Prerequisites

- Python **3.11 or newer**, Git, and pipx.
- Codex CLI installed on your PATH, with your normal Codex authentication. SuperCodex reuses that login; it does not install Codex or provide model access.
- macOS or Linux. Native Windows is unsupported; running under WSL remains unverified.

On macOS with Homebrew, install pipx with:

```bash
brew install pipx
pipx ensurepath
```

On Linux, use your distribution's pipx package or another method in the [official pipx installation guide](https://pipx.pypa.io/stable/how-to/install-pipx.html), then run `pipx ensurepath`. Reopen your terminal after PATH changes. If pipx selects a Python older than 3.11, add `--python python3.11` to the install command, or supply the absolute path to a supported interpreter.

## Install a released version

Install the `v0.5.0` release wheel:

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

The default controller prepares a task contract, runs the harness, verifies the patch independently and applies it only to a clean checkout at the original commit. Use `sc --task /path/to/task.json` to provide your own contract, or add `--patch-only` to leave the source unchanged. Missing checks or failed verification stop the task. After an applied patch, review and commit your intended changes before another coding task. `sc --config architect` selects the stronger planner/smaller implementer policy. [Controller options, receipts and accounting](AGENT_USAGE.md#run-with-sc).

`sc --native` explicitly opens the native Codex terminal interface with advisory SuperCodex guidance. It does not enforce harness execution. An installed operator skill in an ordinary Codex session is also guidance; use the default controller when you need enforced orchestration.

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

If you separately installed the operator skill for ordinary Codex sessions, refresh its managed copy after an upgrade:

```bash
sc agent install --user --update
```

This is unnecessary for the default controller, which uses the current installed implementation. Native sessions launched with `sc --native` load current packaged guidance directly. Locally edited skills are preserved by refusing to overwrite them.

## Optional experimental dependencies

The core package has no runtime Python dependencies. Only install extra packages for experiments you intend to use. Add them to the same pipx environment as the CLI:

```bash
# Upstream GEPA engine used by this release:
pipx inject super-codex-harness "gepa==0.1.4"

# Optional local training stack; downloads substantial dependencies:
pipx inject super-codex-harness "trl==1.17.1" "peft==0.21.0"
```

Dependency versions above match SuperCodex 0.5.0. Follow the target release's instructions when upgrading. [pipx CLI reference](https://pipx.pypa.io/stable/reference/cli.html), [experiment guide and training limitations](EXPERIMENTS.md).

Playwright, GitHub, Atlassian and custom MCP services have their own runtime/authentication requirements. Configure only the services needed for your task using [the integrations guide](INTEGRATIONS.md); installing the CLI does not connect those accounts automatically.

## Troubleshooting and removal

If the command is not found, run `pipx ensurepath`, reopen the terminal, and inspect `pipx list`. On the default macOS/Linux installation, `~/.local/bin/sc --version` can test the executable directly. If the download returns 404, check the tag and asset filename on the [Releases page](https://github.com/AryamanCoupa/super-codex/releases); a newly pushed tag may still be building its packages.

If a coding task reports a dirty source, inspect `git status` and commit only your intended changes or choose a clean checkout. If preparation cannot identify meaningful checks, supply a reviewed task JSON or a dedicated pack with executable acceptance criteria. Inspect the printed receipt path for the exact reason. Neither condition triggers a fallback to native editing.

Remove the application with:

```bash
pipx uninstall super-codex-harness
```

Project changes, saved sessions under `~/.local/state/super-codex`, and a separately installed operator skill remain in place. Remove those separately only if you no longer need them.
