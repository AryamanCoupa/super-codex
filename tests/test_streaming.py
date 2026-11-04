import io
import json
import unittest

from codex_harness.streaming import StreamRenderer, sanitize_terminal_text


class FlushedOutput(io.StringIO):
    def __init__(self):
        super().__init__()
        self.flushes = 0

    def flush(self):
        self.flushes += 1
        super().flush()


class StreamingTests(unittest.TestCase):
    def setUp(self):
        self.output = FlushedOutput()
        self.status = FlushedOutput()
        self.now = 0.0
        self.renderer = StreamRenderer(self.output, self.status, lambda: self.now)

    def delta(self, text, identifier="answer"):
        self.renderer.event({"type": "message_delta", "id": identifier, "text": text})

    def complete(self, text, identifier="answer"):
        self.renderer.event({"type": "message_completed", "id": identifier, "text": text})

    def test_plain_text_is_flushed_before_completion(self):
        self.renderer.start("implement", "test-model")
        self.delta("A live ")
        self.assertEqual(self.output.getvalue(), "A live ")
        self.assertEqual(self.output.flushes, 1)
        self.delta("response ✓\n")
        self.assertEqual(self.output.getvalue(), "A live response ✓\n")
        self.assertEqual(self.output.flushes, 2)
        self.complete("A live response ✓\n")
        self.complete("A live response ✓\n")
        self.renderer.finish()
        self.assertEqual(self.output.getvalue(), "A live response ✓\n")

    def test_preparation_displays_answer_before_json_finishes(self):
        self.renderer.start("prepare", "test-model")
        self.delta('{"kind":"answer", "answer":"The first')
        self.assertEqual(self.output.getvalue(), "The first")
        self.assertEqual(self.renderer.answer_text, "The first")
        self.delta(' words", "task":{"prompt":"PRIVATE TASK"}}')
        self.assertEqual(self.output.getvalue(), "The first words")
        self.assertEqual(self.renderer.answer_text, "The first words")
        self.assertNotIn("PRIVATE", self.output.getvalue() + self.status.getvalue())
        self.assertNotIn("verified", self.status.getvalue())

    def test_json_escaping_at_every_chunk_boundary(self):
        answer = 'Café 日本語 😀 / "quoted" \\ path\nnext\tcolumn\r\b\f'
        body = json.dumps({"task": {"answer": "DO NOT DISPLAY", "items": ["}", "answer"]},
                           "answer": answer, "kind": "answer", "apply_patch": False})
        visible = 'Café 日本語 😀 / "quoted" \\ path\nnext\tcolumn'
        for boundary in range(len(body) + 1):
            with self.subTest(boundary=boundary):
                output = io.StringIO()
                renderer = StreamRenderer(output, io.StringIO())
                renderer.start("prepare", "test-model")
                renderer.event({"type": "message_delta", "id": "a", "text": body[:boundary]})
                renderer.event({"type": "message_delta", "id": "a", "text": body[boundary:]})
                renderer.event({"type": "message_completed", "id": "a", "text": body})
                self.assertEqual(output.getvalue(), visible)
                self.assertEqual(renderer.answer_text, answer)

    def test_one_character_deltas_decode_unicode_and_escaped_answer_key(self):
        self.renderer.start("prepare", "test-model")
        body = '  {"task":{"answer":"hidden"},"answ\\u0065r":"é\\n\\ud83d\\ude80","kind":"answer"}'
        for char in body:
            self.delta(char)
        self.assertEqual(self.output.getvalue(), "é\n🚀")
        self.assertEqual(self.renderer.answer_text, "é\n🚀")

    def test_split_surrogate_pair_is_not_prematurely_displayed(self):
        self.renderer.start("prepare", "test-model")
        self.delta('{"answer":"Launch \\ud83d')
        self.assertEqual(self.output.getvalue(), "Launch ")
        self.delta('\\ud')
        self.assertEqual(self.output.getvalue(), "Launch ")
        self.delta('e80 now"}')
        self.assertEqual(self.output.getvalue(), "Launch 🚀 now")

    def test_plain_commentary_and_structured_final_are_separate(self):
        self.renderer.start("prepare", "test-model")
        self.delta("Checking available tools.", "commentary")
        self.complete("Checking available tools.", "commentary")
        self.assertEqual(self.renderer.answer_text, "")
        self.delta('{"answer":"Found three results.', "final")
        self.complete('{"answer":"Found three results.","task":null}', "final")
        self.renderer.finish()
        self.assertEqual(self.output.getvalue(), "Checking available tools.\nFound three results.\n")
        self.assertEqual(self.renderer.answer_text, "Found three results.")

    def test_answer_is_retained_for_controller_across_other_stages(self):
        self.renderer.start("prepare", "test-model")
        self.complete('{"answer":"Task accepted.","kind":"task"}')
        self.renderer.finish()
        self.renderer.start("implement", "test-model")
        self.complete("Implementation progress.")
        self.assertEqual(self.renderer.answer_text, "Task accepted.")
        self.renderer.start("prepare", "test-model")
        self.assertEqual(self.renderer.answer_text, "")

    def test_nested_and_nonstring_answers_do_not_leak(self):
        for body in ('{"task":{"answer":"secret"},"answer":null}',
                     '{"answer":{"answer":"secret"},"task":null}',
                     '{"task":[{"answer":"secret"}],"kind":"blocked"}'):
            with self.subTest(body=body):
                self.setUp()
                self.renderer.start("prepare", "test-model")
                for char in body:
                    self.delta(char)
                self.assertEqual(self.output.getvalue(), "")
                self.assertEqual(self.renderer.answer_text, "")

    def test_review_json_is_hidden_but_plain_progress_is_visible(self):
        self.renderer.start("review", "test-model")
        self.delta("Reviewing changes.", "commentary")
        self.complete('{"verdict":"pass","internal":"hidden"}', "review")
        self.assertEqual(self.output.getvalue(), "Reviewing changes.")

    def test_completion_adds_only_unseen_suffix(self):
        self.renderer.start("plan", "test-model")
        self.delta("Step one")
        self.complete("Step one, step two.")
        self.complete("Step one, step two.")
        self.delta("Step one, step two.")
        self.assertEqual(self.output.getvalue(), "Step one, step two.")

    def test_changed_completion_does_not_concatenate_inconsistent_answer(self):
        self.renderer.start("prepare", "test-model")
        self.delta('{"answer":"Partial answer')
        self.complete('{"answer":"Revised answer"}')
        self.assertEqual(self.output.getvalue(), "Partial answer\n")
        self.assertEqual(self.renderer.answer_text, "Partial answer")
        self.assertIn("final response changed", self.status.getvalue())

    def test_terminal_sequences_are_removed_at_all_boundaries(self):
        unsafe = ("safe\x1b[2Jvisible\x1b]52;c;c2VjcmV0\x07!"
                  "\x1b]8;;https://example.invalid\x1b\\link\x1b]8;;\x1b\\"
                  "\x1bPprivate payload\x1b\\\x9dtitle\x9c\x9b31m"
                  "\x1b(0\x08\x0d\x7f\x00\n\tend")
        for boundary in range(len(unsafe) + 1):
            with self.subTest(boundary=boundary):
                output = io.StringIO()
                renderer = StreamRenderer(output, io.StringIO())
                renderer.start("implement", "test-model")
                renderer.event({"type": "message_delta", "id": "a", "text": unsafe[:boundary]})
                renderer.event({"type": "message_delta", "id": "a", "text": unsafe[boundary:]})
                self.assertEqual(output.getvalue(), "safevisible!link\n\tend")

    def test_json_terminal_sequences_are_sanitized_after_decoding(self):
        self.renderer.start("prepare", "test-model")
        answer = "Safe\x1b]52;c;private\x07 answer"
        for char in json.dumps({"answer": answer}):
            self.delta(char)
        self.assertEqual(self.output.getvalue(), "Safe answer")
        self.assertEqual(self.renderer.answer_text, answer)

    def test_complete_receipt_text_sanitizer_is_safe_and_independent(self):
        self.assertEqual(sanitize_terminal_text("Blocked\x1b]52;c;secret\x07\nRetry\t✓"),
                         "Blocked\nRetry\t✓")
        self.assertEqual(sanitize_terminal_text("First\x1b["), "First")
        self.assertEqual(sanitize_terminal_text("Next message"), "Next message")

    def test_tool_events_show_only_sanitized_name_and_known_status_once(self):
        self.renderer.start("prepare", "test-model")
        started = {"type": "tool_started", "id": "call-1", "tool": "search\x1b[2J\nrepos",
                   "arguments": {"secret": "SECRET ARGUMENT"}, "result": "SECRET RESULT"}
        self.renderer.event(started)
        self.renderer.event(started)
        self.renderer.event(dict(started, type="tool_completed", status="failed"))
        self.renderer.event(dict(started, type="tool_completed", status="failed"))
        self.renderer.event(dict(started, id="call-2", type="tool_completed", status="SECRET STATUS"))
        self.assertEqual(self.output.getvalue(), "")
        status = self.status.getvalue()
        self.assertEqual(status.count("Tool started: search repos"), 1)
        self.assertEqual(status.count("Tool failed: search repos"), 1)
        self.assertIn("Tool completed: search repos", status)
        self.assertNotIn("SECRET", status)
        self.assertNotIn("\x1b", status)

    def test_reasoning_and_unknown_events_are_never_printed(self):
        self.renderer.start("prepare", "test-model")
        for kind in ("reasoning_delta", "reasoning", "unknown", "tool_result"):
            self.renderer.event({"type": kind, "text": "PRIVATE", "result": "PRIVATE"})
        self.assertEqual(self.output.getvalue(), "")
        self.assertNotIn("PRIVATE", self.status.getvalue())

    def test_heartbeat_requires_ten_seconds_without_visible_output(self):
        self.renderer.start("implement", "test-model")
        self.now = 9.9
        self.renderer.idle()
        self.assertNotIn("Waiting", self.status.getvalue())
        self.delta("Progress")
        self.now = 19.8
        self.renderer.idle()
        self.assertNotIn("Waiting", self.status.getvalue())
        self.now = 20
        self.renderer.idle()
        self.renderer.idle()
        self.assertEqual(self.status.getvalue().count("Waiting"), 1)
        self.now = 30
        self.renderer.idle()
        self.assertEqual(self.status.getvalue().count("Waiting"), 2)
        self.renderer.finish()
        self.now = 50
        self.renderer.idle()
        self.assertEqual(self.status.getvalue().count("Waiting"), 2)

    def test_incomplete_escape_does_not_emit_raw_payload_or_break_finish(self):
        self.renderer.start("implement", "test-model")
        self.delta("Done\x1b]52;c;hidden")
        self.renderer.finish()
        self.renderer.finish()
        self.assertEqual(self.output.getvalue(), "Done\n")

    def test_malformed_events_are_ignored(self):
        self.renderer.start("prepare", "test-model")
        for event in (None, [], {}, {"type": []}, {"type": "message_delta", "text": None}):
            self.renderer.event(event)
        self.renderer.event({"type": "tool_completed", "status": {"result": "PRIVATE"}})
        self.renderer.event({"type": "stage_error", "message": "failed\x1b[2J\nplease retry"})
        self.assertEqual(self.output.getvalue(), "")
        self.assertIn("Codex error: failed please retry", self.status.getvalue())
        self.assertNotIn("PRIVATE", self.status.getvalue())


if __name__ == "__main__":
    unittest.main()
