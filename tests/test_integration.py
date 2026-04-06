"""
Integration tests for the running media stack.

Requires services to be running (docker compose up).
Skipped automatically when services are not reachable.

Run with:
    pytest tests/test_integration.py -v

Or to run ALL tests including integration:
    pytest tests/ -v
"""

import json
import os
import subprocess
import unittest
from urllib.request import Request, urlopen
from urllib.error import URLError

from conftest import load_module

arr = load_module('arr_config', 'setup-arr-config.py')

# ── Config from .env ──────────────────────────────────────────────────────────

NAS_DIR = os.path.join(os.path.dirname(__file__), '..', 'nas')
ENV_FILE = os.path.join(NAS_DIR, '.env')

env = arr.read_env(ENV_FILE)

LAN_IP       = env.get('LAN_IP', '127.0.0.1')
SONARR_KEY   = env.get('SONARR_API_KEY')   or arr.read_arr_key('/volume1/docker/media/sonarr/config/config.xml')
RADARR_KEY   = env.get('RADARR_API_KEY')   or arr.read_arr_key('/volume1/docker/media/radarr/config/config.xml')
LIDARR_KEY   = env.get('LIDARR_API_KEY')   or arr.read_arr_key('/volume1/docker/media/lidarr/config/config.xml')
PROWLARR_KEY = env.get('PROWLARR_API_KEY') or arr.read_arr_key('/volume1/docker/media/prowlarr/config/config.xml')
SABNZBD_KEY  = env.get('SABNZBD_API_KEY')  or arr.read_sabnzbd_key('/volume1/docker/media/sabnzbd/config/sabnzbd.ini')
BAZARR_KEY   = env.get('BAZARR_API_KEY')   or arr.read_bazarr_key('/volume1/docker/media/bazarr/config')

SONARR   = f"http://{LAN_IP}:49152"
RADARR   = f"http://{LAN_IP}:49151"
LIDARR   = f"http://{LAN_IP}:49154"
PROWLARR = f"http://{LAN_IP}:49150"
SABNZBD  = f"http://{LAN_IP}:49155"
BAZARR   = f"http://{LAN_IP}:49153"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get(base, key, path):
    return arr.GET(base, key, path)

def _sab(mode, **params):
    return arr.sab_api(SABNZBD, SABNZBD_KEY, {'mode': mode, **params})

def _bazarr_get(path):
    return arr.bazarr_get(BAZARR, BAZARR_KEY, path)

def service_reachable(base, key, check_path):
    result = _get(base, key, check_path)
    return result is not None

def skip_if_down(base, key, check_path, name):
    if not service_reachable(base, key, check_path):
        raise unittest.SkipTest(f"{name} not reachable — start the stack first")


# ── API Availability ──────────────────────────────────────────────────────────

class TestServiceAPIs(unittest.TestCase):
    """All service APIs must respond with valid JSON."""

    def test_prowlarr_api(self):
        skip_if_down(PROWLARR, PROWLARR_KEY, '/api/v1/system/status', 'Prowlarr')
        status = _get(PROWLARR, PROWLARR_KEY, '/api/v1/system/status')
        self.assertIn('version', status)

    def test_sonarr_api(self):
        skip_if_down(SONARR, SONARR_KEY, '/api/v3/system/status', 'Sonarr')
        status = _get(SONARR, SONARR_KEY, '/api/v3/system/status')
        self.assertIn('version', status)

    def test_radarr_api(self):
        skip_if_down(RADARR, RADARR_KEY, '/api/v3/system/status', 'Radarr')
        status = _get(RADARR, RADARR_KEY, '/api/v3/system/status')
        self.assertIn('version', status)

    def test_lidarr_api(self):
        skip_if_down(LIDARR, LIDARR_KEY, '/api/v1/system/status', 'Lidarr')
        status = _get(LIDARR, LIDARR_KEY, '/api/v1/system/status')
        self.assertIn('version', status)

    def test_sabnzbd_api(self):
        if not SABNZBD_KEY:
            self.skipTest('SABnzbd API key not found')
        resp = _sab('version')
        if resp is None:
            self.skipTest('SABnzbd not reachable')
        self.assertIn('version', resp)

    def test_bazarr_api(self):
        if not BAZARR_KEY:
            self.skipTest('Bazarr API key not found')
        status = _bazarr_get('/api/system/status')
        if status is None:
            self.skipTest('Bazarr not reachable')
        self.assertIn('data', status)


# ── Prowlarr → *arr connections ───────────────────────────────────────────────

class TestProwlarrConnections(unittest.TestCase):
    """Prowlarr must have Sonarr, Radarr, and Lidarr registered as applications."""

    def setUp(self):
        skip_if_down(PROWLARR, PROWLARR_KEY, '/api/v1/system/status', 'Prowlarr')

    def _get_app_names(self):
        apps = _get(PROWLARR, PROWLARR_KEY, '/api/v1/applications') or []
        return [a['name'].lower() for a in apps]

    def test_sonarr_registered(self):
        self.assertIn('sonarr', self._get_app_names(),
                      "Prowlarr has no Sonarr application — run setup-arr-config.py")

    def test_radarr_registered(self):
        self.assertIn('radarr', self._get_app_names(),
                      "Prowlarr has no Radarr application — run setup-arr-config.py")

    def test_lidarr_registered(self):
        self.assertIn('lidarr', self._get_app_names(),
                      "Prowlarr has no Lidarr application — run setup-arr-config.py")

    def test_apps_use_internal_hostnames(self):
        """Apps must use Docker-internal hostnames, not host IP."""
        apps = _get(PROWLARR, PROWLARR_KEY, '/api/v1/applications') or []
        for app in apps:
            base_url = next(
                (f['value'] for f in app.get('fields', []) if f.get('name') == 'baseUrl'),
                None,
            )
            if base_url:
                self.assertNotIn(LAN_IP, base_url,
                                 f"Prowlarr app '{app['name']}' uses host IP {LAN_IP} "
                                 f"instead of internal hostname")

    def test_apps_use_full_sync(self):
        apps = _get(PROWLARR, PROWLARR_KEY, '/api/v1/applications') or []
        for app in apps:
            self.assertEqual(app.get('syncLevel'), 'fullSync',
                             f"Prowlarr app '{app['name']}' syncLevel is "
                             f"'{app.get('syncLevel')}' — expected 'fullSync'")


# ── Download clients ──────────────────────────────────────────────────────────

class TestDownloadClients(unittest.TestCase):
    """Sonarr, Radarr, and Lidarr must have SABnzbd configured as a download client."""

    def _get_client_names(self, base, key, api):
        clients = _get(base, key, f'/{api}/downloadclient') or []
        return [c['name'].lower() for c in clients]

    def test_sonarr_has_sabnzbd(self):
        skip_if_down(SONARR, SONARR_KEY, '/api/v3/system/status', 'Sonarr')
        self.assertIn('sabnzbd', self._get_client_names(SONARR, SONARR_KEY, 'api/v3'),
                      "Sonarr has no SABnzbd download client")

    def test_radarr_has_sabnzbd(self):
        skip_if_down(RADARR, RADARR_KEY, '/api/v3/system/status', 'Radarr')
        self.assertIn('sabnzbd', self._get_client_names(RADARR, RADARR_KEY, 'api/v3'),
                      "Radarr has no SABnzbd download client")

    def test_lidarr_has_sabnzbd(self):
        skip_if_down(LIDARR, LIDARR_KEY, '/api/v1/system/status', 'Lidarr')
        self.assertIn('sabnzbd', self._get_client_names(LIDARR, LIDARR_KEY, 'api/v1'),
                      "Lidarr has no SABnzbd download client")


# ── Root folders ──────────────────────────────────────────────────────────────

class TestRootFolders(unittest.TestCase):
    """Services must have their media root folders configured."""

    def _get_paths(self, base, key, api):
        folders = _get(base, key, f'/{api}/rootfolder') or []
        return [f['path'] for f in folders]

    def test_sonarr_tv_folder(self):
        skip_if_down(SONARR, SONARR_KEY, '/api/v3/system/status', 'Sonarr')
        paths = self._get_paths(SONARR, SONARR_KEY, 'api/v3')
        self.assertIn('/data/Media/TV Shows', paths)

    def test_sonarr_anime_folder(self):
        skip_if_down(SONARR, SONARR_KEY, '/api/v3/system/status', 'Sonarr')
        paths = self._get_paths(SONARR, SONARR_KEY, 'api/v3')
        self.assertIn('/data/Media/Anime/TV Shows', paths)

    def test_radarr_movies_folder(self):
        skip_if_down(RADARR, RADARR_KEY, '/api/v3/system/status', 'Radarr')
        paths = self._get_paths(RADARR, RADARR_KEY, 'api/v3')
        self.assertIn('/data/Media/Movies', paths)

    def test_lidarr_music_folder(self):
        skip_if_down(LIDARR, LIDARR_KEY, '/api/v1/system/status', 'Lidarr')
        paths = self._get_paths(LIDARR, LIDARR_KEY, 'api/v1')
        self.assertIn('/data/Media/Music', paths)


# ── Bazarr connections (Bug #5 regression) ────────────────────────────────────

class TestBazarrConnections(unittest.TestCase):
    """
    Regression test for Bug #5: configure_bazarr() was sending JSON instead
    of form data — Bazarr returned 204 but saved nothing. Verify the fix
    actually wired Bazarr to Sonarr and Radarr.
    """

    def setUp(self):
        if not BAZARR_KEY:
            self.skipTest('Bazarr API key not found')
        settings = _bazarr_get('/api/system/settings')
        if settings is None:
            self.skipTest('Bazarr not reachable')
        self._sonarr = settings.get('sonarr', {})
        self._radarr = settings.get('radarr', {})
        self._general = settings.get('general', {})

    def test_bazarr_sonarr_api_key_configured(self):
        self.assertTrue(self._sonarr.get('apikey'),
                        "Bazarr has no Sonarr API key — configure_bazarr() may have sent JSON instead of form data")

    def test_bazarr_radarr_api_key_configured(self):
        self.assertTrue(self._radarr.get('apikey'),
                        "Bazarr has no Radarr API key — configure_bazarr() may have sent JSON instead of form data")

    def test_bazarr_sonarr_uses_internal_hostname(self):
        ip = self._sonarr.get('ip', '')
        self.assertEqual(ip, 'sonarr',
                         f"Bazarr Sonarr IP is '{ip}' — should be 'sonarr' (Docker internal hostname)")

    def test_bazarr_radarr_uses_internal_hostname(self):
        ip = self._radarr.get('ip', '')
        self.assertEqual(ip, 'radarr',
                         f"Bazarr Radarr IP is '{ip}' — should be 'radarr' (Docker internal hostname)")

    def test_bazarr_sonarr_enabled(self):
        self.assertTrue(self._general.get('use_sonarr'),
                        "Bazarr use_sonarr is False — Sonarr integration not enabled")

    def test_bazarr_radarr_enabled(self):
        self.assertTrue(self._general.get('use_radarr'),
                        "Bazarr use_radarr is False — Radarr integration not enabled")

    def test_bazarr_live_sonarr_connection(self):
        """Bazarr must be able to reach Sonarr and report its version."""
        status = _bazarr_get('/api/system/status')
        if status is None:
            self.skipTest('Bazarr not reachable')
        sonarr_version = status.get('data', {}).get('sonarr_version', '')
        self.assertTrue(sonarr_version,
                        "Bazarr reports empty sonarr_version — not connected to Sonarr")

    def test_bazarr_live_radarr_connection(self):
        """Bazarr must be able to reach Radarr and report its version."""
        status = _bazarr_get('/api/system/status')
        if status is None:
            self.skipTest('Bazarr not reachable')
        radarr_version = status.get('data', {}).get('radarr_version', '')
        self.assertTrue(radarr_version,
                        "Bazarr reports empty radarr_version — not connected to Radarr")


# ── SABnzbd configuration ─────────────────────────────────────────────────────

class TestSabnzbdConfiguration(unittest.TestCase):
    """SABnzbd must have download directories and categories configured."""

    def setUp(self):
        if not SABNZBD_KEY:
            self.skipTest('SABnzbd API key not found')
        resp = _sab('version')
        if resp is None:
            self.skipTest('SABnzbd not reachable')

    def _get_config(self, keyword):
        resp = _sab('get_config', section='misc', keyword=keyword)
        return (resp or {}).get('config', {}).get('misc', {}).get(keyword)

    def test_complete_dir_configured(self):
        val = self._get_config('complete_dir')
        self.assertEqual(val, '/data/complete',
                         f"SABnzbd complete_dir is '{val}' — expected '/data/complete'")

    def test_incomplete_dir_configured(self):
        val = self._get_config('download_dir')
        self.assertEqual(val, '/data/incomplete',
                         f"SABnzbd download_dir is '{val}' — expected '/data/incomplete'")

    def test_categories_configured(self):
        resp = _sab('get_config', section='categories')
        cats = {c['name'] for c in (resp or {}).get('config', {}).get('categories', [])}
        for expected in ('tv', 'movies', 'music'):
            self.assertIn(expected, cats,
                          f"SABnzbd missing '{expected}' category")

    def test_host_whitelist_contains_arr_services(self):
        val = self._get_config('host_whitelist')
        if isinstance(val, list):
            whitelist = set(val)
        else:
            whitelist = {h.strip() for h in (val or '').split(',') if h.strip()}
        for host in ('sonarr', 'radarr', 'sabnzbd', 'prowlarr'):
            self.assertIn(host, whitelist,
                          f"SABnzbd host_whitelist missing '{host}'")


if __name__ == '__main__':
    unittest.main()
