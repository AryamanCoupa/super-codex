import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_harness.research import resolve_research


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="supercodex research ")
        self.home = Path(self.temp.name)
        self.default = self.home / ".config/super-codex/research.toml"
        self.native = self.home / ".codex/config.toml"
        self.environment = patch.dict(os.environ, {}, clear=False)
        self.environment.start()
        os.environ.pop("CODEX_HOME", None)

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def json_config(self, value):
        return self.write(self.home / "research.json", json.dumps(value))

    def test_no_default_file_does_not_import_or_even_read_native_configuration(self):
        self.write(self.native, 'model = "private-model"\n[mcp_servers.unselected]\nurl = "https://example.invalid/mcp"\n')
        with patch("codex_harness.research._configuration") as read_configuration:
            self.assertEqual(resolve_research([], home=self.home), {})
        read_configuration.assert_not_called()
        self.assertFalse(self.default.exists())

    def test_default_file_selects_one_existing_connection_and_overrides_tool_allowlist(self):
        self.write(self.default, '[existing_mcp_servers.catalog]\nenabled_tools = ["search_repositories"]\n')
        self.write(self.native, '''model = "unrelated-model"
[mcp_servers.catalog]
url = "https://example.invalid/mcp"
bearer_token_env_var = "EXAMPLE_MCP_TOKEN"
enabled_tools = ["search_repositories", "create_repository"]
required = true
[mcp_servers.unselected]
command = "unselected-server"
''')
        before = {p: p.read_bytes() for p in (self.default, self.native)}
        result = resolve_research([], home=self.home)
        self.assertEqual(set(result), {"catalog"})
        self.assertEqual(result["catalog"]["enabled_tools"], ["search_repositories"])
        self.assertEqual(result["catalog"]["bearer_token_env_var"], "EXAMPLE_MCP_TOKEN")
        self.assertTrue(result["catalog"]["required"])
        self.assertEqual({p: p.read_bytes() for p in before}, before)
        result["catalog"]["enabled_tools"].append("local-mutation")
        self.assertEqual(resolve_research([], home=self.home)["catalog"]["enabled_tools"], ["search_repositories"])

    def test_codex_home_override_is_used_only_for_named_connection_references(self):
        external = self.home / "alternate codex"
        self.write(external / "config.toml", '[mcp_servers.docs]\ncommand = "docs-server"\n')
        self.write(self.native, "this config is deliberately invalid")
        self.write(self.default, '[existing_mcp_servers.docs]\nenabled_tools = ["fetch"]\n')
        with patch.dict(os.environ, {"CODEX_HOME": str(external)}):
            result = resolve_research([], home=self.home)
        self.assertEqual(result, {"docs": {"command": "docs-server", "enabled_tools": ["fetch"]}})

    def test_default_uses_xdg_config_home_but_explicit_home_is_hermetic(self):
        xdg = self.home / "user settings"
        self.write(xdg / "super-codex/research.toml", '[mcp_servers.xdg]\ncommand = "xdg-server"\nenabled_tools = ["search"]\n')
        self.write(self.default, '[mcp_servers.home]\ncommand = "home-server"\nenabled_tools = ["fetch"]\n')
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(xdg)}), patch("codex_harness.research.Path.home", return_value=self.home):
            self.assertEqual(set(resolve_research([])), {"xdg"})
            self.assertEqual(set(resolve_research([], home=self.home)), {"home"})

    def test_explicit_file_replaces_default_selection_and_presets_override_same_named_server(self):
        self.write(self.default, "broken default configuration")
        config = self.json_config({"mcp_servers": {
            "github": {"url": "https://example.invalid/private", "http_headers": {"Authorization": "private-example-value"}, "enabled_tools": ["custom_search"]},
            "docs": {"command": "docs-server", "enabled_tools": ["fetch"]},
        }})
        result = resolve_research(["github"], str(config), home=self.home)
        self.assertEqual(set(result), {"github", "docs"})
        self.assertEqual(result["github"]["url"], "https://api.githubcopilot.com/mcp/readonly")
        self.assertIn("search_repositories", result["github"]["enabled_tools"])
        self.assertNotIn("http_headers", result["github"])
        self.assertEqual(result["docs"]["enabled_tools"], ["fetch"])

    def test_custom_and_referenced_servers_require_nonempty_tool_allowlists(self):
        for section in ("mcp_servers", "existing_mcp_servers"):
            for tools in (None, [], "fetch", [""], [False], ["fetch", 4]):
                with self.subTest(section=section, tools=tools):
                    server = {} if tools is None else {"enabled_tools": tools}
                    config = self.json_config({section: {"docs": server}})
                    with self.assertRaisesRegex(ValueError, "nonempty enabled_tools"):
                        resolve_research([], config, home=self.home)

    def test_named_presets_are_explicit_and_unknown_presets_fail_without_file_access(self):
        result = resolve_research(["github", "atlassian", "openai-docs", "playwright"], home=self.home)
        self.assertEqual(set(result), {"github", "atlassian", "openai_docs", "playwright"})
        self.assertFalse(self.default.exists())
        for names in (["unknown"], ["../github"], "github", [None]):
            with self.subTest(names=names), self.assertRaisesRegex(ValueError, "Research MCP presets"):
                resolve_research(names, home=self.home)

    def test_missing_configuration_or_reference_has_clear_redacted_error(self):
        with self.assertRaisesRegex(ValueError, "Research configuration file was not found"):
            resolve_research([], self.home / "missing.toml", home=self.home)
        self.write(self.default, '[existing_mcp_servers.missing]\nenabled_tools = ["search"]\n')
        self.write(self.native, '[mcp_servers.present]\nurl = "https://example.invalid/private-token-value"\n')
        with self.assertRaisesRegex(ValueError, "not found in Codex configuration") as caught:
            resolve_research([], home=self.home)
        self.assertNotIn("private-token-value", str(caught.exception))

    def test_parse_and_validation_errors_do_not_echo_private_values(self):
        private = "private-header-example-value"
        cases = (
            {"mcp_servers": {"docs": {"url": "https://example.invalid", "http_headers": {"Authorization": private}, "enabled_tools": []}}},
            {"mcp_servers": private},
            {"unexpected": private},
            {"existing_mcp_servers": {"docs": {"enabled_tools": ["read"], "url": private}}},
        )
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(ValueError) as caught:
                    resolve_research([], self.json_config(value), home=self.home)
                self.assertNotIn(private, str(caught.exception))
        invalid = self.write(self.home / "invalid.toml", f'[mcp_servers.docs]\nurl = "{private}')
        with self.assertRaisesRegex(ValueError, "JSON/TOML syntax") as caught:
            resolve_research([], invalid, home=self.home)
        self.assertNotIn(private, str(caught.exception))

    def test_conflicting_connection_sources_are_rejected(self):
        config = self.json_config({
            "mcp_servers": {"docs": {"command": "docs", "enabled_tools": ["fetch"]}},
            "existing_mcp_servers": {"docs": {"enabled_tools": ["fetch"]}},
        })
        with self.assertRaisesRegex(ValueError, "both directly configured"):
            resolve_research([], config, home=self.home)

    def test_explicit_tool_override_is_scoped_and_never_changes_native_configuration(self):
        self.write(self.native, '[mcp_servers.docs]\nurl="https://example.invalid/mcp"\n[mcp_servers.docs.tools.fetch]\napproval_mode="prompt"\noutput_token_limit=1000\n[mcp_servers.docs.tools.edit]\napproval_mode="prompt"\n')
        original = self.native.read_bytes()
        config = self.json_config({"existing_mcp_servers": {"docs": {
            "enabled_tools": ["fetch"], "tools": {"fetch": {"approval_mode": "approve"}}}}})
        server = resolve_research([], config, home=self.home)["docs"]
        self.assertEqual(server["tools"]["fetch"], {"approval_mode": "approve", "output_token_limit": 1000})
        self.assertEqual(server["tools"]["edit"]["approval_mode"], "prompt")
        self.assertEqual(self.native.read_bytes(), original)
        for overrides in ({"edit": {"approval_mode": "approve"}}, {"fetch": {"approval_mode": "unknown"}}, {"fetch": {"enabled": True}}):
            config = self.json_config({"existing_mcp_servers": {"docs": {"enabled_tools": ["fetch"], "tools": overrides}}})
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                resolve_research([], config, home=self.home)


if __name__ == "__main__":
    unittest.main()
