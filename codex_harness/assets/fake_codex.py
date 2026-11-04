"""Offline integration fixture. Deliberately fails once, then applies a known repair."""
import json
import sys
from pathlib import Path

if "--version" in sys.argv:
    print("fake-codex 1 (simulation; not a model)")
    raise SystemExit(0)
workspace = Path(sys.argv[sys.argv.index("-C") + 1])
prompt = sys.stdin.read()
marker = workspace / ".git" / "simulation-attempt"
second = marker.exists()
marker.write_text("1")
if second:
    if "stats.mean" in prompt:
        (workspace / "stats.py").write_text("def mean(values):\n    return sum(values) / len(values) if values else None\n")
    elif "slug.slug" in prompt:
        (workspace / "slug.py").write_text("import re\ndef slug(text):\n    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')\n")
    elif "chunks.chunks" in prompt:
        (workspace / "chunks.py").write_text("def chunks(items, size):\n    if size <= 0:\n        raise ValueError('positive size required')\n    return [items[i:i+size] for i in range(0, len(items), size)]\n")
print(json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "Simulation repair" if second else "Simulation initial failure"}}))
print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 30}}))
