# Opt-in research experiments

Version 0.3 adds executable experiments for every capability in the previously deferred list: parallel workers, independent candidate selection, fitted routing, successful-experience retrieval, ACE-style context adaptation, upstream GEPA, recursive calls and local fine-tuning. These are separate from the standard `run` command. They are not a promise that combining them improves quality or cost.

```bash
super-codex experimental list
super-codex experimental --help
```

Use a clean committed repository, real acceptance checks, a new output directory, and explicit prices for money budgets. Output must be outside the target repository or explicitly Git-ignored. All example model names must be available to your account. Select a task pack with `--pack` as usual; its skills, tools, checks and policy still apply.

## Choose the experiment by observed failure

| Observation | Experiment | What actually runs |
|---|---|---|
| Different attempts sometimes solve a well-verified task | `best-of-n` | Independent isolated runner trials; choose a passing patch by measured candidate cost or explicit token proxy |
| Relevant facts are spread across separable areas | `teams` | Read-only specialist sessions, optional strong coordinator, one verified implementer |
| You have matched cheap/strong evaluations across task families | `router train`, then `run --router` | Fit local TF-IDF/logistic weights; use similarity/context checks and a strong fallback |
| Prior verified work contains relevant repository experience | `memory build`, then `run --memory` | BM25 retrieval of compact trajectories with revision/pack provenance |
| Repeated errors justify reusable domain guidance | `ace` | Structured playbook reflection, curation, counters, incremental edits, retrieval, deduplication and pruning |
| You can afford a prompt-search experiment | `gepa` | Actual upstream GEPA Pareto selection, reflective mutation and merge attempts with verified rollouts |
| A large repository benefits from nested questions | `recursive` | Bounded model-requested read/search/delegate/answer calls, followed by verified implementation |
| You have sufficient distinct verified examples and suitable hardware | `finetune export`, `finetune train` | Local patch distillation data, then genuine TRL/PEFT supervised LoRA training on an open-weight model |

Default runtime dependencies remain empty. GEPA and training packages are optional and are never installed merely by importing the harness.

## Independent candidates and teams

```bash
super-codex experimental best-of-n task.json --repo /path/to/repo \
  --pack .harness/packs/my-api --config economy \
  --candidates 3 --concurrency 2 --selection-metric tokens \
  --max-total-tokens 300000 --output .harness/experiments/samples-01

super-codex experimental teams task.json --repo /path/to/repo \
  --pack .harness/packs/my-api --config economy \
  --specialist-model gpt-6-luna --coordinator-model gpt-6.1-sol \
  --concurrency 2 --max-total-tokens 300000 \
  --output .harness/experiments/team-01
```

The specialists inspect localization, contracts and test gaps by default. `--specialists roles.json` accepts a list of `{ "name": "...", "focus": "..." }` objects. They do not concurrently edit or merge patches. Candidate sampling selects among externally passing patches; majority agreement is not used as a correctness signal. Charge the experiment for all candidates and coordination, not just the selected patch. [Detailed behavior](EXPERIMENTAL_PARALLEL.md).

## Fit a router and retrieve useful experience

```bash
super-codex experimental router train --from-runs .harness/model-comparison \
  --cheap-model gpt-6-luna --strong-model gpt-6.1-sol \
  --cost-metric tokens --output .harness/router.json
super-codex experimental memory build --from-runs .harness/development-runs \
  --exclude-suite untouched-holdout.json --output .harness/memory.json
super-codex experimental run task.json --repo /path/to/repo \
  --pack .harness/packs/my-api --router .harness/router.json \
  --memory .harness/memory.json --exclude-suite untouched-holdout.json \
  --output .harness/experiments/routed-01
```

Router training needs matched single-model comparisons, including failures, with the same checks, policy apart from model, tools and runtime. It requires at least eight task groups by default and both learnable labels. Threshold evaluation uses a task-grouped validation split. The fitted score is uncalibrated; the retrospective report is not prospective performance. The execution command validates runtime/revision/pack/policy metadata and falls back to the strong model when it differs. It never overrides an explicit `--model` silently.

Memory stores compact verified attempt/check/file metadata by default. `--include-handoffs` opts into free-text handoffs after review. Current-task and excluded-holdout prompts are filtered. Revision and pack matches are required unless stale-revision use is explicitly enabled. Semantic duplicates still need curation. [Data formats, training and retrieval](EXPERIMENTAL_ROUTING.md).

## Evolve instructions or a playbook

```bash
super-codex experimental ace .harness/packs/my-api \
  --from-runs .harness/development-runs --repo /path/to/repo \
  --model gpt-6.1-sol --rounds 1 --max-calls 4 \
  --output .harness/experiments/ace-01

python -m pip install -e '.[gepa]'
super-codex experimental gepa .harness/packs/my-api \
  --train-suite train.json --validation-suite validation.json \
  --holdout-suite untouched-holdout.json --repo /path/to/repo \
  --max-metric-calls 20 --max-reflection-calls 8 \
  --output .harness/experiments/gepa-01
```

GEPA suites contain `{ "tasks": [{ "repo": "...", "task": "...", "revision": "..." }] }`; paths resolve relative to the suite. Training and validation both guide optimization and are recorded as development data. Reserved holdouts are checked for overlap and are not executed or given to the optimizer. Both methods output candidates requiring separate holdout comparison and normal `pack promote`; they cannot promote themselves. ACE can also supply selected playbook bullets with `experimental run --ace-playbook PATH`.

GEPA uses the actual `gepa==0.1.4` engine. ACE is a local implementation of the generator/reflector/curator pattern with lexical retrieval/deduplication, rather than the authors' exact embedding implementation or a reproduced benchmark. [Algorithm details and promotion workflow](EXPERIMENTAL_OPTIMIZERS.md).

## Recursive model calls

```bash
super-codex experimental recursive task.json --repo /path/to/repo \
  --pack .harness/packs/my-api --root-model gpt-6.1-sol \
  --child-model gpt-6-luna --max-depth 2 --max-calls 8 \
  --max-total-tokens 200000 --output .harness/experiments/recursive-01
```

The root requests typed file reads, literal searches, subquestions and answers. Children can delegate within the global call/depth budget. Only bounded evidence windows and child summaries return to the parent. `--path` narrows the wrapper's file index; `--analyze-only` stops before implementation. The implementer receives advice as untrusted context and still passes the normal clean-clone checks.

This is a recursive-call experiment inspired by [RLMs](https://arxiv.org/html/2512.24601v1), using a typed environment rather than generated REPL code. Corpus/path limits bound wrapper retrieval; they are not restrictions on Codex's native read tools. One Codex invocation can contain internal model/tool turns. Audits retain every outer call, depth, usage, selected models and final patch provenance.

## Local fine-tuning and distillation

```bash
super-codex experimental finetune export \
  --from-runs .harness/development-runs --exclude-suite untouched-holdout.json \
  --output .harness/training/patch-data

python -m pip install -e '.[finetune]'
super-codex experimental finetune train \
  --dataset .harness/training/patch-data --base-model YOUR_OPEN_WEIGHT_MODEL \
  --revision PINNED_MODEL_COMMIT --max-steps 20 --max-length 4096 \
  --output .harness/training/lora-01
```

Export requires distinct verified patches and their original source files at frozen commits. It excludes failed/unverified records, keeps normalized-task groups and identical base/patch pairs out of both splits, validates patch identity, and records teacher-model provenance. It exports prompt/completion examples, not hidden reasoning or entire event logs. Review this private data before training.

The optional backend calls [TRL SFTTrainer](https://huggingface.co/docs/trl/v1.17.1/sft_trainer) with completion-only loss and [PEFT LoRA](https://huggingface.co/docs/peft/v0.21.0/package_reference/lora). It saves a local adapter, uses fixed maximum steps, disables remote model code and hub uploads, and rejects examples that would truncate the patch. `--cpu` is available; otherwise hardware selection follows the training stack. The step-end timeout is soft and does not bound downloads, initialization or a single long step.

The training API wrapper is tested with injected dependencies. A real GPU/MPS/CPU training job has **not** been validated in this repository. This trains compatible open-weight models; it does not modify hosted Codex model weights. Adapter serving/merging depends on your inference backend. Compare the trained and base model on separate coding tasks before using it. Validation loss alone is not patch correctness; hardware cost is left unknown.

## Budgets, evidence and ablations

Usage budgets are soft between calls, batches or full runner stages. A parallel batch can overshoot by multiple in-flight calls; interruption drains those calls under their timeouts. Missing usage blocks subsequent paid stages and automatic patch selection. Inspect `termination_reason`, `budget_overrun` and all spending, including unsuccessful candidates. A verified result already obtained may remain available when a later budget limit prevents more sampling.

Keep at least four comparisons: cheap single run, strong single run, standard repair/escalation, and one selected experimental change. Freeze task checks/revisions and report total experiment cost per success. Count development collection, optimizer reflection/evaluation and training cost when estimating payback. The existing live smoke is not a representative baseline, so no savings percentage is justified.

| Opportunity | Explanation and why it works | Estimated savings at analyzed volume | Implementation effort | Risk to output quality |
|---|---|---:|---|---|
| Fitted routing | Route supported tasks to the measured cheaper model | Unknown; no representative priced baseline | Experimental implementation | Data drift and uncalibrated scores |
| Retrieved experience / ACE | Reuse relevant repository lessons with bounded context | Unknown | Experimental implementation | Stale or misleading advice |
| Parallel / recursive workers | Separate independent questions or candidates | Unknown; can increase total cost | Experimental implementation | Correlated failures and coordination overhead |
| GEPA / LoRA | Amortize optimization over repeated work | Unknown; upfront optimization/training cost | Optional integration | Overfitting and weak verifier signals |

The [coverage map](RESEARCH_COVERAGE.md) identifies the implemented mechanisms, adaptations and boundaries for the reviewed research. Add one method at a time and retain only changes supported by your own held-out evaluation.
