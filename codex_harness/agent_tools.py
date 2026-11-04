"""Discoverable operator skill and CLI context for managed Codex workers."""

import hashlib
import json
import os
import re
import shlex
import sys
from pathlib import Path

from . import __version__
from .config import ASSETS


def invocation():
    # Preserve a virtualenv interpreter symlink; resolving it can select base Python.
    return [str(Path(sys.executable).absolute()), str(Path(__file__).with_name("launch.py").resolve())]


def worker_context():
    from .cli import build_parser
    from .command_catalog import catalog
    paths = "; ".join(" ".join(row["path"]) for row in catalog(build_parser())["commands"])
    command = shlex.join(invocation())
    return (
        "<supercodex_cli>\n"
        f"SuperCodex {__version__} is available from this directory using: {command}\n"
        f"Installed command paths: {paths}.\n"
        "Append `commands <command path> --json` for current arguments, or `<command path> --help`. "
        "Discovery makes no model calls. Use absolute task/repository/output paths.\n"
        "You are a managed worker under the parent run's budget. Read-only discovery, reports, pack inspection, "
        "suggestions and memory queries are available. New runs, experiments, training and pack mutations belong "
        "to the top-level operator: return a concise recommendation in your handoff if needed. "
        "Do not bypass the inherited SUPERCODEX_WORKER guard or launch unaccounted child model jobs.\n"
        "Apply skill-discovery within your assigned role: select the smallest relevant set from this "
        "catalog and skills actually advertised in your session, then read their instructions. "
        "Use `skills --search \"task keywords\"` with the absolute launcher above when selection is unclear. "
        "The assigned role, output JSON schema, tool permissions and parent budget take precedence over "
        "general skill guidance. Preparation remains read-only; skill discovery never authorizes nested "
        "answer commands, agents, model jobs or expanded permissions. Reuse unchanged skills already read.\n"
        "Bundled skill entry points (metadata only; read relevant bodies on demand):\n"
        + skill_catalog_text() + "\n"
        "</supercodex_cli>"
    )


def worker_environment():
    return {**os.environ, "SUPERCODEX_WORKER": "1"}


def check_worker_command(args):
    if os.environ.get("SUPERCODEX_WORKER") != "1":
        return
    allowed = args.action in {"commands", "skills", "doctor", "report", "mcp"}
    allowed |= args.action == "pack" and args.pack_action in {"list", "inspect", "suggest"}
    allowed |= args.action == "agent" and args.agent_action == "show"
    if args.action == "experimental":
        allowed |= args.experiment == "list"
        allowed |= args.experiment == "router" and args.router_action == "choose"
        allowed |= args.experiment == "memory" and args.memory_action == "query"
    if not allowed:
        raise ValueError("Managed worker cannot launch nested runs or mutations outside parent accounting; "
                         "return this command to the top-level operator. Read-only discovery remains available.")


def bundled_skills():
    """List packaged skill entry points without loading every instruction body."""
    rows = []
    for path in sorted((ASSETS / "skills").glob("*/SKILL.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        if not lines or lines[0] != "---" or "---" not in lines[1:]:
            raise ValueError(f"Bundled skill lacks frontmatter: {path.parent.name}")
        metadata = {}
        for line in lines[1:lines.index("---", 1)]:
            key, separator, value = line.partition(":")
            if separator and key in {"name", "description"}:
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                metadata[key] = value
        name, description = metadata.get("name", ""), metadata.get("description", "")
        if (not re.fullmatch(r"[a-z0-9-]+", name) or name != path.parent.name
                or not description or description in {"|", ">"}):
            raise ValueError(f"Bundled skill needs a matching name and single-line description: {path.parent.name}")
        rows.append({"name": name, "description": description, "path": str(path.resolve())})
    if not rows:
        raise ValueError("No bundled skills found; reinstall the SuperCodex package")
    return rows


def skill_catalog_text(rows=None):
    rows = bundled_skills() if rows is None else rows
    return "\n".join(f"- {row['name']}: {row['description']}\n  Read: {json.dumps(row['path'])}" for row in rows)


_SKILL_QUERY_FILLER = frozenset(
    "a an and are as at be by can could do for from get give help how i in is it me my of on or "
    "please should some that the their them there these they this to use using want what when where "
    "which who will with would you your find search skill skills task tasks".split()
)


def _skill_terms(text):
    terms = re.findall(r"[a-z0-9]+", text.casefold())
    # Treat common plurals alike without a dependency or a model call.
    return {term[:-1] if len(term) > 3 and term.endswith("s") and not term.endswith("ss") else term
            for term in terms if term not in _SKILL_QUERY_FILLER}


def search_skills(query, rows=None):
    """Rank bundled names/descriptions by keyword overlap, not semantic suitability."""
    terms = _skill_terms(query)
    if not terms:
        raise ValueError("Skill search requires task keywords, such as GitHub repositories or AI news")
    ranked = []
    for row in bundled_skills() if rows is None else rows:
        score = 4 * len(terms & _skill_terms(row["name"])) + len(terms & _skill_terms(row["description"]))
        if score:
            ranked.append((score, row))
    return [row for _, row in sorted(ranked, key=lambda item: (-item[0], item[1]["name"]))]


def skill_text():
    template = (ASSETS / "operator" / "super-codex" / "SKILL.md").read_text()
    return (template.replace("{{SUPER_CODEX_COMMAND}}", shlex.join(invocation()))
            .replace("{{SUPER_CODEX_SKILLS}}", skill_catalog_text()))


def install_skill(destination, *, update=False):
    """Install only our skill; never rewrite an unrelated or edited skill."""
    destination = Path(destination).absolute()
    skill = destination / "SKILL.md"
    manifest = destination / "installation.json"
    if destination.is_symlink() or skill.is_symlink() or manifest.is_symlink():
        raise ValueError("Refusing to replace a symlinked skill installation")
    text = skill_text()
    digest = hashlib.sha256(text.encode()).hexdigest()
    metadata = {"schema_version": 1, "managed_by": "super-codex", "version": __version__,
                "invocation": invocation(), "skill_sha256": digest}
    if destination.exists():
        if not skill.is_file() or not manifest.is_file():
            raise ValueError("Destination is not a managed SuperCodex skill; choose another scope or preserve it manually")
        old = json.loads(manifest.read_text())
        actual = hashlib.sha256(skill.read_bytes()).hexdigest()
        if not isinstance(old, dict) or old.get("managed_by") != "super-codex" or old.get("skill_sha256") != actual:
            raise ValueError("Installed skill has local edits or unknown ownership; preserve those before reinstalling")
        if actual == digest and old == metadata:
            return {"status": "unchanged", "skill": str(skill), "invocation": invocation()}
        if not update:
            raise ValueError("Managed skill exists; pass --update to refresh its launcher and instructions")
    destination.mkdir(parents=True, exist_ok=True)
    skill.write_text(text)
    manifest.write_text(json.dumps(metadata, indent=2) + "\n")
    return {"status": "installed", "skill": str(skill), "invocation": invocation(),
            "note": "Start a new Codex session in the target project. Project-scoped installs add files: commit them before a harness run."}


def register_parser(subparsers):
    skills = subparsers.add_parser("skills", help="List, search or read bundled skills; no model calls")
    skills.add_argument("name", nargs="?", help="Optional bundled skill name to read")
    skills.add_argument("--search", metavar="QUERY", help="Rank bundled skill names/descriptions by task keywords")
    skills.add_argument("--json", action="store_true", help="Print skill metadata as JSON")
    parser = subparsers.add_parser("agent", help="Teach a top-level Codex agent how to operate SuperCodex")
    actions = parser.add_subparsers(dest="agent_action", required=True)
    actions.add_parser("show", help="Print the operator skill with this installation's absolute launcher")
    install = actions.add_parser("install", help="Install the operator skill for one project or all your projects")
    scope = install.add_mutually_exclusive_group(required=True)
    scope.add_argument("--repo", help="Existing project directory; writes .agents/skills/super-codex")
    scope.add_argument("--user", action="store_true", help="Install under ~/.agents/skills/super-codex")
    install.add_argument("--update", action="store_true", help="Refresh an unedited installation managed by SuperCodex")


def handle(args):
    if args.action == "skills":
        rows = bundled_skills()
        if args.search is not None:
            if args.name:
                raise ValueError("Choose a skill name or --search, not both")
            rows = search_skills(args.search, rows)
        if args.name:
            rows = [row for row in rows if row["name"] == args.name]
            if not rows:
                raise ValueError("Unknown bundled skill; run skills to list available names")
        if args.json:
            result = {"skills": rows}
            if args.search is not None:
                result["query"] = args.search
            print(json.dumps(result, indent=2))
        elif args.name:
            print(Path(rows[0]["path"]).read_text(encoding="utf-8"))
        elif args.search is not None and not rows:
            print("No matching bundled skills. Try different task keywords or inspect the current session's skill catalog.")
        else:
            print(skill_catalog_text(rows))
        return 0
    if args.agent_action == "show":
        print(skill_text())
        return 0
    if args.user:
        destination = Path.home() / ".agents" / "skills" / "super-codex"
    else:
        repo = Path(args.repo).resolve()
        if not repo.is_dir():
            raise ValueError("--repo must name an existing project directory")
        destination = repo / ".agents" / "skills" / "super-codex"
    print(json.dumps(install_skill(destination, update=args.update), indent=2))
    return 0
