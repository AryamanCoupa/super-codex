# Architecture and trust boundaries

`cli.py` loads task and policy configuration. `runner.py` owns Git snapshots, the repair loop, independent checks and artifacts. `codex.py` adapts the installed CLI. `advisors.py` adds optional read-only planning/review under shared budgets. `report.py` summarizes independent trials. `improve.py` versions task packs and enforces promotion gates. Python's standard library provides the core runtime.

`packs.py` handles deterministic discovery, inspection, task/repository suggestions and scaffolding. `optimize.py` orchestrates a single instruction proposal and paired holdout experiment, with aggregate accounting, a registry lock, holdout-consumption history and a durable audit. Proposal deltas preserve unrelated instructions; their empirical validation remains separate from deterministic application.

`session.py` resolves launch configuration and dispatches the default `sc`/`supercodex` path to `controller.py`. The controller owns the terminal prompt or single submitted task. It makes a read-only preparation call in a disposable clone, validates the structured task, preserves pack acceptance requirements, and invokes `runner.py` directly. Explicit `--task` skips model preparation. Preparation usage and elapsed time reduce the remaining run budget; missing accounting stops further model stages. A receipt records actual execution, verification and application separately. Only a passing patch can be applied, after checking the source remains clean at its frozen commit and `git apply --check` succeeds. Failures do not fall back to native editing.

Research/capability answers have advisory receipts and do not claim a verified coding result. This orchestration cannot prove that generated checks cover every requirement. Local setup/verifier commands are trusted code, not a hostile-code sandbox. After patch application, a later coding task requires a fresh clean committed source; the controller never commits or discards user work automatically.

Explicit `--native` retains the native interactive Codex interface. It creates a private bootstrap and worker policy/tool configuration, passes a short file-reading prompt and selected model/MCP overrides, and inherits the terminal plus native Codex permissions. This path is advisory: native inference is outside runner accounting, and direct edits are not verified merely because the session has SuperCodex guidance.

The core workflow is deterministic except model behavior and target commands. A run freezes a Git commit, clones it without sharing object storage, removes its remote, executes setup and baseline checks, then invokes Codex. Candidate patches include tracked modifications and new non-ignored files, compared to the frozen commit even if an agent creates a commit. Protected-path or changed-symlink violations fail the run.

Each verifier receives a fresh clone plus the candidate patch. It does not reuse ignored files, caches or processes from the worker. This catches accidental acceptance based on untracked/ignored helpers. Verifier commands come from the parent task definition. They are local host commands with a reduced environment, not a hardened remote grader. Test code can still be tricked through imported source, and a hostile process can attack resources available to the host user.

Model stages use a separate process session. The runner bounds output and kills the process group on timeout or completion, cleaning up descendants. Codex stdout/stderr is captured locally; valid JSON events are also extracted. Unknown event types are retained. Missing usage prevents further model stages after a failed attempt. A successful patch with missing usage can be returned, but its cost remains unknown and cannot satisfy a dollar-based promotion gate.

Artifacts include the task and policy, base commit, platform/runtime information, pack/task/context/MCP hashes, baseline output, phase prompts/events, candidate patches, verification output, optional plan, and the result JSON. MCP values are not serialized into results, only names and a hash; do not put literal secrets in any configuration.

The CLI parser is also the source of the `commands` inventory. `agent_tools.py` renders the operator skill and a compact worker inventory using an absolute `launch.py` entry point. The Codex adapter saves its effective prefixed prompt and passes a cooperative worker marker to child processes. CLI dispatch blocks new jobs/mutations under this marker so ordinary nested use cannot silently escape accounting. Discovery-context hashes participate in comparison and routing provenance. See [operator and worker behavior](AGENT_USAGE.md).

Output inside the source repository must be explicitly Git-ignored; otherwise the runner rejects it before writing. Promotion requires matching tools, CLI/platform/Python metadata and unique trial IDs, and refuses to replace an active release unrelated to the candidate's original baseline. The optimizer adds provenance, distinct-prompt and fresh-holdout checks. These checks do not provide hostile-code isolation or statistical proof.

## Extending the adapter

`run(policy, model, workspace, prompt, mcp, timeout, log)` returns completion status, return code, failure reason, message, events, usage and estimated cost. `advise(..., role)` adds read-only preparation, planning and review, with structured schemas for preparation and review. Keep result usage normalized as `input_tokens`, `cached_input_tokens`, `output_tokens`. Preserve unknown usage and prices as `None`. New backends must demonstrate timeout cleanup, structured response behavior and accounting with contract tests before claiming support.

## Experimental layer

`experimental/` adds separate opt-in commands. `parallel.py` runs isolated candidates or read-only specialists; `routing.py` fits a local classifier from matched outcomes; `memory.py` retrieves verified experience. `ace.py` maintains structured playbooks, while `gepa.py` integrates the optional upstream optimizer. `recursive.py` provides typed nested read/search/delegate calls. `finetune.py` exports verified patch datasets and optionally invokes TRL/PEFT training. These workflows keep ordinary coding acceptance in `runner.py` and pack promotion in `improve.py`.

Retrieved advice is bounded, marked untrusted and fingerprinted in run records. Paired promotion trials must use matching external advice. Instruction candidates retain cumulative development-task and normalized-prompt provenance across copies and releases. Matching hashes catch exact overlaps; semantic contamination remains a dataset-curation problem. See [experiment contracts and limits](EXPERIMENTS.md).

## Deliberate boundaries

The default controller can apply a verified patch locally; `--patch-only` and the lower-level `run` command leave application to the user. The project does not create commits, publish PRs, update tickets, alter global Codex configuration, automatically trust hooks or schedule itself. The optional training command can update an open-weight model through a local LoRA adapter; hosted Codex weights are unchanged. There is no container sandbox, embedding index, automatic parallel-worker merge system or resumable long-running workflow scheduler. The learned router and lexical retrieval are experiments requiring representative data and evaluation.
