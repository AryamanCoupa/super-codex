# Let Codex operate SuperCodex from any project

Version 0.5 makes `sc` / `supercodex` a controlled coding entry point. The controller invokes the harness directly, so a model cannot silently substitute a native edit for the verified workflow. Command discovery remains available independently: `commands` walks the actual CLI parser, including nested experimental commands, arguments, choices and defaults. Discovery makes no model calls and is not evidence that a coding run happened.

```bash
super-codex commands
super-codex commands --json
super-codex commands experimental router train
super-codex commands pack --json
```

## Run with sc

Follow the [no-clone setup guide](INSTALLATION.md) to install a published wheel or tag archive. A local checkout can use `pipx install /path/to/super-codex` or its installed virtual environment. Then use:

```bash
cd /path/to/project
sc
sc "Implement the export endpoint and verify its contract"
sc --repo /path/to/project --pack backend --config architect
sc --pack frontend --mcp playwright --mcp github "Fix the checkout interaction"
sc --task /absolute/path/to/task.json --patch-only
sc --dry-run
```

`supercodex`, `super-codex` and `ch` accept the same arguments. No subcommand means `start`. Existing commands retain their meaning (`sc run`, `sc pack list`, `sc experimental best-of-n`). Quote a multiword task; if the whole task is an existing command name, use explicit `sc start "run"`. `sc --help` shows the command groups; `sc start --help` shows controller and native options. `sc --version` reports the harness version.

With no task, `sc` opens a simple terminal prompt owned by SuperCodex. A quoted task runs once, including from a noninteractive shell. Each submitted coding request follows this path:

1. A read-only Codex preparation call inspects a disposable source clone and proposes a structured task with acceptance commands. `--task PATH` skips this call and uses your explicit task JSON.
2. The controller validates the contract and preserves selected pack checks and protected paths. Auto-prepared tasks also protect existing tracked files under `test`, `tests` or `__tests__`, Python `test_*.py`/`*_test.py` files, and JavaScript-style `.test.`/`.spec.` files. Explicit `--task` uses your own protection contract. Missing checks or invalid preparation stop the task. Review the chosen acceptance criteria: JSON validation cannot prove their assertions are sufficient.
3. The existing runner executes the selected policy in an isolated clone. It performs baseline checks, implementation, bounded repair/escalation, and any configured planning/review. A separate clean clone verifies the candidate.
4. A receipt records what actually happened. A passing patch is applied only if the target is still clean at the recorded base commit and `git apply --check` succeeds. `--patch-only` keeps the patch without applying it.

There is no silent fallback to native editing. Failed verification never produces an applied patch. This is deterministic workflow enforcement for trusted local projects, not a security sandbox against hostile model output or test code. Setup and verifier commands are executable local code; inspect contracts from untrusted sources before running them.

A recognized unittest report of zero collected tests is a verification error, even though unittest exits successfully. Other test frameworks and custom assertion files need appropriate checks and `protected_paths`; the conventional-file guard is not universal test discovery. Auto-protection freezes existing files, so new acceptance tests can still be added unless a pack protects their entire directory.

The source must be a clean, committed Git checkout. After an accepted patch is applied, review and commit the intended changes before the next coding task, or use another clean checkout. SuperCodex does not discard changes or create commits to satisfy this prerequisite.

The selected pack's policy is preserved by default, or `balanced` is used without a pack. Explicit `--config` overrides it. `--model` changes the implementer and default preparation model; `--operator-model` changes only preparation. Preparation uses the implementer by default, avoiding an extra strong-model call merely because the policy also configures a planner. The controller disables inherited user configuration for all its model calls, including when a policy requests it. Explicitly selected MCP servers are supplied to workers; read-only preparation does not receive them. Your Codex login remains usable. See [integration settings](INTEGRATIONS.md) for managed workers and experimental open-model providers.

Choose a dedicated harness explicitly with `--pack`, or discover candidates with `sc pack list`, `sc pack inspect NAME` and `sc pack suggest TASK --repo REPO`. Parallel workers, learned routing, memory, ACE/GEPA and other experiments remain separate, opt-in workflows. Their availability does not mean they ran on every request.

## Check the evidence

Private artifacts live under `~/.local/state/super-codex/sessions/<id>` by default; `--output-root` chooses another location. Each submitted request has a `turns/0001/receipt.json` (then `0002`, and so on), whose path is printed even when the request is blocked or fails. Keep session artifacts out of public repositories.

The receipt distinguishes `harness_run`, `verified` and `applied`. It includes preparation accounting, the run result path and actual stage evidence, combined token/cost completeness, and the task/base commit/patch hash when available. Inspect the referenced run's checks and `accepted.patch` when assessing the result. A command list, selected policy name or model's claim of success is not substitute evidence.

If patch application is interrupted after it starts, `applied` is null and `application_status` is `unknown`: inspect the source's Git status and diff before retrying. A saved `started` application status after an abrupt process termination also needs this inspection.

Capability questions and research answers are advisory, not verified coding outcomes. Their receipts say that no coding run was verified. Read-only preparation has no task MCP access; requests needing authenticated external research should use an explicitly chosen workflow or native mode and should not claim coding verification.

Preparation and the subsequent run share each task's token, dollar and elapsed-time budget. Unknown preparation usage prevents later model stages; a configured dollar limit also needs known prices. Limits are soft at model-stage boundaries because usage arrives after a Codex turn. Each new REPL submission starts a new task budget: there is no cumulative session-wide financial cap. Receipts retain combined totals so the preparation call is not hidden from the cost comparison.

## Explicit native Codex mode

```bash
sc --native
sc --native --repo /path/to/project --pack backend
sc --native --no-alt-screen "Inspect the existing implementation"
```

`--native` opens the real Codex terminal interface with SuperCodex operator guidance. This mode is advisory: it cannot force Codex to submit a harness job, and direct TUI edits have no independent verification. Native operator inference is outside child-run accounting. Use the default controller for enforced coding orchestration.

Native mode inherits Codex configuration, login, plugins, skills, MCP servers, sandbox and approvals. A short prompt points to a private bootstrap file, preserving existing higher-priority instructions and keeping long task/pack text out of launch arguments. Explicit MCP presets override same-named servers for that session. `--no-alt-screen` applies to this native interface. The native launcher does not install or overwrite the global operator skill. These options use the [official configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference), checked with Playwright MCP on 2026-11-05.

## Install the operator skill once

After installing SuperCodex in a virtual environment, activate it or use the executable's absolute path. To let your top-level Codex agent use SuperCodex in any project:

```bash
/absolute/path/to/super-codex/.venv/bin/super-codex agent install --user
```

This writes only the managed skill under `~/.agents/skills/super-codex`. It does not change your shell startup files or global Codex configuration. Codex discovers this user skill across projects. Project-scoped installation is also available:

```bash
super-codex agent install --repo /absolute/path/to/another-project
```

That writes `.agents/skills/super-codex` inside the target project. It adds files, so commit the intended project skill before running a harness that requires a clean checkout. User-scoped installation avoids changing target repositories. These are supported local skill discovery locations in the [official Codex skill documentation](https://learn.chatgpt.com/docs/build-skills), checked with Playwright MCP on 2026-11-05. Codex normally detects new skills automatically; restart the session if it does not appear.

In Codex, ask for example:

> Use $super-codex to fix the pagination bug in this repository. Discover a suitable pack, define meaningful acceptance checks, and run the balanced policy. Write artifacts outside the repository and report the verified patch. Use at most 100,000 tokens; explain any observed overshoot.

The skill teaches the operator to inspect the repository, create the task, discover packs and command arguments, invoke the selected workflow, and inspect results. It can run these commands within your instructions and budget without asking for confirmation merely because the skill is active. Environment permissions and missing credentials still apply. In an ordinary Codex session, the skill is advisory and the top-level agent translates your request into concrete commands. The default `sc` controller performs its own read-only preparation and enforces the subsequent execution path.

`agent show` prints the rendered skill before installation. Installed skills use an absolute Python/launcher pair, so they do not depend on Codex inheriting your shell alias or activated environment. Keep that installation in place. After moving the checkout, recreating its virtual environment or upgrading, reinstall with `agent install --user --update` (or the same `--repo`). Updates preserve locally edited/unmanaged skills by refusing to overwrite them. The rendered launcher is machine-specific; the packaged source template is portable.

## Run directly against a different path

You do not need to copy SuperCodex into the target repository:

```bash
# Optional shell setup for this terminal only:
export PATH="/absolute/path/to/super-codex/.venv/bin:$PATH"

super-codex doctor
super-codex run /absolute/path/to/task.json \
  --repo /absolute/path/to/another-project \
  --config balanced \
  --output /absolute/path/to/supercodex-artifacts/runs
```

The repository must have a committed revision and a clean working tree. The task needs real acceptance checks. An installed operator skill can prepare the task from your request; the [task format](../README.md#run-your-own-task) also supports writing one yourself. Optional `--pack backend` selects a bundled pack; use an absolute directory for your own pack or registry.

Path rules matter:

- `--repo` chooses the source checkout; it does not change how other CLI arguments resolve.
- Relative task, configuration, pack and output paths resolve from the shell's current directory. Absolute paths avoid ambiguity.
- Paths inside an evaluation suite resolve relative to that suite file.
- Setup and acceptance commands execute inside the cloned repository. `{python}` means the harness interpreter; use reproducible setup for project dependencies.
- Local pack discovery looks under the current directory. Use `pack list --root /path/to/packs` or an explicit pack path when elsewhere.
- Output must be outside the source or explicitly Git-ignored. Experimental commands require a fresh output directory.

A successful run writes `accepted.patch` under the reported artifact directory. The source checkout is unchanged by the run. Review it, then apply it when ready:

```bash
git -C /absolute/path/to/another-project apply --check /absolute/path/to/run/accepted.patch
git -C /absolute/path/to/another-project apply /absolute/path/to/run/accepted.patch
```

Without installing the package, an absolute launcher also works:

```bash
/path/to/python3.11 /path/to/super-codex/codex_harness/launch.py commands
```

## Awareness inside managed runs

Every Codex implementation, preparation, planning and review invocation receives a compact current command inventory and the absolute launcher. Full argument help is loaded on demand. The adapter saves the exact effective prompt and its hashes alongside the event log, and run records include a discovery-context hash. Routing and pack comparisons refuse to silently match new guidance against evidence collected without it.

The top-level operator can choose and run all applicable workflows. A worker already inside a managed run inherits `SUPERCODEX_WORKER=1`; CLI dispatch allows discovery, reports, inspection, suggestions and queries, while refusing nested runs, training and mutations that would escape the parent's accounting. Workers can recommend another workflow in their handoff. Accounted delegation uses the top-level `teams`, `best-of-n` or `recursive` commands.

This marker is cooperative bookkeeping, not an OS security boundary: a process could unset it, use Python APIs directly, or filter inherited environment variables. The prompt also instructs workers to preserve it. Tests exercise normal subprocess inheritance; a live Codex skill-selection/command-choice benchmark has not been run.
