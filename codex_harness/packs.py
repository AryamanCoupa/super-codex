"""Discover and scaffold task packs without invoking a model or running repo code."""

import json
import re
from collections import Counter
from pathlib import Path

from .config import ASSETS, read, toml_value
from .improve import copy_pack, pack_digest


def resolve_pack(name):
    if not name:
        return None
    path = Path(name).expanduser()
    if not path.exists():
        # A packaged name must not be interpreted as a path out of assets.
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", str(name)):
            raise ValueError(f"No task pack found: {name}")
        path = ASSETS / "packs" / str(name)
    path = path.resolve()
    if (path / "active.json").exists():
        release = read(path / "active.json").get("current")
        if not isinstance(release, str) or not re.fullmatch(r"release-[0-9a-f]{16}", release):
            raise ValueError("Invalid active release identifier")
        target = path / "releases" / release
        if target.is_symlink() or path not in target.resolve().parents:
            raise ValueError("Registry release must remain inside its registry")
        path = target
    if not (path / "pack.toml").is_file():
        raise ValueError(f"No task pack found: {name}")
    return path.resolve()


def inspect_pack(name):
    path = resolve_pack(name)
    if path is None:
        raise ValueError("A task pack is required")
    manifest = read(path / "pack.toml")
    if not isinstance(manifest.get("name", path.name), str):
        raise ValueError("Pack name must be a string")
    if any(not isinstance(manifest.get(key, {}), dict) for key in ("task", "policy", "match")):
        raise ValueError("Pack task, policy and match fields must be tables")
    from .runner import pack_context
    context, mcp = pack_context(path)
    selector = Path(name).expanduser()
    registry = selector.is_dir() and (selector / "active.json").is_file()
    bundled = ASSETS.resolve() in path.parents
    checks = manifest.get("task", {}).get("checks", [])
    return {
        "name": manifest.get("name", path.name), "version": str(manifest.get("version", "unversioned")),
        "description": manifest.get("description", ""), "path": str(path),
        "selector": str(selector.resolve()) if registry else (path.name if bundled else str(path)),
        "source": "registry" if registry else ("bundled" if bundled else "custom"),
        "active_release": path.name if registry else None,
        "skills": manifest.get("skills", []), "mcp_servers": sorted(mcp),
        "task_defaults": manifest.get("task", {}), "policy": manifest.get("policy", {}),
        "match": manifest.get("match", {}), "needs_checks": not bool(checks),
        "context_characters": len(context), "available": True,
    }


def discover_packs(roots=()):
    """List bundled packs and direct children of local roots; never recurse through repos."""
    explicit = list(roots)
    roots = explicit or [Path.cwd() / ".harness" / "packs", Path.cwd() / ".harness" / "registries"]
    candidates = list(sorted((ASSETS / "packs").iterdir()))
    for item in roots:
        root = Path(item).expanduser()
        if not root.exists():
            if explicit:
                raise ValueError(f"Pack discovery root does not exist: {root}")
            continue
        if not root.is_dir():
            raise ValueError(f"Pack discovery root must be a directory: {root}")
        if (root / "pack.toml").is_file() or (root / "active.json").is_file():
            candidates.append(root)
        else:
            # Bounded, one-level discovery avoids scanning dependencies and archived releases.
            entries = []
            for child in root.iterdir():
                entries.append(child)
                if len(entries) > 500:
                    raise ValueError(f"Discovery root has over 500 entries; select a narrower root: {root}")
            candidates.extend(child for child in sorted(entries) if not child.is_symlink() and child.is_dir()
                              and ((child / "pack.toml").is_file() or (child / "active.json").is_file()))
    found, seen = [], set()
    for candidate in candidates:
        identity = candidate.resolve()
        if identity in seen:
            continue
        seen.add(identity)
        try:
            found.append(inspect_pack(candidate))
        except (OSError, ValueError, KeyError, TypeError) as error:
            found.append({"name": candidate.name, "selector": str(identity), "path": str(identity),
                          "source": "invalid", "available": False, "error": str(error)})
    return sorted(found, key=lambda row: (row["name"], row["selector"]))


def _task_data(task):
    value = {"prompt": task} if isinstance(task, str) else dict(task or {})
    prompt = value.get("prompt", "")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("A nonempty task prompt is required")
    return value


def _repo_signals(repo):
    if repo is None:
        return {}, []
    root = Path(repo).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Repository directory does not exist: {root}")
    files = [name for name in ("pyproject.toml", "requirements.txt", "setup.py", "package.json",
                               "go.mod", "Cargo.toml", "pom.xml", "build.gradle") if (root / name).is_file()]
    signals = {}
    if any(name in files for name in ("pyproject.toml", "requirements.txt", "setup.py")):
        signals["backend"] = ["Python project manifest present"]
    package = root / "package.json"
    if package.is_file() and not package.is_symlink() and package.stat().st_size <= 256_000:
        try:
            data = read(package)
            dependencies = set(data.get("dependencies", {})) | set(data.get("devDependencies", {}))
            frontend = sorted(dependencies & {"react", "vue", "svelte", "next", "vite", "@playwright/test"})
            if frontend:
                signals["frontend"] = ["package.json declares " + ", ".join(frontend)]
        except (OSError, ValueError, TypeError, AttributeError):
            pass
    return signals, files


def suggest_packs(task, repo=None, roots=(), records=()):
    """Return explainable heuristics, not a claim of measured model-quality routing."""
    task = _task_data(task)
    prompt = task["prompt"].lower()
    words = set(re.findall(r"[a-z0-9]+", prompt))
    signals, manifests = _repo_signals(repo)
    vocabulary = {
        "backend": {"python", "api", "endpoint", "database", "backend", "pagination", "server"},
        "frontend": {"frontend", "browser", "react", "vue", "svelte", "css", "ui", "component", "layout", "page"},
        "issue-to-patch": {"jira", "atlassian", "ticket", "issue"},
    }
    suggestions = []
    for pack in discover_packs(roots):
        if not pack["available"]:
            continue
        name = pack["name"]
        match = pack.get("match", {})
        family = match.get("family", name) if isinstance(match, dict) else name
        if not isinstance(family, str):
            family = name
        keywords = set(vocabulary.get(family, ()))
        configured = match.get("task_keywords", []) if isinstance(match, dict) else []
        if isinstance(configured, list):
            keywords.update(word.lower() for word in configured if isinstance(word, str) and word)
        hits = sorted(term for term in keywords if (term in words if " " not in term else term in prompt))
        reasons = ["Task mentions: " + ", ".join(hits)] if hits else []
        score = min(len(hits), 4) * 2
        for reason in signals.get(family, []):
            reasons.append(reason)
            score += 2
        patterns = match.get("repo_files", []) if isinstance(match, dict) else []
        if repo and isinstance(patterns, list):
            for item in patterns[:20]:
                if not isinstance(item, str) or Path(item).is_absolute() or ".." in Path(item).parts:
                    continue
                # Exact relative filenames only; user patterns never expand into an unbounded tree walk.
                candidate = Path(repo).resolve() / item
                if Path(repo).resolve() in candidate.resolve().parents and candidate.is_file():
                    score += 2
                    reasons.append(f"Repository contains {item}")
        if score:
            suggestions.append({"name": name, "selector": pack["selector"], "score": score,
                                "reasons": reasons, "source": pack["source"],
                                "needs_checks": pack["needs_checks"]})
    suggestions.sort(key=lambda row: (-row["score"], row["source"] == "bundled", row["name"], row["selector"]))
    relevant = []
    for row in records:
        if not task.get("id") or row.get("task_id") != task["id"]:
            continue
        evidence_task = row.get("task", {})
        if isinstance(evidence_task, dict) and evidence_task.get("prompt"):
            if " ".join(str(evidence_task["prompt"]).lower().split()) != " ".join(prompt.split()):
                continue
            if "checks" in task and evidence_task.get("checks") != task["checks"]:
                continue
        relevant.append(row)
    failed = [row for row in relevant if row.get("status") in {"failed", "stalled", "budget_exhausted"}]
    statuses = dict(Counter(row.get("status", "unknown") for row in relevant))
    specialized = bool(suggestions and suggestions[0]["source"] in {"custom", "registry"})
    reason = ("Repeated failures on this task justify a small evidence-based pack experiment."
              if len(failed) >= 2 else
              "No matching pack was found; create a narrowly scoped pack and specify acceptance checks."
              if not suggestions else
              "A matching local pack exists; evaluate it before creating another pack."
              if specialized else
              "Start with the suggested template; create a dedicated pack when this task family recurs.")
    return {"method": "deterministic heuristics; rankings are not measured accuracy estimates",
            "recommended_pack": suggestions[0]["selector"] if suggestions else None,
            "suggestions": suggestions, "repository_manifests": manifests,
            "create_recommended": not suggestions or len(failed) >= 2,
            "creation_reason": reason, "matching_result_statuses": statuses,
            "evidence_scope": "Matches task ID and, when recorded, prompt and supplied checks. Legacy results with no task details match by ID only; repository identity is not inferred.",
            "next_steps": ["Confirm acceptance checks against the repository's documented workflow.",
                           "Compare changes on separate development and holdout tasks before promotion."]}


def create_pack(source, destination, *, name=None, task=None, repo=None):
    """Copy a template and record user scope; unspecified checks remain explicitly incomplete."""
    source = resolve_pack(source)
    if source is None:
        raise ValueError("A source template is required")
    destination = Path(destination).expanduser().resolve()
    name = name or destination.name
    if not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", name):
        raise ValueError("Pack name must contain 1–80 letters, numbers, underscores or hyphens")
    value = _task_data(task) if task is not None else None
    if repo is not None:
        _repo_signals(repo)
    manifest = read(source / "pack.toml")
    # Validate before creating anything; copy_pack expands bundled skills into the new pack.
    pack_digest(source)
    defaults = dict(manifest.get("task", {}))
    defaults.pop("checks", None)
    defaults.pop("setup", None)
    for field in ("checks", "setup"):
        if value and field in value:
            commands = value[field]
            if not isinstance(commands, list) or not all(isinstance(c, list) and c and all(isinstance(a, str) and a for a in c) for c in commands):
                raise ValueError(f"{field} must contain argv arrays")
            defaults[field] = commands
    family = manifest.get("name", source.name)
    manifest.update({"name": name, "version": "1", "task": defaults})
    if value:
        manifest["description"] = value["prompt"][:500]
    if not manifest.get("match"):
        manifest["match"] = {"family": family, "task_keywords": [], "repo_files": []}
    manifest_text = "\n".join(f"{json.dumps(key)} = {toml_value(item)}" for key, item in manifest.items()) + "\n"
    created = copy_pack(source, destination)
    (created / "pack.toml").write_text(manifest_text)
    if value:
        # Task-specific facts live in an editable example, not permanently injected instructions.
        example = dict(value)
        example.setdefault("id", name)
        example.setdefault("checks", [])
        (created / "task.example.json").write_text(json.dumps(example, indent=2) + "\n")
    return {**inspect_pack(created),
            "next_steps": ["Edit instructions.md for recurring constraints and failure modes.",
                           "Set match.task_keywords and match.repo_files for future suggestions.",
                           "Supply real acceptance checks; empty checks deliberately prevent execution.",
                           "Register a baseline, then optimize against separate development and holdout tasks."]}
