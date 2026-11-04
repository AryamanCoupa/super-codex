"""SuperCodex entry point and explicitly selected advisory native session."""

import json
import os
import shlex
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from . import __version__
from .agent_tools import invocation, skill_text
from .config import load_policy, toml_value
from .packs import resolve_pack
from .runner import pack_context, validate_output_directory


def register_parser(subparsers):
    parser = subparsers.add_parser("start", help="Run the enforced SuperCodex controller (default); --native opens advisory Codex")
    parser.add_argument("prompt", nargs="?", help="Quoted task or question; otherwise open the controller prompt")
    parser.add_argument("--native", action="store_true", help="Explicit advisory Codex TUI; harness execution is not enforced")
    parser.add_argument("--task", help="Validated task JSON/TOML; skip model preparation")
    parser.add_argument("--patch-only", action="store_true", help="Save a verified patch without applying it to the source")
    parser.add_argument("--repo", "-C", default=".", help="Working project directory; defaults to current directory")
    parser.add_argument("--pack", help="Dedicated pack or registry; otherwise let the operator suggest one")
    parser.add_argument("--config", help="Worker policy override; otherwise use selected pack policy, or balanced without a pack")
    parser.add_argument("--model", "-m", help="Override the worker and default operator model")
    parser.add_argument("--operator-model", help="Override the read-only preparation model (or native operator with --native)")
    parser.add_argument("--mcp", action="append", default=[], help="Add a bundled MCP preset; repeatable")
    parser.add_argument("--mcp-config", help="Additional MCP JSON/TOML configuration")
    parser.add_argument("--output-root", help="Session/artifact root; default: ~/.local/state/super-codex")
    parser.add_argument("--no-alt-screen", action="store_true", help="With --native, use Codex's inline terminal mode")
    parser.add_argument("--dry-run", action="store_true", help="Preview the launch without writing files or invoking Codex")


def prepare(args):
    from .cli import mcp_config

    repo = Path(args.repo).expanduser().resolve()
    if not repo.is_dir():
        raise ValueError("--repo must be an existing directory")
    pack = resolve_pack(args.pack)
    policy = load_policy(args.config or (None if pack else "balanced"), pack,
                         {"model": args.model} if args.model else None)
    if not all(isinstance(value, str) and value for value in policy["codex_command"]):
        raise ValueError("codex_command must contain nonempty string arguments")
    operator = args.operator_model or args.model or policy.get("planner_model") or policy["model"]
    if not isinstance(operator, str) or not operator.strip():
        raise ValueError("Choose a nonempty operator model")
    context, pack_mcp = pack_context(pack)
    mcp = {**pack_mcp, **mcp_config(args.mcp, args.mcp_config)}
    root = Path(args.output_root).expanduser() if args.output_root else Path.home() / ".local/state/super-codex"
    root = validate_output_directory(repo, root)
    folder = root / "sessions" / uuid.uuid4().hex
    policy_file, mcp_file = folder / "worker-policy.json", folder / "worker-mcp.json"
    run_argv = invocation() + ["run", "TASK_FILE", "--repo", str(repo), "--config", str(policy_file),
                               "--output", str(folder / "runs")]
    if pack:
        run_argv += ["--pack", str(pack)]
    if mcp:
        run_argv += ["--mcp-config", str(mcp_file)]
    prompt = (
        f"You are the SuperCodex {__version__} top-level operator in an interactive Codex session. "
        "Use the following workflow guidance for this session while following the user's requests and "
        "existing higher-priority instructions. This is the operator, not a managed worker.\n\n"
        + skill_text()
        + f"\n<session_defaults>\nWorking project: {json.dumps(str(repo))}\n"
        + f"Session artifacts and task definitions: {json.dumps(str(folder))}\n"
        + f"Worker policy: {json.dumps(str(policy_file))}\n"
        + f"Selected pack: {json.dumps(str(pack) if pack else None)}\n"
        + f"Selected additional MCP servers: {json.dumps(sorted(mcp))}\n"
        + f"Verified run template (replace TASK_FILE with an absolute task path): {shlex.join(run_argv)}\n"
        + "For coding work, inspect the repository, define real acceptance checks, and use the harness run "
        "or appropriate experimental command rather than silently treating a direct edit as verified. "
        "Preserve these policy, tool and output defaults in delegated commands. Create task files in the "
        "session directory to keep the source clean. If a new pack is selected, inspect its policy/tools "
        "and reconcile them explicitly with the selected session policy.\n"
        + "An ordinary request to implement or fix code authorizes applying its successful accepted patch: "
        "inspect the diff, confirm the target is still clean at the result's base commit, run git apply --check, "
        "then apply it and report validation. Respect requests for patch-only, review-only or planning-only work. "
        "Do not overwrite concurrent or unrelated user edits; if the source is dirty, inspect and explain the "
        "specific prerequisite instead of discarding changes or claiming a verified run.\n"
        + "Planning, repair, fallback, review, dedicated packs and experimental methods are available; select "
        "them by task evidence and user budget, not all at once. Native operator/TUI usage is separate from "
        "harness run accounting; do not claim run totals include the operator. Existing Codex permissions and "
        "approval behavior still apply to nested CLI and network access.\n</session_defaults>\n"
    )
    if context:
        prompt += f"\n<selected_task_pack>\n{context}\n</selected_task_pack>\n"
    if args.prompt:
        prompt += "\n<user_task>\n" + args.prompt + "\n</user_task>\n"
    else:
        prompt += ("\nNo task has been supplied yet. Briefly say SuperCodex is ready and wait for the user's "
                   "next message. Do not scan the repository, create tasks or start additional model jobs yet.\n")
    argv = list(policy["codex_command"]) + ["-C", str(repo), "--model", operator, "--add-dir", str(folder),
                                            "-c", f"model_reasoning_effort={toml_value(policy['reasoning_effort'])}"]
    if policy.get("local_provider"):
        argv += ["--oss", "--local-provider", policy["local_provider"]]
    if args.no_alt_screen:
        argv.append("--no-alt-screen")
    for name, config in mcp.items():
        argv += ["-c", f"mcp_servers.{toml_value(name)}={toml_value(config)}"]
    # Keep arbitrary task/pack content out of argv and avoid platform argument-size limits.
    # The file exists before launch and its directory is explicitly writable/readable to Codex.
    initial_prompt = (
        "Initialize this SuperCodex session by reading the UTF-8 instructions at "
        f"{json.dumps(str(folder / 'bootstrap.txt'))}. Follow that workflow for this session while respecting "
        "existing higher-priority instructions. The file contains session defaults and the user's task, "
        "or instructions to wait when no task was provided."
    )
    argv += ["--", initial_prompt]
    # The real command stays in memory. Preview/log metadata never expose MCP values.
    public_argv = list(policy["codex_command"]) + argv[len(policy["codex_command"]):]
    for index, value in enumerate(public_argv):
        if isinstance(value, str) and value.startswith("mcp_servers."):
            public_argv[index] = "mcp_servers.<selected-server>=<private configuration>"
    public_argv[-1] = "<Read the SuperCodex bootstrap file in the session directory>"
    preview = {"version": __version__, "mode": "native_advisory", "harness_enforced": False, "repo": str(repo), "pack": str(pack) if pack else None,
               "operator_model": operator, "worker_model": policy["model"], "worker_policy": str(policy_file),
               "artifact_directory": str(folder), "additional_mcp_servers": sorted(mcp), "command": public_argv,
               "inherits_codex_configuration": True,
               "note": "Native Codex TUI with SuperCodex guidance. Operator usage is separate from verified-run accounting; experiments remain selective."}
    return {"argv": argv, "repo": repo, "folder": folder, "policy": policy, "mcp": mcp, "pack": pack,
            "prompt": prompt, "initial_prompt": initial_prompt, "preview": preview}


def handle(args):
    if not args.native:
        from .controller import handle as controlled_handle
        return controlled_handle(args)
    if args.task or args.patch_only:
        raise ValueError("--task and --patch-only require the enforced controller; omit --native")
    return handle_native(args)


def handle_native(args):
    plan = prepare(args)
    if args.dry_run:
        print(json.dumps(plan["preview"], indent=2))
        return 0
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ValueError("Interactive start requires a terminal. Use --dry-run to preview, or run TASK --repo REPO for non-interactive execution.")
    if not shutil.which(plan["argv"][0]):
        raise ValueError("Codex executable was not found. Install/login to Codex, or set codex_command in your policy.")
    folder = plan["folder"]
    folder.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.chmod(folder, 0o700)
    payloads = {"worker-policy.json": json.dumps(plan["policy"], indent=2),
                "worker-mcp.json": json.dumps({"mcp_servers": plan["mcp"]}, indent=2),
                "bootstrap.txt": plan["prompt"], "session.json": json.dumps(plan["preview"], indent=2)}
    for name, content in payloads.items():
        with (folder / name).open("x", encoding="utf-8") as stream:
            os.chmod(folder / name, 0o600)
            stream.write(content + "\n")
    print(f"SuperCodex: native advisory mode; harness execution is NOT enforced.\nOpening Codex in {plan['repo']}\nSession artifacts: {folder}", file=sys.stderr, flush=True)
    try:
        # Inherit terminal handles, native authentication/configuration and permission behavior.
        result = subprocess.call(plan["argv"], cwd=plan["repo"])
    except KeyboardInterrupt:
        result = 130
    except OSError as error:
        (folder / "exit.json").write_text(json.dumps({"status": "launch_failed", "error": str(error)}) + "\n")
        raise
    (folder / "exit.json").write_text(json.dumps({"status": "exited", "returncode": result}) + "\n")
    return result if result >= 0 else 128 - result
