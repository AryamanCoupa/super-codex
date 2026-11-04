"""Advisory per-message skill selection in the current native Codex session.

The event handler reads packaged metadata and writes only its JSON response.
Hook registration separately inspects Codex's exact definition for scoped trust.
"""

import sys

if __package__ in (None, ""):
    sys.dont_write_bytecode = True

import json
import os
from pathlib import Path
import shlex
import subprocess

if __package__ in (None, ""):
    # The installed/source package beside this trusted entry point, never cwd.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from codex_harness.agent_tools import bundled_skills, search_skills, skill_catalog_text
from codex_harness.prompt_hook import HOOK_KEY, _inspect_hook, _toml


MAX_INPUT_BYTES = 1_000_000
MAX_TOPIC_SKILLS = 3


def hook_definition():
    command = shlex.join([str(Path(sys.executable).absolute()), "-I", "-B", str(Path(__file__).resolve())])
    return {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": command,
                                              "timeout": 10,
                                              "statusMessage": "Selecting SuperCodex skills"}]}]}


def hook_overrides(codex_command, timeout=10):
    """Trust only this inspected hook for this launch, without global changes."""
    definition = hook_definition()
    try:
        digest = _inspect_hook(codex_command, definition, timeout)
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as error:
        raise ValueError("Cannot enable the SuperCodex skill reminder with this Codex installation; "
                         "continue with bootstrap skills or explicitly choose --no-prompt-hook.") from error
    return ["-c", "hooks.UserPromptSubmit=" + _toml(definition["UserPromptSubmit"]),
            "-c", "hooks.state=" + _toml({HOOK_KEY: {"trusted_hash": digest}})]


def remind(payload):
    """Return trusted skill guidance; the user's prompt is matching data only."""
    if os.environ.get("SUPERCODEX_WORKER") == "1":
        return {}
    if not isinstance(payload, dict) or payload.get("hook_event_name") != "UserPromptSubmit":
        raise ValueError("Expected a UserPromptSubmit event")
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or "\0" in prompt:
        raise ValueError("Expected a nonempty text prompt")
    if len(prompt.encode("utf-8")) > MAX_INPUT_BYTES:
        raise ValueError("Prompt exceeds the reminder input limit")
    rows = bundled_skills()
    by_name = {row["name"]: row for row in rows}
    base_names = ("skill-discovery", "verify-changes")
    if any(name not in by_name for name in base_names):
        raise ValueError("Required bundled skill metadata is unavailable")
    try:
        matches = search_skills(prompt, rows)
    except ValueError:
        matches = []  # Empty/filler-only keyword queries need no topic shortlist.
    topics = [row for row in matches if row["name"] not in base_names][:MAX_TOPIC_SKILLS]
    instruction = (
        "SuperCodex skill guidance for this turn. Work in the current Codex session with its existing "
        "tools, streaming, context and permissions. Apply skill-discovery to select the smallest relevant "
        "set from the skills advertised by this session and the bundled candidates below. Read the selected "
        "SKILL.md instructions before applying them; reuse unchanged instructions already read. For code "
        "changes, use verify-changes to check the result and report the evidence.\n"
        "The topic shortlist matches keywords only; it is not a requirement to use every candidate or "
        "proof that a skill fits or was applied. Briefly name the skills actually being applied, then "
        "complete the user's task. Skill loading alone is not completion. No answer command, child-model "
        "process or managed receipt is compulsory for native work. Use managed workflows when the user "
        "selects them, and report only receipts that actually exist.\n"
        "For useful independent subtasks, consider economical-delegation and the native delegation tools "
        "actually available. Delegate bounded work only when it adds value, preserve the user's budget "
        "and model choices, and verify results. Do not add agents just to wrap a tool call.\n"
        "Existing higher-priority instructions, repository rules, user constraints and permission controls "
        "still apply. If this is session initialization with no user task and the bootstrap says to wait, "
        "briefly confirm readiness and wait; do not invent a task or start discovery work.\n"
        "Selection and verification entry points (verification applies when relevant):\n"
        + skill_catalog_text([by_name[name] for name in base_names])
        + "\nPossible topic skills:\n"
        + (skill_catalog_text(topics) if topics else
           "No bundled topic match. Check the advertised native catalog and use ordinary tools when no skill fits.")
    )
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": instruction}}


def main():
    if os.environ.get("SUPERCODEX_WORKER") == "1":
        print("{}")
        return 0
    try:
        data = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(data) > MAX_INPUT_BYTES:
            raise ValueError("Reminder payload exceeds its input limit")
        response = remind(json.loads(data))
        print(json.dumps(response, ensure_ascii=False))
    except (OSError, ValueError, TypeError, UnicodeError):
        print("{}")
        print("SuperCodex skill reminder unavailable for this message; continue with the session bootstrap.",
              file=sys.stderr)
    return 0  # Advisory guidance never blocks the user's native turn.


if __name__ == "__main__":
    raise SystemExit(main())
