# Security and data handling

SuperCodex is for repositories, task manifests, setup commands, checks, packs and MCP servers that you trust. It is not a sandbox for executing arbitrary public submissions.

- Setup and verification commands execute locally as your user. A reduced environment strips most credentials but does not isolate the filesystem, network or local services. Use an independently secured container/VM for untrusted tasks.
- Git clones keep ordinary changes away from your working tree. They do not prevent malicious code from reaching other host files. No hidden-test secrecy is claimed.
- Codex runs with its own workspace-write/read-only policies and noninteractive approval behavior. MCP servers execute under their own permissions. Browser isolation separates profiles, not host security domains.
- A tool allow-list is not an operation-level permission boundary for a multiplexed server. Grant least-privilege service credentials and enforce policy on the server.
- Artifacts can contain private code, URLs, prompts, logs or secrets printed by tools. They are ignored by Git and run directories use private permissions, but there is no complete automatic redaction. Review before sharing.
- Never commit authentication files, tokens, browser storage state, private MCP endpoint details or raw experiment logs. Use environment-variable references for credentials.
- Protected paths and fresh verification catch ordinary test tampering and cache contamination. They do not establish adversarial grader integrity.
- Task-pack proposals can contain bad advice or injected instructions. Inspect candidates, evaluate them independently, retain immutable versions and roll back. Promotion gates do not prove statistical significance or prevent a human from editing files outside the CLI.

For a suspected vulnerability, use the repository host's private security-reporting feature if available. Avoid public issues containing exploit details, credentials or private run artifacts.
