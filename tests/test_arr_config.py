"""
Unit tests for nas/setup-arr-config.py

Each test class is named after the bug it guards against so failures
immediately point to the relevant fix.
"""

import io
import json
import os
import tempfile
import unittest
import unittest.mock as mock
from urllib.error import HTTPError, URLError
from urllib.request import Request

from conftest import load_module

arr = load_module('arr_config', 'setup-arr-config.py')


# ── read_env ──────────────────────────────────────────────────────────────────

class TestReadEnv(unittest.TestCase):
    """read_env() must handle all common .env edge cases."""

    def _write_env(self, content):
        f = tempfile.NamedTemporaryFile('w', suffix='.env', delete=False)
        f.write(content)
        f.close()
        return f.name

    def test_basic_key_value(self):
        path = self._write_env('FOO=bar\n')
        self.assertEqual(arr.read_env(path), {'FOO': 'bar'})

    def test_strips_inline_comment(self):
        """Values like KEY=value  # comment must strip the comment."""
        path = self._write_env('KEY=hello  # this is a comment\n')
        self.assertEqual(arr.read_env(path)['KEY'], 'hello')

    def test_value_with_equals_sign(self):
        """Values containing = (e.g. base64 WireGuard keys) must not be truncated."""
        path = self._write_env('WG_KEY=abc123==\n')
        self.assertEqual(arr.read_env(path)['WG_KEY'], 'abc123==')

    def test_skips_blank_lines_and_comments(self):
        path = self._write_env('# comment\n\nFOO=bar\n')
        self.assertEqual(arr.read_env(path), {'FOO': 'bar'})

    def test_skips_empty_values(self):
        """Keys with no value (KEY=) must not appear in the result."""
        path = self._write_env('EMPTY=\nSET=yes\n')
        result = arr.read_env(path)
        self.assertNotIn('EMPTY', result)
        self.assertEqual(result['SET'], 'yes')

    def test_missing_file_returns_empty_dict(self):
        self.assertEqual(arr.read_env('/nonexistent/.env'), {})


# ── read_bazarr_key ───────────────────────────────────────────────────────────

class TestReadBazarrKey(unittest.TestCase):
    """read_bazarr_key() must find the API key across config file variants."""

    def test_finds_key_in_yaml_format(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, 'config'))
            with open(os.path.join(d, 'config', 'config.yaml'), 'w') as f:
                f.write('general:\n  apikey: abc123xyz\n')
            key = arr.read_bazarr_key(d)
            self.assertEqual(key, 'abc123xyz')

    def test_finds_key_in_ini_format(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, 'config.ini'), 'w') as f:
                f.write('[general]\napikey = myapikey\n')
            key = arr.read_bazarr_key(d)
            self.assertEqual(key, 'myapikey')

    def test_returns_none_when_not_found(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(arr.read_bazarr_key(d))


# ── Bug #3: bazarr_get/bazarr_post must not crash on HTTP errors ──────────────

class TestBazarrHelpersSwallowHTTPErrors(unittest.TestCase):
    """
    Regression: bazarr_get and bazarr_post previously used _request() which
    re-raises HTTPError, crashing the entire script on any Bazarr API error.
    They now use _safe_request() and must return None instead of raising.
    """

    def _make_http_error(self, code=500):
        return HTTPError(
            url='http://bazarr/api/test',
            code=code,
            msg='Internal Server Error',
            hdrs={},
            fp=io.BytesIO(b'server error'),
        )

    def test_bazarr_get_returns_none_on_http_error(self):
        with mock.patch.object(arr, 'urlopen', side_effect=self._make_http_error(500)):
            result = arr.bazarr_get('http://bazarr', 'key', '/api/system/settings')
        self.assertIsNone(result)  # Must not raise

    def test_bazarr_post_returns_none_on_http_error(self):
        with mock.patch.object(arr, 'urlopen', side_effect=self._make_http_error(403)):
            result = arr.bazarr_post('http://bazarr', 'key', '/api/system/settings', {})
        self.assertIsNone(result)  # Must not raise

    def test_bazarr_get_returns_none_on_network_error(self):
        with mock.patch.object(arr, 'urlopen', side_effect=URLError('connection refused')):
            result = arr.bazarr_get('http://bazarr', 'key', '/api/system/settings')
        self.assertIsNone(result)


# ── Bug #5a: bazarr_post_form must send form-encoded data, not JSON ───────────

class TestBazarrPostFormEncoding(unittest.TestCase):
    """
    Regression: configure_bazarr() previously POSTed JSON to Bazarr's
    /api/system/settings endpoint, which only reads request.form.
    Bazarr returned HTTP 204 and silently discarded all changes.

    bazarr_post_form() must send application/x-www-form-urlencoded.
    """

    def _mock_urlopen(self, captured):
        def _inner(req, timeout=None):
            captured['content_type'] = req.get_header('Content-type')
            captured['body'] = req.data.decode() if req.data else ''
            captured['method'] = req.method
            response = mock.MagicMock()
            response.read.return_value = b'{}'
            response.__enter__ = lambda s: s
            response.__exit__ = mock.MagicMock(return_value=False)
            return response
        return _inner

    def test_sends_form_content_type(self):
        captured = {}
        with mock.patch.object(arr, 'urlopen', self._mock_urlopen(captured)):
            arr.bazarr_post_form('http://bazarr', 'apikey', '/api/system/settings',
                                 {'settings-sonarr-ip': 'sonarr'})
        self.assertIn('application/x-www-form-urlencoded', captured['content_type'])

    def test_body_is_url_encoded_not_json(self):
        captured = {}
        with mock.patch.object(arr, 'urlopen', self._mock_urlopen(captured)):
            arr.bazarr_post_form('http://bazarr', 'apikey', '/api/system/settings',
                                 {'settings-sonarr-ip': 'sonarr', 'settings-sonarr-port': '8989'})
        body = captured['body']
        # Must look like URL-encoded form data, not JSON
        self.assertNotIn('{', body)
        self.assertIn('settings-sonarr-ip=sonarr', body)
        self.assertIn('settings-sonarr-port=8989', body)

    def test_sends_x_api_key_header(self):
        req_captured = {}

        def capture_req(req, timeout=None):
            req_captured['headers'] = dict(req.headers)
            r = mock.MagicMock()
            r.read.return_value = b'{}'
            r.__enter__ = lambda s: s
            r.__exit__ = mock.MagicMock(return_value=False)
            return r

        with mock.patch.object(arr, 'urlopen', capture_req):
            arr.bazarr_post_form('http://bazarr', 'myapikey123', '/api/system/settings', {})
        # urllib title-cases headers: 'X-api-key'
        headers_lower = {k.lower(): v for k, v in req_captured['headers'].items()}
        self.assertEqual(headers_lower.get('x-api-key'), 'myapikey123')


# ── Bug #5b: configure_bazarr must use correct form keys and lowercase bools ──

class TestConfigureBazarrFormData(unittest.TestCase):
    """
    Regression: configure_bazarr() must build form data with:
    - Key format: settings-{section}-{field}  (not the JSON structure)
    - Booleans as lowercase 'true'/'false'  (dynaconf rejects 'True'/'False')
    - Internal Docker hostnames ('sonarr', 'radarr') not LAN IP
    """

    EMPTY_SETTINGS = {
        'sonarr':  {'apikey': '', 'ip': '127.0.0.1', 'port': 8989, 'ssl': False, 'base_url': '/'},
        'radarr':  {'apikey': '', 'ip': '127.0.0.1', 'port': 7878, 'ssl': False},
        'general': {'use_sonarr': False, 'use_radarr': False, 'use_auth': False},
        'auth':    {'username': '', 'type': None, 'password': ''},
    }

    def _run_configure(self, sonarr_key='sonarr_api', radarr_key='radarr_api',
                       username=None, password=None):
        """Run configure_bazarr with mocked HTTP calls and capture form data."""
        captured_form = {}

        def mock_get(base, key, path):
            return self.EMPTY_SETTINGS

        def mock_post_form(base, key, path, form_data):
            captured_form.update(form_data)
            return {}  # HTTP 204-equivalent success

        with mock.patch.object(arr, 'bazarr_get', mock_get), \
             mock.patch.object(arr, 'bazarr_post_form', mock_post_form):
            arr.configure_bazarr(
                'http://bazarr', 'bazarr_api_key',
                sonarr_key, radarr_key,
                '/config/bazarr',
                username=username, password=password,
            )

        return captured_form

    def test_uses_settings_section_field_key_format(self):
        form = self._run_configure()
        # All keys must follow settings-{section}-{field} format
        for key in form:
            self.assertTrue(key.startswith('settings-'),
                            f"Form key '{key}' does not start with 'settings-'")

    def test_uses_internal_docker_hostnames(self):
        form = self._run_configure()
        self.assertEqual(form.get('settings-sonarr-ip'), 'sonarr',
                         "Sonarr host must be 'sonarr' (Docker internal), not an IP")
        self.assertEqual(form.get('settings-radarr-ip'), 'radarr',
                         "Radarr host must be 'radarr' (Docker internal), not an IP")

    def test_uses_correct_ports(self):
        form = self._run_configure()
        self.assertEqual(form.get('settings-sonarr-port'), '8989')
        self.assertEqual(form.get('settings-radarr-port'), '7878')

    def test_sets_api_keys(self):
        form = self._run_configure(sonarr_key='abc123', radarr_key='def456')
        self.assertEqual(form.get('settings-sonarr-apikey'), 'abc123')
        self.assertEqual(form.get('settings-radarr-apikey'), 'def456')

    def test_booleans_are_lowercase(self):
        """Dynaconf validates use_sonarr/use_radarr/ssl as bool — 'True' fails, 'true' passes."""
        form = self._run_configure()
        bool_fields = [
            'settings-sonarr-ssl',
            'settings-radarr-ssl',
            'settings-general-use_sonarr',
            'settings-general-use_radarr',
        ]
        for field in bool_fields:
            val = form.get(field, '')
            self.assertIn(val, ('true', 'false'),
                          f"Field '{field}' has value '{val}' — must be lowercase 'true' or 'false'")
            self.assertEqual(val, val.lower(),
                             f"Field '{field}' value '{val}' must be lowercase")

    def test_enable_flags_are_true(self):
        form = self._run_configure()
        self.assertEqual(form.get('settings-general-use_sonarr'), 'true')
        self.assertEqual(form.get('settings-general-use_radarr'), 'true')

    def test_skips_when_already_configured(self):
        """If apikey already matches, no form data should be sent."""
        captured_form = {}

        already_set = dict(self.EMPTY_SETTINGS)
        already_set['sonarr'] = {**already_set['sonarr'], 'apikey': 'sonarr_api'}
        already_set['radarr'] = {**already_set['radarr'], 'apikey': 'radarr_api'}

        def mock_get(base, key, path):
            return already_set

        def mock_post_form(base, key, path, form_data):
            captured_form.update(form_data)
            return {}

        with mock.patch.object(arr, 'bazarr_get', mock_get), \
             mock.patch.object(arr, 'bazarr_post_form', mock_post_form):
            arr.configure_bazarr(
                'http://bazarr', 'bazarr_api_key',
                'sonarr_api', 'radarr_api', '/config/bazarr',
            )

        # Nothing should have been posted since keys already match
        self.assertEqual(captured_form, {})

    def test_auth_credentials_use_correct_keys(self):
        form = self._run_configure(username='admin', password='secret')
        self.assertEqual(form.get('settings-auth-username'), 'admin')
        self.assertEqual(form.get('settings-auth-password'), 'secret')
        self.assertEqual(form.get('settings-auth-type'), 'basic')
        self.assertEqual(form.get('settings-general-use_auth'), 'true')


# ── sabnzbd_ini_set ───────────────────────────────────────────────────────────

class TestSabnzbdIniSet(unittest.TestCase):
    """sabnzbd_ini_set() must correctly replace values in sabnzbd.ini."""

    def _make_ini(self, content):
        f = tempfile.NamedTemporaryFile('w', suffix='.ini', delete=False)
        f.write(content)
        f.close()
        return f.name

    def test_replaces_existing_key(self):
        path = self._make_ini('[misc]\nhost = ::\n')
        result = arr.sabnzbd_ini_set(path, 'host', '0.0.0.0')
        self.assertTrue(result)
        with open(path) as f:
            self.assertIn('host = 0.0.0.0', f.read())

    def test_returns_false_when_key_not_found(self):
        path = self._make_ini('[misc]\nother = value\n')
        result = arr.sabnzbd_ini_set(path, 'host', '0.0.0.0')
        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
