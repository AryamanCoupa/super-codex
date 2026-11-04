"""Session-local native Codex prompt routing, without shell interpolation.

Codex calls this file directly as a UserPromptSubmit command hook. It records
the exact prompt and supplies a concrete answer command as developer context.
It never invokes a model itself or writes the user's Codex configuration.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import uuid


MAX_INPUT_BYTES = 1_000_000
MAX_CONTEXT_BYTES = 16_000
HOOK_KEY = "/<session-flags>/config.toml:user_prompt_submit:0:0"


def _toml(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[" + ",".join(_toml(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(json.dumps(key) + "=" + _toml(item) for key, item in value.items()) + "}"
    raise ValueError("Unsupported hook configuration value")


def hook_definition(session_file):
    command = shlex.join([str(Path(sys.executable).absolute()), str(Path(__file__).resolve()),
                          "--session", str(Path(session_file).absolute())])
    return {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": command,
                                              "timeout": 10,
                                              "statusMessage": "Routing through SuperCodex"}]}]}


def _inspect_hook(codex_command, definition, timeout):
    """Ask installed Codex for its own hook hash without authentication or a turn."""
    if not isinstance(codex_command, list) or not codex_command or not all(
            isinstance(part, str) and part for part in codex_command):
        raise ValueError("codex_command must be a nonempty argv array")
    override = "hooks.UserPromptSubmit=" + _toml(definition["UserPromptSubmit"])
    with tempfile.TemporaryDirectory(prefix="supercodex-hook-probe-") as temporary:
        env = dict(os.environ)
        env.update(CODEX_HOME=temporary, SUPERCODEX_WORKER="1")
        env.pop("OPENAI_API_KEY", None)
        argv = codex_command + ["app-server", "--strict-config", "-c", 'model_provider="ollama"',
                                 "-c", "features.plugins=false", "-c", override]
        process = subprocess.Popen(argv, cwd=temporary, env=env, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   start_new_session=True)
        selector = selectors.DefaultSelector()
        buffer, consumed = bytearray(), 0
        selector.register(process.stdout, selectors.EVENT_READ)

        def send(request):
            process.stdin.write((json.dumps(request) + "\n").encode())
            process.stdin.flush()

        try:
            send({"id": 1, "method": "initialize", "params": {
                "clientInfo": {"name": "supercodex_hook_probe", "version": "1"}}})
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                for key, _ in selector.select(min(.1, max(0, deadline - time.monotonic()))):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        raise ValueError("Codex closed its hook inspection connection")
                    consumed += len(chunk)
                    if consumed > MAX_INPUT_BYTES:
                        raise ValueError("Codex hook inspection exceeded its output limit")
                    buffer.extend(chunk)
                    while b"\n" in buffer:
                        line, _, rest = buffer.partition(b"\n")
                        buffer[:] = rest
                        if not line.strip():
                            continue
                        response = json.loads(line)
                        if not isinstance(response, dict):
                            raise ValueError("Codex returned an invalid hook inspection response")
                        if "error" in response:
                            raise ValueError("Codex rejected the session-local hook configuration")
                        if response.get("id") == 1:
                            send({"method": "initialized"})
                            send({"id": 2, "method": "hooks/list", "params": {"cwds": [temporary]}})
                        elif response.get("id") == 2:
                            result = response.get("result")
                            if not isinstance(result, dict) or not isinstance(result.get("data"), list):
                                raise ValueError("Codex returned an invalid hook list")
                            entries = result["data"]
                            if any(not isinstance(entry, dict) or entry.get("errors")
                                   or not isinstance(entry.get("hooks"), list) for entry in entries):
                                raise ValueError("Codex could not load the session-local hook")
                            hooks = [hook for entry in entries for hook in entry["hooks"]]
                            if len(hooks) != 1 or not isinstance(hooks[0], dict):
                                raise ValueError("Unexpected hooks in isolated hook inspection")
                            hook = hooks[0]
                            expected = definition["UserPromptSubmit"][0]["hooks"][0]["command"]
                            if (hook.get("key") != HOOK_KEY or hook.get("source") != "sessionFlags"
                                    or hook.get("eventName") != "userPromptSubmit"
                                    or hook.get("handlerType") != "command"
                                    or hook.get("command") != expected or hook.get("enabled") is not True
                                    or not re.fullmatch(r"sha256:[0-9a-f]{64}", hook.get("currentHash", ""))):
                                raise ValueError("Codex hook inspection did not match the owned hook")
                            return hook["currentHash"]
            raise ValueError("Codex hook inspection timed out")
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                if process.poll() is None:
                    raise
            process.wait()
            selector.close()
            process.stdin.close()
            process.stdout.close()


def hook_overrides(codex_command, session_file, timeout=10):
    """Return only the owned hook and its exact, session-scoped trust override.

    Native Codex merges hook sources across layers. This does not replace user
    hooks, grant trust to other hooks, or bypass the native hook-trust mechanism.
    """
    definition = hook_definition(session_file)
    try:
        digest = _inspect_hook(codex_command, definition, timeout)
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as error:
        raise ValueError("Cannot enable per-message SuperCodex routing with this Codex installation. "
                         "Use a compatible Codex version or explicitly choose --no-prompt-hook "
                         "for bootstrap-only guidance.") from error
    return ["-c", "hooks.UserPromptSubmit=" + _toml(definition["UserPromptSubmit"]),
            "-c", "hooks.state=" + _toml({HOOK_KEY: {"trusted_hash": digest}})]


def _read_object(path, limit=MAX_INPUT_BYTES):
    with Path(path).open("rb") as source:
        data = source.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Routing data exceeded its size limit")
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError("Routing data must be a JSON object")
    return value


def _write_private(path, text):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as destination:
        destination.write(text)


def _context(root):
    rows = []
    candidates = []
    if root.is_dir():
        for path in root.glob("sessions/*/turns/*/receipt.json"):
            try:
                if not path.is_symlink() and path.resolve().is_relative_to(root):
                    candidates.append((path.stat().st_mtime_ns, str(path), path))
            except OSError:
                continue
    for _, _, path in sorted(candidates)[-6:]:
        try:
            receipt = _read_object(path)
        except (OSError, ValueError):
            continue
        # No native transcript, reasoning, tool arguments or tool results.
        row = {key: receipt.get(key, "") for key in ("request", "answer", "status")}
        if not all(isinstance(value, str) for value in row.values()):
            continue
        if row["status"] == "running":
            continue
        row["request"] = row["request"][:2000]
        row["answer"] = row["answer"][:3500]
        row["status"] = row["status"][:80]
        rows.append(row)
    while rows:
        encoded = json.dumps({"recent_turns": rows}, ensure_ascii=False)
        if len(encoded.encode()) <= MAX_CONTEXT_BYTES:
            return encoded
        if len(rows) > 1:
            rows.pop(0)
        else:
            rows[0]["request"] = rows[0]["request"][:1000]
            rows[0]["answer"] = rows[0]["answer"][:1000]
    return '{"recent_turns":[]}'


def route(payload, session_file):
    """Capture a user message and return its per-turn developer instruction."""
    if os.environ.get("SUPERCODEX_WORKER") == "1":
        return {}
    if not isinstance(payload, dict) or payload.get("hook_event_name") != "UserPromptSubmit":
        raise ValueError("Expected a UserPromptSubmit event")
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Expected a nonempty user prompt")
    path = Path(session_file).absolute()
    configuration = _read_object(path)
    digest = configuration.get("bootstrap_prompt_sha256")
    if isinstance(digest, str) and hashlib.sha256(prompt.encode()).hexdigest() == digest:
        return {}
    argv = configuration.get("answer_argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(arg, str) and arg for arg in argv):
        raise ValueError("Missing answer command in session routing configuration")
    output = configuration.get("output_root")
    if not isinstance(output, str) or not Path(output).is_absolute():
        raise ValueError("Missing absolute answer output root")
    root = Path(output).resolve()
    directory = path.parent.resolve()
    if not root.is_relative_to(directory):
        raise ValueError("Answer output root must remain inside the private session")
    messages = directory / "messages"
    if messages.is_symlink():
        raise ValueError("Message storage must not be a symlink")
    messages.mkdir(mode=0o700, exist_ok=True)
    messages.chmod(0o700)
    identifier = uuid.uuid4().hex
    prompt_file = messages / f"{identifier}.prompt.txt"
    context_file = messages / f"{identifier}.context.json"
    _write_private(prompt_file, prompt)
    _write_private(context_file, _context(root))
    command = shlex.join(argv + ["--prompt-file", str(prompt_file), "--context-file", str(context_file)])
    instruction = (
        "SuperCodex routing applies to this user message, including news, research, questions and coding. "
        "Before native browsing, answering, delegation or source edits, execute this exact command:\n"
        + command + "\n"
        "The prompt file preserves the user's actual message verbatim. Do not replace it with a summary. "
        "Preserve the bootstrap's repository, task pack, model policy and tool selections encoded in this command. "
        "Use the bounded recent-turn context only to interpret follow-ups. The managed request uses skill-discovery "
        "to choose and read relevant available skills before doing the work; listing skills alone is not a result. "
        "If the host blocks this command with a permission or sandbox error, including 'Operation not permitted', "
        "use the host's normal approval flow, when available, to request permission to rerun the exact same command. "
        "Explain that it starts the requested managed SuperCodex task. Keep the child Codex sandbox, approval "
        "settings, selected tools and budgets unchanged; never weaken them to make the retry succeed. If approval "
        "is denied or unavailable, report the blocker and any receipt instead of silently switching to native work. "
        "After the command finishes, "
        "read its receipt and use its answer and cited sources in your response; preserve source links "
        "and distinguish advisory answers from verified coding changes. Command discovery or merely "
        "describing SuperCodex does not satisfy routing. Do not silently bypass a failed or blocked run "
        "with native tools or an invented result: report the concrete failure and its receipt. "
        "Existing higher-priority instructions, native control commands and explicit user requests "
        "to change or bypass this workflow still apply."
    )
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": instruction}}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Internal session-local SuperCodex prompt hook")
    parser.add_argument("--session", required=True)
    args = parser.parse_args(argv)
    if os.environ.get("SUPERCODEX_WORKER") == "1":
        print("{}")
        return 0
    try:
        data = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(data) > MAX_INPUT_BYTES:
            raise ValueError("Prompt payload exceeded its size limit")
        response = route(json.loads(data), args.session)
        print(json.dumps(response, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, UnicodeError):
        print("SuperCodex could not route this message safely. Check the private session routing "
              "configuration or restart sc; no answer model was invoked by the hook.", file=sys.stderr)
        return 2  # Native UserPromptSubmit contract: block this turn with a reason.


if __name__ == "__main__":
    raise SystemExit(main())
