# Validation and requirement audit

Validation recorded 2026-11-05 for version 0.5.0, with historical results labeled below. Local platform: macOS arm64, Python 3.11.0, Git 2.50.1, Codex CLI 0.164.0. CI covers macOS/Linux and Python 3.11/3.13, with a separate upstream GEPA integration job. Public CI and release outcomes are recorded in [GitHub Actions](https://github.com/AryamanCoupa/super-codex/actions). The live smoke tests establish execution wiring, not a model-quality comparison.

## What is implemented

| Requirement | Implementation | Evidence / limit |
|---|---|---|
| Local Codex harness | CLI adapter, disposable clones, external checks | Real Luna smoke test passed |
| Cheap model with stronger fallback | Economy/balanced policies; explicit escalation | Offline routing and stall/escalation tests; no representative savings claim |
| Strong reasoning with smaller execution | Optional read-only Sol planner and Luna worker | Planner handoff and shared accounting tests |
| Accuracy-first mode | Strong planner, fallback and structured independent review | Review rejection, repair and invalid-review tests; live reviewer quality unmeasured |
| Task-specific reusable harness | Discover, inspect, suggest, create and run packs | CLI, matching/provenance, incomplete-check and self-contained snapshot tests |
| Improve over time | One bounded instruction delta → paired fresh holdout trials → gated local release | Offline integration, shared budgets, history/provenance, environment, regression, cost and rollback tests |
| Standard integrations | Playwright, GitHub, Atlassian and docs presets | Upstream documentation checked; end-to-end OAuth/account connection not claimed |
| Custom tools | Generic custom MCP TOML | No internal product names or private endpoints in published source |
| Open-source distribution | MIT license, no-clone setup guide, research, tests, release workflow | Versioned GitHub release packages; no PyPI publication |
| Open models later | Codex OSS flags and adapter boundary | Experimental, not live-validated |
| Parallel cheap teams and best-of-N | Isolated candidates; read-only specialists, optional coordinator and one implementer | Offline real-runner tests cover verification, all-candidate accounting, budgets and interruptions |
| Learned routing and successful experience | Fitted TF-IDF/logistic model; verified BM25 memory | Matched data, grouped splits, context fallback, exclusions and composed-run provenance tests |
| ACE and GEPA | Structured local ACE variant; optional actual GEPA 0.1.4 engine | Separate reflection/curation, bounded playbooks, historical provenance; real upstream search exercised with offline rollouts |
| Recursive model calls | Typed read/search/delegate/answer environment and verified worker | Call/depth budgets, malformed responses, unknown usage, isolation and worker acceptance tests |
| Local fine-tuning | Verified patch export and optional TRL/PEFT LoRA training | Dataset/provenance/split tests and injected training API contracts; no actual hardware training run |
| Agent command discovery and cross-project use | Parser-derived inventory, automatic worker context and installable operator skill | Foreign-directory subprocess runs, full CLI discovery, managed-worker accounting guard, installation/update preservation and independent offline skill workflow |
| Explicit native launcher | `sc --native`, optional task/policy/pack/MCP selection | Actual simulated TUI on a controlling PTY, inherited input/output/configuration, private bootstrap, model selection, dry-run and exit propagation; advisory mode, no live interactive model benchmark |
| Enforced default controller | Read-only task preparation, fixed checks, isolated run, independent verifier, receipt and checked application | Real CLI subprocess tests and a live small-model preparation-to-application smoke; no native fallback |

## Offline verification

All **239 behavioral tests passed** on the local platform in 81.831 seconds, with the optional upstream GEPA package available. Without that extra, the real-GEPA integration test is skipped. Tests cover process timeouts/output limits, stdin backpressure, cached-token cost calculation, malformed events, unknown usage, dirty-source rejection, output-directory safety, protected-file deletion/modification, candidate symlinks, untracked files, agent-created commits, baseline false positives, setup errors, repairs, stall detection, escalation, planner accounting, review gating, discovery, task matching, CLI scaffolding, bounded instruction deltas, holdout separation/reuse, shared optimization budgets, matched runtime metadata, cost/quality gates, self-contained releases and rollback.

Controller coverage includes three real subprocess CLI tests for preparation-to-application, failed verification, and explicit task contracts with patch-only output. Additional tests cover preserved pack gates and original requests, automatic existing-test protection, malformed/missing checks, unknown or exhausted preparation budgets, interrupted inference/application, missing artifacts, source changes, advisory receipts and private file permissions. Unittest commands that collect zero tests are rejected before invoking a worker.

The experimental tests additionally exercise parallel execution and selection, recursive child calls, fitted routing, verified trajectory retrieval, ACE curation, GEPA adapter/search behavior, fine-tuning dataset integrity and the composed CLI. Most model responses are simulated. The GEPA integration invokes the actual upstream search algorithm with offline scoring/reflection; it does not measure live Codex optimization quality. Training tests inject lightweight dependency implementations and do not download or train a model.

The standalone offline demo exercises the real subprocess adapter with a simulator over three fixtures. It deliberately fails on the first attempt, then repairs each task. These are simulation outcomes, not model evaluation scores.

The 0.4.0 wheel built successfully. All 54 packaged source/asset files matched the checkout byte-for-byte. A fresh virtual environment outside the checkout installed the wheel without runtime dependencies and exercised all four console aliases (`sc`, `supercodex`, `super-codex`, `ch`), version output, non-writing launch previews, all 35 leaf commands and the three-task offline demo. Earlier 0.3.1 packaging checks also exercised operator-skill installation, its absolute launcher and two concurrent best-of-N candidates. The operator skill passed its validator, as did the two experimental skills in 0.3; `git diff --check` passed.

The native interactive integration test invokes a real local stand-in process through a controlling pseudo-terminal. It reads the bootstrap, receives terminal input, retains inherited environment and stdin/stdout handles, sees the frozen worker policy, and returns its exit code through the launcher. The target source remains untouched and session configuration files have private permissions. Launch preparation keeps selected pack policy unless explicitly overridden, redacts MCP values in previews, and preserves native configuration/permissions. This is an offline process contract, not a live Codex task outcome. Version 0.5 exposes this advisory behavior only through `--native`; the default controller's enforcement is a separate execution path.

An independent operator-skill check installed the skill into a temporary project and used the absolute launcher from another directory. It exercised discovery, fixtures, packs, doctor, run and report, observed the expected dirty-source rejection after project installation, and completed the offline mean repair after committing only the generated fixture skill. The patch passed `git apply --check`, and the source stayed clean and unchanged. This validates the offline workflow and instructions; no live Codex skill-selection benchmark or global user-skill installation was performed. See [agent usage](AGENT_USAGE.md).

The optimizer integration test runs a proposal plus four baseline/candidate trials through the real runner, subprocess adapter and clean verifiers using a simulated CLI. An equivalent candidate is rejected, with proposal and evaluation usage accounted together. Other tests cover successful promotion and interruption/rejection paths. This validates control flow; it does not measure live proposal quality.

## Live controller smoke (0.5.0)

A free-text request to fix empty-input arithmetic mean went through the default controller using `gpt-6-luna` for both preparation and implementation. Preparation selected the existing tests and protected them. The baseline failed; one worker attempt changed `stats.py`; all three assertions passed in a fresh verifier clone. The controller then applied the accepted patch to the original clean checkout and saved its receipt. No direct source edit by the worker was needed.

| Observation | Preparation | Implementation | Combined |
|---|---:|---:|---:|
| Input tokens | 46,385 | 65,109 | 111,494 |
| Cached input tokens (included above) | 30,592 | 48,128 | 78,720 |
| Output tokens | 532 | 538 | 1,070 |
| Total tokens | 46,917 | 65,647 | 112,564 |

Elapsed time was 42.544 seconds. Dollar cost was unknown because no rate table was configured. The shared soft token budget was 100,000; the final model stage exceeded it by 12,564. The controller charged preparation against the remaining worker allowance, but cannot stop a Codex turn at an exact token limit. The live smoke required permission to run outside the outer filesystem sandbox while retaining Codex's own read-only/workspace-write sandboxes. Artifacts remain private and are excluded from distribution.

This fixture is too small to demonstrate better accuracy or savings. Conventional test-file freezing and interruption accounting were additionally checked offline after the live smoke; they do not change its recorded outcome.

## Historical runner smoke (0.1)

Task: fix `mean([])` to return `None` while preserving ordinary arithmetic means. The source repository had three assertions covering empty input, ordinary values and negative values. Its baseline failed; after the model edited only `stats.py`, all three checks passed in a clean verifier clone.

| Observation | Result |
|---|---:|
| Model | `gpt-6-luna` |
| Implementation attempts | 1 |
| End-to-end seconds | 27.209 |
| Input tokens | 79,754 |
| Cached input tokens (included in input) | 63,104 |
| Output tokens | 573 |
| Total tokens | 80,327 |
| Dollar cost | Unknown; no assumed rate table |

The first launch inside an outer filesystem sandbox failed to initialize Codex and did not complete a model turn. A permitted retry outside that outer sandbox succeeded while retaining Codex's own workspace-write sandbox. Both run artifacts remain private and ignored by Git.

The configured soft token limit was 12,000, which one Codex turn exceeded. This directly demonstrates why the wrapper cannot promise hard token/dollar enforcement from final-turn usage. Subsequent stages are stopped when a limit is observed; process timeout is separately enforced.

## Findings fixed during review

- Failure signatures originally varied with verifier paths and timing; normalization now lets stall detection work.
- Stall detection now allows a scheduled change to a stronger model instead of stopping before escalation.
- Input is passed through a temporary file, so a child refusing stdin cannot block timeout handling.
- Planning/review spending counts toward the same run; budget exhaustion before mandatory review prevents acceptance.
- Unknown usage remains unknown in reports, instead of appearing as zero.
- Candidate and source fingerprints, fixed holdout task/policy/revision sets, a quality floor, finite cost limits and first-promotion rollback are checked.
- Setup logs are separated from verifier logs, and public templates contain generic custom-service names.
- Promotion rejects mismatched MCP/CLI/platform/Python metadata, duplicate run IDs, verifier infrastructure errors and an unrelated active registry baseline.
- Proposal deltas preserve untouched instruction bytes and reject stale/ambiguous edit targets or invalid usage.
- The optimizer records consumed holdouts, requires task diversity and stops on unknown accounting.
- Saved releases copy selected bundled skill resources; later changes to installed assets do not alter the saved release. Version 0.1 evidence needs re-running against the new canonical digest.
- Unignored artifact directories inside a source checkout are rejected before writes; explicitly ignored output and external output are supported.
- Copies and registered releases retain cumulative learning provenance; normalized development prompts cannot be reused as promotion holdouts after renaming a task.
- Router context validation includes the exact memory/ACE advice supplied to the worker before selecting a model. New context forces the stronger fallback unless supported by comparison evidence.
- Recursive accounting retains unknown usage, including the final worker; incomplete accounting prevents automatic patch selection.
- Fine-tuning splits exclude duplicate normalized prompts and identical base/patch solutions, and reject truncated patch targets.
- Reused ACE playbooks must match their source instructions; current-task and excluded-holdout overlap is rejected when provenance is available.
- All Codex roles receive the current command inventory and absolute launcher; effective prompts and hashes are saved. Promotion and learned routing distinguish runs collected with different discovery context.
- Installed operator skills preserve local edits; the launcher works with a different current directory, paths containing spaces, and Python's isolated import mode.
- Interactive startup preserves a dedicated pack's policy instead of silently overlaying the default balanced preset. Long task/pack instructions live in a private bootstrap file rather than command-line arguments.

## What remains unproven

No broad model-quality benchmark, statistical superiority claim, or dollar-saving estimate is justified by this smoke test. The next scientific step is a representative held-out task suite comparing cheap single attempts, cheap repair, escalation, architect mode, accuracy mode, and a strong-model baseline at explicitly measured cost. Add one experimental method at a time and include tuning expenses when claiming net savings. Parallel workers, learned routing, memory, ACE/GEPA, recursion and fine-tuning are now executable experiments, with the fidelity and validation limits in the [coverage map](RESEARCH_COVERAGE.md). Live open-model compatibility, actual hardware training and the quality/cost benefits remain unproven.
