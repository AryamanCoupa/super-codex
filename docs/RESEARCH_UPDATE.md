# Research extension: dedicated harnesses that improve from evidence

Reviewed 2026-11-05. This extends [the original review](RESEARCH.md). Research used an isolated **Playwright MCP** browser; upstream README material used the connected GitHub MCP tools. General browser search returned noisy results, so primary papers and author-maintained pages were followed directly. The table distinguishes full-page/method review from abstract-only review. It is a curated review, not an exhaustive survey or a claim that these results reproduce with Codex.

Version 0.3 implements the additional [experimental workflows](EXPERIMENTS.md). Current coverage is summarized below and in the [research-to-code map](RESEARCH_COVERAGE.md); the conservative standard pack optimizer remains available unchanged in purpose.

## Additional evidence and implementation decisions

| Primary source and reading scope | What matters here | Decision |
|---|---|---|
| [ACE: Agentic Context Engineering](https://arxiv.org/html/2510.04618v1), full HTML; methods, ablations and limitations | Evolving domain playbooks can help, while whole-context rewrites can erase accumulated knowledge. Incremental updates preserve unrelated entries. Results concern AppWorld and financial tasks; noisy feedback can degrade memory. “Smaller” in this study does not mean a tiny local model. | Standard proposals use bounded deltas. The experimental local ACE variant adds separate reflection/curation, stable bullet IDs, helpful/harmful counters, incremental updates, lexical retrieval/deduplication and pruning. It does not reproduce the authors' semantic retrieval implementation or benchmark. |
| [ExpeL](https://arxiv.org/html/2308.10144v1), full HTML; method, retrieval ablations and limitations | Cross-task insights plus retrieval of successful experiences helped on HotpotQA, ALFWorld and WebShop. One ablation found adding reflections could hurt, plausibly through erroneous reflections. | Experimental memory retrieves compact verified trajectories using BM25, source revisions, pack identity and task exclusions. Free-text handoffs require explicit inclusion. No embedding index or exact ExpeL reproduction is claimed. |
| [Automatically Learning Skills for Coding Agents / gskill](https://gepa-ai.github.io/gepa/blog/2026/02/18/automatically-learning-skills-for-coding-agents/), full article; [GEPA upstream](https://github.com/gepa-ai/gepa), README and API/adapter source | Repository-specific skills learned with a smaller implementer transferred to another coding agent in two repository experiments. Tasks came from SWE-smith, with separate training/validation/test splits. The authors flag synthetic repair tasks as a limitation. Some Bleve figures differ between sections; do not treat the headline as a general guarantee. | Dedicated packs and a strong proposer/smaller worker are directly relevant. `pack optimize` is conservative; `experimental gepa` uses the upstream Pareto search, reflective mutation and merge attempts. Repository rollouts and separate promotion checks replace the article's experiment setup; reported gains are not reproduced. |
| [EvalPlus](https://arxiv.org/html/2305.01210v1), full HTML; approach and evaluation; [upstream](https://github.com/evalplus/evalplus), README | Stronger test inputs exposed incorrect generated programs that passed original tests; even reference solutions could be wrong. Input mutation and validated contracts improve evaluation coverage. | Acceptance checks are a first-class dependency. New packs do not invent executable checks. Add trusted edge cases, property/differential tests or mutation testing in task checks when appropriate. No bundled automatic test generator is claimed. |
| [Recursive Language Models](https://arxiv.org/html/2512.24601v1), full HTML; method, cost and ablations | Keeping long input in an external environment and querying relevant portions can outperform stuffing a prompt. The GPT-5 experiment used GPT-5-mini subcalls. Recursive calls were not uniformly better; smaller inputs and expensive tail trajectories expose tradeoffs. The open model was a large model. | The recursive experiment supports bounded read/search/delegate/answer calls and a final verified implementation. It uses a typed environment rather than generated REPL code. Default coding runs do not invoke it. |
| [Advanced tool use](https://www.anthropic.com/research/advanced-tool-use), full page; tool-search and programmatic-calling sections | Deferred discovery and code-based filtering can reduce tool-schema and intermediate-result overhead in that platform. Search itself adds latency; gains depend on tool-library size. | Select MCP servers and skills per pack; inspect the effective set before running. Provider-native deferred loading is not a portable Codex feature implemented by this wrapper. Avoid installing every integration into every task. |
| [SWE-smith](https://arxiv.org/abs/2504.21798), abstract v2 | Synthesizes repository repair tasks with failing tests and supports training software agents at scale. Synthetic failures are useful data but need coverage of realistic work. | Automatic synthetic task generation is not implemented. Verified real run patches can now feed experimental TRL/PEFT supervised LoRA training. Human-curated issues and independent downstream checks remain necessary. |
| [Darwin Gödel Machine](https://arxiv.org/abs/2505.22954), abstract v3 | Explores changes to agent code through an archive and empirical benchmark validation. This is broader and more expensive than changing a task instruction. | Keep the runner, verifier and permission policy outside automatic pack updates. Architecture evolution would be a separate sandboxed research project with independent evaluations. |

## What changed in SuperCodex

**Discovery and specialization:** `pack list` finds bundled packs, local packs and active releases; `inspect` exposes skills, MCP tools, checks and context size. `suggest` ranks task/repository matches and can flag recurring failures for an experiment. Rankings are explainable heuristics, not trained estimates of success. `create` copies the selected template and records the task without silently assuming its example test commands work in a different repository.

**Controlled adaptation:** `pack optimize` makes one candidate from development records, evaluates baseline and candidate on frozen held-out tasks, and promotes only a measured improvement. It checks source provenance, distinct tasks, unique run IDs, matching tools/runtime/policy, per-task regressions and cost. It records proposal plus evaluation spend, stops when accounting is unknown, and preserves the active version when a candidate is rejected. The automatic workflow records consumed holdouts and refuses to reuse them in that registry. Semantic leakage still needs human review.

**Memory preservation:** a proposal is a bounded edit, not an unrestricted replacement of accumulated instructions. This prevents unrelated content from disappearing during application; it cannot establish that the new advice is correct. Quality still comes from checks, representative data and independent review.

These choices follow the quality-first experiment process in [Langfuse's cost guide](https://langfuse.com/academy/experiments/cost-optimization) and task-distribution guidance in [its dataset guide](https://langfuse.com/academy/datasets). No live dataset service is required or configured.

## What to test next, in order

1. **Verifier adequacy:** confirm that realistic wrong patches fail the acceptance checks. More retries against weak tests can amplify false success.
2. **Task-pack ablation:** compare no pack, a short curated pack, and an optimized pack. Hold model, checks, tools and revision fixed. Include tuning cost in the payback calculation.
3. **Adaptive effort:** compare a cheap single attempt, repair/escalation and a strong baseline. Use failure evidence rather than a model's uncalibrated confidence to decide escalation.
4. **Selective experience retrieval:** compare a few relevant, proven examples with instructions alone. Record source revision and retire stale guidance. Do not mix held-out answers into memory.
5. **Optional parallel candidates:** try independent candidates or disjoint research workers only when the task can be divided and results independently verified. Charge for every candidate, coordination and selection. Majority agreement alone is not correctness.
6. **Learned routing or weight adaptation:** consider these after collecting enough representative data. Router training, fine-tuning, hosting and revalidation are part of total cost.

Repeated-run reliability is different from finding one successful sample. Keep independent repetitions separate from repair attempts, and inspect failure distributions as well as averages. [Agent evaluation guidance](https://www.anthropic.com/research/demystifying-evals-for-ai-agents) discusses this distinction. The current report does not estimate a new `pass^k` metric.

## Cost hypotheses, not savings claims

Baseline: one previously recorded live smoke task, unknown dollar cost; no representative production volume. Therefore none of the following has a defensible percentage-saving estimate yet.

| Opportunity | Explanation and why it works | Estimated savings at analyzed volume | Implementation effort | Risk to output quality |
|---|---|---:|---|---|
| Pack suggestion without inference | Use local manifests/task terms to avoid a paid routing call | Unknown | Implemented | Heuristics can select the wrong family; selection stays explicit |
| Bounded instruction edits | Change only the evidence-supported part of reusable context | Unknown | Implemented | A plausible instruction can still generalize badly |
| One-command controlled tuning | Measure whether recurring-task improvements justify tuning spend | Unknown; first experiment adds cost | Implemented | Dataset overlap and weak verifiers can exaggerate gains |
| Narrower tool/context loading | Reduce irrelevant schemas and repeated output | Unknown | Pack configuration supported | Missing a needed tool or fact can increase retries |
| Recursive or parallel workers | Delegate separable, context-heavy work with compact outputs | Unknown; may increase cost | Experimental implementation | Coordination errors and expensive tail runs |

The next result worth publishing is a reproducible comparison on representative tasks, not another list of techniques. Use the [task-pack guide](TASK_PACKS.md) to run that experiment.
