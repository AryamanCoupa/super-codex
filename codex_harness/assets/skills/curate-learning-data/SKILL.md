---
name: curate-learning-data
description: Prepare verified run evidence for SuperCodex routing, retrieval, instruction optimization or local patch fine-tuning while preserving provenance and separate evaluation tasks.
---

Use complete run records with task/check/revision/pack identity. A success message is insufficient: inspect the external checks and required review. Diagnose setup, tool and accounting errors separately from model quality. Keep failed runs in routing/cost analysis; use verified successful patches for supervised patch examples.

Split by task family where possible. Group duplicate prompts, renamed tasks and identical base/patch solutions so they cannot cross development, validation and final holdout sets. Lexical hashes cannot detect every semantic duplicate. Optimizer validation is development feedback; reserve fresh promotion/audit tasks.

For memory, start with compact check/file/trajectory metadata and revision provenance. Review free-text handoffs before inclusion. For fine-tuning, retain the original input code and the exact verified patch, check usage rights and sensitive content, and avoid truncated targets. Export locally before choosing a training backend. Keep private traces out of the public repository.

Document the dataset version, exclusions, rejected rows and model/procedure used to produce labels. Generated tests and reference answers need independent review. Re-run comparisons after changing acceptance tests or data semantics rather than comparing incompatible scores.
