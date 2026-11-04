"""Discoverable operator skill and CLI context for managed Codex workers."""

import hashlib
import json
import os
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
        "</supercodex_cli>"
    )


def worker_environment():
    return {**os.environ, "SUPERCODEX_WORKER": "1"}


def check_worker_command(args):
    if os.environ.get("SUPERCODEX_WORKER") != "1":
        return
    allowed = args.action in {"commands", "doctor", "report", "mcp"}
    allowed |= args.action == "pack" and args.pack_action in {"list", "inspect", "suggest"}
    allowed |= args.action == "agent" and args.agent_action == "show"
    if args.action == "experimental":
        allowed |= args.experiment == "list"
        allowed |= args.experiment == "router" and args.router_action == "choose"
        allowed |= args.experiment == "memory" and args.memory_action == "query"
    if not allowed:
        raise ValueError("Managed worker cannot launch nested runs or mutations outside parent accounting; "
                         "return this command to the top-level operator. Read-only discovery remains available.")


def skill_text():
    template = (ASSETS / "operator" / "super-codex" / "SKILL.md").read_text()
    return template.replace("{{SUPER_CODEX_COMMAND}}", shlex.join(invocation()))


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
    parser = subparsers.add_parser("agent", help="Teach a top-level Codex agent how to operate SuperCodex")
    actions = parser.add_subparsers(dest="agent_action", required=True)
    actions.add_parser("show", help="Print the operator skill with this installation's absolute launcher")
    install = actions.add_parser("install", help="Install the operator skill for one project or all your projects")
    scope = install.add_mutually_exclusive_group(required=True)
    scope.add_argument("--repo", help="Existing project directory; writes .agents/skills/super-codex")
    scope.add_argument("--user", action="store_true", help="Install under ~/.agents/skills/super-codex")
    install.add_argument("--update", action="store_true", help="Refresh an unedited installation managed by SuperCodex")


def handle(args):
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
