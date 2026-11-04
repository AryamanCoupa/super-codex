"""Resolve explicitly selected research connections without inheriting Codex settings.

The optional user file stores connection definitions or references to named Codex
connections. Referencing a connection reads it into memory; credentials and other
Codex configuration are never copied to a file by this module. Tool-name filters
limit exposure but cannot make a multiplexed read/write tool read-only. Remote
permissions remain the responsibility of the selected server and its credentials.
"""

import copy
import os
from pathlib import Path

from .config import ASSETS, read


PRESETS = ("github", "atlassian", "openai-docs", "playwright")


def _configuration(path, label):
    try:
        value = read(path)
    except FileNotFoundError:
        raise ValueError(f"{label} file was not found; select an existing JSON/TOML file") from None
    except (OSError, ValueError):
        # Parser/OS errors must not echo URLs, headers, or arbitrary private values.
        raise ValueError(f"Could not read {label.lower()}; check permissions and JSON/TOML syntax") from None
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain an object/table")
    return value


def _servers(configuration, key):
    value = configuration.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"Research {key} must be a table of named servers")
    if any(not isinstance(name, str) or not name.strip() for name in value):
        raise ValueError("Research MCP server names must be nonempty strings")
    return value


def _tools(server):
    if not isinstance(server, dict):
        raise ValueError("Each research MCP server must be an object/table")
    value = server.get("enabled_tools")
    if (not isinstance(value, list) or not value
            or any(not isinstance(tool, str) or not tool.strip() for tool in value)):
        raise ValueError("Custom and existing research MCP servers require a nonempty enabled_tools array of tool names")
    return copy.deepcopy(value)


def _tool_overrides(reference):
    overrides = reference.get("tools", {})
    if not isinstance(overrides, dict) or set(overrides) - set(reference["enabled_tools"]):
        raise ValueError("Research tool overrides must name only explicitly enabled tools")
    for settings in overrides.values():
        if (not isinstance(settings, dict) or set(settings) != {"approval_mode"}
                or settings["approval_mode"] not in ("auto", "prompt", "writes", "approve")):
            raise ValueError("Research tool overrides support only a valid Codex approval_mode")
    return copy.deepcopy(overrides)


def resolve_research(names, config_path=None, *, home=None):
    """Return only opted-in research MCP servers, with CLI presets taking precedence.

    Without an explicit path, an existing ``~/.config/super-codex/research.toml``
    supplies the opt-in selection (respecting ``XDG_CONFIG_HOME`` unless a test
    home is supplied explicitly). Named references are resolved from
    ``$CODEX_HOME/config.toml`` or ``~/.codex/config.toml``. Missing default
    research configuration means no custom connections and does not read Codex
    configuration. Bundled presets are selected explicitly through ``names``.
    """
    if not isinstance(names, list) or any(name not in PRESETS for name in names):
        raise ValueError("Research MCP presets must be a list selected from github, atlassian, openai-docs, playwright")
    user_home = Path(home) if home is not None else Path.home()
    config_root = user_home / ".config"
    if home is None and os.environ.get("XDG_CONFIG_HOME"):
        config_root = Path(os.environ["XDG_CONFIG_HOME"]).expanduser()
    path = Path(config_path).expanduser() if config_path is not None else config_root / "super-codex/research.toml"
    configuration = _configuration(path, "Research configuration") if config_path is not None or path.exists() else {}
    if set(configuration) - {"mcp_servers", "existing_mcp_servers"}:
        raise ValueError("Research configuration supports only mcp_servers and existing_mcp_servers tables")
    direct = _servers(configuration, "mcp_servers")
    references = _servers(configuration, "existing_mcp_servers")
    if direct.keys() & references.keys():
        raise ValueError("A research MCP server cannot be both directly configured and an existing connection reference")
    result = {}
    for name, server in direct.items():
        _tools(server)
        result[name] = copy.deepcopy(server)
    if references:
        for reference in references.values():
            _tools(reference)
            if set(reference) - {"enabled_tools", "tools"}:
                raise ValueError("Existing research MCP references support only enabled_tools and per-tool overrides")
            _tool_overrides(reference)
        codex_home = Path(os.environ["CODEX_HOME"]).expanduser() if os.environ.get("CODEX_HOME") else user_home / ".codex"
        native = _configuration(codex_home / "config.toml", "Codex configuration")
        native_servers = native.get("mcp_servers", {})
        if not isinstance(native_servers, dict):
            raise ValueError("Codex mcp_servers must be a table of named servers")
        for name, reference in references.items():
            server = native_servers.get(name)
            if not isinstance(server, dict):
                raise ValueError("A referenced research MCP server was not found in Codex configuration; check its name")
            result[name] = copy.deepcopy(server)
            result[name]["enabled_tools"] = _tools(reference)
            overrides = _tool_overrides(reference)
            if overrides:
                settings = result[name].setdefault("tools", {})
                if not isinstance(settings, dict):
                    raise ValueError("Existing Codex per-tool configuration must be a table")
                for tool, override in overrides.items():
                    settings[tool] = {**settings.get(tool, {}), **override}
    # Bundled server definitions are deliberate selections; keep their authored
    # endpoint/tool settings instead of retaining private same-named credentials.
    for name in names:
        result.update(copy.deepcopy(read(ASSETS / "mcp" / f"{name}.toml")["mcp_servers"]))
    return result
