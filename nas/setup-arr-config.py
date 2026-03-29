#!/usr/bin/env python3
"""
setup-arr-config.py — Arr Stack Auto-Configuration

Configures Sonarr, Radarr, Lidarr, Prowlarr, and generates Unpackerr config.
Safe to re-run — skips items already configured.

Usage:
    python3 /volume1/docker/media/setup-arr-config.py

Still requires manual setup after:
    Bazarr      — Settings → Sonarr / Radarr tabs (enter API keys)
    Seerr       — Setup wizard at http://<NAS>:5056
    Tautulli    — Setup wizard at http://<NAS>:8181
    Prowlarr    — Add your indexers manually
    qBittorrent — Add /downloads/ToFetch as watched folder (Settings → Downloads)
"""

import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# ── Terminal colours ──────────────────────────────────────────────────────────

GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

errors = 0

def ok(msg):
    print(f"  {GREEN}✔{RESET}  {msg}")

def skip(msg):
    print(f"  –  {msg} (already set)")

def warn(msg):
    print(f"  {YELLOW}!{RESET}  {msg}")

def fail(msg):
    global errors
    errors += 1
    print(f"  {RED}✘{RESET}  {msg}")

def section(title):
    print(f"\n{BOLD}━━━ {title} {'━' * (52 - len(title))}{RESET}")

# ── Read config ───────────────────────────────────────────────────────────────

def read_env(path):
    env = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, _, v = line.partition('=')
                    env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return env

def read_arr_key(config_xml):
    try:
        tree = ET.parse(config_xml)
        return tree.find('ApiKey').text
    except Exception:
        return None

def read_sabnzbd_key(ini_path):
    try:
        with open(ini_path) as f:
            for line in f:
                m = re.match(r'^api_key\s*=\s*(\S+)', line)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return None

# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _request(url, key, method='GET', data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = Request(url, data=body, headers={
        'X-Api-Key': key,
        'Content-Type': 'application/json',
        'User-Agent': 'setup-arr-config/1.0',
    }, method=method)
    try:
        with urlopen(req, timeout=15) as resp:
            content = resp.read()
            return json.loads(content) if content else {}
    except HTTPError as e:
        body_text = e.read().decode(errors='replace')[:300]
        print(f"    HTTP {e.code}: {body_text}")
        return None
    except URLError:
        return None

def GET(base, key, path):   return _request(f"{base}{path}", key, 'GET')
def POST(base, key, path, data): return _request(f"{base}{path}", key, 'POST', data)
def PUT(base, key, path, data):  return _request(f"{base}{path}", key, 'PUT', data)

# ── Wait for service ──────────────────────────────────────────────────────────

def wait_ready(name, base, key, check_path, retries=24, interval=5):
    sys.stdout.write(f"  Waiting for {name} ")
    sys.stdout.flush()
    for _ in range(retries):
        if GET(base, key, check_path) is not None:
            print(f"{GREEN}✔{RESET}")
            return True
        sys.stdout.write(".")
        sys.stdout.flush()
        time.sleep(interval)
    print(f"{RED}✘ timed out{RESET}")
    return False

# ── Root folders ──────────────────────────────────────────────────────────────

def add_root_folder(base, key, api, path):
    existing = GET(base, key, f"/{api}/rootfolder")
    if existing is None:
        fail(f"Root folder: can't reach API"); return
    if any(f['path'] == path for f in existing):
        skip(f"Root folder: {path}"); return
    result = POST(base, key, f"/{api}/rootfolder", {"path": path})
    ok(f"Root folder: {path}") if result else fail(f"Root folder: {path}")

# ── Download clients ──────────────────────────────────────────────────────────

def add_download_client(base, key, api, name, implementation, field_overrides):
    existing = GET(base, key, f"/{api}/downloadclient")
    if existing is None:
        fail(f"Download client {name}: can't reach API"); return
    if any(c['name'] == name for c in existing):
        skip(f"Download client: {name}"); return

    schemas = GET(base, key, f"/{api}/downloadclient/schema")
    if not schemas:
        fail(f"Download client {name}: can't get schema"); return
    schema = next((s for s in schemas if s.get('implementation') == implementation), None)
    if not schema:
        fail(f"Download client {name}: '{implementation}' not in schema"); return

    schema['name'] = name
    schema['enable'] = True
    field_map = {f['name']: i for i, f in enumerate(schema.get('fields', []))}
    for fname, fval in field_overrides.items():
        if fname in field_map:
            schema['fields'][field_map[fname]]['value'] = fval

    result = POST(base, key, f"/{api}/downloadclient", schema)
    ok(f"Download client: {name}") if result else fail(f"Download client: {name}")

# ── Remote path mappings ──────────────────────────────────────────────────────

def add_remote_path_mapping(base, key, api, host, remote, local):
    existing = GET(base, key, f"/{api}/remotePathMapping")
    if existing is None:
        fail(f"Remote path mapping: can't reach API"); return
    if any(m.get('host') == host and m.get('remotePath') == remote for m in existing):
        skip(f"Remote path: {host} {remote} → {local}"); return
    result = POST(base, key, f"/{api}/remotePathMapping",
                  {"host": host, "remotePath": remote, "localPath": local})
    ok(f"Remote path: {host} {remote} → {local}") if result else fail(f"Remote path: {host} {remote} → {local}")

# ── Hardlinks ─────────────────────────────────────────────────────────────────

def enable_hardlinks(base, key, api):
    config = GET(base, key, f"/{api}/config/mediamanagement")
    if config is None:
        fail("Hardlinks: can't get media management config"); return
    if config.get('copyUsingHardlinks'):
        skip("Hardlinks (already enabled)"); return
    config['copyUsingHardlinks'] = True
    result = PUT(base, key, f"/{api}/config/mediamanagement", config)
    ok("Hardlinks enabled") if result else fail("Hardlinks: failed to update")

# ── Prowlarr app connections ──────────────────────────────────────────────────

def add_prowlarr_app(prowlarr_base, prowlarr_key, app_name, implementation,
                     config_contract, app_internal_url, app_key, sync_categories):
    existing = GET(prowlarr_base, prowlarr_key, "/api/v1/applications")
    if existing is None:
        fail(f"Prowlarr app {app_name}: can't reach API"); return
    if any(a['name'] == app_name for a in existing):
        skip(f"Prowlarr app: {app_name}"); return

    # Use schema to avoid hardcoding all fields
    schemas = GET(prowlarr_base, prowlarr_key, "/api/v1/applications/schema")
    if schemas:
        schema = next((s for s in schemas if s.get('implementation') == implementation), None)
    else:
        schema = None

    if schema:
        schema['name'] = app_name
        schema['syncLevel'] = 'fullSync'
        field_map = {f['name']: i for i, f in enumerate(schema.get('fields', []))}
        overrides = {
            'prowlarrUrl':      'http://prowlarr:9696',
            'baseUrl':          app_internal_url,
            'apiKey':           app_key,
            'syncCategories':   sync_categories,
        }
        for fname, fval in overrides.items():
            if fname in field_map:
                schema['fields'][field_map[fname]]['value'] = fval
        data = schema
    else:
        # Fallback: minimal payload
        data = {
            'syncLevel': 'fullSync',
            'name': app_name,
            'fields': [
                {'name': 'prowlarrUrl',    'value': 'http://prowlarr:9696'},
                {'name': 'baseUrl',        'value': app_internal_url},
                {'name': 'apiKey',         'value': app_key},
                {'name': 'syncCategories', 'value': sync_categories},
            ],
            'implementationName': app_name,
            'implementation':     implementation,
            'configContract':     config_contract,
            'tags': [],
        }

    result = POST(prowlarr_base, prowlarr_key, "/api/v1/applications", data)
    ok(f"Prowlarr app: {app_name}") if result else fail(f"Prowlarr app: {app_name}")

# ── Unpackerr config ──────────────────────────────────────────────────────────

UNPACKERR_TEMPLATE = """\
# Unpackerr Configuration — auto-generated by setup-arr-config.py
# Docs: https://github.com/Unpackerr/unpackerr/wiki/Configuration

debug        = false
quiet        = false
interval     = "2m"
start_delay  = "1m"
retry_delay  = "5m"
max_retries  = 3
parallel     = 1
file_mode    = "0644"
dir_mode     = "0755"
delete_delay = "5m"
delete_orig  = false

[[sonarr]]
  url      = "http://sonarr:8989"
  api_key  = "{sonarr_key}"
  paths    = ["/data/Downloads/Torrents/Completed", "/data/Downloads/Usenet/complete"]
  protocols = "torrent,usenet"
  timeout  = "10s"

[[radarr]]
  url      = "http://radarr:7878"
  api_key  = "{radarr_key}"
  paths    = ["/data/Downloads/Torrents/Completed", "/data/Downloads/Usenet/complete"]
  protocols = "torrent,usenet"
  timeout  = "10s"

[[lidarr]]
  url      = "http://lidarr:8686"
  api_key  = "{lidarr_key}"
  paths    = ["/data/Downloads/Torrents/Completed", "/data/Downloads/Usenet/complete"]
  protocols = "torrent,usenet"
  timeout  = "10s"
"""

def write_unpackerr_config(sonarr_key, radarr_key, lidarr_key):
    out_path = "/volume1/docker/media/unpackerr/config/unpackerr.conf"
    if os.path.exists(out_path):
        skip(f"Unpackerr config (already exists at {out_path})")
        return
    content = UNPACKERR_TEMPLATE.format(
        sonarr_key=sonarr_key or 'REPLACE_WITH_SONARR_API_KEY',
        radarr_key=radarr_key or 'REPLACE_WITH_RADARR_API_KEY',
        lidarr_key=lidarr_key or 'REPLACE_WITH_LIDARR_API_KEY',
    )
    try:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, 'w') as f:
            f.write(content)
        ok(f"Unpackerr config written to {out_path}")
        warn("Restart unpackerr after this script:  docker-compose restart unpackerr")
    except Exception as e:
        fail(f"Unpackerr config: {e}")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    script_dir = os.path.dirname(os.path.realpath(__file__))
    env_file   = os.path.join(script_dir, '.env')
    env        = read_env(env_file)

    LAN_IP  = env.get('LAN_IP', '')
    QB_USER = env.get('QBITTORRENT_USER', 'admin')
    QB_PASS = env.get('QBITTORRENT_PASS', '')

    if not LAN_IP:
        print("Error: LAN_IP not set in .env"); sys.exit(1)
    if not QB_PASS:
        print("Error: QBITTORRENT_PASS not set in .env"); sys.exit(1)

    # Host-mapped URLs (used by this script running on the NAS)
    SONARR   = f"http://{LAN_IP}:49152"
    RADARR   = f"http://{LAN_IP}:49151"
    LIDARR   = f"http://{LAN_IP}:49154"
    PROWLARR = f"http://{LAN_IP}:49150"

    # Docker-internal URLs (used for service-to-service config)
    SONARR_INT   = "http://sonarr:8989"
    RADARR_INT   = "http://radarr:7878"
    LIDARR_INT   = "http://lidarr:8686"

    BASE = "/volume1/docker/media"
    SONARR_KEY   = read_arr_key(f"{BASE}/sonarr/config/config.xml")
    RADARR_KEY   = read_arr_key(f"{BASE}/radarr/config/config.xml")
    LIDARR_KEY   = read_arr_key(f"{BASE}/lidarr/config/config.xml")
    PROWLARR_KEY = read_arr_key(f"{BASE}/prowlarr/config/config.xml")
    SABNZBD_KEY  = read_sabnzbd_key(f"{BASE}/sabnzbd/config/sabnzbd.ini")

    print(f"\n{BOLD}╔══════════════════════════════════════════╗")
    print("║     Arr Stack Auto-Configuration         ║")
    print(f"╚══════════════════════════════════════════╝{RESET}")
    print("\nAPI keys found:")
    for name, key in [('Sonarr', SONARR_KEY), ('Radarr', RADARR_KEY),
                      ('Lidarr', LIDARR_KEY), ('Prowlarr', PROWLARR_KEY),
                      ('SABnzbd', SABNZBD_KEY)]:
        status = f"{GREEN}✔{RESET} {key[:8]}..." if key else f"{RED}✘{RESET} not found"
        print(f"  {name:<12} {status}")

    # qBittorrent shares Gluetun's network namespace — use 'gluetun' as hostname
    QB_HOST = "gluetun"
    QB_PORT = 49156  # WEBUI_PORT from docker-compose

    # ── Sonarr ────────────────────────────────────────────────────────────────

    section("Sonarr")
    if not SONARR_KEY:
        fail("API key not found — is the container running?")
    elif wait_ready("Sonarr", SONARR, SONARR_KEY, "/api/v3/system/status"):
        add_root_folder(SONARR, SONARR_KEY, "api/v3", "/data/Media/TV Shows")
        add_root_folder(SONARR, SONARR_KEY, "api/v3", "/data/Media/Anime/TV Shows")
        add_download_client(SONARR, SONARR_KEY, "api/v3", "qBittorrent", "QBittorrent", {
            "host": QB_HOST, "port": QB_PORT, "useSsl": False,
            "username": QB_USER, "password": QB_PASS, "category": "tv-sonarr",
        })
        if SABNZBD_KEY:
            add_download_client(SONARR, SONARR_KEY, "api/v3", "SABnzbd", "Sabnzbd", {
                "host": "sabnzbd", "port": 8080, "useSsl": False,
                "apiKey": SABNZBD_KEY, "category": "tv",
            })
        else:
            warn("SABnzbd key not found — skipping SABnzbd download client")
        add_remote_path_mapping(SONARR, SONARR_KEY, "api/v3",
                                QB_HOST, "/downloads", "/data/Downloads/Torrents")
        enable_hardlinks(SONARR, SONARR_KEY, "api/v3")

    # ── Radarr ────────────────────────────────────────────────────────────────

    section("Radarr")
    if not RADARR_KEY:
        fail("API key not found — is the container running?")
    elif wait_ready("Radarr", RADARR, RADARR_KEY, "/api/v3/system/status"):
        add_root_folder(RADARR, RADARR_KEY, "api/v3", "/data/Media/Movies")
        add_root_folder(RADARR, RADARR_KEY, "api/v3", "/data/Media/Anime/Movies")
        add_download_client(RADARR, RADARR_KEY, "api/v3", "qBittorrent", "QBittorrent", {
            "host": QB_HOST, "port": QB_PORT, "useSsl": False,
            "username": QB_USER, "password": QB_PASS, "category": "radarr",
        })
        if SABNZBD_KEY:
            add_download_client(RADARR, RADARR_KEY, "api/v3", "SABnzbd", "Sabnzbd", {
                "host": "sabnzbd", "port": 8080, "useSsl": False,
                "apiKey": SABNZBD_KEY, "category": "movies",
            })
        else:
            warn("SABnzbd key not found — skipping SABnzbd download client")
        add_remote_path_mapping(RADARR, RADARR_KEY, "api/v3",
                                QB_HOST, "/downloads", "/data/Downloads/Torrents")
        enable_hardlinks(RADARR, RADARR_KEY, "api/v3")

    # ── Lidarr ────────────────────────────────────────────────────────────────

    section("Lidarr")
    if not LIDARR_KEY:
        fail("API key not found — is the container running?")
    elif wait_ready("Lidarr", LIDARR, LIDARR_KEY, "/api/v1/system/status"):
        add_root_folder(LIDARR, LIDARR_KEY, "api/v1", "/data/Media/Music")
        add_download_client(LIDARR, LIDARR_KEY, "api/v1", "qBittorrent", "QBittorrent", {
            "host": QB_HOST, "port": QB_PORT, "useSsl": False,
            "username": QB_USER, "password": QB_PASS, "category": "lidarr",
        })
        if SABNZBD_KEY:
            add_download_client(LIDARR, LIDARR_KEY, "api/v1", "SABnzbd", "Sabnzbd", {
                "host": "sabnzbd", "port": 8080, "useSsl": False,
                "apiKey": SABNZBD_KEY, "category": "music",
            })
        else:
            warn("SABnzbd key not found — skipping SABnzbd download client")
        add_remote_path_mapping(LIDARR, LIDARR_KEY, "api/v1",
                                QB_HOST, "/downloads", "/data/Downloads/Torrents")
        enable_hardlinks(LIDARR, LIDARR_KEY, "api/v1")

    # ── Prowlarr ──────────────────────────────────────────────────────────────

    section("Prowlarr")
    if not PROWLARR_KEY:
        fail("API key not found — is the container running?")
    elif wait_ready("Prowlarr", PROWLARR, PROWLARR_KEY, "/api/v1/system/status"):
        if SONARR_KEY:
            add_prowlarr_app(PROWLARR, PROWLARR_KEY,
                             "Sonarr", "Sonarr", "SonarrSettings",
                             SONARR_INT, SONARR_KEY,
                             [5000, 5010, 5020, 5030, 5040, 5045, 5050, 5070])
        if RADARR_KEY:
            add_prowlarr_app(PROWLARR, PROWLARR_KEY,
                             "Radarr", "Radarr", "RadarrSettings",
                             RADARR_INT, RADARR_KEY,
                             [2000, 2010, 2020, 2030, 2040, 2045, 2050, 2060])
        if LIDARR_KEY:
            add_prowlarr_app(PROWLARR, PROWLARR_KEY,
                             "Lidarr", "Lidarr", "LidarrSettings",
                             LIDARR_INT, LIDARR_KEY,
                             [3000, 3010, 3030, 3040, 3050])

    # ── Unpackerr ─────────────────────────────────────────────────────────────

    section("Unpackerr")
    write_unpackerr_config(SONARR_KEY, RADARR_KEY, LIDARR_KEY)

    # ── Summary ───────────────────────────────────────────────────────────────

    print(f"\n{'═' * 52}")
    if errors == 0:
        print(f"{GREEN}{BOLD}  All done — no errors.{RESET}")
    else:
        print(f"{RED}{BOLD}  Done with {errors} error(s) — review output above.{RESET}")

    print(f"""
  Still needs manual setup:
  • Bazarr      http://{LAN_IP}:49153  → Settings → Sonarr & Radarr tabs
  • Seerr       http://{LAN_IP}:5056   → Setup wizard on first visit
  • Tautulli    http://{LAN_IP}:8181   → Setup wizard on first visit
  • Prowlarr    http://{LAN_IP}:49150  → Add your indexers
  • qBittorrent http://{LAN_IP}:49156  → Settings → Downloads → add watched
                                         folder: /downloads/ToFetch
""")
    print('═' * 52)
    sys.exit(0 if errors == 0 else 1)


if __name__ == '__main__':
    main()
