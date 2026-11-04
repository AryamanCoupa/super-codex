import json
import unittest

from codex_harness.codex import parse_events


def completed(usage):
    return {"type": "turn.completed", "usage": usage}


def parse(*events):
    return parse_events("\n".join(json.dumps(event) for event in events))


class EventValidationTests(unittest.TestCase):
    def setUp(self):
        self.usage = {"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 10}

    def test_malformed_usage_stays_unknown_before_or_after_valid_turns(self):
        for usage in (None, [], "unavailable", 12, {},
                      dict(self.usage, input_tokens=True),
                      dict(self.usage, output_tokens=-1)):
            for events in ((completed(usage), completed(self.usage)),
                           (completed(self.usage), completed(usage))):
                with self.subTest(usage=usage, events=events):
                    result = parse(*events)
                    self.assertTrue(result["completed"])
                    self.assertIsNone(result["usage"])

    def test_invalid_cache_count_cannot_be_hidden_by_other_turns(self):
        malformed = {"input_tokens": 1, "cached_input_tokens": 2, "output_tokens": 1}
        self.assertIsNone(parse(completed(malformed), completed(self.usage))["usage"])

    def test_malformed_items_do_not_crash_or_corrupt_valid_usage(self):
        for item in (None, [], "warning", 3,
                     {"type": "agent_message", "text": None},
                     {"type": "agent_message", "text": {"message": "invalid"}}):
            with self.subTest(item=item):
                result = parse({"type": "item.completed", "item": item},
                               {"type": "item.completed", "item": {"type": "agent_message", "text": "Valid handoff"}},
                               completed(self.usage))
                self.assertEqual(result["message"], "Valid handoff")
                self.assertEqual(result["usage"], self.usage)

    def test_failed_turn_remains_failed_after_valid_completion(self):
        result = parse(completed(self.usage), {"type": "turn.failed"})
        self.assertFalse(result["completed"])
        self.assertEqual(result["usage"], self.usage)


if __name__ == "__main__":
    unittest.main()
