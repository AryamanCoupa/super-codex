"""Temporary Codex authentication homes without inherited tools or instructions."""

import json
import os
import tempfile
import tomllib
from contextlib import contextmanager
from pathlib import Path

from .agent_tools import worker_environment
from .config import toml_value


_PROVIDER_FIELDS = {
    "name", "base_url", "env_key", "env_key_instructions",
    "experimental_bearer_token", "wire_api", "query_params", "http_headers",
    "env_http_headers", "request_max_retries", "stream_max_retries",
    "stream_idle_timeout_ms", "websocket_connect_timeout_ms",
    "requires_openai_auth", "supports_websockets", "supports_standalone_web_search",
}


def _read_config(home):
    try:
        with (home / "config.toml").open("rb") as source:
            return tomllib.load(source)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        # Parser errors may include the offending line, potentially a secret.
        raise ValueError("Cannot read Codex config.toml; repair its TOML syntax or file permissions.") from None


def _provider_config(policy, native):
    selected = policy.get("model_provider") or policy.get("local_provider") or "openai"
    if not isinstance(selected, str) or not selected:
        raise ValueError("model_provider must name a Codex model provider.")
    definitions = policy.get("model_providers", {})
    if not isinstance(definitions, dict):
        raise ValueError("model_providers must be a table of provider definitions.")
    native_definitions = native.get("model_providers", {})
    if not isinstance(native_definitions, dict):
        raise ValueError("Codex model_providers configuration must be a table.")
    provider = definitions.get(selected)
    if provider is None and (policy.get("model_provider") or selected not in {"openai", "ollama", "lmstudio"}):
        provider = native_definitions.get(selected)
    if provider is None and selected in {"openai", "ollama", "lmstudio"}:
        return {"model_provider": selected}, selected == "openai"
    if not isinstance(provider, dict):
        raise ValueError("Selected model provider needs a model_providers definition in the policy or Codex config.")
    if set(provider) - _PROVIDER_FIELDS:
        raise ValueError("Selected provider uses unsupported authentication or settings for isolated streaming; "
                         "use an env_key/HTTP-header provider or the exec transport.")
    requires_login = provider.get("requires_openai_auth", selected == "openai")
    if not isinstance(requires_login, bool):
        raise ValueError("Provider requires_openai_auth must be a boolean.")
    return {"model_provider": selected, "model_providers": {selected: provider}}, requires_login


def _check_mcp_oauth(home, mcp):
    remote = {name: config for name, config in (mcp or {}).items()
              if isinstance(config, dict) and config.get("url")
              and not (config.get("bearer_token_env_var") or config.get("http_headers")
                       or config.get("env_http_headers"))}
    if not remote:
        return
    error = ("Selected MCP OAuth credentials cannot be reused in an isolated streaming home; "
             "configure bearer_token_env_var or env_http_headers for that connection, "
             "or use the exec transport with the existing Codex login.")
    if any(config.get("oauth") is not None for config in remote.values()):
        raise ValueError(error)
    try:
        with (home / ".credentials.json").open() as source:
            credentials = json.load(source)
    except FileNotFoundError:
        return  # Public HTTP servers do not necessarily require authentication.
    except (OSError, ValueError):
        raise ValueError("Cannot inspect the Codex MCP OAuth store; use explicit environment authentication.") from None
    if not isinstance(credentials, dict):
        raise ValueError("Unsupported Codex MCP OAuth store format; use explicit environment authentication.")
    for record in credentials.values():
        if not isinstance(record, dict):
            raise ValueError("Unsupported Codex MCP OAuth store format; use explicit environment authentication.")
        if record.get("server_name") in remote or any(
                record.get("url", record.get("server_url")) == server["url"]
                for server in remote.values()):
            raise ValueError(error)


def _private_write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as target:
        target.write(data)


@contextmanager
def isolated_codex_home(policy, mcp=None):
    """Yield a complete worker environment with a disposable, private CODEX_HOME.

    Only file login credentials and the explicitly selected provider definition
    are copied. User hooks, tools, skills, instructions, plugins and profiles are
    never imported. Keyring-only login and existing MCP OAuth stores are unsupported;
    environment credentials remain available. ChatGPT snapshots preserve access
    and identity tokens but blank the refresh token, so the child cannot rotate
    the native login's refresh token. Existing timestamps are preserved. Expired
    or stale logins require renewing normal Codex authentication or using the
    exec transport. The source home is never changed.
    """
    env = worker_environment()
    source = Path(env["CODEX_HOME"]).expanduser() if env.get("CODEX_HOME") else Path.home() / ".codex"
    native = _read_config(source)
    config, requires_login = _provider_config(policy, native)
    _check_mcp_oauth(source, mcp)
    config.update(cli_auth_credentials_store="file", mcp_oauth_credentials_store="file")
    api_key = env.get("OPENAI_API_KEY") if requires_login else None
    auth = None
    if requires_login:
        storage = native.get("cli_auth_credentials_store", "file")
        if storage == "keyring" and not api_key:
            raise ValueError("Codex keyring login cannot be copied to an isolated streaming home; "
                             "use OPENAI_API_KEY, run codex -c 'cli_auth_credentials_store=\"file\"' login, "
                             "or select the exec transport.")
        stored = {}
        if not api_key:
            try:
                with (source / "auth.json").open() as source_file:
                    stored = json.load(source_file)
            except FileNotFoundError:
                pass
            except (OSError, ValueError):
                raise ValueError("Cannot read Codex auth.json; repair its format or file permissions, "
                                 "or use OPENAI_API_KEY.") from None
        if not isinstance(stored, dict):
            raise ValueError("Unsupported Codex auth.json format; run codex login again.")
        if api_key:
            auth = {"OPENAI_API_KEY": api_key}
        elif isinstance(stored.get("OPENAI_API_KEY"), str) and stored["OPENAI_API_KEY"]:
            auth = {"OPENAI_API_KEY": stored["OPENAI_API_KEY"]}
        elif isinstance(stored.get("tokens"), dict):
            tokens = stored["tokens"]
            access = tokens.get("access_token")
            if not isinstance(access, str) or not access:
                raise ValueError("Codex login lacks an access token; run codex login again "
                                 "or use OPENAI_API_KEY.")
            auth = {key: stored[key] for key in ("auth_mode", "OPENAI_API_KEY", "last_refresh")
                    if key in stored}
            auth["tokens"] = {key: tokens[key] for key in ("access_token", "id_token", "account_id")
                              if key in tokens}
            auth["tokens"]["refresh_token"] = ""
        if auth is None:
            raise ValueError("Codex login is unavailable for isolated streaming; run codex login with "
                             "cli_auth_credentials_store=\"file\", set OPENAI_API_KEY, "
                             "or use the exec transport for a keyring login.")
    with tempfile.TemporaryDirectory(prefix="supercodex-auth-") as temporary:
        home = Path(temporary)
        home.chmod(0o700)
        if auth is not None:
            _private_write(home / "auth.json", json.dumps(auth).encode())
        content = "".join(f"{key} = {toml_value(value)}\n" for key, value in config.items())
        _private_write(home / "config.toml", content.encode())
        env["CODEX_HOME"] = str(home)
        yield env
