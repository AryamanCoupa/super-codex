"""Real CLI/process handshakes: text must be visible before the model finishes."""

import json
import contextlib
import io
import os
import selectors
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from codex_harness.runner import git
from codex_harness.controller import _print_receipt


FAKE_SERVER = r'''
import json, os, sys, time
from pathlib import Path
root = Path(os.environ['FIXTURE_ROOT'])
def send(value):
    print(json.dumps(value), flush=True)
def notify(method, **params):
    send({'method': method, 'params': params})
if '--version' in sys.argv:
    print('streaming-fixture 1')
    raise SystemExit(0)
assert 'app-server' in sys.argv
for line in sys.stdin:
    request = json.loads(line)
    method = request.get('method')
    if method == 'initialize':
        send({'id': request['id'], 'result': {'userAgent': 'fixture'}})
    elif method == 'thread/start':
        params = request['params']
        workspace = Path(params['cwd'])
        preparing = params['sandbox'] == 'read-only'
        with (root / 'calls.jsonl').open('a') as stream:
            stream.write(json.dumps({'sandbox': params['sandbox'],
                'approval': params['approvalPolicy'],
                'worker': os.environ.get('SUPERCODEX_WORKER'),
                'workspace': str(workspace)}) + '\n')
        send({'id': request['id'], 'result': {'thread': {'id': 'thread-1'},
             'model': params['model'], 'approvalPolicy': params['approvalPolicy'],
             'sandbox': {'type': 'readOnly' if preparing else 'workspaceWrite', 'networkAccess': False}}})
    elif method == 'turn/start':
        params = request['params']
        send({'id': request['id'], 'result': {'turn': {'id': 'turn-1', 'status': 'inProgress'}}})
        if preparing:
            assert 'outputSchema' in params
            if (root / 'task.json').exists():
                answer = json.dumps({'kind': 'task', 'answer': '', 'apply_patch': True,
                                     'task': json.loads((root / 'task.json').read_text())})
            else:
                answer = json.dumps({'kind': 'answer', 'answer': 'VISIBLE FIRST\nSecond part.',
                                     'apply_patch': False, 'task': None})
        else:
            (workspace / 'value.py').write_text('def answer():\n    return 42\n')
            answer = 'Candidate ready for verification.'
        item = {'id': 'message-1', 'type': 'agentMessage', 'phase': 'final_answer', 'text': ''}
        notify('item/started', threadId='thread-1', turnId='turn-1', item=item)
        split = answer.find('VISIBLE FIRST') + len('VISIBLE FIRST') if 'VISIBLE FIRST' in answer else len(answer) // 2
        notify('item/agentMessage/delta', threadId='thread-1', turnId='turn-1', itemId='message-1', delta=answer[:split])
        if (root / 'handshake').exists():
            deadline = time.monotonic() + 12
            while not (root / 'continue').exists():
                if time.monotonic() > deadline:
                    raise SystemExit('No live output was observed by the test')
                time.sleep(.01)
        notify('item/agentMessage/delta', threadId='thread-1', turnId='turn-1', itemId='message-1', delta=answer[split:])
        item['text'] = answer
        notify('item/completed', threadId='thread-1', turnId='turn-1', item=item)
        notify('thread/tokenUsage/updated', threadId='thread-1', turnId='turn-1',
               tokenUsage={'total': {'inputTokens': 100, 'cachedInputTokens': 20, 'outputTokens': 30}})
        notify('turn/completed', threadId='thread-1', turn={'id': 'turn-1', 'status': 'completed', 'error': None})
'''


class StreamingControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='sc streaming cli ')
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / 'source'
        self.repo.mkdir()
        self.fake = self.root / 'fake.py'
        self.fake.write_text(FAKE_SERVER)
        self.artifacts = self.root / 'artifacts'
        self.policy = self.root / 'policy.json'
        self.policy.write_text(json.dumps({
            'model': 'fixture-model', 'escalation_model': None,
            'codex_command': [sys.executable, str(self.fake)],
            'max_attempts': 1, 'cheap_attempts': 1, 'max_tokens': 1000,
            'run_timeout_seconds': 40, 'attempt_timeout_seconds': 15,
            'check_timeout_seconds': 10,
            'prices': {'fixture-model': {'input': 1, 'cached_input': .5, 'output': 2}},
        }))
        self.env = {**os.environ, 'FIXTURE_ROOT': str(self.root),
                    'CODEX_HOME': str(self.root / 'empty-codex-home'),
                    'XDG_CONFIG_HOME': str(self.root / 'empty-config')}
        self.env.pop('SUPERCODEX_WORKER', None)
        self.env.pop('OPENAI_API_KEY', None)
        Path(self.env['CODEX_HOME']).mkdir()
        (Path(self.env['CODEX_HOME']) / 'auth.json').write_text('{"OPENAI_API_KEY":"offline-fixture"}')
        launcher = Path(__file__).resolve().parents[1] / 'codex_harness/launch.py'
        self.argv = [sys.executable, str(launcher), 'Answer this fixture request.',
                     '--managed',
                     '--repo', str(self.repo), '--config', str(self.policy),
                     '--output-root', str(self.artifacts)]

    def tearDown(self):
        self.temp.cleanup()

    def receipt(self):
        paths = list(self.artifacts.glob('sessions/*/turns/0001/receipt.json'))
        self.assertEqual(len(paths), 1)
        return json.loads(paths[0].read_text())

    def test_answer_is_flushed_before_completion_and_not_repeated(self):
        (self.root / 'handshake').touch()
        process = subprocess.Popen(self.argv, cwd=self.root, env=self.env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = b''
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        try:
            deadline = time.monotonic() + 10
            while b'VISIBLE FIRST' not in output and time.monotonic() < deadline:
                for key, _ in selector.select(.1):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if chunk:
                        output += chunk
                    else:
                        selector.unregister(key.fileobj)
                if process.poll() is not None:
                    break
            self.assertIn(b'VISIBLE FIRST', output, 'Answer remained buffered until model completion')
            self.assertIsNone(process.poll())
            self.assertEqual(self.receipt()['status'], 'running',
                             'The receipt must not be finalized while the model is blocked')
            (self.root / 'continue').touch()
            tail, errors = process.communicate(timeout=10)
            output += tail
            self.assertEqual(process.returncode, 0, errors.decode() + output.decode())
        finally:
            selector.close()
            if process.poll() is None:
                process.kill()
            process.communicate()
        self.assertEqual(output.count(b'VISIBLE FIRST'), 1)
        self.assertIn(b'VISIBLE FIRST\nSecond part.', output)
        self.assertNotIn(b'"apply_patch"', output)
        self.assertNotIn(b'"kind"', output)
        receipt = self.receipt()
        self.assertEqual(receipt['status'], 'advisory')
        self.assertEqual(receipt['preparation']['transport'], 'app-server')
        self.assertEqual(receipt['totals']['tokens'], 130)
        self.assertFalse(receipt['verified'])

    def test_explicit_managed_streaming_still_verifies_before_applying(self):
        (self.repo / 'value.py').write_text('def answer():\n    return 0\n')
        (self.repo / 'tests').mkdir()
        (self.repo / 'tests/test_value.py').write_text(
            'import unittest\nfrom value import answer\nclass Checks(unittest.TestCase):\n'
            '    def test_answer(self):\n        self.assertEqual(answer(), 42)\n')
        git(self.repo, 'init', '-q')
        git(self.repo, 'add', '.')
        git(self.repo, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
            '-c', 'commit.gpgsign=false', 'commit', '-qm', 'Fixture')
        (self.root / 'task.json').write_text(json.dumps({
            'id': 'fixture', 'prompt': 'Make answer return 42.',
            'checks': [['{python}', '-m', 'unittest', 'discover', '-s', 'tests']],
            'setup': [], 'protected_paths': ['tests'], 'baseline_must_fail': True,
        }))
        result = subprocess.run(self.argv, cwd=self.root, env=self.env,
                                text=True, capture_output=True, timeout=35)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        receipt = self.receipt()
        self.assertEqual(receipt['status'], 'applied')
        self.assertTrue(receipt['verified'])
        self.assertEqual(receipt['totals']['tokens'], 260)
        self.assertEqual((self.repo / 'value.py').read_text(), 'def answer():\n    return 42\n')
        calls = [json.loads(line) for line in (self.root / 'calls.jsonl').read_text().splitlines()]
        self.assertEqual([call['sandbox'] for call in calls], ['read-only', 'workspace-write'])
        self.assertTrue(all(call['approval'] == 'never' and call['worker'] == '1' for call in calls))
        self.assertTrue(all(call['workspace'] != str(self.repo) for call in calls))


class ReceiptDisplayTests(unittest.TestCase):
    def test_blocked_and_revised_final_text_cannot_send_terminal_commands(self):
        for status in ('advisory', 'blocked'):
            with self.subTest(status=status), contextlib.redirect_stdout(io.StringIO()) as output:
                receipt = {'status': status, 'verified': False, 'preparation': None,
                           'answer': '\x1b]52;c;encoded-clipboard\x07Final answer',
                           'reason': '\x1b[2JRequest blocked', 'receipt_path': '/tmp/receipt.json',
                           'totals': {'tokens': 1, 'usage_complete': True,
                                      'cost_usd': 0, 'cost_complete': True}}
                _print_receipt(receipt, streamed_answer='Earlier draft')
                text = output.getvalue()
                self.assertNotIn('\x1b', text)
                self.assertNotIn('encoded-clipboard', text)
                self.assertIn('Final answer' if status == 'advisory' else 'Request blocked', text)


if __name__ == '__main__':
    unittest.main()
