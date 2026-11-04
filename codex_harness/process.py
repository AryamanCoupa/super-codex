"""Bounded subprocess execution; no shell interpolation."""

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
    process.wait()


def execute(argv, cwd, timeout, stdin="", env=None, log=None, max_bytes=8_000_000):
    started = time.monotonic()
    output = bytearray()
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
        while selector.get_map():
            if time.monotonic() - started >= timeout:
                reason = "timeout"
                break
            for key, _ in selector.select(min(0.1, max(0.001, timeout))):
                data = os.read(key.fileobj.fileno(), 65536)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                output.extend(data[:max_bytes - len(output)])
                if len(output) >= max_bytes:
                    reason = "output_limit"
                    break
            if reason:
                break
        if not reason:
            try:
                process.wait(timeout=max(0.001, timeout - (time.monotonic() - started)))
            except subprocess.TimeoutExpired:
                reason = "timeout"
    finally:
        stop(process)
        selector.close()
        process.stdout.close()
    text = output.decode("utf-8", errors="replace")
    if log:
        Path(log).write_text(text)
    return {"returncode": process.returncode, "reason": reason, "output": text,
            "seconds": round(time.monotonic() - started, 3)}


def verifier_env():
    # Tests execute trusted local code. Do not pass provider/MCP secrets to them.
    names = ("PATH", "HOME", "TMPDIR", "TEMP", "LANG", "LC_ALL", "SYSTEMROOT")
    env = {k: os.environ[k] for k in names if k in os.environ}
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"})
    return env
