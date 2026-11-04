"""One accounted harness request from an exact user message."""

from pathlib import Path


MAX_PROMPT_BYTES = 1_000_000
MAX_CONTEXT_BYTES = 64_000


def register_parser(subparsers):
    parser = subparsers.add_parser(
        "answer", help="Answer one user message through SuperCodex, including research or coding")
    message = parser.add_mutually_exclusive_group(required=True)
    message.add_argument("prompt", nargs="?", help="Exact user message, quoted as one argument")
    message.add_argument("--prompt-file", help="UTF-8 file containing the exact user message")
    parser.add_argument("--context-file", help="Optional UTF-8 conversation context (maximum 64,000 bytes)")
    parser.add_argument("--repo", "-C", default=".", help="Working project directory; defaults to current directory")
    parser.add_argument("--config", help="Worker policy override; otherwise use selected pack policy or balanced")
    parser.add_argument("--pack", help="Dedicated task pack or registry")
    parser.add_argument("--model", "-m", help="Override the worker and default preparation model")
    parser.add_argument("--operator-model", help="Override only the read-only preparation model")
    parser.add_argument("--mcp", action="append", default=[], help="Worker MCP preset; repeatable")
    parser.add_argument("--mcp-config", help="Additional worker MCP JSON/TOML configuration")
    parser.add_argument("--research-mcp", action="append", default=[], help="Preparation-only MCP preset; repeatable")
    parser.add_argument("--research-mcp-config", help="Private preparation-only MCP JSON/TOML configuration")
    parser.add_argument("--output-root", help="Session/artifact root; defaults to the private user state directory")
    parser.add_argument("--patch-only", action="store_true", help="Keep a verified coding patch for review without applying it")
    parser.add_argument("--dry-run", action="store_true", help="Preview the request setup without writing files or invoking a model")
    # This command is noninteractive by design, even when called from the native
    # Codex TUI. Exec preserves existing login/MCP credential compatibility.
    parser.set_defaults(answer_mode=True, answer_context=None, managed=True,
                        no_stream=True, native=False, task=None, no_alt_screen=False)


def _validate(text, label, maximum):
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"{label} must not be empty")
    if "\0" in text:
        raise ValueError(f"{label} must not contain NUL characters")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeError:
        raise ValueError(f"{label} must contain valid UTF-8 text") from None
    if size > maximum:
        raise ValueError(f"{label} exceeds the {maximum:,}-byte limit")
    return text


def _read_text(path, label, maximum):
    try:
        source = Path(path).expanduser()
        if not source.is_file():
            raise ValueError(f"{label} must name an existing regular file")
        with source.open("rb") as stream:
            data = stream.read(maximum + 1)
    except OSError:
        raise ValueError(f"Could not read {label.lower()}; check the file path and permissions") from None
    if len(data) > maximum:
        raise ValueError(f"{label} exceeds the {maximum:,}-byte limit")
    try:
        text = data.decode("utf-8")
    except UnicodeError:
        raise ValueError(f"{label} must contain valid UTF-8 text") from None
    return _validate(text, label, maximum)


def handle(args):
    """Validate inputs before handing the exact request to the managed controller."""
    if args.prompt_file is not None:
        if args.prompt is not None:
            raise ValueError("Use either a quoted prompt or --prompt-file, not both")
        prompt = _read_text(args.prompt_file, "Prompt file", MAX_PROMPT_BYTES)
    else:
        prompt = _validate(args.prompt, "Prompt", MAX_PROMPT_BYTES)
    context = (_read_text(args.context_file, "Context file", MAX_CONTEXT_BYTES)
               if args.context_file is not None else None)
    args.prompt = prompt
    args.answer_context = context
    from .controller import handle as controlled_handle

    return controlled_handle(args)
