"""Bounded subprocess execution; no shell interpolation."""

import codecs
import os
import selectors
import signal
import subprocess
import tempfile
import time
from pathlib import Path


def stop(process):
    # Every child starts in its own session. Kill descendants even if the leader exited.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except PermissionError:
        # Some macOS sandboxes report EPERM instead of ESRCH once a child
        # session is gone. Never ignore inability to terminate a live child.
        if process.poll() is None:
            raise
    process.wait()


def execute(argv, cwd, timeout, stdin="", env=None, log=None, max_bytes=8_000_000,
            on_output=None, on_idle=None):
    """Run a bounded child, optionally delivering decoded output as it arrives.

    Callbacks run synchronously; ``on_idle`` runs every polling cycle, including
    cycles with output. Callback exceptions propagate after terminating the child
    process group and preserving any captured output in ``log``.
    """
    started = time.monotonic()
    output = bytearray()
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    reason = None
    input_file = tempfile.TemporaryFile()
    input_file.write(stdin.encode())
    input_file.seek(0)
    try:
        process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=input_file,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   start_new_session=True)
    finally:
        input_file.close()
    selector = selectors.DefaultSelector()
    try:
        selector.register(process.stdout, selectors.EVENT_READ)
        while selector.get_map() or process.poll() is None:
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                reason = "timeout"
                break
            if on_idle is not None:
                on_idle()
            poll_timeout = min(0.1, max(0.001, remaining))
            if not selector.get_map():
                # A child may close stdout before exiting. Keep heartbeats and
                # the deadline active while it finishes.
                try:
                    process.wait(timeout=poll_timeout)
                except subprocess.TimeoutExpired:
                    pass
                continue
            for key, _ in selector.select(poll_timeout):
                data = os.read(key.fileobj.fileno(), 65536)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                captured = data[:max_bytes - len(output)]
                output.extend(captured)
                if on_output is not None:
                    chunk = decoder.decode(captured)
                    if chunk:
                        on_output(chunk)
                if len(output) >= max_bytes:
                    reason = "output_limit"
                    break
            if reason:
                break
        if on_output is not None:
            tail = decoder.decode(b"", final=True)
            if tail:
                on_output(tail)
    finally:
        try:
            stop(process)
        finally:
            selector.close()
            process.stdout.close()
            if log:
                Path(log).write_text(output.decode("utf-8", errors="replace"))
    text = output.decode("utf-8", errors="replace")
    return {"returncode": process.returncode, "reason": reason, "output": text,
            "seconds": round(time.monotonic() - started, 3)}


def verifier_env():
    # Tests execute trusted local code. Do not pass provider/MCP secrets to them.
    names = ("PATH", "HOME", "TMPDIR", "TEMP", "LANG", "LC_ALL", "SYSTEMROOT")
    env = {k: os.environ[k] for k in names if k in os.environ}
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"})
    return env
