import contextlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from codex_harness.app_server import _Protocol, invoke
from codex_harness.codex import parse_events


FAKE = r'''
import json, os, pathlib, sys, time

root = pathlib.Path(__file__).parent
(root / "pid").write_text(str(os.getpid()))

def emit(value):
    data = (json.dumps(value, ensure_ascii=False) + "\n").encode()
    # Exercise a UTF-8 sequence split across OS writes.
    point = data.find("é".encode()) + 1
    if point > 0:
        os.write(1, data[:point]); os.write(1, data[point:])
    else:
        os.write(1, data)

def notification(method, **params):
    emit({"method": method, "params": {"threadId": "thread-1", **params}})

for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")
    if method == "initialize":
        emit({"id": request["id"], "result": {"userAgent": "fixture"}})
    elif method == "thread/start":
        params = request["params"]
        assert params["ephemeral"] is True
        assert params["approvalPolicy"] == "never"
        sandbox = "workspaceWrite" if params["sandbox"] == "workspace-write" else "readOnly"
        emit({"id": request["id"], "result": {"thread": {"id": "thread-1"},
             "model": params["model"], "approvalPolicy": "never",
             "sandbox": {"type": sandbox, "networkAccess": False}}})
    elif method == "turn/start":
        params = request["params"]
        (root / "request.json").write_text(json.dumps(params))
        emit({"id": request["id"], "result": {"turn": {"id": "turn-1"}}})
        notification("turn/started", turn={"id": "turn-1"})
        if (root / "hang").exists():
            time.sleep(30)
        if (root / "flood").exists():
            os.write(1, b"x" * 4096)
            time.sleep(30)
        notification("item/started", item={"type": "agentMessage", "id": "a1", "phase": "commentary", "text": ""})
        notification("item/agentMessage/delta", itemId="a1", turnId="turn-1", delta="Checking café.\n")
        # The test's observer must acknowledge the live delta before completion.
        deadline = time.monotonic() + 2
        while not (root / "ack").exists():
            if time.monotonic() > deadline:
                sys.exit(5)
            time.sleep(0.01)
        notification("item/completed", item={"type": "agentMessage", "id": "a1", "phase": "commentary", "text": "Checking café.\n"})
        item = {"id": "m1", "type": "mcpToolCall", "server": "tracker", "tool": "search", "arguments": {}, "status": "inProgress"}
        notification("item/started", item=item)
        item["status"] = "completed"
        item["result"] = {"content": [{"type": "text", "text": "Found it"}]}
        notification("item/completed", item=item)
        for total in (10, 20):
            notification("thread/tokenUsage/updated", turnId="turn-1", tokenUsage={"total": {
                "inputTokens": total, "cachedInputTokens": 4, "outputTokens": 6}})
        answer = json.dumps({"kind": "answer", "answer": "Hello café", "apply_patch": False, "task": None}, ensure_ascii=False)
        notification("item/started", item={"type": "agentMessage", "id": "a2", "phase": "final_answer", "text": ""})
        notification("item/agentMessage/delta", itemId="a2", turnId="turn-1", delta=answer[:30])
        notification("item/agentMessage/delta", itemId="a2", turnId="turn-1", delta=answer[30:])
        notification("item/completed", item={"type": "agentMessage", "id": "a2", "phase": "final_answer", "text": answer})
        notification("turn/completed", turn={"id": "turn-1", "status": "completed", "items": []})
'''


class Observer:
    def __init__(self, root):
        self.root, self.events, self.idles = root, [], 0

    def event(self, event):
        self.events.append(event)
        if event["type"] == "message_delta":
            (self.root / "ack").touch()

    def idle(self):
        self.idles += 1


class AppServerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.script = self.root / "server.py"
        self.script.write_text(FAKE)
        self.policy = {"codex_command": [sys.executable, "-u", str(self.script)], "reasoning_effort": "low"}
        self.observer = Observer(self.root)
        self.log = self.root / "events.jsonl"

        @contextlib.contextmanager
        def isolated(policy, mcp):
            yield {**os.environ, "SUPERCODEX_WORKER": "1"}

        patcher = mock.patch("codex_harness.codex_home.isolated_codex_home", isolated)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_turn(self, **kwargs):
        return invoke(self.policy, "test-model", self.root, "test prompt", {}, "prepare",
                      kwargs.get("timeout", 5), self.log, kwargs.get("observer", self.observer))

    def assert_stopped(self):
        pid = int((self.root / "pid").read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_real_deltas_arrive_before_backend_completion_and_preserve_audit(self):
        result = self.run_turn()
        self.assertEqual(result["returncode"], 0, result)
        self.assertIsNone(result["reason"])
        parsed = parse_events(result["output"])
        self.assertTrue(parsed["completed"])
        self.assertEqual(parsed["usage"], {"input_tokens": 20, "cached_input_tokens": 4, "output_tokens": 6})
        self.assertEqual(json.loads(parsed["message"])["answer"], "Hello café")
        deltas = [e for e in self.observer.events if e["type"] == "message_delta"]
        self.assertEqual(deltas[0]["text"], "Checking café.\n")
        self.assertEqual(deltas[-1]["phase"], "final_answer")
        self.assertEqual(len([e for e in self.observer.events if e["type"] == "tool_completed"]), 1)
        self.assertTrue(any(e.get("item", {}).get("type") == "mcp_tool_call" for e in parsed["events"]))
        request = json.loads((self.root / "request.json").read_text())
        self.assertIn("answer", request["outputSchema"]["required"])
        self.assertEqual(request["sandboxPolicy"], {"type": "readOnly", "networkAccess": False})
        self.assertEqual(request["approvalPolicy"], "never")
        self.assertTrue(self.observer.idles)
        self.assert_stopped()

    def test_timeout_stops_worker_and_preserves_log(self):
        (self.root / "hang").touch()
        result = self.run_turn(timeout=0.3)
        self.assertEqual(result["reason"], "timeout")
        self.assertEqual(result["returncode"], 1)
        self.assertIsNone(parse_events(result["output"])["usage"])
        self.assertTrue(self.log.exists())
        self.assert_stopped()

    def test_output_cap_stops_protocol_without_claiming_success(self):
        (self.root / "flood").touch()
        with mock.patch("codex_harness.app_server.MAX_BYTES", 1200):
            result = self.run_turn()
        self.assertEqual(result["reason"], "output_limit")
        self.assertFalse(parse_events(result["output"])["completed"])
        self.assert_stopped()

    def test_observer_interruption_stops_worker_and_writes_log(self):
        class Interrupted(Observer):
            def event(self, event):
                if event["type"] == "message_delta":
                    raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            self.run_turn(observer=Interrupted(self.root))
        self.assertTrue(self.log.exists())
        self.assert_stopped()

    def test_early_eof_is_failure_even_when_process_exits_zero(self):
        self.script.write_text("pass\n")
        result = self.run_turn()
        self.assertEqual(result["returncode"], 1)
        self.assertEqual(result["reason"], "protocol_eof")


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.sent, self.events = [], []
        self.protocol = _Protocol({"reasoning_effort": "low"}, "test-model", "/tmp/project", "prompt",
                                  "prepare", self.sent.append, self.events.append, None)

    def test_permission_and_elicitation_requests_are_declined(self):
        for method, expected in (("item/commandExecution/requestApproval", {"decision": "decline"}),
                                 ("mcpServer/elicitation/request", {"action": "decline"}),
                                 ("item/permissions/requestApproval", {"permissions": {}, "scope": "turn"})):
            self.protocol.receive({"id": 50, "method": method, "params": {}})
            self.assertEqual(self.sent[-1], {"id": 50, "result": expected})
        self.protocol.receive({"id": 51, "method": "unknown/request", "params": {}})
        self.assertEqual(self.sent[-1]["error"]["code"], -32601)

    def test_policy_mismatch_blocks_before_model_turn(self):
        self.protocol.receive({"id": 2, "result": {"thread": {"id": "t"}, "model": "test-model",
            "approvalPolicy": "never", "sandbox": {"type": "dangerFullAccess"}}})
        self.assertEqual(self.protocol.reason, "policy_mismatch")
        self.assertFalse(any(x.get("method") == "turn/start" for x in self.sent))

    def test_missing_usage_remains_unknown_and_failed_turn_retains_usage(self):
        self.protocol.receive({"method": "turn/completed", "params": {"turn": {"status": "completed"}}})
        parsed = parse_events("\n".join(json.dumps(x) for x in self.events))
        self.assertIsNone(parsed["usage"])
        self.events.clear()
        self.protocol.usage = {"input_tokens": 20, "cached_input_tokens": 2, "output_tokens": 3}
        self.protocol.receive({"method": "turn/completed", "params": {"turn": {"status": "failed"}}})
        parsed = parse_events("\n".join(json.dumps(x) for x in self.events))
        self.assertFalse(parsed["completed"])
        self.assertEqual(parsed["usage"], self.protocol.usage)

    def test_invalid_or_regressing_usage_stays_unknown(self):
        for invalid in (None, [], {"total": None}, {"total": []},
                        {"total": {"inputTokens": True, "cachedInputTokens": 0, "outputTokens": 1}},
                        {"total": {"inputTokens": 5, "cachedInputTokens": 6, "outputTokens": 1}},
                        {"total": {"inputTokens": 5, "cachedInputTokens": 1, "outputTokens": 1}}):
            with self.subTest(invalid=invalid):
                self.protocol.usage_invalid = False
                self.protocol.usage = {"input_tokens": 20, "cached_input_tokens": 4, "output_tokens": 6}
                self.protocol.receive({"method": "thread/tokenUsage/updated", "params": {"tokenUsage": invalid}})
                self.protocol.receive({"method": "thread/tokenUsage/updated", "params": {"tokenUsage": {
                    "total": {"inputTokens": 25, "cachedInputTokens": 5, "outputTokens": 7}}}})
                self.assertIsNone(self.protocol.usage)
                self.assertTrue(self.protocol.usage_invalid)

    def test_malformed_nested_protocol_objects_fail_cleanly(self):
        for event in ({"method": []}, {"method": "turn/started", "params": {"turn": None}},
                      {"method": "turn/completed", "params": {"turn": []}},
                      {"method": "turn/completed", "params": {"turn": {"status": []}}},
                      {"method": "item/started", "params": {"item": {"type": [], "id": []}}},
                      {"id": 2, "result": {"thread": None, "sandbox": None}},
                      {"id": 3, "result": {"turn": None}}):
            with self.subTest(event=event):
                self.protocol.receive(event)
                self.assertTrue(self.protocol.done)
                self.assertIn(self.protocol.reason, {"protocol_error", "policy_mismatch"})


if __name__ == "__main__":
    unittest.main()
