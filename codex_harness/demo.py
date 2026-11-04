"""Small diagnostic fixtures. These are not a representative model benchmark."""

import json
import subprocess
import sys
from pathlib import Path

from .config import ASSETS, load_policy, load_task
from .runner import run, save

CASES = {
    "mean": ("def mean(values):\n    return sum(values) / len(values)\n",
             "def mean(values):\n    if not values:\n        return None\n    return sum(values) / len(values)\n",
             "Return None for an empty sequence in stats.mean; preserve the arithmetic mean for other sequences.",
             "from stats import mean\nimport unittest\nclass Tests(unittest.TestCase):\n    def test_empty(self): self.assertIsNone(mean([]))\n    def test_numbers(self): self.assertEqual(mean([1, 2, 3]), 2)\n    def test_negative(self): self.assertEqual(mean([-2, -4]), -3)\n", "stats.py"),
    "slug": ("def slug(text):\n    return text.lower().replace(' ', '-')\n",
             "import re\ndef slug(text):\n    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')\n",
             "In slug.slug, lowercase ASCII letters and collapse each run of non-ASCII-alphanumeric characters to one hyphen, trimming leading/trailing hyphens.",
             "from slug import slug\nimport unittest\nclass Tests(unittest.TestCase):\n    def test_words(self): self.assertEqual(slug('Hello World'), 'hello-world')\n    def test_punctuation(self): self.assertEqual(slug(' Hello,   World! '), 'hello-world')\n    def test_empty(self): self.assertEqual(slug(' !!! '), '')\n    def test_digits(self): self.assertEqual(slug('Build 42'), 'build-42')\n", "slug.py"),
    "chunks": ("def chunks(items, size):\n    return [items[i:i+size] for i in range(0, len(items), size)]\n",
               "def chunks(items, size):\n    if size <= 0:\n        raise ValueError('size must be positive')\n    return [items[i:i+size] for i in range(0, len(items), size)]\n",
               "Make chunks.chunks reject zero and negative chunk sizes with ValueError, including for empty input. Preserve partial final chunks.",
               "from chunks import chunks\nimport unittest\nclass Tests(unittest.TestCase):\n    def test_partial(self): self.assertEqual(chunks([1,2,3], 2), [[1,2],[3]])\n    def test_empty(self): self.assertEqual(chunks([], 2), [])\n    def test_invalid(self):\n        for size in [0, -1, -3]:\n            with self.assertRaises(ValueError): chunks([], size)\n", "chunks.py"),
}


def create(destination):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    repo = destination / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / ".gitignore").write_text("__pycache__/\n")
    for name, (broken, fixed, prompt, test, filename) in CASES.items():
        (repo / filename).write_text(broken)
        (repo / "tests" / f"test_{name}.py").write_text(test)
        save(destination / f"{name}.json", {"id": name, "prompt": prompt,
             "checks": [["{python}", "-m", "unittest", "discover", "-s", "tests", "-p", f"test_{name}.py", "-v"]],
             "protected_paths": ["tests", ".gitignore"], "baseline_must_fail": True})
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Harness Demo", "-c", "user.email=demo@example.invalid",
                    "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "commit", "-qm", "Add diagnostic tasks"], check=True)
    save(destination / "suite.json", {"repeat": 3, "seed": 42,
         "tasks": [{"repo": "repo", "task": f"{name}.json"} for name in CASES],
         "variants": [{"name": "cheap-single", "policy": {"max_attempts": 1}},
                      {"name": "cheap-repair", "policy": {"max_attempts": 3}},
                      {"name": "cascade", "policy": {"max_attempts": 3, "cheap_attempts": 2, "escalation_model": "gpt-6.1-sol"}}]})
    return destination


def demo(destination, live=False, model=None):
    dest = create(destination)
    overrides = {"max_attempts": 2}
    if not live:
        overrides.update({"model": "simulator", "codex_command": [sys.executable, str(ASSETS / "fake_codex.py")],
                          "prices": {"simulator": {"input": 0.0, "cached_input": 0.0, "output": 0.0}}})
    if model:
        overrides["model"] = model
    policy = load_policy(overrides=overrides)
    records = []
    for name in CASES:
        record = run(dest / "repo", load_task(dest / f"{name}.json"), policy, dest / "runs",
                     label="live-smoke" if live else "simulation", progress=lambda x: print(x, flush=True))
        records.append(record)
    return records
