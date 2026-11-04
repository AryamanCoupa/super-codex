"""Native Codex with task-relevant skill guidance and optional managed workflows."""

import hashlib
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
    hook = parser.add_mutually_exclusive_group()
    hook.add_argument("--prompt-hook", choices=("skills", "answer", "off"), default=None,
                      help="Per-message skill guidance (default), explicit managed answer routing, or bootstrap only")
    hook.add_argument("--no-prompt-hook", action="store_const", const="off", dest="prompt_hook",
                      help="Alias for --prompt-hook off; keep native bootstrap skills without a per-message hook")
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
    if args.operator_model:
        answer_argv += ["--operator-model", args.operator_model]
    for preset in args.research_mcp:
        answer_argv += ["--research-mcp", preset]
    if args.research_mcp_config:
        answer_argv += ["--research-mcp-config", str(Path(args.research_mcp_config).expanduser().resolve())]
    hook_mode = getattr(args, "prompt_hook", None) or "skills"
    routing_enabled = hook_mode == "answer"
    hook_requested = hook_mode != "off"
    routing_instructions = (
        "This session routes each user request through SuperCodex answer. The UserPromptSubmit hook "
        "supplies the exact command and a private file containing the verbatim user message. Execute that "
        "command before doing the task directly; then inspect its receipt and report its actual result. "
        "Skill discovery applies inside the assigned managed request. Command discovery alone is not execution. "
        "If an outer permission restriction prevents startup, use the host's normal approval flow to retry "
        "the same command when permitted. Keep the child's sandbox, policy and tools unchanged. Do not "
        "silently fall back to native work or invent a result after a blocked run. Explicit user requests "
        "to change or bypass this workflow and higher-priority instructions still apply.\n"
        if routing_enabled else
        "Use relevant skills and tools directly in this Codex session. Start with skill-discovery, "
        "read the smallest relevant set, then apply it to the task. Debugging uses evidence and verification; "
        "multi-agent work is useful only for bounded subtasks whose benefit justifies coordination. "
        "There is no required answer command, nested Codex model, clean Git checkout or receipt for native work. "
        "Use managed commands only when explicitly requested or selected for a concrete benefit. "
        "A skill reminder is guidance, not evidence that a skill or managed workflow actually ran.\n"
    )
    skills = bundled_skills()
    prompt = (
        f"You are the SuperCodex {__version__} operator in the current native Codex session. "
        "Existing higher-priority instructions and user constraints still apply.\n\n"
        + routing_instructions
        + skill_text()
        + f"\n<session_defaults>\nWorking project: {json.dumps(str(repo))}\n"
        + f"Session artifacts: {json.dumps(str(folder))}\n"
        + f"Optional worker policy: {json.dumps(str(policy_file))}\n"
        + f"Selected pack: {json.dumps(str(pack) if pack else None)}\n"
        + f"Selected additional MCP servers: {json.dumps(sorted(mcp))}\n"
        + routing_instructions
        + "For each new task, apply skill-discovery: check the current session and bundled skill catalogs, "
        "use keyword search when selection is unclear, and read only the relevant skill instructions. "
        "Reuse unchanged instructions already read. Follow the session's selected execution mode; routed "
        "requests discover and apply skills within the managed command. "
        "A skill catalog or startup acknowledgment is not the requested result. For repository discovery, "
        "use the available GitHub tools in that execution context; initialize/discover operations and follow "
        "pagination. For current news, retrieve fresh sources and cite them. For coding, inspect the target, "
        "make a scoped change, run meaningful checks and report the observed evidence. Preserve unrelated "
        "changes. A research receipt is advisory, not a verified coding run.\n"
        + "The CLI also supports isolated verification, repeated evaluation, task packs and cost comparisons. "
        "Do not launch unrelated or recursive model jobs. Research does not require a clean Git checkout. "
        "CLI jobs have their own source, "
        "permission and accounting requirements; use the normal authorization flow if an explicit job "
        "needs permissions, and report actual failures. Never bypass the native sandbox or approval policy.\n"
        + f"Optional managed coding template (replace TASK_FILE): {shlex.join(run_argv)}\n"
        + f"{'Required' if routing_enabled else 'Optional'} answer command template (append a quoted prompt or --prompt-file): {shlex.join(answer_argv)}\n"
        + "Preserve the selected policy, pack and tools when executing these commands. Inspect their "
        "receipts before describing their results as harness-verified. Native operator usage is separate "
        "from their reported model usage. Select planning, review, repair, escalation or multi-agent "
        "experiments only when they add value for this task.\n</session_defaults>\n"
    )
    if context:
        prompt += f"\n<selected_task_pack>\n{context}\n</selected_task_pack>\n"
    if args.prompt:
        prompt += (f"\nInitial user request file: {json.dumps(str(folder / 'initial-request.txt'))}\n"
                   "<user_task>\n" + args.prompt + "\n</user_task>\n")
        if routing_enabled:
            prompt += ("Execute this required initial answer command exactly once, then inspect its receipt. "
                       "The initialization message is excluded from the hook to avoid duplicate routing:\n"
                       + shlex.join(answer_argv + ["--prompt-file", str(folder / "initial-request.txt")]) + "\n")
        else:
            prompt += "Carry out this request using the relevant skills and current tools; initialization alone does not complete it.\n"
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
    initial_prompt = ("Load the SuperCodex skill catalog and session defaults from "
                      f"{json.dumps(str(folder / 'bootstrap.txt'))}. "
                      + ("Each user request routes through the SuperCodex answer command supplied by the hook. "
                         "If the bootstrap includes an initial request, run its required answer command once and inspect the receipt. "
                         if routing_enabled else
                         "For each task, start with skill-discovery, read the relevant skills and use native tools directly. ")
                      + "Respect existing higher-priority instructions. If no task was provided, briefly confirm readiness and wait.")
    argv += ["--", initial_prompt]
    # The real command stays in memory. Preview/log metadata never expose MCP values.
    public_argv = list(policy["codex_command"]) + argv[len(policy["codex_command"]):]
    for index, value in enumerate(public_argv):
        if isinstance(value, str) and value.startswith("mcp_servers."):
            public_argv[index] = "mcp_servers.<selected-server>=<private configuration>"
    public_argv[-1] = "<Read the SuperCodex bootstrap file in the session directory>"
    preview = {"version": __version__, "mode": "native_advisory", "harness_enforced": False, "repo": str(repo), "pack": str(pack) if pack else None,
               "workflow": "supercodex_answer_with_skills" if routing_enabled else "supercodex_skills",
               "prompt_routing": "supercodex_answer" if routing_enabled else "native",
               "prompt_hook": {"mode": hook_mode, "requested": hook_requested,
                               "status": "pending" if hook_requested else "disabled"},
               "bundled_skills": [row["name"] for row in skills],
               "operator_model": operator, "worker_model": policy["model"], "worker_policy": str(policy_file),
               "artifact_directory": str(folder), "additional_mcp_servers": sorted(mcp), "command": public_argv,
               "inherits_codex_configuration": True,
               "note": ("Native Codex UI with per-message answer-command instructions and skill discovery. "
                        "Hook delivery is not proof of command execution; inspect actual receipts. "
                        "The answer child uses buffered exec; outer native model usage is separate."
                        if routing_enabled else
                        "Native Codex with task-relevant skills and existing tools. No compulsory child-model "
                        "calls or receipts. Skill reminders guide selection; managed workflows are explicit options.")}
    routing = {"answer_argv": answer_argv, "output_root": str(folder / "answers"),
               "bootstrap_prompt_sha256": hashlib.sha256(initial_prompt.encode()).hexdigest()}
    return {"argv": argv, "repo": repo, "folder": folder, "policy": policy, "mcp": mcp, "pack": pack,
            "answer_argv": answer_argv, "skills": skills, "routing": routing,
            "prompt": prompt, "initial_prompt": initial_prompt, "preview": preview}


def handle(args):
    managed = args.managed or args.task or args.patch_only or args.no_stream
    if args.native and managed:
        raise ValueError("--task, --patch-only and --no-stream select the managed controller; omit --native")
    if managed:
        from .controller import handle as controlled_handle
        return controlled_handle(args)
    if args.prompt_hook != "answer" and (args.research_mcp or args.research_mcp_config):
        raise ValueError("Research tool settings require --prompt-hook answer or --managed; "
                         "native skill work uses your existing Codex connections or --mcp")
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
    if plan["preview"]["prompt_hook"]["mode"] == "answer":
        payloads["session-routing.json"] = json.dumps(plan["routing"], indent=2)
    for name, content in payloads.items():
        with (folder / name).open("x", encoding="utf-8") as stream:
            os.chmod(folder / name, 0o600)
            stream.write(content if name == "initial-request.txt" else content + "\n")
    if plan["preview"]["prompt_hook"]["requested"]:
        hook_mode = plan["preview"]["prompt_hook"]["mode"]
        overrides = None
        try:
            if hook_mode == "answer":
                from .prompt_hook import hook_overrides
                overrides = hook_overrides(plan["policy"]["codex_command"], folder / "session-routing.json")
            else:
                from .skill_hook import hook_overrides
                overrides = hook_overrides(plan["policy"]["codex_command"])
        except (OSError, ValueError) as error:
            status = "failed" if hook_mode == "answer" else "unavailable"
            plan["preview"]["prompt_hook"]["status"] = status
            (folder / "session.json").write_text(json.dumps(plan["preview"], indent=2) + "\n")
            with (folder / "hook-registration.json").open("x", encoding="utf-8") as stream:
                os.chmod(folder / "hook-registration.json", 0o600)
                json.dump({"mode": hook_mode, "status": status, "event": "UserPromptSubmit", "error": str(error)}, stream)
            if hook_mode == "answer":
                with (folder / "exit.json").open("x", encoding="utf-8") as stream:
                    os.chmod(folder / "exit.json", 0o600)
                    json.dump({"status": "hook_registration_failed", "error": str(error)}, stream)
                raise
            print("SuperCodex skill reminder unavailable; continuing with bootstrap skills and native tools. "
                  "Inspect hook-registration.json in the session artifacts for details.", file=sys.stderr, flush=True)
        if overrides is not None:
            plan["argv"][-2:-2] = overrides
            plan["preview"]["command"][-2:-2] = overrides
            plan["preview"]["prompt_hook"]["status"] = "active"
            with (folder / "hook-registration.json").open("x", encoding="utf-8") as stream:
                os.chmod(folder / "hook-registration.json", 0o600)
                json.dump({"mode": hook_mode, "status": "active", "event": "UserPromptSubmit", "overrides": overrides}, stream)
            (folder / "session.json").write_text(json.dumps(plan["preview"], indent=2) + "\n")
    hook_info = plan["preview"]["prompt_hook"]
    mode = ("per-message answer routing" if hook_info["mode"] == "answer" else
            "per-message skill guidance" if hook_info["status"] == "active" else "bootstrap skills and native tools")
    print(f"SuperCodex: native Codex with {mode} and {len(plan['skills'])} task skills.\nOpening Codex in {plan['repo']}\nSession artifacts: {folder}", file=sys.stderr, flush=True)
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
