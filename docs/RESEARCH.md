# Research review: when a small model benefits from a better harness

Reviewed 2026-11-04. This is a curated primary-source review, not an exhaustive review of every paper. Sources were searched and fetched using web tools initially, then Playwright for browser research and upstream repository tools for implementation documentation. Some papers were reviewed through their abstracts; RouteLLM, test-time compute and Agentless were also inspected in full HTML. Vendor case studies are not independent proof of generalization to Codex.

The [2026-11-05 extension](RESEARCH_UPDATE.md) adds ACE, ExpeL, learned repository skills, EvalPlus, recursive language models, tool discovery, synthetic tasks and architecture evolution. Version 0.3 adds [executable experiments](EXPERIMENTS.md); the [coverage map](RESEARCH_COVERAGE.md) records the current implementation and remaining boundaries. The initial selection decisions below have been updated accordingly.

## The conclusion that drives the implementation

A harness can improve the information, feedback, tools, and computation available to a model. It cannot guarantee that a cheap model acquires capabilities it lacks. Optimize the **verified outcome per total cost**, including failures, planning, retries, review and tuning. For accuracy-sensitive work, compare policies at a stated higher budget. This is an engineering objective, not a promise about a particular model.

Our proposed policy order is: focused task and tests → small implementer → targeted repair → stronger implementer when needed. Add a strong planner when decomposition or architecture is the failure mode. Add independent review when executable tests miss important requirements. Every optional layer should survive an ablation on the target task distribution.

## Evidence and translation into code

| Evidence | Finding and limitation | SuperCodex decision |
|---|---|---|
| [SWE-agent, 2024](https://arxiv.org/abs/2405.15793) | Agent-computer interface design affects software-task performance. Results concern a particular model/tool/benchmark combination. | Keep tool feedback useful and the adapter thin; reuse Codex's native editing and execution loop. |
| [Agentless, 2024, full v1](https://arxiv.org/html/2407.01489v1) | Localization followed by focused repair can compete with elaborate agents. Paper versions report different results; do not mix their numbers. | Scope tasks, inspect relevant files, produce small patches, verify externally. Avoid extra agents by default. |
| [mini-swe-agent upstream](https://github.com/SWE-agent/mini-swe-agent) | The maintainers demonstrate a minimal shell-based agent and straightforward trajectories. README results are upstream claims. | Avoid building a second full tool runtime around Codex. Keep the baseline simple. |
| [Reflexion, 2023](https://arxiv.org/abs/2303.11366) | Feedback and episodic reflection can improve later trials without weight updates. Benchmark results do not establish savings on real repositories. | Feed concrete failed checks and a compact handoff to a fresh attempt. |
| [Self-Refine, 2023](https://arxiv.org/abs/2303.17651) | Iterative self-feedback improves selected tasks. Self-evaluation is not independent ground truth. | Use executable checks as the primary signal, with optional separate review. |
| [LATS, 2023/2024](https://arxiv.org/abs/2310.04406) | Tree search combines planning, acting, value estimates and reflection. Search requires additional calls and a useful evaluator. | Deferred until representative data justify branching and selection costs. |
| [Test-time compute, 2024, full paper](https://arxiv.org/html/2408.03314v1) | Compute allocation depends on problem difficulty; smaller models can outperform larger ones under some matched-compute conditions. Experiments focus on MATH, and difficulty estimation has its own cost, omitted from some experiments. | Bounded adaptive effort; do not extrapolate headline ratios to software work. |
| [FrugalGPT, 2023](https://arxiv.org/abs/2305.05176) | Cascades can trade cost for accuracy using learned selection. Reported gains depend on the queried models and datasets. | Start with an observable verifier-based cascade, not uncalibrated model confidence. |
| [RouteLLM, 2024, full paper](https://arxiv.org/html/2406.18665v2) | Learned routing uses preference data to balance strong and weak models. Routing quality and training distribution matter. | Default routing is transparent policy. The optional TF-IDF/logistic router learns from matched verified outcomes; it is not the RouteLLM architecture or a calibrated confidence estimate. |
| [Long-running harnesses, 2025](https://www.anthropic.com/research/effective-harnesses-for-long-running-agents) | Small increments and persistent progress artifacts support continuity across sessions. | Save patches, checks, plans, handoffs and per-attempt events. Fresh retries reuse the edited workspace and bounded diagnostics. |
| [Harness design, 2026](https://www.anthropic.com/research/harness-design-long-running-apps) | Separate planning and evaluation can expose missing functionality; scaffolding should change as model capabilities improve. Examples include expensive multi-hour runs. | Optional planner and independent reviewer, with all their usage counted. No claim that extra roles always save money. |
| [Multi-agent research system, 2025](https://www.anthropic.com/research/multi-agent-research-system) | Independent exploration can benefit from parallelism, but coordination and token use rise. The authors explicitly distinguish research from tightly coupled coding work. | Sequential specialist roles first. No default swarm of cheap agents editing the same files. |
| [Context engineering, 2025](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents) | Relevant, compact context and clear tools matter more than maximizing context volume. | Pack context size cap, selective skills/MCP tools, bounded feedback and targeted retrieval. |
| [Evaluating AGENTS.md, v3, 2026](https://arxiv.org/abs/2602.11988) | Context files did not generally improve success in the reported settings and increased inference cost. Repository overviews were not useful there. | Keep instructions specific to non-obvious constraints; require evaluation before promoting additions. |
| [AGENTS.md efficiency study, 2026](https://arxiv.org/abs/2601.20404) | A different study reports lower runtime/output-token usage with context files. Different repositories and outcomes prevent a universal conclusion. | Treat instruction quality as an empirical question, not “more rules is better.” |
| [Agent evals, 2026](https://www.anthropic.com/research/demystifying-evals-for-ai-agents) | Outcomes, trajectories, realistic tasks and multiple types of graders reveal different failure modes. | Immutable task definitions in the runner, external checks, independent trials, status breakdowns and complete artifacts. |
| [Infrastructure noise, 2026](https://www.anthropic.com/research/infrastructure-noise) | Resource and runtime differences can alter benchmark outcomes. | Freeze revisions, dependencies, resource conditions and timeouts; distinguish launch/setup failures from model failures. |
| [GEPA, 2025](https://arxiv.org/abs/2507.19457) | Reflective prompt evolution uses execution feedback and candidate selection. This does not imply safe unsupervised self-rewriting. | Standard pack proposals remain bounded edits. The optional GEPA integration runs the actual upstream optimizer with verified rollouts and separate reserved holdouts; final candidates still require promotion. |
| [DSPy, 2023](https://arxiv.org/abs/2310.03714) | Programmatic pipelines can optimize prompts/demonstrations against evaluation objectives. | Version task packs and evaluate changes under fixed contracts; no DSPy dependency or claimed reproduction. |

## Implementation documentation reviewed

| Primary source | What it establishes |
|---|---|
| [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode) | `exec`, JSONL events, usage events, sandbox flags and existing authentication. |
| [Codex configuration](https://learn.chatgpt.com/docs/config-file/config-reference) | Configuration overrides, permissions and MCP options. |
| [Codex models](https://learn.chatgpt.com/docs/models) | Current example model names and retirement differences between account/auth modes. |
| [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) | Server registration, OAuth, tool allow-lists and required startup. |
| [OpenAI prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching) | Cache reuse depends on model, prefix structure and settings. A stable prompt alone does not guarantee a hit; the CLI controls requests. |
| [Playwright MCP](https://github.com/microsoft/playwright-mcp) | Isolated/headless browser configuration. Pinned package example: 0.0.84. |
| [GitHub remote MCP](https://github.com/github/github-mcp-server/blob/main/docs/remote-server.md) | Hosted endpoint and read-only endpoint variant. |
| [Atlassian MCP](https://atlassian.github.io/atlassian-mcp-server/) | Recommended v2 endpoint and OAuth/API-token access. |
| [Atlassian tool catalog](https://support.atlassian.com/atlassian-ai-gateway/docs/supported-tools/) | Supported tool names and discovery behavior. |
| [Langfuse cost optimization](https://langfuse.com/academy/experiments/cost-optimization) | Establish output quality and representative evaluations before optimizing cost. |
| [Langfuse datasets](https://langfuse.com/academy/datasets) | Use real-world scenarios and meaningful expected outcomes. |

## Techniques selected, conditional, and deferred

**Implemented:** scoped acceptance contracts; direct repository inspection; task-specific instructions; selective tool loading; protected tests; clean verification; bounded feedback; repair loops; explicit escalation; optional strong planning; optional independent review; usage accounting; repeated variant comparisons; evidence-based instruction proposals; immutable promotion and rollback.

**Supported by configuration:** reasoning effort, model selection, per-task MCP servers, custom scripts as checks, task-specific setup, price tables, alternative skills, and experimental Codex OSS provider flags. Retrieval uses Codex's filesystem tools and selected MCP sources. This is not a separate embedding or vector-search implementation.

**Opt-in experiments in v0.3:** independent best-of-N sampling, read-only specialist teams, fitted routing, verified-experience retrieval, structured ACE playbooks, upstream GEPA, bounded recursive calls and local supervised LoRA training. Each needs suitable data, a useful verifier and full accounting. More sampling can optimize the tests rather than actual correctness when checks are weak. Calibrated judges, automatic regression-test generation and concurrent-edit merging are not implemented.

**Not fitted into v0.1:** blind majority voting over code, unlimited self-reflection, automatic installation of every MCP server, huge generated AGENTS.md files, tree search on every task, fine-tuning without a dataset, or autonomous changes to protected evaluation logic. These add expense or new failure modes without task-specific evidence.

## Cost opportunities, with an honest baseline

There is no representative production cost baseline yet. The live smoke result in VALIDATION.md has unknown dollar cost and one task. Therefore savings at the analyzed volume cannot be estimated responsibly. The table expresses hypotheses to test, following the [cost-optimization process](https://langfuse.com/academy/experiments/cost-optimization).

| Opportunity | Explanation and why it works | Estimated savings at analyzed volume | Implementation effort | Risk to output quality |
|---|---|---:|---|---|
| Smaller implementer | Use cheaper capacity on bounded edits that pass checks | Unknown; no priced baseline | Implemented | May miss complex requirements |
| Selective escalation | Pay for stronger execution only after useful failure evidence | Unknown | Implemented | Weak checks can accept an incorrect cheap result |
| Strong planner | Supply decomposition and invariants to the smaller implementer | Unknown; can increase cost | Implemented | Wrong plan can propagate errors |
| Short task packs | Remove irrelevant instructions and tool schemas | Unknown | Implemented | Removing needed context may hurt |
| Independent review | Catch correctness gaps beyond tests | Usually adds inference cost; net effect unmeasured | Implemented | Judge errors and correlated blind spots |
| Cache reuse | Account for actual cached tokens and preserve useful prefixes where practical | Unknown; controlled by Codex/provider | Observed, not guaranteed | Fresh contexts can lose cache reuse |
| Task-pack optimization | Amortize a tested improvement across recurring tasks | Unknown; include tuning and evaluation cost | Implemented | Overfitting and holdout leakage |

## What would justify a “SuperCodex improves Codex” claim?

Run a strong-model baseline, a cheap single-attempt baseline, and each proposed harness variant on the same held-out tasks, revisions, checks and environment. Use enough independent repetitions to characterize noise. Report success rate, failures by category, first-attempt success, total cost per successful task, latency and human review. Include optimization cost when claiming net savings. Publish sanitized artifacts and the limitations. Until that experiment is complete, this is a functional research-informed harness, not a demonstrated new state of the art.
