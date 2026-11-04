"""Bounded Codex app-server client with real assistant-text deltas.

The app-server protocol is NDJSON over stdio. Requests are never logged because
their configuration can contain credentials; only normalized run events are.
"""

import json
import os
import re
import selectors
import subprocess
import time
from pathlib import Path

from . import __version__
from .config import ASSETS, toml_value
from .process import stop


MAX_BYTES = 8_000_000


def _command(policy, mcp):
    argv = list(policy["codex_command"]) + ["app-server", "--listen", "stdio://"]
    overrides = {"approval_policy": "never", "sandbox_workspace_write.network_access": False}
    if policy.get("web_search") is not None:
        overrides["web_search"] = policy["web_search"]
    for key, value in overrides.items():
        argv += ["-c", f"{key}={toml_value(value)}"]
    for name, config in mcp.items():
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise ValueError("MCP server names must contain only letters, numbers, underscores or hyphens")
        argv += ["-c", f"mcp_servers.{name}={toml_value(config)}"]
    return argv


def _item(item):
    result = dict(item)
    kind = item.get("type", "")
    result["type"] = re.sub(r"(?<!^)(?=[A-Z])", "_", kind).lower()
    for camel, snake in (("aggregatedOutput", "aggregated_output"), ("exitCode", "exit_code")):
        if camel in result:
            result[snake] = result.pop(camel)
    return result


class _Protocol:
    def __init__(self, policy, model, workspace, prompt, role, send, emit, observer):
        self.policy, self.model, self.workspace = policy, model, str(workspace)
        self.prompt, self.role, self.send, self.emit, self.observer = prompt, role, send, emit, observer
        self.thread_id = self.turn_id = None
        self.usage = None
        self.usage_invalid = False
        self.phases = {}
        self.done = False
        self.reason = None

    def notify(self, event):
        if self.observer is not None:
            self.observer.event(event)

    def error(self, reason, message):
        self.reason, self.done = reason, True
        self.emit({"type": "error", "message": message})
        self.notify({"type": "stage_error", "message": message})

    def begin(self):
        self.send({"id": 1, "method": "initialize", "params": {
            "clientInfo": {"name": "supercodex", "version": __version__}}})

    def receive(self, event):
        if not isinstance(event, dict):
            self.error("protocol_error", "Codex app-server sent a non-object response.")
            return
        if "method" in event and not isinstance(event["method"], str):
            self.error("protocol_error", "Codex app-server sent an invalid method.")
            return
        if "id" in event and "method" in event:
            # A managed worker has no interactive approval channel. Decline all
            # permission requests; never turn an unexpected prompt into consent.
            method = event["method"]
            if method == "account/chatgptAuthTokens/refresh":
                message = "Codex login needs refreshing. Run codex login, then retry SuperCodex."
                self.send({"id": event["id"], "error": {"code": -32000, "message": message}})
                self.error("authentication_required", message)
                return
            results = {
                "item/commandExecution/requestApproval": {"decision": "decline"},
                "item/fileChange/requestApproval": {"decision": "decline"},
                "item/permissions/requestApproval": {"permissions": {}, "scope": "turn"},
                "mcpServer/elicitation/request": {"action": "decline"},
            }
            response = {"id": event["id"]}
            if method in results:
                response["result"] = results[method]
            else:
                response["error"] = {"code": -32601, "message": "Unsupported request in managed session"}
            self.send(response)
            return
        if "id" in event:
            self.response(event)
            return
        method, params = event.get("method"), event.get("params", {})
        if not isinstance(params, dict):
            self.error("protocol_error", "Codex app-server sent invalid notification parameters.")
            return
        if params.get("threadId") not in (None, self.thread_id):
            return
        if method == "turn/started":
            turn = params.get("turn")
            if not isinstance(turn, dict) or not isinstance(turn.get("id"), str):
                self.error("protocol_error", "Codex app-server sent an invalid turn.")
                return
            self.turn_id = turn["id"]
            self.emit({"type": "turn.started"})
        elif method == "thread/tokenUsage/updated":
            snapshot = params.get("tokenUsage")
            usage = snapshot.get("total") if isinstance(snapshot, dict) else None
            # Fresh ephemeral thread: totals include every model/tool iteration.
            # Each notification is a snapshot, not an additional charge.
            keys = (
                ("inputTokens", "input_tokens"), ("cachedInputTokens", "cached_input_tokens"),
                ("outputTokens", "output_tokens"))
            valid = (isinstance(usage, dict)
                     and all(isinstance(usage.get(camel), int) and not isinstance(usage[camel], bool)
                             and usage[camel] >= 0 for camel, _ in keys)
                     and usage["cachedInputTokens"] <= usage["inputTokens"])
            translated = {snake: usage[camel] for camel, snake in keys} if valid else None
            if valid and self.usage is not None:
                valid = all(translated[key] >= value for key, value in self.usage.items())
            self.usage_invalid = self.usage_invalid or not valid
            self.usage = translated if not self.usage_invalid else None
        elif method == "item/agentMessage/delta":
            item_id, delta = params.get("itemId"), params.get("delta")
            if isinstance(delta, str) and isinstance(item_id, str):
                phase = self.phases.get(item_id)
                self.emit({"type": "item.agent_message.delta", "item_id": item_id,
                           "delta": delta, "phase": phase})
                self.notify({"type": "message_delta", "id": item_id, "text": delta, "phase": phase})
        elif method in {"item/started", "item/completed"}:
            raw = params.get("item")
            if (not isinstance(raw, dict) or not isinstance(raw.get("type"), str)
                    or not isinstance(raw.get("id"), str)
                    or (raw.get("type") == "agentMessage" and not isinstance(raw.get("text"), str))):
                self.error("protocol_error", "Codex app-server sent an invalid item.")
                return
            item = _item(raw)
            self.emit({"type": method.replace("/", "."), "item": item})
            item_id = item.get("id")
            if item.get("type") == "agent_message":
                self.phases[item_id] = item.get("phase")
                if method == "item/completed":
                    self.notify({"type": "message_completed", "id": item_id,
                                 "text": item.get("text", ""), "phase": item.get("phase")})
            elif item.get("type") in {"mcp_tool_call", "command_execution", "file_change", "web_search"}:
                label = item.get("tool") or item.get("type")
                self.notify({"type": "tool_started" if method == "item/started" else "tool_completed",
                             "id": item_id, "tool": label, "status": item.get("status")})
        elif method == "turn/completed":
            turn = params.get("turn")
            if not isinstance(turn, dict) or turn.get("status") not in ("completed", "failed", "interrupted"):
                self.error("protocol_error", "Codex app-server sent an invalid completion.")
                return
            status = turn.get("status")
            self.done = True
            # Keep observed charges even on a failed turn. parse_events also sees
            # turn.failed, so this cannot mark a failed worker as completed.
            self.emit({"type": "turn.completed", "usage": self.usage or {}, "status": status})
            if status != "completed":
                self.reason = "turn_" + str(status or "failed")
                self.emit({"type": "turn.failed", "error": turn.get("error")})
                self.notify({"type": "stage_error", "message": "Codex turn " + str(status or "failed")})
        elif method == "error":
            # Codex may retry transient upstream errors. Only turn/completed
            # decides terminal success; retain this notification for the audit.
            self.emit({"type": "error", "error": params.get("error"),
                       "will_retry": params.get("willRetry", False)})

    def response(self, event):
        if "error" in event:
            error = event.get("error") or {}
            message = error.get("message", "Codex app-server rejected a request.") if isinstance(error, dict) else str(error)
            self.error("protocol_error", str(message)[:2000])
            return
        result = event.get("result")
        if not isinstance(result, dict):
            self.error("protocol_error", "Codex app-server sent an invalid response.")
            return
        if event["id"] == 1:
            self.send({"method": "initialized"})
            self.start_thread()
        elif event["id"] == 2:
            thread = result.get("thread")
            self.thread_id = thread.get("id") if isinstance(thread, dict) else None
            expected = "workspaceWrite" if self.role == "implement" else "readOnly"
            sandbox = result.get("sandbox")
            if (not isinstance(self.thread_id, str) or result.get("approvalPolicy") != "never"
                    or not isinstance(sandbox, dict) or sandbox.get("type") != expected or sandbox.get("networkAccess", False)
                    or result.get("model") != self.model):
                self.error("policy_mismatch", "Codex app-server did not honor the requested model or sandbox policy.")
                return
            params = {"threadId": self.thread_id, "input": [{"type": "text", "text": self.prompt}],
                      "approvalPolicy": "never", "effort": self.policy["reasoning_effort"],
                      "sandboxPolicy": {"type": expected, "networkAccess": False}}
            if self.role in {"review", "prepare"}:
                params["outputSchema"] = json.loads((ASSETS / f"{self.role}.schema.json").read_text())
            self.send({"id": 3, "method": "turn/start", "params": params})
        elif event["id"] == 3:
            turn = result.get("turn")
            if not isinstance(turn, dict) or not isinstance(turn.get("id"), str):
                self.error("protocol_error", "Codex app-server sent an invalid turn response.")
                return
            self.turn_id = turn["id"]

    def start_thread(self):
        params = {"model": self.model, "cwd": self.workspace, "approvalPolicy": "never",
                  "sandbox": "workspace-write" if self.role == "implement" else "read-only",
                  "ephemeral": True}
        provider = self.policy.get("local_provider") or self.policy.get("model_provider")
        if provider:
            params["modelProvider"] = provider
        self.send({"id": 2, "method": "thread/start", "params": params})


def invoke(policy, model, workspace, prompt, mcp, role, timeout, log, observer=None):
    """Run one isolated ephemeral Codex turn and stream observed text deltas.

    Return process-like fields; ``output`` is exec-compatible normalized JSONL.
    No automatic transport fallback can duplicate a partially charged turn.
    """
    from .codex_home import isolated_codex_home

    started = time.monotonic()
    lines, diagnostic = [], bytearray()
    process = None
    cleaned = False
    protocol = None
    reason = None
    normalized_bytes = 0

    def emit(event):
        nonlocal normalized_bytes
        line = json.dumps(event, ensure_ascii=False) + "\n"
        normalized_bytes += len(line.encode())
        if normalized_bytes > MAX_BYTES:
            raise OverflowError("output_limit")
        lines.append(line)

    try:
        argv = _command(policy, mcp)
        with isolated_codex_home(policy, mcp) as env:
            process = subprocess.Popen(argv, cwd=workspace, env=env, stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            selector = selectors.DefaultSelector()
            pending, buffer = bytearray(), bytearray()
            total_bytes = 0
            for pipe in (process.stdin, process.stdout, process.stderr):
                os.set_blocking(pipe.fileno(), False)
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(process.stderr, selectors.EVENT_READ, "stderr")

            def send(request):
                pending.extend((json.dumps(request, ensure_ascii=False) + "\n").encode())
                try:
                    selector.get_key(process.stdin)
                except KeyError:
                    selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")

            protocol = _Protocol(policy, model, workspace, prompt, role, send, emit, observer)
            try:
                protocol.begin()
                while not protocol.done:
                    remaining = timeout - (time.monotonic() - started)
                    if remaining <= 0:
                        reason = "timeout"
                        break
                    if observer is not None:
                        observer.idle()
                    for key, _ in selector.select(min(0.1, remaining)):
                        if key.data == "stdin":
                            try:
                                written = os.write(key.fd, pending[:65536])
                            except BlockingIOError:
                                continue
                            del pending[:written]
                            if not pending:
                                selector.unregister(process.stdin)
                            continue
                        try:
                            data = os.read(key.fd, 65536)
                        except BlockingIOError:
                            continue
                        if not data:
                            selector.unregister(key.fileobj)
                            if key.data == "stdout" and not protocol.done:
                                reason = "protocol_eof"
                            continue
                        total_bytes += len(data)
                        if total_bytes > MAX_BYTES:
                            reason = "output_limit"
                            break
                        if key.data == "stderr":
                            diagnostic.extend(data[:max(0, 32000 - len(diagnostic))])
                            continue
                        buffer.extend(data)
                        while b"\n" in buffer and not protocol.done:
                            line, _, rest = buffer.partition(b"\n")
                            buffer[:] = rest
                            if not line.strip():
                                continue
                            try:
                                event = json.loads(line)
                            except (ValueError, UnicodeDecodeError):
                                protocol.error("protocol_error", "Codex app-server sent malformed JSON.")
                                break
                            protocol.receive(event)
                    if reason:
                        break
                reason = reason or protocol.reason
            finally:
                # Interrupt is best effort: never wait beyond the run's deadline.
                # Killing the private process group also cleans up MCP children.
                if protocol.turn_id and not protocol.done:
                    try:
                        request = {"id": 4, "method": "turn/interrupt", "params": {
                            "threadId": protocol.thread_id, "turnId": protocol.turn_id}}
                        os.write(process.stdin.fileno(), (json.dumps(request) + "\n").encode())
                    except (OSError, ValueError):
                        pass
                stop(process)
                cleaned = True
                selector.close()
                for pipe in (process.stdin, process.stdout, process.stderr):
                    pipe.close()
    except OverflowError:
        reason = "output_limit"
    except (OSError, ValueError) as exc:
        reason = "configuration_error" if process is None else "transport_error"
        message = str(exc)[:2000]
        emit({"type": "error", "message": message})
        if observer is not None:
            observer.event({"type": "stage_error", "message": message})
    finally:
        if process is not None and not cleaned:
            stop(process)
            for pipe in (process.stdin, process.stdout, process.stderr):
                if pipe is not None:
                    pipe.close()
        if log:
            contents = "".join(lines)
            if diagnostic:
                contents += "\n[app-server diagnostics]\n" + diagnostic.decode("utf-8", errors="replace")
            Path(log).write_text(contents)
    return {"returncode": 0 if protocol and protocol.done and not reason else 1,
            "reason": reason, "output": "".join(lines), "seconds": round(time.monotonic() - started, 3)}
