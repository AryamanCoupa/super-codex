"""One bounded, auditable task-pack improvement experiment.

The proposer receives development evidence only. A candidate gets one evaluation on
fresh holdout tasks; rejected candidates never become the active release.
"""

import copy
import math
import os
import random
import re
import shutil
import tempfile
from pathlib import Path

from .config import load_policy, load_task, positive, read
from .improve import development_history, fingerprint, pack_digest, promote, propose, register
from .runner import clone, git, run, save, validate_output_directory


def _prompt_hash(task):
    # Catch task-ID changes and whitespace/case-only changes. This is not a
    # semantic duplicate detector; dataset curation remains necessary.
    return fingerprint(" ".join(task["prompt"].casefold().split()))


def _current(registry):
    pointer = registry / "active.json"
    if not pointer.exists():
        return None
    release = read(pointer).get("current", "")
    if not isinstance(release, str) or not re.fullmatch(r"release-[0-9a-f]{16}", release):
        raise ValueError("Invalid active registry release")
    path = registry / "releases" / release
    if path.is_symlink() or not (path / "pack.toml").is_file():
        raise ValueError("Invalid active registry release directory")
    return pack_digest(path)


def _number(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and value >= 0)


def _proposal_tokens(proposal):
    usage = (proposal or {}).get("usage")
    if not isinstance(usage, dict):
        return None
    values = [usage.get("input_tokens"), usage.get("output_tokens")]
    if not all(_number(v) and isinstance(v, int) for v in values):
        return None
    return sum(values)


def _accounting(proposal, records, attempted):
    items = []
    if attempted:
        items.append({"tokens": _proposal_tokens(proposal), "cost_usd": (proposal or {}).get("cost_usd")})
    items.extend(records)
    result = {}
    for field in ("tokens", "cost_usd"):
        known = [row[field] for row in items if _number(row.get(field))]
        result[field] = sum(known) if len(known) == len(items) else None
        result["known_" + field] = sum(known)
    result["proposal"] = items[0] if attempted else {"tokens": 0, "cost_usd": 0}
    result["evaluation"] = {
        field: sum(row[field] for row in records) if all(_number(row.get(field)) for row in records) else None
        for field in ("tokens", "cost_usd")
    }
    result["evaluation_runs"] = len(records)
    result["note"] = "Includes proposal and all attempted trials; excludes historical development runs."
    return result


def optimize(source, development_records, holdout_suite_path, repo, registry, output, *,
             config=None, model="gpt-6.1-sol", max_runs=40, min_runs=10,
             min_distinct_tasks=3, max_cost_ratio=1.0, cost_metric="usd", min_pass_rate=0.8,
             max_total_tokens=1_000_000, max_total_cost_usd=None, progress=None, adapter=None):
    """Propose once, compare paired trials, and promote only if every gate passes.

    ``holdout_suite_path`` contains ``tasks`` (repo/task/revision), ``repeat`` and
    optional ``seed``. Baseline/candidate variants are supplied by this function.
    Budgets are checked between model stages; one proposal or full run can
    overshoot. No daemon, repeated search, or weight training is performed.
    """
    source, repo, registry, output = [Path(p).resolve() for p in (source, repo, registry, output)]
    for name, value in (("max_runs", max_runs), ("min_runs", min_runs),
                        ("min_distinct_tasks", min_distinct_tasks), ("max_total_tokens", max_total_tokens)):
        positive(value, name, integer=True)
    if cost_metric not in ("usd", "tokens"):
        raise ValueError("cost_metric must be usd or tokens")
    positive(max_cost_ratio, "max_cost_ratio")
    if not _number(min_pass_rate) or min_pass_rate > 1:
        raise ValueError("min_pass_rate must be between zero and one")
    if max_total_cost_usd is not None:
        positive(max_total_cost_usd, "max_total_cost_usd")
    if output.exists():
        raise ValueError("Optimization output must be a new directory")
    if source == registry or source in registry.parents:
        raise ValueError("Registry must be outside the source pack")
    if any(output == p or p in output.parents for p in (source, registry)):
        raise ValueError("Optimization output must be outside the source pack and registry")
    digest = pack_digest(source)
    active = _current(registry)
    if active is not None and active != digest:
        raise ValueError("Source pack must match the registry's current release")
    if active is None and registry.exists() and any(registry.iterdir()):
        raise ValueError("An uninitialized registry must be empty")
    if not development_records:
        raise ValueError("At least one development result is required")
    inherited = development_history(source)
    development_hashes = inherited["development_task_hashes"]
    development_prompts = inherited["development_prompt_hashes"]
    for row in development_records:
        task = row.get("task")
        if row.get("pack_sha256") != digest:
            raise ValueError("Development evidence lacks or mismatches this source pack hash; rerun it with --pack")
        if (not isinstance(task, dict) or not isinstance(task.get("prompt"), str)
                or not task["prompt"].strip() or row.get("task_sha256") != fingerprint(task)
                or row.get("task_id") != task.get("id") or not isinstance(row.get("attempts"), list)
                or not isinstance(row.get("status"), str)):
            raise ValueError("Development evidence needs a complete, matching task record")
        development_hashes.add(row["task_sha256"])
        development_prompts.add(_prompt_hash(task))
    suite_path = Path(holdout_suite_path).resolve()
    suite = read(suite_path)
    if not isinstance(suite, dict) or set(suite) - {"tasks", "repeat", "seed"}:
        raise ValueError("Holdout suite accepts tasks/repeat/seed only; paired variants are managed by optimize")
    if isinstance(suite.get("seed", 42), bool) or not isinstance(suite.get("seed", 42), int):
        raise ValueError("Holdout seed must be an integer")
    repeats = suite.get("repeat", 1)
    positive(repeats, "repeat", integer=True)
    tasks = suite.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("Holdout suite needs tasks")
    count = len(tasks) * repeats
    if count < min_runs:
        raise ValueError(f"Need at least {min_runs} holdout runs per variant")
    if count * 2 > max_runs:
        raise ValueError(f"Holdout requires {count * 2} runs, above max_runs={max_runs}")
    baseline_policy = load_policy(config, source)
    proposal_policy = load_policy(config, source, {"model": model})
    if cost_metric == "usd" or max_total_cost_usd is not None:
        roles = [baseline_policy["model"], model]
        roles.extend(baseline_policy[k] for k in ("planner_model", "reviewer_model") if baseline_policy.get(k))
        if baseline_policy.get("escalation_model") and baseline_policy["max_attempts"] > baseline_policy["cheap_attempts"]:
            roles.append(baseline_policy["escalation_model"])
        if any(role not in baseline_policy.get("prices", {}) for role in roles):
            raise ValueError("USD optimization requires explicit prices for every worker and proposal model; use tokens explicitly as a proxy")
    jobs, prompt_hashes, seen = [], set(), set()
    for entry in tasks:
        if not isinstance(entry, dict) or set(entry) - {"repo", "task", "revision"}:
            raise ValueError("Each holdout entry accepts repo/task/revision only")
        task_repo = (suite_path.parent / entry["repo"]).resolve()
        task_path = (suite_path.parent / entry["task"]).resolve()
        task = load_task(task_path, source)
        task_hash, prompt_hash = fingerprint(task), _prompt_hash(task)
        if task_hash in development_hashes or prompt_hash in development_prompts:
            raise ValueError("Holdout overlaps development evidence, including renamed or reformatted prompts")
        if git(task_repo, "status", "--porcelain"):
            raise ValueError("Holdout repositories must be clean before optimization")
        base = git(task_repo, "rev-parse", "--verify", f"{entry.get('revision', 'HEAD')}^{{commit}}").decode().strip()
        key = (str(task_repo), task_hash, base)
        if key in seen:
            raise ValueError("Duplicate holdout entry; use repeat for repetitions")
        seen.add(key)
        prompt_hashes.add(prompt_hash)
        jobs.append({"repo": task_repo, "task": task, "task_path": task_path, "base": base})
    if len(prompt_hashes) < min_distinct_tasks:
        raise ValueError(f"Need at least {min_distinct_tasks} distinct holdout prompts; repetitions do not add task diversity")
    history_path = registry / "holdout-history.json"
    history = read(history_path) if history_path.exists() else {"experiments": []}
    used_prompts = {h for experiment in history["experiments"] for h in experiment["prompt_hashes"]}
    if used_prompts & prompt_hashes:
        raise ValueError("Holdout was used by an earlier optimization in this registry; provide fresh tasks to avoid tuning on feedback")
    for checkout in {repo, *(job["repo"] for job in jobs)}:
        for artifact in (output, output / "candidate", output / "baseline", output / "runs", registry,
                         registry / "releases"):
            validate_output_directory(checkout, artifact)
    if git(repo, "status", "--porcelain"):
        raise ValueError("Proposal repository must be clean before optimization")
    proposal_base = git(repo, "rev-parse", "--verify", "HEAD^{commit}").decode().strip()
    suite_digest = fingerprint(sorted((str(j["repo"]), fingerprint(j["task"]), j["base"]) for j in jobs))
    progress = progress or (lambda message: None)
    output.mkdir(parents=True, mode=0o700)
    os.chmod(output, 0o700)
    audit = {"schema_version": 1, "status": "preparing", "source_pack_sha256": digest,
             "holdout_suite_sha256": suite_digest, "distinct_holdout_tasks": len(prompt_hashes),
             "planned_evaluation_runs": count * 2, "proposal_model": model,
             "proposal_base_commit": proposal_base, "registry": str(registry),
             "audit_path": str(output / "optimization.json"), "artifacts": str(output),
             "limits": {"max_runs": max_runs, "max_total_tokens": max_total_tokens,
                        "max_total_cost_usd": max_total_cost_usd},
             "limits_note": "Budget checks occur between proposal/full-run stages and may overshoot by one stage.",
             "validation_note": "Empirical gate, not statistical proof. Prompt hashes catch exact/format duplicates, not semantic leakage. Use curated fresh holdouts."}
    records, proposal_result, attempted, in_flight = [], None, False, None

    def write_audit():
        audit["accounting"] = _accounting(proposal_result, records, attempted)
        audit["budget_overrun"] = (audit["accounting"]["known_tokens"] > max_total_tokens
                                   or (max_total_cost_usd is not None
                                       and audit["accounting"]["known_cost_usd"] > max_total_cost_usd))
        audit["results"] = [{k: r.get(k) for k in ("id", "label", "status", "artifact_directory")} for r in records]
        save(output / "optimization.json", audit)

    def budget_stop():
        accounting = _accounting(proposal_result, records, attempted)
        if accounting["tokens"] is None:
            return "usage_unknown", "Missing token accounting; stopped before further model calls"
        if (cost_metric == "usd" or max_total_cost_usd is not None) and accounting["cost_usd"] is None:
            return "usage_unknown", "Missing dollar accounting; stopped before further model calls"
        if accounting["tokens"] >= max_total_tokens:
            return "budget_exceeded", "Optimization token budget reached"
        if max_total_cost_usd is not None and accounting["cost_usd"] >= max_total_cost_usd:
            return "budget_exceeded", "Optimization dollar budget reached"
        return None

    registry.mkdir(parents=True, exist_ok=True)
    lock_path = registry / ".optimize.lock"
    try:
        lock = lock_path.open("x")
    except FileExistsError:
        audit.update(status="rejected", reason="Another optimization owns the registry lock; inspect it before removing a stale lock")
        write_audit()
        return audit
    try:
        with lock:
            lock.write(str(output) + "\n")
        if _current(registry) != active:
            raise ValueError("Registry changed during optimization preflight")
        if active is None:
            register(source, registry)
        baseline = output / "baseline"
        shutil.copytree(source, baseline)
        if pack_digest(baseline) != digest:
            raise ValueError("Source pack changed during snapshot")
        write_audit()
        progress("Proposing one instruction change from development evidence")
        candidate = output / "candidate"
        with tempfile.TemporaryDirectory(prefix="super-codex-optimize-") as temp:
            frozen_repo = Path(temp) / "repo"
            clone(repo, frozen_repo, proposal_base)
            attempted = True
            proposal_result = propose(baseline, candidate, development_records, frozen_repo,
                                      proposal_policy, model, adapter=adapter)
        audit["candidate_pack_sha256"] = pack_digest(candidate)
        write_audit()
        stopped = budget_stop()
        if stopped:
            audit.update(status=stopped[0], reason=stopped[1])
            return audit
        if (candidate / "instructions.md").read_text().strip() == (baseline / "instructions.md").read_text().strip():
            audit.update(status="rejected", reason="Proposal made no instruction change; no holdout calls were spent")
            return audit
        if load_policy(config, candidate) != baseline_policy or any(
                load_task(j["task_path"], candidate) != j["task"] for j in jobs):
            raise ValueError("Candidate changed policy or task checks; only instruction changes may be optimized")
        # Reserve once feedback can be observed. An interrupted/rejected cycle
        # still consumes these holdouts; later attempts need a fresh dataset.
        history = read(history_path) if history_path.exists() else {"experiments": []}
        if {h for x in history["experiments"] for h in x["prompt_hashes"]} & prompt_hashes:
            raise ValueError("Holdout was consumed while this experiment was preparing")
        history["experiments"].append({"suite_sha256": suite_digest, "prompt_hashes": sorted(prompt_hashes),
                                       "audit_path": str(output / "optimization.json")})
        save(history_path, history)
        randomizer = random.Random(suite.get("seed", 42))
        for repetition in range(repeats):
            pairs = list(jobs)
            randomizer.shuffle(pairs)
            for job in pairs:
                variants = [("baseline", baseline), ("candidate", candidate)]
                randomizer.shuffle(variants)
                for label, pack in variants:
                    stopped = budget_stop()
                    if stopped:
                        audit.update(status=stopped[0], reason=stopped[1])
                        return audit
                    progress(f"Holdout {len(records) + 1}/{count * 2}: {label}, repetition {repetition + 1}")
                    in_flight = {"id": f"unreturned-trial-{len(records) + 1}", "label": label,
                                 "status": "unreturned", "tokens": None, "cost_usd": None}
                    record = run(job["repo"], copy.deepcopy(job["task"]), copy.deepcopy(baseline_policy),
                                 output / "runs", pack, adapter=adapter, revision=job["base"], label=label,
                                 progress=progress)
                    records.append(record)
                    in_flight = None
                    audit["status"] = "evaluating"
                    write_audit()
                    if record["status"] in {"infrastructure_error", "setup_failed", "baseline_error", "invalid_baseline",
                                            "interrupted", "agent_error", "usage_unknown", "verification_error"}:
                        audit.update(status="interrupted" if record["status"] == "interrupted" else "rejected",
                                     reason=f"Holdout {record['status']}; resolve it before another experiment with fresh holdouts")
                        return audit
        stopped = budget_stop()
        if stopped:
            audit.update(status=stopped[0], reason=stopped[1])
            return audit
        if _current(registry) != digest or pack_digest(source) != digest:
            raise ValueError("Active registry or source changed; candidate cannot replace a different baseline")
        release = promote(candidate, registry, [r for r in records if r["label"] == "baseline"],
                          [r for r in records if r["label"] == "candidate"], min_runs=min_runs,
                          max_cost_ratio=max_cost_ratio, metric=cost_metric, min_pass_rate=min_pass_rate)
        audit.update(status="promoted", release=str(release), reason="Candidate passed paired quality and cost gates")
    except KeyboardInterrupt:
        audit.update(status="interrupted", reason="Optimization interrupted; existing active release retained")
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        audit.update(status="rejected", reason=str(error))
    finally:
        if in_flight is not None:
            records.append(in_flight)
        if attempted and proposal_result is None:
            # propose persists raw accounting even when candidate validation fails.
            paths = list((output / ".harness" / "proposals").glob("*/result.json"))
            if len(paths) == 1:
                proposal_result = read(paths[0])
            if _proposal_tokens(proposal_result) is None and audit["status"] == "rejected":
                audit["status"] = "usage_unknown"
                audit["reason"] += "; missing proposal usage prevents further model calls"
        try:
            write_audit()
        finally:
            lock_path.unlink(missing_ok=True)
    return audit
