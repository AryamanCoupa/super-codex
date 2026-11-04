"""Codex CLI adapter. Keep orchestration independent of the model backend."""

import hashlib
import json
from pathlib import Path
from .config import ASSETS, toml_value
from .process import execute


def command(policy, model, workspace, mcp, role="implement"):
    argv = list(policy["codex_command"]) + ["exec", "--json", "--ephemeral", "--color", "never",
                                          "--sandbox", "workspace-write" if role == "implement" else "read-only", "-C", str(workspace)]
    if not policy.get("inherit_user_config", False):
        argv.append("--ignore-user-config")
    if policy.get("local_provider"):
        argv += ["--oss", "--local-provider", policy["local_provider"]]
    argv += ["--model", model]
    overrides = {
        "approval_policy": "never",
        "model_reasoning_effort": policy["reasoning_effort"],
        "sandbox_workspace_write.network_access": False,
    }
    for key, value in overrides.items():
        argv += ["-c", f"{key}={toml_value(value)}"]
    for name, config in mcp.items():
        argv += ["-c", f"mcp_servers.{toml_value(name)}={toml_value(config)}"]
    if role in {"review", "prepare"}:
        argv += ["--output-schema", str(ASSETS / f"{role}.schema.json")]
    return argv + ["-"]


def parse_events(output):
    usage = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
    completed, failed, seen_usage, invalid_usage = False, False, False, False
    events, messages = [], []
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue  # CLI warnings can share the captured stream.
        if not isinstance(event, dict):
            continue
        events.append(event)
        kind = event.get("type")
        if kind == "turn.completed":
            completed = True
            u = event.get("usage", {})
            if (isinstance(u, dict)
                    and all(isinstance(u.get(k), int) and not isinstance(u[k], bool) and u[k] >= 0 for k in usage)
                    and u["cached_input_tokens"] <= u["input_tokens"]):
                seen_usage = True
                for key in usage:
                    usage[key] += u[key]
            else:
                invalid_usage = True
        if kind == "turn.failed":
            failed = True
        item = event.get("item", {})
        if kind == "item.completed" and isinstance(item, dict) and item.get("type") == "agent_message":
            message = item.get("text")
            if isinstance(message, str):
                messages.append(message)
    if usage["cached_input_tokens"] > usage["input_tokens"]:
        seen_usage = False
    return {"usage": usage if seen_usage and not invalid_usage else None, "completed": completed and not failed,
            "message": "\n".join(messages), "events": events}


def estimate_cost(usage, rates):
    if usage is None or rates is None:
        return None
    return ((usage["input_tokens"] - usage["cached_input_tokens"]) * rates["input"]
            + usage["cached_input_tokens"] * rates["cached_input"]
            + usage["output_tokens"] * rates["output"]) / 1_000_000


def _invoke(argv, workspace, prompt, timeout, log):
    from .agent_tools import worker_context, worker_environment

    context = worker_context()
    effective_prompt = context + "\n\n" + prompt
    if log:
        # Keep the exact sent prompt alongside the parent-generated task prompt.
        # Use the log's stem because some workflows put several calls in one folder.
        path = Path(log)
        path.with_name(path.stem + ".effective-prompt.txt").write_text(effective_prompt)
    result = execute(argv, workspace, timeout, stdin=effective_prompt,
                     env=worker_environment(), log=log)
    result["cli_context_sha256"] = hashlib.sha256(context.encode()).hexdigest()
    result["effective_prompt_sha256"] = hashlib.sha256(effective_prompt.encode()).hexdigest()
    return result


class CodexAdapter:
    def run(self, policy, model, workspace, prompt, mcp, timeout, log):
        result = _invoke(command(policy, model, workspace, mcp), workspace, prompt, timeout, log)
        result.update(parse_events(result.pop("output")))
        result["cost_usd"] = estimate_cost(result["usage"], policy.get("prices", {}).get(model))
        return result

    def advise(self, policy, model, workspace, prompt, timeout, log, role):
        # Advisors get repository reads and built-in tools, without pack MCP servers.
        argv = command(policy, model, workspace, {}, role=role)
        result = _invoke(argv, workspace, prompt, timeout, log)
        result.update(parse_events(result.pop("output")))
        result["cost_usd"] = estimate_cost(result["usage"], policy.get("prices", {}).get(model))
        return result
