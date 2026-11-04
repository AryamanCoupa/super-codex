"""Validated, portable task and policy definitions."""

import copy
import json
import math
import re
import tomllib
from pathlib import Path

ASSETS = Path(__file__).parent / "assets"


def read(path):
    path = Path(path)
    with path.open("rb") as f:
        return tomllib.load(f) if path.suffix == ".toml" else json.load(f)


def merge(base, overlay):
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def positive(value, name, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a positive number")
    if not math.isfinite(value) or value <= 0 or (integer and not isinstance(value, int)):
        raise ValueError(f"Invalid {name}: {value}")


def load_policy(path=None, pack=None, overrides=None):
    policy = read(ASSETS / "policy.toml")
    if pack:
        policy = merge(policy, read(pack / "pack.toml").get("policy", {}))
    if path:
        preset = ASSETS / "policies" / f"{path}.toml"
        if not Path(path).exists() and preset.is_file():
            path = preset
        policy = merge(policy, read(path))
    if overrides:
        policy = merge(policy, overrides)
    for key in ("max_attempts", "cheap_attempts", "max_tokens", "feedback_chars"):
        positive(policy[key], key, integer=True)
    for key in ("attempt_timeout_seconds", "run_timeout_seconds", "check_timeout_seconds"):
        positive(policy[key], key)
    if policy.get("max_cost_usd") is not None:
        positive(policy["max_cost_usd"], "max_cost_usd")
    if policy.get("local_provider") not in (None, "ollama", "lmstudio"):
        raise ValueError("local_provider must be ollama or lmstudio")
    if not isinstance(policy["codex_command"], list) or not policy["codex_command"]:
        raise ValueError("codex_command must be a nonempty argv array")
    for name in ("model", "reasoning_effort"):
        if not isinstance(policy[name], str) or not policy[name]:
            raise ValueError(f"{name} must be a nonempty string")
    for rates in policy.get("prices", {}).values():
        for key in ("input", "cached_input", "output"):
            value = rates.get(key)
            if isinstance(value, bool) or not isinstance(value, (float, int)) or value < 0 or not math.isfinite(value):
                raise ValueError("prices need finite nonnegative input/cached_input/output rates per million tokens")
    if policy.get("max_cost_usd") is not None:
        models = [policy["model"]]
        models.extend(policy[k] for k in ("planner_model", "reviewer_model") if policy.get(k))
        if policy.get("escalation_model") and policy["max_attempts"] > policy["cheap_attempts"]:
            models.append(policy["escalation_model"])
        if any(m not in policy.get("prices", {}) for m in models):
            raise ValueError("Dollar budgets require explicit prices for every selected model")
    return policy


def load_task(path, pack=None):
    task = merge(read(pack / "pack.toml").get("task", {}) if pack else {}, read(path))
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", task.get("id", "")):
        raise ValueError("Task id must contain 1–80 letters, numbers, underscores or hyphens")
    if not isinstance(task.get("prompt"), str) or not task["prompt"].strip():
        raise ValueError("Task needs a nonempty prompt")
    for field in ("checks", "setup"):
        commands = task.get(field, [])
        if not isinstance(commands, list) or (field == "checks" and not commands):
            raise ValueError("At least one check is required")
        for command in commands:
            if not isinstance(command, list) or not command or not all(isinstance(x, str) and x for x in command):
                raise ValueError(f"{field} must contain argv arrays; shell strings are not supported")
    task.setdefault("protected_paths", [])
    for path in task["protected_paths"]:
        if not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in Path(path).parts:
            raise ValueError("protected_paths must be repository-relative paths or glob patterns")
    return task


def toml_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{json.dumps(k)} = {toml_value(v)}" for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(v) for v in value) + "]"
    if isinstance(value, (str, int, float)):
        return json.dumps(value)
    raise ValueError(f"Unsupported TOML value: {type(value)}")
