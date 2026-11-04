"""Report attempts separately from independent benchmark trials."""

import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from .config import read


def wilson(successes, total):
    if not total:
        return [0.0, 1.0]
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [max(0, center - half), min(1, center + half)]


def summarize(records):
    groups = defaultdict(list)
    for record in records:
        groups[record.get("label", "default")].append(record)
    result = {}
    for label, rows in sorted(groups.items()):
        successes = sum(r["status"] == "passed" for r in rows)
        known = [r["cost_usd"] for r in rows if r.get("cost_usd") is not None]
        complete = len(known) == len(rows)
        result[label] = {
            "runs": len(rows), "successes": successes, "pass_rate": successes / len(rows),
            "wilson_95_interval": wilson(successes, len(rows)),
            "first_attempt_successes": sum(bool(r["attempts"] and r["attempts"][0].get("passed")) for r in rows),
            "mean_seconds": statistics.mean(r["seconds"] for r in rows),
            "mean_tokens": statistics.mean(r["tokens"] for r in rows) if all(r.get("tokens") is not None for r in rows) else None,
            "total_cost_usd": sum(known) if complete else None,
            "cost_per_success_usd": sum(known) / successes if complete and successes else None,
            "priced_runs": len(known), "statuses": dict(Counter(r["status"] for r in rows)),
            "base_commits": sorted(set(r["base_commit"] for r in rows)),
        }
    return result


def read_results(directory):
    return [read(p) for p in sorted(Path(directory).glob("*/result.json"))]


def markdown(summary):
    lines = ["| Variant | Runs | Passed | First attempt | Mean tokens | Mean seconds | $ / success |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for label, row in summary.items():
        cost = row["cost_per_success_usd"]
        tokens = f"{row['mean_tokens']:.0f}" if row["mean_tokens"] is not None else "unknown"
        lines.append(f"| {label} | {row['runs']} | {row['successes']} | {row['first_attempt_successes']} | "
                     f"{tokens} | {row['mean_seconds']:.1f} | {cost if cost is not None else 'unknown'} |")
    lines.append("\nCost per success includes spending on failures. Attempts are sequential repairs, not independent pass@k samples.")
    return "\n".join(lines)
