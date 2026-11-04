# Use SuperCodex skills from any project

In **SuperCodex 0.5.6**, `sc` / `supercodex` opens native Codex with SuperCodex's operator skill, twelve task skills and any selected task pack. A lightweight UserPromptSubmit hook suggests up to three bundled skills from the message's keywords and tells the current model to read and apply relevant instructions. Research uses native web/MCP connections; coding can inspect, edit and check changes directly. This default hook starts no model, saves no per-turn prompt copies and requires no managed receipt.

Skills guide behavior rather than enforcing it. They call for scoped work, current sources, meaningful verification and honest reporting. Explicit `answer`, `--managed`, `run`, evaluation and pack commands remain available when their additional orchestration is useful. Follow the [installation guide](INSTALLATION.md) to install or upgrade to 0.5.6 without cloning the repository.

## Run with sc

Follow the [installation guide](INSTALLATION.md), then open your project:

```bash
cd /path/to/project
sc
sc "Find the repositories matching my request"
sc "Fix the export bug and verify its contract"
sc --repo /path/to/project --pack backend
sc --pack frontend --mcp playwright "Fix the checkout interaction"
sc --dry-run
```

`supercodex`, `super-codex` and `ch` accept the same arguments. No subcommand means `start`. Quote a multiword initial request; if the whole request is an existing command name, use explicit `sc start "run"`. `sc --help` shows command groups, `sc start --help` shows launch options, and `sc --version` reports the installed version.

With no task, Codex reads the private bootstrap and waits. A quoted initial request is handled with relevant skills after initialization. The bootstrap supplies the catalog, selected pack/policy defaults and optional CLI templates; the per-turn hook reinforces skill application on later messages. Its shortlist is only a candidate set: check the broader native and bundled catalogs when needed, read selected instructions and complete the actual task. Already-read unchanged instructions can be reused. Name skills actually applied and report evidence; loading or listing a skill is not task completion.

For a defect, `debug-with-evidence` calls for investigating the failure, repairing its cause and verifying behavior. `economical-delegation` covers useful multi-agent work: divide independent subtasks only when it adds value, assign bounded work using available delegation tools and check the results. The hook does not start agents automatically, decide model suitability or prove that a skill was followed.

For research, discover the actual connected tools, use their supported search/read operations, handle pagination and access limits, and cite the retrieved sources. A repository lookup or news question does not need a clean Git checkout or a child Codex process. For coding, preserve unrelated edits, reproduce the issue when practical, make a scoped change, inspect its diff and run meaningful checks. Report exactly what was tested and any remaining uncertainty. A native test result is not a managed-run receipt.

## Bundled skill coverage

The catalog is available from the operator skill even without a selected pack. Skills are loaded on demand to avoid putting every instruction into every task's context. Inspect the installed catalog or read a skill without starting a model:

```bash
sc skills
sc skills --search "GitHub repositories"
sc skills --search "latest AI news" --json
sc skills github-context
sc skills skill-discovery
sc skills --json
```

The list includes each skill's name, description and installed path; a name selects its full instructions. `--search` matches task keywords against bundled skill names and descriptions and returns a shortlist with those same paths. It does not search third-party or project skills, inspect all instruction bodies, install anything or invoke a model. Keyword matches are candidates to review, not a semantic guarantee. An empty result means no bundled keyword match; a relevant skill may still be available in the native session catalog. Use a few concrete keywords, read the shortlisted instructions, then perform the actual task.

| Skill | Use it for |
|---|---|
| `skill-discovery` | Selecting and reading relevant native or bundled skills for the current task |
| `research-with-sources` | Current research, source quality, dates, citations and uncertainty |
| `github-context` | Repository discovery, code/issue/PR evidence, pagination and access limits |
| `atlassian-context` | Issue and documentation context through available Atlassian tools |
| `browser-verify` | Browser exploration and evidence with Playwright |
| `plan-and-context` | Task scope, relevant context, constraints and acceptance criteria |
| `debug-with-evidence` | Reproduction, diagnosis, targeted repair and evidence |
| `verify-changes` | Behavior checks, diff review and honest completion reports |
| `economical-delegation` | Bounded delegation and stronger-model escalation when they add value |
| `evaluate-harness` | Representative evaluation and cost/quality comparisons |
| `select-experiment` | Choosing an optional experiment from the actual task's evidence |
| `curate-learning-data` | Reviewing verified evidence for reusable learning data |

The catalog does not grant permissions or install MCP connections. Existing user instructions, project rules, tool approvals and credentials still apply. No skill can guarantee accuracy or savings; use the reported evidence to assess the result.

## Optional harness commands

Discover arguments before running an unfamiliar command:

```bash
super-codex commands
super-codex commands answer
super-codex commands experimental router train
super-codex commands pack --json
```

Command discovery makes no model calls. Use the managed workflows when the user requests a receipt or isolated verification, when comparing strategies, or when a recurring task needs a reusable pack. Starting `sc` alone does not start those jobs, and the operator should not introduce extra model calls merely because a command exists.

`answer` is an explicit one-request controller entry point, useful for automation or a requested managed research receipt:

```bash
super-codex answer "Research this question" --repo /path/to/project
super-codex answer --prompt-file /path/to/message.txt \
  --context-file /path/to/relevant-context.txt \
  --repo /path/to/project --config /path/to/policy.json
super-codex answer "Find matching repositories" --research-mcp github
```

It uses buffered Codex exec and does not open another interactive session. Supply either a quoted prompt or a UTF-8 prompt file. Optional bounded context is separate from the original request. Questions receive advisory receipts; coding requests go through the controller's verification gates. An advisory receipt records execution, not proof that every factual claim is correct. `answer --dry-run` previews settings without invoking a model. Default skills mode does not require it; explicit `--prompt-hook answer` makes the supplied command and receipt part of each request's workflow.

## Enforce a task with the managed controller

`sc --managed` opens the controller's terminal prompt. `sc --managed "TASK"` runs one request and can be used from a noninteractive shell. Each submitted coding request follows this path:

1. A read-only Codex preparation call inspects a disposable source clone and proposes a structured task with acceptance commands. `--task PATH` skips this call and uses your explicit task JSON.
2. The controller validates the contract and preserves selected pack checks and protected paths. Auto-prepared tasks also protect existing tracked files under `test`, `tests` or `__tests__`, Python `test_*.py`/`*_test.py` files, and JavaScript-style `.test.`/`.spec.` files. Explicit `--task` uses your own protection contract. Missing checks or invalid preparation stop the task. Review the chosen acceptance criteria: JSON validation cannot prove their assertions are sufficient.
3. The existing runner executes the selected policy in an isolated clone. It performs baseline checks, implementation, bounded repair/escalation, and any configured planning/review. A separate clean clone verifies the candidate.
4. A receipt records what actually happened. A passing patch is applied only if the target is still clean at the recorded base commit and `git apply --check` succeeds. `--patch-only` keeps the patch without applying it.

An explicit managed session streams public response text and tool activity through Codex app-server. The internal preparation contract remains hidden, and a final receipt distinguishes advisory text from verified code. Text arriving early does not indicate acceptance. Use `sc --managed --no-stream` to select buffered Codex exec when needed for compatibility; an error never triggers a silent transport retry. Keyring-only authentication and MCP OAuth stores are unsupported by the isolated live transport. See [authentication and version compatibility](INSTALLATION.md).

There is no silent fallback to native editing. Failed verification never produces an applied patch. This is deterministic workflow enforcement for trusted local projects, not a security sandbox against hostile model output or test code. Setup and verifier commands are executable local code; inspect contracts from untrusted sources before running them.

A recognized unittest report of zero collected tests is rejected regardless of Python's exit code. Other test frameworks and custom assertion files need appropriate checks and `protected_paths`; the conventional-file guard is not universal test discovery. Auto-protection freezes existing files, so new acceptance tests can still be added unless a pack protects their entire directory.

Managed coding requires a clean, committed Git checkout. After an accepted patch is applied, review and commit the intended changes before the next coding task, or use another clean checkout. SuperCodex does not discard changes or create commits to satisfy this prerequisite. Managed research questions can run from any directory. Without a committed target, preparation uses an empty private Git workspace; it does not initialize the selected directory, copy its files, or claim to inspect them. A coding request in that situation receives guidance to select a clean committed project with `--repo`.

The selected pack's policy is preserved by default, or `balanced` is used without a pack. Explicit `--config` overrides it. In managed mode, `--model` changes the implementer and default preparation model; `--operator-model` changes only preparation. Preparation uses the implementer by default, avoiding an extra strong-model call merely because the policy also configures a planner. The controller disables inherited user configuration for all its model calls, including when a policy requests it. `--mcp` and task-pack MCP servers go to workers. Separately selected `--research-mcp` or private research configuration goes only to preparation, not to workers, planners or reviewers. Authentication support depends on the selected transport. See [integration settings](INTEGRATIONS.md) and [managed live transport limits](INSTALLATION.md).

Choose a dedicated harness explicitly with `--pack`, or discover candidates with `sc pack list`, `sc pack inspect NAME` and `sc pack suggest TASK --repo REPO`. Parallel workers, learned routing, memory, ACE/GEPA and other experiments remain separate, opt-in workflows. Their availability does not mean they ran on every request.

## Check the evidence

Private session artifacts live under `~/.local/state/super-codex/sessions/<id>` by default; `--output-root` chooses another location. Native startup stores its bootstrap, worker defaults and hook configuration/status. The default skills hook adds no per-turn prompt/context files or receipts. Explicit answer routing captures exact messages and bounded recent managed-answer context privately; each delegated request writes its own receipt under the supplied artifact root. Follow the printed receipt path. Merely opening Codex or activating a hook does not create a verified-run result. Keep session artifacts out of public repositories.

The receipt distinguishes `harness_run`, `verified` and `applied`. It includes preparation accounting, the run result path and actual stage evidence, combined token/cost completeness, and the task/base commit/patch hash when available. Inspect the referenced run's checks and `accepted.patch` when assessing the result. A command list, selected policy name or model's claim of success is not substitute evidence.

If patch application is interrupted after it starts, `applied` is null and `application_status` is `unknown`: inspect the source's Git status and diff before retrying. A saved `started` application status after an abrupt process termination also needs this inspection.

Capability questions and research answers are advisory, not verified coding outcomes. `answer` research receipts say that no coding run was verified and record actual selected MCP calls with server, tool and completion status. Native research is the default and uses ordinary Codex tools directly; it does not generate a SuperCodex receipt. Use `answer` only when a managed research run is useful or requested. An available server name does not prove that a lookup happened. Missing tools or authentication should produce a concrete blocked explanation instead of an invented answer. See [research configuration](INTEGRATIONS.md#research-from-any-directory).

The preparation sandbox is read-only for local commands. Remote MCP permissions are controlled by the server and credentials; a tool allow-list cannot restrict read/write operations hidden behind the same tool name. Use appropriately scoped research connections.

Preparation and the subsequent run share each task's token, dollar and elapsed-time budget. Unknown preparation usage prevents later model stages; a configured dollar limit also needs known prices. Limits are soft at model-stage boundaries because usage arrives after a Codex turn. Each new REPL submission starts a new task budget: there is no cumulative session-wide financial cap. Receipts retain combined totals so the preparation call is not hidden from the cost comparison.

## Native configuration and permissions

```bash
sc
sc --repo /path/to/project --pack backend
sc --no-alt-screen "Inspect the existing implementation"
sc --native                         # explicit alias for the default interface
sc --prompt-hook skills              # default: per-turn skill application reminder
sc --prompt-hook answer              # opt in to exact-prompt answer routing
sc --prompt-hook off                 # bootstrap guidance only
sc --no-prompt-hook                  # alias for --prompt-hook off
```

Native mode inherits Codex configuration, login, plugins, skills, MCP servers, sandbox and approvals. A short prompt points to a private bootstrap file; the catalog points to bundled skill files in the installation. Existing higher-priority instructions remain intact. Explicit MCP presets override same-named servers for that session. The launcher does not copy skills into the target checkout or rewrite global Codex configuration.

The default `skills` hook is a lightweight reminder, not a child-task launcher. Registration uses one local app-server inspection without a model turn to validate the exact owned hook and its session-scoped trust hash. User hooks and global settings remain unchanged. If skills-hook registration is unavailable, the launcher visibly warns and continues with bootstrap guidance; runtime reminder errors are also nonblocking and diagnostic. `off` skips registration, while `--dry-run` starts no hook/model process and writes no files. Native permissions and user scope remain in force.

Explicit `--prompt-hook answer` retains exact-prompt routing: each user message receives an `answer --prompt-file` command that the operator must execute and verify through its receipt. The quoted initial task routes once; bootstrap initialization and managed workers are excluded from recursive routing. This mode stops on registration errors and does not silently replace failed requests with native work. It uses buffered child output while the outer Codex UI streams normally. Host permission errors may need the normal approval flow for the same command; never weaken sandbox or approval settings. Its child receipts exclude outer-operator inference cost. Both hook modes deliver instructions, not a guarantee of model compliance.

`--native` cannot be combined with `--managed`. For compatibility, `--task`, `--patch-only` and `--no-stream` select managed mode. `--research-mcp` and `--research-mcp-config` configure explicit `--prompt-hook answer`, `answer` or `start --managed`; skills/off modes use existing native tools or selected `--mcp` integrations. Native connections are not automatically inherited by a managed child. See the [official configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).

## Install the operator skill once

After installing SuperCodex in a virtual environment, activate it or use the executable's absolute path. To let your top-level Codex agent use SuperCodex in any project:

```bash
/absolute/path/to/super-codex/.venv/bin/super-codex agent install --user
```

This writes only the operator skill under `~/.agents/skills/super-codex`. It does not change your shell startup files or global Codex configuration. Codex discovers this user skill across projects. Project-scoped installation is also available:

```bash
super-codex agent install --repo /absolute/path/to/another-project
```

That writes `.agents/skills/super-codex` inside the target project. It adds files, so commit the intended project skill before running a harness that requires a clean checkout. User-scoped installation avoids changing target repositories. These are supported local skill discovery locations in the [official Codex skill documentation](https://learn.chatgpt.com/docs/build-skills), checked with Playwright MCP on 2026-11-05. Codex normally detects new skills automatically; restart the session if it does not appear.

In Codex, ask for example:

> Use $super-codex to fix the pagination bug in this repository. Discover a suitable pack, define meaningful acceptance checks, and run the balanced policy. Write artifacts outside the repository and report the verified patch. Use at most 100,000 tokens; explain any observed overshoot.

The operator skill supplies the catalog and teaches Codex to read and apply relevant guidance, use native tools, verify changes and report evidence. It respects explicit answer routing when selected and explains managed runs, packs and evaluations. Installing this skill alone does not register a hook. It can perform authorized work without asking for confirmation merely because a skill is active; environment permissions and credentials still apply. Managed commands enforce their own workflows once invoked.

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

Every Codex implementation, preparation, planning and review invocation receives the current command inventory, absolute launcher and bundled skill catalog. Relevant instructions and full argument help are loaded on demand within the assigned task and budget. The adapter saves the effective prompt and hashes alongside the event log, and run records include a discovery-context hash. Routing and pack comparisons refuse to silently match new guidance against evidence collected without it.

The top-level operator can choose and run all applicable workflows. A worker already inside a managed run inherits `SUPERCODEX_WORKER=1`; CLI dispatch allows discovery, reports, inspection, suggestions and queries, while refusing `answer`, nested runs, training and mutations that would escape the parent's accounting. Workers can recommend another workflow in their handoff. Accounted delegation uses the top-level `teams`, `best-of-n` or `recursive` commands.

This marker is cooperative bookkeeping, not an OS security boundary: a process could unset it, use Python APIs directly, or filter inherited environment variables. The prompt also instructs workers to preserve it. Tests exercise normal subprocess inheritance; a live Codex skill-selection/command-choice benchmark has not been run.
