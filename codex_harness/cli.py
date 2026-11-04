import argparse
import json
import random
import re
import shutil
import sys
from pathlib import Path

from . import __version__
from .config import ASSETS, load_policy, load_task, read
from .demo import create, demo
from .process import execute
from .report import markdown, read_results, summarize
from .runner import git, pack_context, run, save
from .improve import copy_pack, promote, propose, register, rollback
from .packs import create_pack, discover_packs, inspect_pack, resolve_pack, suggest_packs


def pack_path(name):
    return resolve_pack(name)


def mcp_config(names, extra=None):
    result = {}
    for name in names or []:
        if not re.fullmatch(r"[a-z-]+", name):
            raise ValueError("Invalid MCP preset name")
        result.update(read(ASSETS / "mcp" / f"{name}.toml")["mcp_servers"])
    if extra:
        result.update(read(extra).get("mcp_servers", {}))
    return result


def build_parser():
    parser = argparse.ArgumentParser(prog="super-codex", description="SuperCodex: stronger workflows, measured cost")
    parser.add_argument("--version", "-V", action="version", version=f"SuperCodex {__version__}")
    sub = parser.add_subparsers(dest="action", required=True)
    commands = sub.add_parser("commands", help="Discover every installed CLI command and its arguments without model calls")
    commands.add_argument("path", nargs="*", help="Optional command path, for example: experimental router train")
    commands.add_argument("--json", action="store_true", help="Print structured argument and usage metadata")
    doctor = sub.add_parser("doctor", help="Inspect local prerequisites without invoking a model")
    doctor.add_argument("--config")
    runner = sub.add_parser("run", help="Run a trusted local coding task")
    runner.add_argument("task")
    runner.add_argument("--repo", required=True)
    runner.add_argument("--revision", default="HEAD")
    runner.add_argument("--config")
    runner.add_argument("--pack")
    runner.add_argument("--model")
    runner.add_argument("--mcp", action="append", default=[])
    runner.add_argument("--mcp-config")
    runner.add_argument("--output", default=".harness/runs")
    runner.add_argument("--label", default="default")
    benchmark = sub.add_parser("eval", help="Run a suite across policy/task-pack variants")
    benchmark.add_argument("suite")
    benchmark.add_argument("--config")
    benchmark.add_argument("--output", default=".harness/evals")
    benchmark.add_argument("--max-runs", type=int, default=100)
    report = sub.add_parser("report")
    report.add_argument("directory")
    report.add_argument("--json", action="store_true")
    demo_parser = sub.add_parser("demo", help="Offline end-to-end simulation; --live invokes your model")
    demo_parser.add_argument("--output", default=".harness/demo")
    demo_parser.add_argument("--live", action="store_true")
    demo_parser.add_argument("--model")
    init = sub.add_parser("fixtures", help="Create three runnable smoke tasks and a sample eval suite")
    init.add_argument("destination")
    pack = sub.add_parser("pack", help="Create and improve a reusable task-specific harness")
    ps = pack.add_subparsers(dest="pack_action", required=True)
    listing = ps.add_parser("list", help="Discover bundled packs, local packs and active releases")
    listing.add_argument("--root", action="append", default=[], help="Pack or registry directory; repeatable")
    listing.add_argument("--json", action="store_true")
    inspection = ps.add_parser("inspect", help="Show a pack's instructions budget, tools, skills and defaults")
    inspection.add_argument("pack")
    suggestion = ps.add_parser("suggest", help="Suggest a pack from task/repository evidence without a model call")
    suggestion.add_argument("task", nargs="?", help="Task JSON/TOML file (or use --prompt)")
    suggestion.add_argument("--prompt")
    suggestion.add_argument("--repo")
    suggestion.add_argument("--root", action="append", default=[])
    suggestion.add_argument("--from-runs", help="Optional directory of past results for recurring-failure suggestions")
    creation = ps.add_parser("create", help="Build a dedicated pack from a template and task")
    creation.add_argument("destination")
    creation.add_argument("--from", dest="source", required=True, help="Template or existing pack; use pack suggest to choose")
    creation.add_argument("--name")
    creation.add_argument("--task")
    creation.add_argument("--prompt")
    creation.add_argument("--repo")
    fork = ps.add_parser("fork")
    fork.add_argument("source")
    fork.add_argument("destination")
    learn = ps.add_parser("learn", help="Save failure evidence for review; does not change active instructions")
    learn.add_argument("pack")
    learn.add_argument("--from-result", required=True)
    proposal = ps.add_parser("propose", help="Use a model to propose one evidence-based instruction update")
    proposal.add_argument("pack")
    proposal.add_argument("destination")
    proposal.add_argument("--from-result", action="append", required=True)
    proposal.add_argument("--repo", required=True)
    proposal.add_argument("--config")
    proposal.add_argument("--model", default="gpt-6.1-sol")
    promotion = ps.add_parser("promote", help="Gate a candidate using separate holdout trials and publish a local release")
    promotion.add_argument("candidate")
    promotion.add_argument("--baseline-runs", required=True)
    promotion.add_argument("--candidate-runs", required=True)
    promotion.add_argument("--registry", required=True)
    promotion.add_argument("--min-runs", type=int, default=10)
    promotion.add_argument("--min-pass-rate", type=float, default=0.8)
    promotion.add_argument("--max-cost-ratio", type=float, default=1.0)
    promotion.add_argument("--cost-metric", choices=["usd", "tokens"], default="usd")
    back = ps.add_parser("rollback")
    back.add_argument("registry")
    registration = ps.add_parser("register", help="Store an initial pack version before improving it")
    registration.add_argument("pack")
    registration.add_argument("--registry", required=True)
    optimization = ps.add_parser("optimize", help="Propose, compare on fresh holdouts and conditionally promote one update")
    optimization.add_argument("pack")
    optimization.add_argument("--from-result", action="append", required=True)
    optimization.add_argument("--holdout", required=True, help="JSON suite with tasks, repeat and seed")
    optimization.add_argument("--repo", required=True, help="Repository for the read-only proposal session")
    optimization.add_argument("--registry", required=True)
    optimization.add_argument("--output", required=True, help="New experiment directory")
    optimization.add_argument("--config")
    optimization.add_argument("--model", default="gpt-6.1-sol", help="Proposal model; evaluation follows the pack/policy")
    optimization.add_argument("--max-runs", type=int, default=40)
    optimization.add_argument("--min-runs", type=int, default=10)
    optimization.add_argument("--min-distinct-tasks", type=int, default=3)
    optimization.add_argument("--min-pass-rate", type=float, default=0.8)
    optimization.add_argument("--max-cost-ratio", type=float, default=1.0)
    optimization.add_argument("--cost-metric", choices=["usd", "tokens"], default="usd")
    optimization.add_argument("--max-total-tokens", type=int, default=1_000_000)
    optimization.add_argument("--max-total-cost-usd", type=float)
    mcp = sub.add_parser("mcp", help="Print a Codex config snippet; never changes global settings")
    mcp.add_argument("names", nargs="+", choices=["playwright", "github", "atlassian", "openai-docs"])
    from .experimental.cli import register_parser
    register_parser(sub)
    from .agent_tools import register_parser as register_agent_parser
    register_agent_parser(sub)
    from .session import register_parser as register_session_parser
    register_session_parser(sub)
    return parser


def main(argv=None):
    parser = build_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    commands = {name for action in parser._actions if isinstance(action, argparse._SubParsersAction)
                for name in action.choices}
    if not argv or argv[0] not in commands | {"--help", "-h", "--version", "-V"}:
        argv.insert(0, "start")
    args = parser.parse_args(argv)
    try:
        from .agent_tools import check_worker_command
        check_worker_command(args)
        if args.action == "start":
            from .session import handle
            return handle(args)
        if args.action == "agent":
            from .agent_tools import handle
            return handle(args)
        if args.action == "commands":
            from .command_catalog import catalog, render_catalog
            print(json.dumps(catalog(parser, args.path), indent=2) if args.json else render_catalog(parser, args.path))
            return 0
        if args.action == "experimental":
            from .experimental.cli import handle
            return handle(args)
        if args.action == "doctor":
            policy = load_policy(args.config)
            status = {}
            for label, command in {"python": [sys.executable, "--version"], "git": ["git", "--version"],
                                   "codex": policy["codex_command"] + ["--version"]}.items():
                try:
                    value = execute(command, Path.cwd(), 10)
                    status[label] = {"ok": value["returncode"] == 0, "version": value["output"].strip()}
                except OSError as error:
                    status[label] = {"ok": False, "error": str(error)}
            status["node_for_playwright"] = bool(shutil.which("node") and shutil.which("npx"))
            status["model"] = policy["model"]
            status["note"] = "No authentication, model availability or MCP connection was tested. Requires Codex --ignore-user-config support (tested 0.164.0)."
            print(json.dumps(status, indent=2))
            return 0 if all(status[k]["ok"] for k in ("python", "git", "codex")) else 1
        if args.action == "run":
            pack = pack_path(args.pack)
            policy = load_policy(args.config, pack, {"model": args.model} if args.model else None)
            record = run(args.repo, load_task(args.task, pack), policy, args.output, pack,
                         mcp_config(args.mcp, args.mcp_config), revision=args.revision,
                         label=args.label, progress=lambda x: print(x, file=sys.stderr, flush=True))
            print(json.dumps({k: record[k] for k in ("status", "tokens", "cost_usd", "budget_overrun", "artifact_directory")}, indent=2))
            return 0 if record["status"] == "passed" else 1
        if args.action == "eval":
            suite = read(args.suite)
            root = Path(args.suite).resolve().parent
            repeats = suite.get("repeat", 1)
            if not isinstance(repeats, int) or repeats < 1:
                raise ValueError("repeat must be a positive integer")
            variants, tasks = suite["variants"], suite["tasks"]
            if not variants or not tasks or len({v["name"] for v in variants}) != len(variants):
                raise ValueError("Suite needs tasks and uniquely named variants")
            count = repeats * len(variants) * len(tasks)
            if count > args.max_runs:
                raise ValueError(f"Suite requests {count} runs, above --max-runs {args.max_runs}")
            jobs = []
            for task in tasks:
                repo = (root / task["repo"]).resolve()
                base = git(repo, "rev-parse", f"{task.get('revision', 'HEAD')}^{{commit}}").decode().strip()
                for variant in variants:
                    pack_name = variant.get("pack")
                    pack = pack_path(str(root / pack_name) if pack_name and (root / pack_name).exists() else pack_name)
                    policy = load_policy(args.config, pack, variant.get("policy"))
                    task_data = load_task(root / task["task"], pack)
                    context, pack_mcp = pack_context(pack)
                    mcp = mcp_config(variant.get("mcp", []), root / variant["mcp_config"] if variant.get("mcp_config") else None)
                    jobs.append((repo, task_data, policy, pack, mcp, base, variant["name"]))
            records = []
            randomizer = random.Random(suite.get("seed", 42))
            for repetition in range(repeats):
                randomizer.shuffle(jobs)
                for repo, task, policy, pack, mcp, base, label in jobs:
                    record = run(repo, task, policy, args.output, pack, mcp, revision=base, label=label,
                                 progress=lambda x: print(x, file=sys.stderr, flush=True))
                    records.append(record)
                    if record["status"] == "interrupted":
                        print(markdown(summarize(records)))
                        return 130
            summary = summarize(records)
            save(Path(args.output) / "summary.json", summary)
            print(markdown(summary))
            return 0 if all(r["status"] == "passed" for r in records) else 1
        if args.action == "report":
            summary = summarize(read_results(args.directory))
            print(json.dumps(summary, indent=2) if args.json else markdown(summary))
        elif args.action == "fixtures":
            print(create(args.destination))
        elif args.action == "demo":
            records = demo(args.output, args.live, args.model)
            print(markdown(summarize(records)))
            return 0 if all(r["status"] == "passed" for r in records) else 1
        elif args.action == "mcp":
            for name in args.names:
                print((ASSETS / "mcp" / f"{name}.toml").read_text())
        elif args.action == "pack":
            if args.pack_action == "list":
                packs = discover_packs(args.root)
                if args.json:
                    print(json.dumps(packs, indent=2))
                else:
                    for item in packs:
                        details = (f"skills={len(item['skills'])}, tools={','.join(item['mcp_servers']) or 'none'}"
                                   if item["available"] else item["error"])
                        print(f"{item['name']} [{item['source']}] {item['selector']} — {details}")
            elif args.pack_action == "inspect":
                print(json.dumps(inspect_pack(args.pack), indent=2))
            elif args.pack_action in ("suggest", "create"):
                if args.task and args.prompt:
                    raise ValueError("Choose a task file or --prompt, not both")
                task = read(args.task) if args.task else args.prompt
                if args.pack_action == "suggest":
                    if task is None:
                        raise ValueError("Supply a task file or --prompt")
                    result = suggest_packs(task, args.repo, args.root,
                                           read_results(args.from_runs) if args.from_runs else ())
                else:
                    result = create_pack(args.source, args.destination, name=args.name, task=task, repo=args.repo)
                print(json.dumps(result, indent=2))
            elif args.pack_action == "fork":
                source = pack_path(args.source)
                destination = Path(args.destination).resolve()
                if source == destination or source in destination.parents:
                    raise ValueError("Destination must be outside the source pack")
                copy_pack(source, destination)
                print(f"Reusable pack created at {destination}; edit pack.toml, instructions.md and skills.")
            elif args.pack_action == "learn":
                pack = pack_path(args.pack)
                if ASSETS.resolve() in pack.parents:
                    raise ValueError("Fork a bundled pack before saving evidence")
                result = read(args.from_result)
                directory = pack / "evidence"
                directory.mkdir(exist_ok=True)
                safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", result["id"])
                path = directory / f"{safe_id}.json"
                if path.exists():
                    raise ValueError("Evidence already exists")
                save(path, result)
                print(f"Evidence saved to {path}. Review it, propose one pack change, and compare on holdout tasks before promotion.")
            elif args.pack_action == "propose":
                policy = load_policy(args.config, overrides={"model": args.model})
                result = propose(pack_path(args.pack), args.destination, [read(p) for p in args.from_result],
                                 Path(args.repo).resolve(), policy, args.model)
                print(json.dumps(result, indent=2))
            elif args.pack_action == "promote":
                destination = promote(pack_path(args.candidate), args.registry,
                                      read_results(args.baseline_runs), read_results(args.candidate_runs),
                                      min_runs=args.min_runs, max_cost_ratio=args.max_cost_ratio, metric=args.cost_metric,
                                      min_pass_rate=args.min_pass_rate)
                print(f"Promoted immutable local release: {destination}")
            elif args.pack_action == "rollback":
                print(rollback(args.registry))
            elif args.pack_action == "register":
                print(register(pack_path(args.pack), args.registry))
            elif args.pack_action == "optimize":
                from .optimize import optimize
                result = optimize(pack_path(args.pack), [read(p) for p in args.from_result], args.holdout,
                                  args.repo, args.registry, args.output, config=args.config, model=args.model,
                                  max_runs=args.max_runs, min_runs=args.min_runs, min_distinct_tasks=args.min_distinct_tasks,
                                  max_cost_ratio=args.max_cost_ratio, cost_metric=args.cost_metric,
                                  min_pass_rate=args.min_pass_rate, max_total_tokens=args.max_total_tokens,
                                  max_total_cost_usd=args.max_total_cost_usd,
                                  progress=lambda x: print(x, file=sys.stderr, flush=True))
                print(json.dumps(result, indent=2))
                return 0 if result["status"] == "promoted" else (130 if result["status"] == "interrupted" else 1)
        return 0
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
