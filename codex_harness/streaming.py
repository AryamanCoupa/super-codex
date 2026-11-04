"""Display live, public agent output without exposing structured task contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
import sys
import time
from typing import Callable, TextIO


class _TerminalText:
    """Remove terminal commands, including commands split between deltas."""

    def __init__(self) -> None:
        self.state = "text"

    def feed(self, text: str) -> str:
        output: list[str] = []
        for char in text:
            value = ord(char)
            if self.state == "text":
                if char == "\x1b":
                    self.state = "escape"
                elif char == "\x9b":
                    self.state = "csi"
                elif char in "\x90\x98\x9d\x9e\x9f":
                    self.state = "string"
                elif char in "\n\t" or (
                    value >= 32 and not 127 <= value <= 159
                    and not 0xD800 <= value <= 0xDFFF
                ):
                    output.append(char)
            elif self.state == "escape":
                if char == "[":
                    self.state = "csi"
                elif char in "]PX^_":
                    self.state = "string"
                elif 0x20 <= value <= 0x2F:
                    self.state = "escape_intermediate"
                elif char != "\x1b":
                    self.state = "text"
            elif self.state == "escape_intermediate":
                if char == "\x1b":
                    self.state = "escape"
                elif 0x30 <= value <= 0x7E:
                    self.state = "text"
            elif self.state == "csi":
                if char == "\x1b":
                    self.state = "escape"
                elif 0x40 <= value <= 0x7E:
                    self.state = "text"
            elif self.state == "string":
                if char in "\x07\x9c":
                    self.state = "text"
                elif char == "\x1b":
                    self.state = "string_escape"
            elif self.state == "string_escape":
                if char in "\\\x07\x9c":
                    self.state = "text"
                elif char != "\x1b":
                    self.state = "string"
        return "".join(output)


def sanitize_terminal_text(text: str) -> str:
    """Strip terminal commands from a complete message, preserving text and line breaks.

    Use the stateful renderer for deltas so escape sequences spanning chunks are
    removed together. Each complete message has an independent terminal state.
    """
    return _TerminalText().feed(text)


class _JsonString:
    """Incrementally decode one JSON string, holding incomplete escape sequences."""

    _escapes = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f",
                "n": "\n", "r": "\r", "t": "\t"}

    def __init__(self) -> None:
        self.escape = False
        self.hex_digits: str | None = None
        self.high_surrogate: int | None = None
        self.closed = False
        self.invalid = False

    def _character(self, char: str) -> str:
        value = ord(char)
        prefix = ""
        if self.high_surrogate is not None:
            high = self.high_surrogate
            self.high_surrogate = None
            if 0xDC00 <= value <= 0xDFFF:
                return chr(0x10000 + ((high - 0xD800) << 10) + value - 0xDC00)
            prefix = chr(high)
        if 0xD800 <= value <= 0xDBFF:
            self.high_surrogate = value
            return prefix
        return prefix + char

    def feed(self, char: str) -> str:
        if self.closed or self.invalid:
            return ""
        if self.hex_digits is not None:
            if char not in "0123456789abcdefABCDEF":
                self.invalid = True
                return ""
            self.hex_digits += char
            if len(self.hex_digits) == 4:
                decoded = chr(int(self.hex_digits, 16))
                self.hex_digits = None
                return self._character(decoded)
            return ""
        if self.escape:
            self.escape = False
            if char == "u":
                self.hex_digits = ""
                return ""
            if char not in self._escapes:
                self.invalid = True
                return ""
            return self._character(self._escapes[char])
        if char == "\\":
            self.escape = True
            return ""
        if char == '"':
            self.closed = True
            if self.high_surrogate is not None:
                decoded = chr(self.high_surrogate)
                self.high_surrogate = None
                return decoded
            return ""
        if ord(char) < 32:
            self.invalid = True
            return ""
        return self._character(char)


class _PreparationAnswer:
    """Extract only a top-level answer string; validation belongs to the controller."""

    def __init__(self) -> None:
        self.depth = 0
        self.expect_key = False
        self.expect_value = False
        self.key = ""
        self.string: _JsonString | None = None
        self.string_kind = ""
        self.key_parts: list[str] = []
        self.found = False
        self.done = False
        self.invalid = False

    def feed(self, text: str) -> str:
        output: list[str] = []
        for char in text:
            if self.done or self.invalid:
                break
            if self.string is not None:
                decoded = self.string.feed(char)
                if self.string_kind == "answer":
                    output.append(decoded)
                elif self.string_kind == "key":
                    self.key_parts.append(decoded)
                if self.string.invalid:
                    self.invalid = True
                if self.string.closed:
                    if self.string_kind == "key":
                        self.key = "".join(self.key_parts)
                        self.expect_key = False
                    self.string = None
                continue
            if char in " \t\r\n":
                continue
            if char == '"':
                self.string = _JsonString()
                self.string_kind = "skip"
                if self.depth == 1:
                    if self.expect_key:
                        self.string_kind = "key"
                        self.key_parts = []
                    elif self.expect_value and self.key == "answer" and not self.found:
                        self.string_kind = "answer"
                        self.found = True
                    self.expect_value = False
            elif char in "{[":
                self.depth += 1
                if self.depth == 1:
                    self.expect_key = char == "{"
                elif self.depth == 2:
                    self.expect_value = False
            elif char in "}]":
                self.depth -= 1
                if self.depth <= 0:
                    self.done = True
            elif self.depth == 1 and char == ":":
                self.expect_value = True
            elif self.depth == 1 and char == ",":
                self.expect_key = True
                self.expect_value = False
                self.key = ""
        return "".join(output)


@dataclass
class _Message:
    raw: str = ""
    pending: str = ""
    mode: str = "pending"
    completed: bool = False
    revised: bool = False
    terminal: _TerminalText = field(default_factory=_TerminalText)
    answer: _PreparationAnswer = field(default_factory=_PreparationAnswer)
    answer_text: str = ""


class StreamRenderer:
    """Render genuine response deltas and limited tool status, flushing immediately.

    ``answer_text`` retains the decoded preparation answer for the controller's
    final-output deduplication. Display sanitization does not alter that value.
    Streamed preparation text is provisional; this class never marks it verified.
    """

    def __init__(
        self,
        stream: TextIO | None = None,
        status_stream: TextIO | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.stream = sys.stdout if stream is None else stream
        self.status_stream = sys.stderr if status_stream is None else status_stream
        self.clock = clock
        self.role = ""
        self._answer_text = ""
        self._messages: dict[str, _Message] = {}
        self._tools: set[tuple[str, str]] = set()
        self._active = False
        self._line_open = False
        self._last_message: str | None = None
        self._last_output = self.clock()

    @property
    def answer_text(self) -> str:
        return self._answer_text

    @staticmethod
    def _label(value: object, fallback: str, limit: int = 160) -> str:
        if not isinstance(value, str):
            return fallback
        cleaned = " ".join(sanitize_terminal_text(value).split())
        return cleaned[:limit] or fallback

    def _write(self, text: str) -> None:
        if not text:
            return
        self.stream.write(text)
        self.stream.flush()
        self._line_open = not text.endswith("\n")
        self._last_output = self.clock()

    def _status(self, text: str) -> None:
        if self._line_open:
            self._write("\n")
        self.status_stream.write(text + "\n")
        self.status_stream.flush()
        self._last_output = self.clock()

    def start(self, role: str, model: str) -> None:
        self.role = role
        self._messages = {}
        self._tools = set()
        self._last_message = None
        self._active = True
        if role == "prepare":
            self._answer_text = ""
        label = {"prepare": "Preparing response", "plan": "Planning",
                 "implement": "Implementing", "review": "Reviewing"}.get(role, "Running Codex")
        self._status(f"{label} ({self._label(model, 'configured model')})…")

    def _message(self, identifier: str, state: _Message, text: str) -> None:
        if state.mode == "pending":
            state.pending += text
            content = state.pending.lstrip()
            if not content:
                return
            if self.role in {"prepare", "review"} and content[0] in "{[":
                state.mode = "answer" if self.role == "prepare" and content[0] == "{" else "hidden"
            else:
                state.mode = "plain"
            text = state.pending
            state.pending = ""
        if state.mode == "hidden":
            return
        if state.mode == "answer":
            text = state.answer.feed(text)
            state.answer_text += text
            if state.answer.found:
                self._answer_text = state.answer_text
        visible = state.terminal.feed(text)
        if visible:
            if self._last_message != identifier and self._line_open:
                self._write("\n")
            self._last_message = identifier
            self._write(visible)

    def event(self, event: dict) -> None:
        if not isinstance(event, dict):
            return
        kind = event.get("type")
        if not isinstance(kind, str):
            return
        if kind in {"message_delta", "message_completed"}:
            text = event.get("text")
            if not isinstance(text, str):
                return
            identifier = event.get("id")
            identifier = identifier if isinstance(identifier, str) else "message"
            state = self._messages.setdefault(identifier, _Message())
            if state.completed:
                return
            if kind == "message_completed":
                state.completed = True
                if text.startswith(state.raw):
                    text = text[len(state.raw):]
                elif state.raw.startswith(text):
                    return
                else:
                    # Already displayed deltas cannot be retracted. Let the
                    # controller validate and print a revised final answer.
                    if not state.revised:
                        self._status("The final response changed; checking the completed result.")
                        state.revised = True
                    return
            state.raw += text
            self._message(identifier, state, text)
        elif kind in {"tool_started", "tool_completed"}:
            tool = self._label(event.get("tool"), "tool")
            identifier = self._label(event.get("id"), tool)
            state = "started" if kind == "tool_started" else "completed"
            status = event.get("status")
            if kind == "tool_completed" and isinstance(status, str) and status in {"failed", "error", "cancelled", "canceled"}:
                state = status
            key = (identifier, state)
            if key not in self._tools:
                self._tools.add(key)
                self._status(f"Tool {state}: {tool}")
        elif kind == "stage_error":
            self._status(f"Codex error: {self._label(event.get('message'), 'request failed', 500)}")

    def idle(self) -> None:
        if self._active and self.clock() - self._last_output >= 10:
            self._status("Waiting for more Codex output…")

    def finish(self) -> None:
        if self._line_open:
            self._write("\n")
        self._active = False
