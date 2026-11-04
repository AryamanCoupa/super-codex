"""Command discovery derived from the same parser that executes commands."""

import argparse

from . import __version__


def _children(parser):
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            summaries = {choice.dest: choice.help for choice in action._choices_actions}
            for name, child in action.choices.items():
                yield name, child, summaries.get(name) or child.description or ""


def _select(parser, path):
    description = parser.description or ""
    for component in path:
        children = {name: (child, summary) for name, child, summary in _children(parser)}
        if component not in children:
            raise ValueError(f"Unknown command path: {' '.join(path)}; use commands to list available commands")
        parser, description = children[component]
    return parser, description


def _argument(action):
    item = {"name": action.dest, "flags": list(action.option_strings),
            "required": action.required, "nargs": action.nargs,
            "description": action.help or ""}
    if action.default != argparse.SUPPRESS:
        item["default"] = action.default
    if action.choices is not None:
        item["choices"] = list(action.choices)
    if action.type is not None:
        item["type"] = getattr(action.type, "__name__", str(action.type))
    if isinstance(action, argparse._AppendAction):
        item["repeatable"] = True
    return item


def catalog(parser, path=()):
    """Return JSON-compatible leaf commands and arguments for a command subtree.

    No command is executed. This uses argparse's action metadata so added
    subcommands automatically become discoverable without a parallel registry.
    """
    path = tuple(path)
    selected, description = _select(parser, path)
    commands, groups = [], []

    def visit(current, components, summary):
        children = list(_children(current))
        item = {"path": list(components), "command": " ".join((parser.prog, *components)),
                "description": summary, "usage": current.format_usage().strip()}
        if children:
            item["subcommands"] = [name for name, _, _ in children]
            groups.append(item)
            for name, child, child_summary in children:
                visit(child, (*components, name), child_summary)
        else:
            item["arguments"] = [_argument(action) for action in current._actions
                                 if action.help != argparse.SUPPRESS]
            commands.append(item)

    visit(selected, path, description)
    return {"schema_version": 1, "version": __version__, "program": parser.prog,
            "scope": list(path), "groups": groups, "commands": commands,
            "note": "Discovery only; execution may invoke models, consume usage or write local artifacts. Read command help before running."}


def render_catalog(parser, path=()):
    selected, _ = _select(parser, tuple(path))
    if not list(_children(selected)):
        return selected.format_help().rstrip()
    inventory = catalog(parser, path)
    lines = [f"SuperCodex {__version__} — installed commands"]
    for command in inventory["commands"]:
        summary = f" — {command['description']}" if command["description"] else ""
        lines.append(command["command"] + summary)
    lines.append("Inspect arguments: super-codex commands <command path> --json, or <command path> --help")
    return "\n".join(lines)
