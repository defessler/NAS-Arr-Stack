#!/usr/bin/env python3
"""
setup-arr-config.py — Arr Stack Auto-Configuration

Configures as much of the stack as possible via API.
Safe to re-run — skips items already configured.

Usage:
    python3 /volume1/docker/media/setup-arr-config.py

Still requires manual setup after:
    Tautulli    — Setup wizard at http://<NAS>:8181  (needs your Plex token)
    Prowlarr    — Add your indexers manually
    qBittorrent — Settings → Downloads → add watched folder: /downloads/ToFetch
    Seerr       — Run setup wizard first, then re-run this script to wire up
                  Sonarr/Radarr. Plex connection still needs manual setup.
"""

import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

# ── Terminal colours ──────────────────────────────────────────────────────────

GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

errors = 0

def ok(msg):   print(f"  {GREEN}✔{RESET}  {msg}")
def skip(msg): print(f"  –  {msg} (already set)")
def warn(msg): print(f"  {YELLOW}!{RESET}  {msg}")
def fail(msg):
    global errors; errors += 1
    print(f"  {RED}✘{RESET}  {msg}")
def section(title):
    print(f"\n{BOLD}━━━ {title} {'━' * max(0, 52 - len(title))}{RESET}")

# ── Read config files ─────────────────────────────────────────────────────────

def read_env(path):
    """Read key=value pairs from a file, ignoring comments and blank lines.
    Inline comments after the value (e.g. KEY=value  # comment) are stripped."""
    env = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, _, v = line.partition('=')
                # Strip inline comments
                v = v.split('#')[0].strip()
                if v:
                    env[k.strip()] = v
    except FileNotFoundError:
        pass
    return env

def read_env_merged(script_dir):
    """.env holds real values (gitignored). Copy from .env.example to create it."""
    return read_env(os.path.join(script_dir, '.env'))

def read_arr_key(config_xml):
    """Read API key from a *arr config.xml file."""
    try:
        return ET.parse(config_xml).find('ApiKey').text
    except Exception:
        return None

def read_sabnzbd_key(ini_path):
    """Read api_key from SABnzbd's sabnzbd.ini."""
    try:
        with open(ini_path) as f:
            for line in f:
                m = re.match(r'^api_key\s*=\s*(\S+)', line)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return None

def read_bazarr_key(config_dir):
    """Read API key from Bazarr's config file.
    Tries both the given directory and a nested config/ subdirectory,
    and several filenames — Bazarr versions differ on location and name."""
    search_dirs = [config_dir, os.path.join(config_dir, 'config')]
    for d in search_dirs:
        for filename in ('config.yaml', 'config.ini', 'config'):
            path = os.path.join(d, filename)
            try:
                with open(path) as f:
                    content = f.read()
                m = re.search(r'^\s*apikey\s*[=:]\s*[\'"]?([^\s\'"]+)',
                              content, re.MULTILINE)
                if m:
                    return m.group(1)
            except FileNotFoundError:
                continue
            except Exception:
                continue
    return None

def read_json_key(json_path, *keys):
    """Read a value from a JSON file by key path."""
    try:
        with open(json_path) as f:
            data = json.load(f)
        for k in keys:
            data = data[k]
        return data
    except Exception:
        return None

# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _request(url, headers, method='GET', data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=15) as resp:
            content = resp.read()
            return json.loads(content) if content else {}
    except HTTPError as e:
        body_text = e.read().decode(errors='replace')
        # Expose the status code and body to callers that want to inspect it
        e._body_text = body_text
        print(f"    HTTP {e.code}: {body_text[:200]}")
        raise
    except (URLError, OSError):
        return None

def _safe_request(url, headers, method='GET', data=None):
    """Like _request but returns (result_or_None, http_code_or_None)."""
    body = json.dumps(data).encode() if data is not None else None
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=15) as resp:
            content = resp.read()
            return (json.loads(content) if content else {}), resp.status
    except HTTPError as e:
        body_text = e.read().decode(errors='replace')
        print(f"    HTTP {e.code}: {body_text[:200]}")
        return None, e.code
    except (URLError, OSError):
        return None, None


def _arr_headers(key):
    return {'X-Api-Key': key, 'Content-Type': 'application/json',
            'User-Agent': 'setup-arr-config/1.0'}

def GET(base, key, path):
    result, _ = _safe_request(f"{base}{path}", _arr_headers(key))
    return result

def POST(base, key, path, data):
    result, _ = _safe_request(f"{base}{path}", _arr_headers(key), 'POST', data)
    return result

def POST_status(base, key, path, data):
    """POST that also returns the HTTP status code."""
    return _safe_request(f"{base}{path}", _arr_headers(key), 'POST', data)

def PUT(base, key, path, data):
    result, _ = _safe_request(f"{base}{path}", _arr_headers(key), 'PUT', data)
    return result

def sab_api(base, key, params):
    """SABnzbd uses query-string API, not JSON body."""
    params.update({'apikey': key, 'output': 'json'})
    url = f"{base}/api?{urlencode(params)}"
    try:
        with urlopen(Request(url), timeout=15) as resp:
            return json.loads(resp.read())
    except HTTPError as e:
        body = e.read().decode(errors='replace')
        print(f"    SABnzbd HTTP {e.code}: {body[:150]}")
        return None
    except Exception as e:
        print(f"    SABnzbd error: {e}")
        return None

def sabnzbd_ini_set(ini_path, keyword, value):
    """Directly replace a keyword value in sabnzbd.ini as a fallback when
    the API set_config call fails. Returns True on success."""
    try:
        with open(ini_path, 'r') as f:
            content = f.read()
        new_content, n = re.subn(
            rf'^({re.escape(keyword)}\s*=\s*).*$',
            f'{keyword} = {value}',
            content, flags=re.MULTILINE
        )
        if n == 0:
            return False  # keyword not present in ini — can't add safely
        with open(ini_path, 'w') as f:
            f.write(new_content)
        return True
    except Exception:
        return False

def bazarr_get(base, key, path):
    return _request(f"{base}{path}", {'X-API-KEY': key,
                                       'Content-Type': 'application/json'})

def bazarr_post(base, key, path, data):
    return _request(f"{base}{path}", {'X-API-KEY': key,
                                       'Content-Type': 'application/json'},
                    'POST', data)

# ── Wait for service ──────────────────────────────────────────────────────────

def wait_ready(name, base, key, check_path, retries=24, interval=5):
    sys.stdout.write(f"  Waiting for {name} ")
    sys.stdout.flush()
    for _ in range(retries):
        if GET(base, key, check_path) is not None:
            print(f"{GREEN}✔{RESET}"); return True
        sys.stdout.write("."); sys.stdout.flush()
        time.sleep(interval)
    print(f"{RED}✘ timed out{RESET}"); return False

# ── *arr helpers ──────────────────────────────────────────────────────────────

def add_root_folder(base, key, api, path, extra_fields=None):
    existing = GET(base, key, f"/{api}/rootfolder")
    if existing is None:
        fail(f"Root folder: can't reach API"); return
    if any(f['path'] == path for f in existing):
        skip(f"Root folder: {path}"); return
    # Lidarr requires a 'name' field; Sonarr/Radarr accept but ignore it
    name = os.path.basename(path.rstrip('/')) or path
    payload = {"path": path, "name": name}
    if extra_fields:
        payload.update(extra_fields)
    result = POST(base, key, f"/{api}/rootfolder", payload)
    ok(f"Root folder: {path}") if result else fail(f"Root folder: {path}")

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
        fail(f"Download client {name}: '{implementation}' not found"); return
    schema['name'] = name
    schema['enable'] = True
    field_map = {f['name']: i for i, f in enumerate(schema.get('fields', []))}
    for fname, fval in field_overrides.items():
        if fname in field_map:
            schema['fields'][field_map[fname]]['value'] = fval
    result = POST(base, key, f"/{api}/downloadclient", schema)
    ok(f"Download client: {name}") if result else fail(f"Download client: {name}")

def add_remote_path_mapping(base, key, api, host, remote, local):
    existing = GET(base, key, f"/{api}/remotePathMapping")
    if existing is None:
        fail("Remote path mapping: can't reach API"); return
    # Check by remote path alone — host may be stored differently (e.g. qbittorrent vs gluetun)
    if any(m.get('remotePath', '').rstrip('/') == remote.rstrip('/') for m in existing):
        skip(f"Remote path: {remote} → {local}"); return
    result, status = POST_status(base, key, f"/{api}/remotePathMapping",
                                 {"host": host, "remotePath": remote, "localPath": local})
    if result is not None:
        ok(f"Remote path: {host} {remote} → {local}")
    elif status == 500:
        # "RemotePath already configured" — treat as already set
        skip(f"Remote path: {remote} → {local} (already configured)")
    else:
        fail(f"Remote path: {host} {remote} → {local}")

def configure_auth(base, key, api, username, password):
    """Set Forms authentication on a *arr service, bypassed for local addresses."""
    config = GET(base, key, f"/{api}/config/host")
    if config is None:
        fail("Auth: can't get host config"); return
    already_set = (
        config.get('authenticationMethod', '').lower() not in ('none', '')
        and config.get('username') == username
        and config.get('authenticationRequired') == 'DisabledForLocalAddresses'
    )
    if already_set:
        skip(f"Auth: {username} (already set)"); return
    config['authenticationMethod'] = 'Forms'
    config['authenticationRequired'] = 'DisabledForLocalAddresses'
    config['username'] = username
    config['password'] = password
    config['passwordConfirmation'] = password
    result = PUT(base, key, f"/{api}/config/host", config)
    ok(f"Auth: {username} (LAN bypass on)") if result else fail("Auth: failed to set credentials")

def enable_hardlinks(base, key, api):
    config = GET(base, key, f"/{api}/config/mediamanagement")
    if config is None:
        fail("Hardlinks: can't get config"); return
    if config.get('copyUsingHardlinks'):
        skip("Hardlinks (already enabled)"); return
    config['copyUsingHardlinks'] = True
    result = PUT(base, key, f"/{api}/config/mediamanagement", config)
    ok("Hardlinks enabled") if result else fail("Hardlinks: failed to update")

def get_quality_profile(base, key, api, preferred='1080p'):
    """Return (id, name) of best matching quality profile."""
    profiles = GET(base, key, f"/{api}/qualityprofile") or []
    if not profiles:
        return None, None
    match = next((p for p in profiles if preferred.lower() in p['name'].lower()), None)
    chosen = match or profiles[0]
    return chosen['id'], chosen['name']

def get_language_profile(base, key):
    """Return id of first language profile (Sonarr only)."""
    profiles = GET(base, key, "/api/v3/languageprofile") or []
    return profiles[0]['id'] if profiles else 1

# ── Prowlarr ──────────────────────────────────────────────────────────────────

def add_prowlarr_app(prowlarr_base, prowlarr_key, app_name, implementation,
                     config_contract, app_internal_url, app_key, sync_categories):
    existing = GET(prowlarr_base, prowlarr_key, "/api/v1/applications")
    if existing is None:
        fail(f"Prowlarr app {app_name}: can't reach API"); return
    if any(a['name'] == app_name for a in existing):
        skip(f"Prowlarr app: {app_name}"); return
    schemas = GET(prowlarr_base, prowlarr_key, "/api/v1/applications/schema") or []
    schema  = next((s for s in schemas if s.get('implementation') == implementation), None)
    if schema:
        schema['name'] = app_name
        schema['syncLevel'] = 'fullSync'
        fm = {f['name']: i for i, f in enumerate(schema.get('fields', []))}
        for fname, fval in {
            'prowlarrUrl':    'http://prowlarr:9696',
            'baseUrl':        app_internal_url,
            'apiKey':         app_key,
            'syncCategories': sync_categories,
        }.items():
            if fname in fm:
                schema['fields'][fm[fname]]['value'] = fval
        data = schema
    else:
        data = {
            'syncLevel': 'fullSync', 'name': app_name, 'tags': [],
            'fields': [
                {'name': 'prowlarrUrl',    'value': 'http://prowlarr:9696'},
                {'name': 'baseUrl',        'value': app_internal_url},
                {'name': 'apiKey',         'value': app_key},
                {'name': 'syncCategories', 'value': sync_categories},
            ],
            'implementationName': app_name, 'implementation': implementation,
            'configContract': config_contract,
        }
    result = POST(prowlarr_base, prowlarr_key, "/api/v1/applications", data)
    ok(f"Prowlarr app: {app_name}") if result else fail(f"Prowlarr app: {app_name}")

# ── SABnzbd ───────────────────────────────────────────────────────────────────

def configure_sabnzbd(base, key, ini_path):
    section("SABnzbd")
    if not key:
        fail("API key not found — is the container running?"); return

    # Test connection
    resp = sab_api(base, key, {'mode': 'version'})
    if not resp:
        fail("Can't reach SABnzbd API"); return
    ok(f"Connected (SABnzbd {resp.get('version', '?')})")

    ini_modified = False

    def _sab_set(label, keyword, value, extra_params=None):
        """Try set_config via API; fall back to direct ini edit on failure."""
        nonlocal ini_modified
        params = {'mode': 'set_config', 'section': 'misc',
                  'keyword': keyword, 'value': value}
        if extra_params:
            params.update(extra_params)
        result = sab_api(base, key, params)
        # status can be True (success) or False (failure); None means API error
        if result is not None and result.get('status') is not False:
            ok(f"{label}: {value}")
            return True
        # API failed — try editing the ini file directly
        if sabnzbd_ini_set(ini_path, keyword, value):
            ok(f"{label}: {value}  (ini edit — SABnzbd restart needed)")
            ini_modified = True
            return True
        fail(f"{label}: failed to set {value}")
        return False

    # Add all service hostnames to host_whitelist so Docker containers can reach
    # SABnzbd. We read the current value first and merge so the container's own
    # hostname (auto-added by SABnzbd) is preserved alongside our service names.
    REQUIRED_HOSTS = {'sabnzbd', 'sonarr', 'radarr', 'lidarr',
                      'bazarr', 'prowlarr', 'localhost', '127.0.0.1'}
    cur = sab_api(base, key, {'mode': 'get_config', 'section': 'misc',
                               'keyword': 'host_whitelist'})
    existing_raw = (cur or {}).get('config', {}).get('misc', {}).get('host_whitelist', '')
    # SABnzbd API may return host_whitelist as a list or a comma-separated string
    if isinstance(existing_raw, list):
        existing = {h.strip() for h in existing_raw if h.strip()}
    else:
        existing = {h.strip() for h in existing_raw.split(',') if h.strip()}
    if REQUIRED_HOSTS.issubset(existing):
        skip("Host whitelist (already contains all required hostnames)")
    else:
        merged = ','.join(sorted(existing | REQUIRED_HOSTS))
        result = sab_api(base, key, {'mode': 'set_config', 'section': 'misc',
                                      'keyword': 'host_whitelist', 'value': merged})
        if result is not None and result.get('status') is not False:
            ok("Host whitelist updated (Docker service hostnames allowed)")
        elif sabnzbd_ini_set(ini_path, 'host_whitelist', merged):
            ok("Host whitelist updated (ini edit — SABnzbd restart needed)")
            ini_modified = True
        else:
            warn("Could not update host_whitelist — Sonarr/Radarr may get 403 from SABnzbd")

    # Download directories
    for label, keyword, value in [
        ("Incomplete dir", "download_dir",  "/data/incomplete"),
        ("Complete dir",   "complete_dir",  "/data/complete"),
    ]:
        current = sab_api(base, key, {'mode': 'get_config', 'section': 'misc',
                                       'keyword': keyword})
        cur_val = (current or {}).get('config', {}).get('misc', {}).get(keyword, '')
        if cur_val == value:
            skip(f"{label}: {value}"); continue
        _sab_set(label, keyword, value)

    # Categories — add tv / movies / music if not present.
    # Uses pp=3 (repair + unpack + delete) per SABnzbd's category API.
    cats_resp = sab_api(base, key, {'mode': 'get_config', 'section': 'categories'})
    existing_cats = {c['name'] for c in
                     (cats_resp or {}).get('config', {}).get('categories', [])}
    for cat_name, cat_dir in [('tv', '/data/complete/tv'),
                               ('movies', '/data/complete/movies'),
                               ('music', '/data/complete/music')]:
        if cat_name in existing_cats:
            skip(f"Category: {cat_name}"); continue
        result = sab_api(base, key, {
            'mode': 'set_config', 'section': 'categories',
            'keyword': cat_name, 'pp': '3',
            'dir': cat_dir,
        })
        if result is not None and result.get('status') is not False:
            ok(f"Category: {cat_name} → {cat_dir}")
        else:
            fail(f"Category: {cat_name}")

    # SABnzbd uses API key auth for all container-to-container communication,
    # so username/password credentials are not needed and would force a browser
    # login prompt with no way to bypass it for local connections.

    if ini_modified:
        warn("SABnzbd config was edited directly — restart to apply:")
        warn("  docker-compose restart sabnzbd")

# ── Bazarr ────────────────────────────────────────────────────────────────────

def configure_bazarr(base, key, sonarr_key, radarr_key, config_path,
                     username=None, password=None):
    section("Bazarr")
    if not key:
        # Config file not present yet — wait for Bazarr to start and write it
        sys.stdout.write("  Waiting for Bazarr config ")
        sys.stdout.flush()
        for _ in range(24):  # up to 2 minutes
            time.sleep(5)
            key = read_bazarr_key(config_path)
            if key:
                print(f"{GREEN}✔{RESET}")
                break
            sys.stdout.write(".")
            sys.stdout.flush()
        else:
            print(f"{RED}✘ timed out{RESET}")
            fail("Bazarr config not found — visit the Bazarr UI once to trigger config creation, then re-run")
            return

    settings = bazarr_get(base, key, "/api/system/settings")
    if settings is None:
        fail("Can't reach Bazarr API"); return

    sonarr_cfg = settings.get('sonarr', {})
    radarr_cfg = settings.get('radarr', {})
    general    = settings.get('general', {})

    changed = False

    # Sonarr connection
    if sonarr_key and sonarr_cfg.get('apikey') != sonarr_key:
        sonarr_cfg.update({
            'ip': 'sonarr', 'port': 8989,
            'base_url': '/', 'ssl': False,
            'apikey': sonarr_key,
        })
        general['use_sonarr'] = True
        changed = True
        ok("Bazarr → Sonarr connection set")
    else:
        skip("Bazarr → Sonarr (already set)" if sonarr_key else "Bazarr → Sonarr (no Sonarr key)")

    # Radarr connection
    if radarr_key and radarr_cfg.get('apikey') != radarr_key:
        radarr_cfg.update({
            'ip': 'radarr', 'port': 7878,
            'base_url': '/', 'ssl': False,
            'apikey': radarr_key,
        })
        general['use_radarr'] = True
        changed = True
        ok("Bazarr → Radarr connection set")
    else:
        skip("Bazarr → Radarr (already set)" if radarr_key else "Bazarr → Radarr (no Radarr key)")

    # Web UI credentials
    auth = settings.get('auth', {})
    if username and password and auth.get('username') != username:
        auth.update({'type': 'basic', 'username': username, 'password': password})
        general['use_auth'] = True
        settings['auth'] = auth
        changed = True
        ok(f"Bazarr auth: {username}")
    elif username:
        skip(f"Bazarr auth: {username} (already set)")

    if changed:
        payload = dict(settings)
        payload['sonarr'] = sonarr_cfg
        payload['radarr'] = radarr_cfg
        payload['general'] = general
        result = bazarr_post(base, key, "/api/system/settings", payload)
        ok("Bazarr settings saved") if result is not None else fail("Bazarr settings: save failed")

# ── Seerr ─────────────────────────────────────────────────────────────────────

def configure_seerr(base, key, sonarr_base, sonarr_key, radarr_base, radarr_key,
                    username=None, password=None):
    section("Seerr")
    if not key:
        warn("settings.json not found — complete the Seerr setup wizard first,")
        warn("then re-run this script to wire up Sonarr/Radarr automatically.")
        return

    # Test connection
    main_settings = GET(base, key, "/api/v1/settings/main")
    if main_settings is None:
        warn("Seerr setup wizard not yet complete — skipping.")
        warn("Visit http://<NAS>:5056, run the wizard, then re-run this script.")
        return

    # Ensure local (username/password) login is enabled so LAN users can log in
    # without needing Plex auth
    if main_settings.get('localLogin') is False:
        main_settings['localLogin'] = True
        result = POST(base, key, "/api/v1/settings/main", main_settings)
        ok("Local login enabled") if result is not None else fail("Local login: failed to enable")
    else:
        skip("Local login (already enabled)")

    # Sonarr
    if sonarr_key:
        existing = GET(base, key, "/api/v1/settings/sonarr") or []
        if any(s.get('hostname') == 'sonarr' for s in existing):
            skip("Seerr → Sonarr (already set)")
        else:
            profile_id, profile_name = get_quality_profile(sonarr_base, sonarr_key,
                                                            "api/v3", "1080p")
            lang_id = get_language_profile(sonarr_base, sonarr_key)
            result = POST(base, key, "/api/v1/settings/sonarr", {
                "name":                "Sonarr",
                "hostname":            "sonarr",
                "port":                8989,
                "apiKey":              sonarr_key,
                "useSsl":              False,
                "baseUrl":             "",
                "activeProfileId":     profile_id or 1,
                "activeProfileName":   profile_name or "HD-1080p",
                "activeDirectory":     "/data/Media/TV Shows",
                "is4k":                False,
                "isDefault":           True,
                "syncEnabled":         False,
                "preventSearch":       False,
                "seasons":             True,
                "enableSeasonFolders": True,
                "tags":                [],
                "animeDirectory":      "/data/Media/Anime/TV Shows",
                "languageProfileId":   lang_id,
            })
            ok("Seerr → Sonarr connection set") if result else fail("Seerr → Sonarr: failed")

    # Radarr
    if radarr_key:
        existing = GET(base, key, "/api/v1/settings/radarr") or []
        if any(r.get('hostname') == 'radarr' for r in existing):
            skip("Seerr → Radarr (already set)")
        else:
            profile_id, profile_name = get_quality_profile(radarr_base, radarr_key,
                                                            "api/v3", "1080p")
            result = POST(base, key, "/api/v1/settings/radarr", {
                "name":                "Radarr",
                "hostname":            "radarr",
                "port":                7878,
                "apiKey":              radarr_key,
                "useSsl":              False,
                "baseUrl":             "",
                "activeProfileId":     profile_id or 1,
                "activeProfileName":   profile_name or "HD-1080p",
                "activeDirectory":     "/data/Media/Movies",
                "is4k":                False,
                "isDefault":           True,
                "syncEnabled":         False,
                "preventSearch":       False,
                "minimumAvailability": "released",
                "tags":                [],
                "animeDirectory":      "/data/Media/Anime/Movies",
            })
            ok("Seerr → Radarr connection set") if result else fail("Seerr → Radarr: failed")

    warn("Seerr Plex connection still needs manual setup in the UI")

# ── Config file generators ────────────────────────────────────────────────────

UNPACKERR_CONF = """\
# Unpackerr Configuration — generated by setup-arr-config.py
# https://github.com/Unpackerr/unpackerr/wiki/Configuration

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
  url       = "http://sonarr:8989"
  api_key   = "{sonarr_key}"
  paths     = ["/data/Downloads/Torrents/Completed", "/data/Downloads/Usenet/complete"]
  protocols = "torrent,usenet"
  timeout   = "10s"

[[radarr]]
  url       = "http://radarr:7878"
  api_key   = "{radarr_key}"
  paths     = ["/data/Downloads/Torrents/Completed", "/data/Downloads/Usenet/complete"]
  protocols = "torrent,usenet"
  timeout   = "10s"

[[lidarr]]
  url       = "http://lidarr:8686"
  api_key   = "{lidarr_key}"
  paths     = ["/data/Downloads/Torrents/Completed", "/data/Downloads/Usenet/complete"]
  protocols = "torrent,usenet"
  timeout   = "10s"
"""

RECYCLARR_CONF = """\
# Recyclarr Configuration — generated by setup-arr-config.py
# https://recyclarr.dev/wiki/
#
# This is a minimal starter config. Customize quality profiles and
# custom formats to your preference — see the Recyclarr wiki for examples.

sonarr:
  main:
    base_url: http://sonarr:8989
    api_key: {sonarr_key}

radarr:
  main:
    base_url: http://radarr:7878
    api_key: {radarr_key}
"""

def write_config_file(label, path, content):
    if os.path.exists(path):
        skip(f"{label} config (already exists)"); return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write(content)
        ok(f"{label} config written → {path}")
    except Exception as e:
        fail(f"{label} config: {e}")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    script_dir = os.path.dirname(os.path.realpath(__file__))
    env        = read_env_merged(script_dir)

    LAN_IP   = env.get('LAN_IP', '')
    QB_USER  = env.get('QBITTORRENT_USER', 'admin')
    QB_PASS  = env.get('QBITTORRENT_PASS', '')
    ARR_USER = env.get('ARR_USERNAME', '')
    ARR_PASS = env.get('ARR_PASSWORD', '')

    if not LAN_IP:  print("Error: LAN_IP not set in .env");        sys.exit(1)
    if not QB_PASS: print("Error: QBITTORRENT_PASS not set in .env"); sys.exit(1)

    # ── Service URLs (host-mapped, used by this script) ───────────────────────
    SONARR   = f"http://{LAN_IP}:49152"
    RADARR   = f"http://{LAN_IP}:49151"
    LIDARR   = f"http://{LAN_IP}:49154"
    PROWLARR = f"http://{LAN_IP}:49150"
    SABNZBD  = f"http://{LAN_IP}:49155"
    BAZARR   = f"http://{LAN_IP}:49153"
    SEERR    = f"http://{LAN_IP}:5056"

    # ── Docker-internal URLs (written into service configs) ───────────────────
    SONARR_INT = "http://sonarr:8989"
    RADARR_INT = "http://radarr:7878"
    LIDARR_INT = "http://lidarr:8686"

    # ── API keys — .env takes priority, config files are the fallback ───────────
    B = "/volume1/docker/media"
    SONARR_KEY   = env.get('SONARR_API_KEY')   or read_arr_key(f"{B}/sonarr/config/config.xml")
    RADARR_KEY   = env.get('RADARR_API_KEY')   or read_arr_key(f"{B}/radarr/config/config.xml")
    LIDARR_KEY   = env.get('LIDARR_API_KEY')   or read_arr_key(f"{B}/lidarr/config/config.xml")
    PROWLARR_KEY = env.get('PROWLARR_API_KEY') or read_arr_key(f"{B}/prowlarr/config/config.xml")
    SABNZBD_KEY  = env.get('SABNZBD_API_KEY')  or read_sabnzbd_key(f"{B}/sabnzbd/config/sabnzbd.ini")
    BAZARR_KEY   = env.get('BAZARR_API_KEY')   or read_bazarr_key(f"{B}/bazarr/config")
    SEERR_KEY    = env.get('SEERR_API_KEY')    or read_json_key(f"{B}/seerr/config/settings.json", "main", "apiKey")

    # qBittorrent shares Gluetun's network namespace
    QB_HOST = "gluetun"
    QB_PORT = 49156

    print(f"\n{BOLD}╔══════════════════════════════════════════╗")
    print("║     Arr Stack Auto-Configuration         ║")
    print(f"╚══════════════════════════════════════════╝{RESET}")
    print("\nAPI keys found:")
    for name, key in [('Sonarr', SONARR_KEY), ('Radarr', RADARR_KEY),
                      ('Lidarr', LIDARR_KEY), ('Prowlarr', PROWLARR_KEY),
                      ('SABnzbd', SABNZBD_KEY), ('Bazarr', BAZARR_KEY),
                      ('Seerr', SEERR_KEY)]:
        s = f"{GREEN}✔{RESET} {key[:8]}..." if key else f"{RED}✘{RESET} not found"
        print(f"  {name:<12} {s}")

    # ── SABnzbd (configure first so Sonarr/Radarr/Lidarr can connect to it) ────

    configure_sabnzbd(SABNZBD, SABNZBD_KEY, f"{B}/sabnzbd/config/sabnzbd.ini")

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
            warn("SABnzbd key not found — skipping")
        add_remote_path_mapping(SONARR, SONARR_KEY, "api/v3",
                                QB_HOST, "/downloads", "/data/Downloads/Torrents")
        enable_hardlinks(SONARR, SONARR_KEY, "api/v3")
        if ARR_USER and ARR_PASS:
            configure_auth(SONARR, SONARR_KEY, "api/v3", ARR_USER, ARR_PASS)

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
            warn("SABnzbd key not found — skipping")
        add_remote_path_mapping(RADARR, RADARR_KEY, "api/v3",
                                QB_HOST, "/downloads", "/data/Downloads/Torrents")
        enable_hardlinks(RADARR, RADARR_KEY, "api/v3")
        if ARR_USER and ARR_PASS:
            configure_auth(RADARR, RADARR_KEY, "api/v3", ARR_USER, ARR_PASS)

    # ── Lidarr ────────────────────────────────────────────────────────────────

    section("Lidarr")
    if not LIDARR_KEY:
        fail("API key not found — is the container running?")
    elif wait_ready("Lidarr", LIDARR, LIDARR_KEY, "/api/v1/system/status"):
        # Lidarr root folder requires qualityProfileId and metadataProfileId
        # (Sonarr/Radarr don't need these but accept them harmlessly)
        lidarr_quality_id, _ = get_quality_profile(LIDARR, LIDARR_KEY, "api/v1")
        lidarr_meta_profiles = GET(LIDARR, LIDARR_KEY, "/api/v1/metadataprofile") or []
        lidarr_meta_id = lidarr_meta_profiles[0]['id'] if lidarr_meta_profiles else 1
        add_root_folder(LIDARR, LIDARR_KEY, "api/v1", "/data/Media/Music", {
            "defaultQualityProfileId":  lidarr_quality_id or 1,
            "defaultMetadataProfileId": lidarr_meta_id,
        })
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
            warn("SABnzbd key not found — skipping")
        add_remote_path_mapping(LIDARR, LIDARR_KEY, "api/v1",
                                QB_HOST, "/downloads", "/data/Downloads/Torrents")
        enable_hardlinks(LIDARR, LIDARR_KEY, "api/v1")
        if ARR_USER and ARR_PASS:
            configure_auth(LIDARR, LIDARR_KEY, "api/v1", ARR_USER, ARR_PASS)

    # ── Prowlarr ──────────────────────────────────────────────────────────────

    section("Prowlarr")
    if not PROWLARR_KEY:
        fail("API key not found — is the container running?")
    elif wait_ready("Prowlarr", PROWLARR, PROWLARR_KEY, "/api/v1/system/status"):
        if SONARR_KEY:
            add_prowlarr_app(PROWLARR, PROWLARR_KEY, "Sonarr", "Sonarr",
                             "SonarrSettings", SONARR_INT, SONARR_KEY,
                             [5000, 5010, 5020, 5030, 5040, 5045, 5050, 5070])
        if RADARR_KEY:
            add_prowlarr_app(PROWLARR, PROWLARR_KEY, "Radarr", "Radarr",
                             "RadarrSettings", RADARR_INT, RADARR_KEY,
                             [2000, 2010, 2020, 2030, 2040, 2045, 2050, 2060])
        if LIDARR_KEY:
            add_prowlarr_app(PROWLARR, PROWLARR_KEY, "Lidarr", "Lidarr",
                             "LidarrSettings", LIDARR_INT, LIDARR_KEY,
                             [3000, 3010, 3030, 3040, 3050])
        if ARR_USER and ARR_PASS:
            configure_auth(PROWLARR, PROWLARR_KEY, "api/v1", ARR_USER, ARR_PASS)

    # ── Bazarr ────────────────────────────────────────────────────────────────

    configure_bazarr(BAZARR, BAZARR_KEY, SONARR_KEY, RADARR_KEY,
                     f"{B}/bazarr/config",
                     username=ARR_USER or None, password=ARR_PASS or None)

    # ── Seerr ─────────────────────────────────────────────────────────────────

    configure_seerr(SEERR, SEERR_KEY, SONARR, SONARR_KEY, RADARR, RADARR_KEY,
                    username=ARR_USER or None, password=ARR_PASS or None)

    # ── Config files ──────────────────────────────────────────────────────────

    section("Unpackerr")
    write_config_file("Unpackerr",
        f"{B}/unpackerr/config/unpackerr.conf",
        UNPACKERR_CONF.format(
            sonarr_key=SONARR_KEY or 'REPLACE_WITH_SONARR_KEY',
            radarr_key=RADARR_KEY or 'REPLACE_WITH_RADARR_KEY',
            lidarr_key=LIDARR_KEY or 'REPLACE_WITH_LIDARR_KEY',
        ))
    if SONARR_KEY or RADARR_KEY:
        warn("Restart unpackerr:  docker-compose restart unpackerr")

    section("Recyclarr")
    write_config_file("Recyclarr",
        f"{B}/recyclarr/config/recyclarr.yml",
        RECYCLARR_CONF.format(
            sonarr_key=SONARR_KEY or 'REPLACE_WITH_SONARR_KEY',
            radarr_key=RADARR_KEY or 'REPLACE_WITH_RADARR_KEY',
        ))
    if SONARR_KEY or RADARR_KEY:
        warn("Recyclarr is a starter config — customise quality profiles in the wiki")

    # ── Summary ───────────────────────────────────────────────────────────────

    print(f"\n{'═' * 52}")
    if errors == 0:
        print(f"{GREEN}{BOLD}  All done — no errors.{RESET}")
    else:
        print(f"{RED}{BOLD}  Done with {errors} error(s) — review output above.{RESET}")

    print(f"""
  Still needs manual setup:
  • Prowlarr    http://{LAN_IP}:49150  → add your indexers
  • qBittorrent http://{LAN_IP}:49156  → Settings → Downloads → watched folder:
                                         /downloads/ToFetch
  • Seerr       http://{LAN_IP}:5056   → Plex connection (needs your Plex token)
  • Tautulli    http://{LAN_IP}:8181   → full setup wizard (needs Plex token)
""")
    print('═' * 52)
    sys.exit(0 if errors == 0 else 1)


if __name__ == '__main__':
    main()
