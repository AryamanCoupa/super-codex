import json
import os
import stat
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_harness.codex_home import isolated_codex_home


class IsolatedCodexHomeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.native = self.root / 'native'
        self.native.mkdir()
        self.environment = patch.dict(os.environ, {
            'HOME': str(self.root), 'CODEX_HOME': str(self.native),
            'PROVIDER_KEY': 'fixture-provider-key',
        }, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.original = {
            'auth_mode': 'chatgpt', 'OPENAI_API_KEY': None,
            'tokens': {'access_token': 'fixture-access', 'id_token': 'fixture-identity',
                       'account_id': 'fixture-account', 'refresh_token': 'fixture-refresh'},
            'last_refresh': '2026-01-01T00:00:00Z',
        }
        (self.native / 'auth.json').write_text(json.dumps(self.original))

    def test_private_snapshot_strips_refresh_and_does_not_import_user_configuration(self):
        (self.native / 'config.toml').write_text('''
model = "ignored-model"
developer_instructions = "ignored instructions"
[hooks]
command = "ignored-command"
[mcp_servers.ignored]
command = "ignored-server"
[plugins.ignored]
enabled = true
''')
        (self.native / 'AGENTS.md').write_text('ignored instructions')
        (self.native / 'skills').mkdir()
        before = (self.native / 'auth.json').read_bytes()
        with isolated_codex_home({}) as env:
            home = Path(env['CODEX_HOME'])
            self.assertNotEqual(home, self.native)
            self.assertEqual(stat.S_IMODE(home.stat().st_mode), 0o700)
            self.assertEqual(env['SUPERCODEX_WORKER'], '1')
            self.assertEqual(env['PROVIDER_KEY'], 'fixture-provider-key')
            self.assertEqual({path.name for path in home.iterdir()}, {'auth.json', 'config.toml'})
            for path in home.iterdir():
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            auth = json.loads((home / 'auth.json').read_text())
            expected = json.loads(before)
            expected['tokens']['refresh_token'] = ''
            self.assertEqual(auth, expected)
            config = tomllib.loads((home / 'config.toml').read_text())
            self.assertEqual(config, {'model_provider': 'openai',
                                      'cli_auth_credentials_store': 'file',
                                      'mcp_oauth_credentials_store': 'file'})
            (home / 'auth.json').write_text('child changed temporary login')
        self.assertFalse(home.exists())
        self.assertEqual((self.native / 'auth.json').read_bytes(), before)
        self.assertEqual(os.environ['CODEX_HOME'], str(self.native))

    def test_temporary_credentials_are_removed_on_interruption(self):
        home = None
        with self.assertRaises(KeyboardInterrupt):
            with isolated_codex_home({}) as env:
                home = Path(env['CODEX_HOME'])
                raise KeyboardInterrupt()
        self.assertFalse(home.exists())

    def test_home_fallback_and_api_key_environment(self):
        (self.root / '.codex').mkdir()
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'fixture-api-key'}):
            os.environ.pop('CODEX_HOME')
            with isolated_codex_home({}) as env:
                home = Path(env['CODEX_HOME'])
                auth = json.loads((home / 'auth.json').read_text())
                self.assertEqual(auth, {'OPENAI_API_KEY': 'fixture-api-key'})
                self.assertEqual(env['OPENAI_API_KEY'], 'fixture-api-key')

    def test_missing_or_keyring_only_auth_has_actionable_error(self):
        (self.native / 'auth.json').unlink()
        with self.assertRaisesRegex(ValueError, 'run codex login'):
            with isolated_codex_home({}):
                self.fail('Missing login must not launch a child')
        (self.native / 'config.toml').write_text('cli_auth_credentials_store = "keyring"\n')
        with self.assertRaisesRegex(ValueError, 'keyring.*OPENAI_API_KEY'):
            with isolated_codex_home({}):
                self.fail('Keyring-only login must not silently lose credentials')

    def test_local_provider_does_not_require_or_copy_login(self):
        (self.native / 'auth.json').unlink()
        with isolated_codex_home({'local_provider': 'ollama'}) as env:
            home = Path(env['CODEX_HOME'])
            self.assertFalse((home / 'auth.json').exists())
            self.assertEqual(tomllib.loads((home / 'config.toml').read_text())['model_provider'], 'ollama')

    def test_api_key_environment_bypasses_unreadable_native_login(self):
        (self.native / 'auth.json').write_text('malformed native login')
        (self.native / 'config.toml').write_text('cli_auth_credentials_store = "keyring"\n')
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'fixture-api-key'}):
            with isolated_codex_home({}) as env:
                auth = json.loads((Path(env['CODEX_HOME']) / 'auth.json').read_text())
                self.assertEqual(auth, {'OPENAI_API_KEY': 'fixture-api-key'})

    def test_explicit_builtin_provider_override_is_preserved(self):
        provider = {'name': 'Local service', 'base_url': 'http://localhost:11435/v1'}
        with isolated_codex_home({'local_provider': 'ollama',
                                  'model_providers': {'ollama': provider}}) as env:
            config = tomllib.loads((Path(env['CODEX_HOME']) / 'config.toml').read_text())
            self.assertEqual(config['model_providers'], {'ollama': provider})

    def test_only_explicit_custom_provider_definition_is_imported(self):
        (self.native / 'config.toml').write_text('''
model_provider = "ignored"
[model_providers.selected]
name = "Selected provider"
base_url = "https://example.invalid/v1"
env_key = "PROVIDER_KEY"
wire_api = "responses"
[model_providers.ignored]
name = "Other provider"
base_url = "https://unused.invalid"
[mcp_servers.ignored]
command = "ignored-server"
''')
        with isolated_codex_home({'model_provider': 'selected'}) as env:
            home = Path(env['CODEX_HOME'])
            config = tomllib.loads((home / 'config.toml').read_text())
            self.assertEqual(config['model_provider'], 'selected')
            self.assertEqual(set(config['model_providers']), {'selected'})
            self.assertNotIn('mcp_servers', config)
            self.assertFalse((home / 'auth.json').exists())
            self.assertEqual(env['PROVIDER_KEY'], 'fixture-provider-key')
        with self.assertRaisesRegex(ValueError, 'unsupported authentication'):
            with isolated_codex_home({'model_provider': 'selected', 'model_providers': {
                    'selected': {'name': 'Unsupported', 'aws': {'credential_export': {'command': 'ignored'}}}}}):
                self.fail('Executable authentication config must not be imported')

    def test_selected_mcp_oauth_requires_explicit_supported_authentication(self):
        selected = {'docs': {'url': 'https://example.invalid/mcp'}}
        (self.native / '.credentials.json').write_text(json.dumps({
            'opaque-home-bound-key': {'server_name': 'docs', 'url': 'https://example.invalid/mcp',
                                     'token_response': {'access_token': 'fixture-mcp-token'}}}))
        with self.assertRaisesRegex(ValueError, 'bearer_token_env_var'):
            with isolated_codex_home({}, selected):
                self.fail('Home-bound MCP OAuth must not silently fail')
        selected['docs']['bearer_token_env_var'] = 'PROVIDER_KEY'
        with isolated_codex_home({}, selected) as env:
            self.assertFalse((Path(env['CODEX_HOME']) / '.credentials.json').exists())
        (self.native / '.credentials.json').unlink()
        with isolated_codex_home({}, {'docs': {'url': 'https://example.invalid/public'}}):
            pass
        with self.assertRaisesRegex(ValueError, 'MCP OAuth'):
            with isolated_codex_home({}, {'docs': {'url': 'https://example.invalid/mcp', 'oauth': {}}}):
                self.fail('Explicit OAuth must not be imported')

    def test_parse_errors_do_not_include_secret_file_contents(self):
        (self.native / 'auth.json').write_text('{"token": fixture-secret-invalid-json}')
        with self.assertRaises(ValueError) as raised:
            with isolated_codex_home({}):
                self.fail('Malformed auth must be rejected')
        self.assertNotIn('fixture-secret', str(raised.exception))


if __name__ == '__main__':
    unittest.main()
