import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from codex_harness.process import execute, stop


WAIT_FOR_FILE = """
def wait_for_file(name):
    deadline = time.monotonic() + 10
    while not Path(name).exists():
        if time.monotonic() >= deadline:
            raise RuntimeError('live callback did not acknowledge output')
        time.sleep(.005)
"""


class ProcessStreamingTests(unittest.TestCase):
    def test_finished_child_permission_error_does_not_mask_result(self):
        finished = Mock(pid=12345)
        finished.poll.return_value = 0
        with patch('codex_harness.process.os.killpg', side_effect=PermissionError):
            stop(finished)
        finished.wait.assert_called_once()
        running = Mock(pid=12345)
        running.poll.return_value = None
        with patch('codex_harness.process.os.killpg', side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                stop(running)

    def test_partial_json_is_delivered_before_exit_and_split_utf8_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chunks = []
            split_cycles = 0

            def on_output(chunk):
                chunks.append(chunk)
                if ''.join(chunks) == '{"progress":"':
                    (root / 'prefix-read').touch()

            def on_idle():
                nonlocal split_cycles
                if (root / 'split-written').exists():
                    split_cycles += 1
                    # The first cycle reads the incomplete UTF-8 sequence.
                    # Only then let the child finish the same character.
                    if split_cycles >= 2:
                        (root / 'split-read').touch()

            child = "import os, time\nfrom pathlib import Path\n" + WAIT_FOR_FILE + r"""
os.write(1, b'{"progress":"')
wait_for_file('prefix-read')
os.write(1, b'\xe2')
Path('split-written').touch()
wait_for_file('split-read')
os.write(1, b'\x82\xac"}\n')
"""
            result = execute([sys.executable, '-c', child], root, 15,
                             on_output=on_output, on_idle=on_idle)

            self.assertEqual(result['returncode'], 0, result['output'])
            self.assertIsNone(result['reason'])
            self.assertEqual(chunks, ['{"progress":"', '€"}\n'])
            self.assertEqual(''.join(chunks), result['output'])

    def test_idle_callback_runs_while_child_has_no_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = []

            def on_idle():
                calls.append(True)
                (root / 'ack').touch()

            child = "import time\nfrom pathlib import Path\n" + WAIT_FOR_FILE + """
wait_for_file('ack')
print('done', flush=True)
"""
            result = execute([sys.executable, '-c', child], root, 15, on_idle=on_idle)
            self.assertEqual(result['returncode'], 0, result['output'])
            self.assertEqual(result['output'], 'done\n')
            self.assertTrue(calls)

    def test_idle_callback_continues_after_child_closes_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            closed_cycles = 0

            def on_idle():
                nonlocal closed_cycles
                if (root / 'closed').exists():
                    closed_cycles += 1
                    if closed_cycles >= 2:
                        (root / 'ack').touch()

            child = "import os, time\nfrom pathlib import Path\n" + WAIT_FOR_FILE + """
os.close(1)
os.close(2)
Path('closed').touch()
wait_for_file('ack')
"""
            result = execute([sys.executable, '-c', child], root, 15, on_idle=on_idle)
            self.assertEqual(result['returncode'], 0)
            self.assertIsNone(result['reason'])
            self.assertGreaterEqual(closed_cycles, 2)

    def test_output_limit_bounds_callbacks_and_flushes_incomplete_utf8(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / 'output.log'
            chunks = []
            child = "import os, time; os.write(1, bytes.fromhex('e282ac') + b'x' * 10000); time.sleep(30)"
            result = execute([sys.executable, '-c', child], tmp, 15,
                             max_bytes=2, on_output=chunks.append, log=log)
            self.assertEqual(result['reason'], 'output_limit')
            self.assertEqual(result['output'], '�')
            self.assertEqual(chunks, ['�'])
            self.assertEqual(log.read_text(), result['output'])

    def test_timeout_preserves_live_output_and_log_and_reaps_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / 'output.log'
            chunks = []
            deadline_reached = False
            clock = time.monotonic

            def on_output(chunk):
                nonlocal deadline_reached
                chunks.append(chunk)
                deadline_reached = True

            def monotonic():
                return clock() + (60 if deadline_reached else 0)

            child = """
import os, time
from pathlib import Path
Path('pid').write_text(str(os.getpid()))
print('progress', flush=True)
time.sleep(30)
"""
            with patch('codex_harness.process.time.monotonic', monotonic):
                result = execute([sys.executable, '-c', child], root, 15,
                                 on_output=on_output, log=log)
            self.assertEqual(result['reason'], 'timeout')
            self.assertEqual(''.join(chunks), 'progress\n')
            self.assertEqual(log.read_text(), result['output'])
            with self.assertRaises(ProcessLookupError):
                os.kill(int((root / 'pid').read_text()), 0)

    def test_callback_failure_and_interruption_save_log_and_reap_child(self):
        for error_type, callback in [(RuntimeError, 'output'),
                                     (KeyboardInterrupt, 'output'),
                                     (RuntimeError, 'idle')]:
            with self.subTest(error=error_type, callback=callback), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                log = root / 'output.log'
                chunks = []

                def on_output(chunk):
                    chunks.append(chunk)
                    if callback == 'output':
                        raise error_type('stop streaming')

                def on_idle():
                    if callback == 'idle' and chunks:
                        raise error_type('stop streaming')

                child = """
import os, time
from pathlib import Path
Path('pid').write_text(str(os.getpid()))
print('progress', flush=True)
time.sleep(30)
"""
                with self.assertRaisesRegex(error_type, 'stop streaming'):
                    execute([sys.executable, '-c', child], root, 15, log=log,
                            on_output=on_output, on_idle=on_idle)
                self.assertEqual(chunks, ['progress\n'])
                self.assertEqual(log.read_text(), 'progress\n')
                with self.assertRaises(ProcessLookupError):
                    os.kill(int((root / 'pid').read_text()), 0)


if __name__ == '__main__':
    unittest.main()
