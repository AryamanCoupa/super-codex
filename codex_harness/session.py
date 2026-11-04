"""Native Codex bootstrap by default, with an explicit enforced controller."""

import json
import os
import shlex
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from . import __version__
from .agent_tools import bundled_skills, invocation, skill_text
from .config import load_policy, toml_value
from .codex import mcp_override
from .packs import resolve_pack
from .runner import pack_context, validate_output_directory


def register_parser(subparsers):
    parser = subparsers.add_parser("start", help="Open Codex with SuperCodex workflow instructions; --managed enforces the controller")
    parser.add_argument("prompt", nargs="?", help="Quoted task or question; otherwise open interactive Codex")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--native", action="store_true", help="Explicit native Codex bootstrap (default); instructions guide harness use")
    mode.add_argument("--managed", action="store_true", help="Use the SuperCodex controller to enforce preparation, verification and receipts")
    parser.add_argument("--task", help="Validated task JSON/TOML; implies --managed and skips model preparation")
    parser.add_argument("--patch-only", action="store_true", help="Implies --managed; save a verified patch without applying it")
    parser.add_argument("--repo", "-C", default=".", help="Working project directory; defaults to current directory")
    parser.add_argument("--pack", help="Dedicated pack or registry; otherwise let the operator suggest one")
    parser.add_argument("--config", help="Worker policy override; otherwise use selected pack policy, or balanced without a pack")
    parser.add_argument("--model", "-m", help="Override the worker and default operator model")
    parser.add_argument("--operator-model", help="Override the read-only preparation model (or native operator with --native)")
    parser.add_argument("--mcp", action="append", default=[], help="Add a bundled MCP preset; repeatable")
    parser.add_argument("--mcp-config", help="Additional MCP JSON/TOML configuration")
    parser.add_argument("--research-mcp", action="append", default=[], help="MCP preset for research/preparation only; repeatable")
    parser.add_argument("--research-mcp-config", help="Private research MCP JSON/TOML; defaults to user config/super-codex/research.toml when present")
    parser.add_argument("--output-root", help="Session/artifact root; default: ~/.local/state/super-codex")
    parser.add_argument("--no-alt-screen", action="store_true", help="Use Codex's inline terminal mode in the native bootstrap")
    parser.add_argument("--no-prompt-hook", action="store_true", help="Compatibility flag; native sessions no longer install prompt-routing hooks")
    parser.add_argument("--no-stream", action="store_true", help="Implies --managed; use buffered Codex exec output for compatibility")
    parser.add_argument("--dry-run", action="store_true", help="Preview the launch without writing files or invoking Codex")


def session_output_directory(repo, root):
    root = Path(root).resolve()
    if root == repo or (repo in root.parents and ".git" in root.relative_to(repo).parts):
        raise ValueError("Choose a separate session output directory outside Git metadata")
    if repo in root.parents:
        status = subprocess.run(["git", "-C", str(repo), "rev-parse", "--show-toplevel"],
                                capture_output=True, timeout=30)
        if status.returncode:
            # A non-repository such as the user's home has no source checkout to
            # dirty. Its ordinary private state directory is a valid destination.
            return root
    return validate_output_directory(repo, root)


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
    root = session_output_directory(repo, root)
    folder = root / "sessions" / uuid.uuid4().hex
    policy_file, mcp_file = folder / "worker-policy.json", folder / "worker-mcp.json"
    run_argv = invocation() + ["start", "--managed", "--no-stream", "--task", "TASK_FILE",
                               "--repo", str(repo), "--config", str(policy_file),
                               "--output-root", str(folder / "runs")]
    if pack:
        run_argv += ["--pack", str(pack)]
    if mcp:
        run_argv += ["--mcp-config", str(mcp_file)]
    answer_argv = invocation() + ["answer", "--repo", str(repo), "--config", str(policy_file),
                                  "--output-root", str(folder / "answers")]
    if pack:
        answer_argv += ["--pack", str(pack)]
    if mcp:
        answer_argv += ["--mcp-config", str(mcp_file)]
    skills = bundled_skills()
    prompt = (
        f"You are the SuperCodex {__version__} operator in the current native Codex session. "
        "Use the relevant skills below to do the user's work with your existing tools. "
        "Research, conversation and coding normally happen in this session; no answer command, "
        "managed controller or additional model process is required for an ordinary request. "
        "Existing higher-priority instructions and user constraints still apply.\n\n"
        + skill_text()
        + f"\n<session_defaults>\nWorking project: {json.dumps(str(repo))}\n"
        + f"Session artifacts: {json.dumps(str(folder))}\n"
        + f"Optional worker policy: {json.dumps(str(policy_file))}\n"
        + f"Selected pack: {json.dumps(str(pack) if pack else None)}\n"
        + f"Selected additional MCP servers: {json.dumps(sorted(mcp))}\n"
        + "Choose and read only the skills relevant to the actual task, then execute that task. "
        "A skill catalog or startup acknowledgment is not the requested result. For repository discovery, "
        "use the connected GitHub tools directly; initialize/discover operations when required and follow "
        "pagination. For current news, retrieve fresh sources and cite them. For coding, inspect the target, "
        "make a scoped change, run meaningful checks and report the observed evidence. Preserve unrelated "
        "changes and do not claim a harness run or receipt for work performed natively.\n"
        + "The CLI remains available when explicitly requested or useful for isolated verification, repeated "
        "evaluation, task packs or cost comparisons. Do not launch child model jobs merely to answer a "
        "question. Native research does not require a clean Git checkout. CLI jobs have their own source, "
        "permission and accounting requirements; use the normal authorization flow if an explicit job "
        "needs permissions, and report actual failures. Never bypass the native sandbox or approval policy.\n"
        + f"Optional managed coding template (replace TASK_FILE): {shlex.join(run_argv)}\n"
        + f"Optional accounted answer template (append a quoted prompt or --prompt-file): {shlex.join(answer_argv)}\n"
        + "Preserve the selected policy, pack and tools when choosing these optional commands. Inspect their "
        "receipts before describing their results as harness-verified. Native operator usage is separate "
        "from their reported model usage. Select planning, review, repair, escalation or multi-agent "
        "experiments only when they add value for this task.\n</session_defaults>\n"
    )
    if context:
        prompt += f"\n<selected_task_pack>\n{context}\n</selected_task_pack>\n"
    if args.prompt:
        prompt += (f"\nInitial user request file: {json.dumps(str(folder / 'initial-request.txt'))}\n"
                   "Carry out this request using the relevant skills and current tools; initialization alone does not complete it.\n"
                   "<user_task>\n" + args.prompt + "\n</user_task>\n")
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
        argv += ["-c", mcp_override(name, config)]
    # Keep arbitrary task/pack content out of argv and avoid platform argument-size limits.
    # The file exists before launch and its directory is explicitly writable/readable to Codex.
    initial_prompt = (
        "Load the SuperCodex skill catalog and session defaults from "
        f"{json.dumps(str(folder / 'bootstrap.txt'))}. Choose and read the relevant skills, then use "
        "the current Codex tools to carry out the user's task in this session. Respect existing higher-priority instructions. If no task was "
        "provided, briefly confirm readiness and wait."
    )
    argv += ["--", initial_prompt]
    # The real command stays in memory. Preview/log metadata never expose MCP values.
    public_argv = list(policy["codex_command"]) + argv[len(policy["codex_command"]):]
    for index, value in enumerate(public_argv):
        if isinstance(value, str) and value.startswith("mcp_servers."):
            public_argv[index] = "mcp_servers.<selected-server>=<private configuration>"
    public_argv[-1] = "<Read the SuperCodex bootstrap file in the session directory>"
    preview = {"version": __version__, "mode": "native_advisory", "harness_enforced": False, "repo": str(repo), "pack": str(pack) if pack else None,
               "workflow": "supercodex_skills",
               "prompt_routing": "native", "bundled_skills": [row["name"] for row in skills],
               "operator_model": operator, "worker_model": policy["model"], "worker_policy": str(policy_file),
               "artifact_directory": str(folder), "additional_mcp_servers": sorted(mcp), "command": public_argv,
               "inherits_codex_configuration": True,
               "note": "Native Codex with task-relevant skills and existing tools. No routing hooks or compulsory child model calls. Managed workflows are explicit opt-ins."}
    return {"argv": argv, "repo": repo, "folder": folder, "policy": policy, "mcp": mcp, "pack": pack,
            "answer_argv": answer_argv, "skills": skills,
            "prompt": prompt, "initial_prompt": initial_prompt, "preview": preview}


def handle(args):
    managed = args.managed or args.task or args.patch_only or args.no_stream
    if args.native and managed:
        raise ValueError("--task, --patch-only and --no-stream select the managed controller; omit --native")
    if managed:
        from .controller import handle as controlled_handle
        return controlled_handle(args)
    if args.research_mcp or args.research_mcp_config:
        raise ValueError("Research tool settings require --managed; the native bootstrap uses your existing Codex connections")
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
    if args.prompt:
        payloads["initial-request.txt"] = args.prompt
    for name, content in payloads.items():
        with (folder / name).open("x", encoding="utf-8") as stream:
            os.chmod(folder / name, 0o600)
            stream.write(content if name == "initial-request.txt" else content + "\n")
    print(f"SuperCodex: native Codex with {len(plan['skills'])} task skills available.\nOpening Codex in {plan['repo']}\nSession artifacts: {folder}", file=sys.stderr, flush=True)
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
