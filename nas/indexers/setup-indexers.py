#!/usr/bin/env python3
"""
setup-indexers.py — Add indexers to Prowlarr

Adds a curated set of public torrent indexers automatically.
Usenet indexers are added if their API key is set in .env.
Private torrent trackers (AvistaZ etc.) are added if credentials are in .env.

Safe to re-run — skips indexers that are already added.

Usage:
    python3 /volume1/docker/media/indexers/setup-indexers.py

.env keys for usenet (all Newznab-compatible):
    NZBGEEK_API_KEY=
    NZBFINDER_API_KEY=
    DRUNKENSLUG_API_KEY=
    NZBPLANET_API_KEY=
    NZBCAT_API_KEY=
    DOGNZB_API_KEY=
    NINJACZENTRAL_API_KEY=
    TABULARASA_API_KEY=

.env keys for private torrent trackers:
    AVISTAZ_USER=          AVISTAZ_PASS=        # Asian movies/TV (private)
    ANIMEBYTES_USER=       ANIMEBYTES_PASS=     # Anime (invite-only)
    ANIMETORRENTS_USER=    ANIMETORRENTS_PASS=  # Anime (private)
"""

import json
import os
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# ── Terminal colours ──────────────────────────────────────────────────────────

GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

errors = 0

def ok(msg):   print(f"  {GREEN}✔{RESET}  {msg}")
def skip(msg): print(f"  –  {msg}")
def warn(msg): print(f"  {YELLOW}!{RESET}  {msg}")
def fail(msg):
    global errors; errors += 1
    print(f"  {RED}✘{RESET}  {msg}")
def section(title):
    print(f"\n{BOLD}━━━ {title} {'━' * max(0, 52 - len(title))}{RESET}")

# ── Indexer definitions ───────────────────────────────────────────────────────
#
# Each entry: (display_name, implementation, extra_fields_dict)
# extra_fields_dict maps Prowlarr field names to values — only include fields
# that differ from the schema defaults.

PUBLIC_TORRENT_INDEXERS = [
    # ── General ───────────────────────────────────────────────────────────────
    "1337x",
    "YTS",
    "EZTV",
    "TorrentGalaxy",
    "LimeTorrents",
    "The Pirate Bay",
    "Knaben",            # Large Norwegian index, good general coverage
    # ── TV ────────────────────────────────────────────────────────────────────
    "ShowRSS",
    # ── Anime / Japanese ──────────────────────────────────────────────────────
    "Nyaa",              # Primary anime tracker
    "SubsPlease",        # Simulcast rips
    "Tokyo Toshokan",    # Japanese media (long-running, broad)
]

# Newznab-compatible usenet indexers.
# Each entry: (display_name, api_url, env_key_name)
USENET_INDEXERS = [
    ("NZBGeek",        "https://api.nzbgeek.info",        "NZBGEEK_API_KEY"),
    ("NZBFinder",      "https://www.nzbfinder.ws",         "NZBFINDER_API_KEY"),
    ("DrunkenSlug",    "https://api.drunkenslug.com",      "DRUNKENSLUG_API_KEY"),
    ("NZBPlanet",      "https://api.nzbplanet.net",        "NZBPLANET_API_KEY"),
    ("NZBcat",         "https://nzb.cat",                  "NZBCAT_API_KEY"),
    ("DogNZB",         "https://api.dognzb.cr",            "DOGNZB_API_KEY"),
    ("NinjaCentral",   "https://www.ninjacentral.co.za",   "NINJACZENTRAL_API_KEY"),
    ("Tabula Rasa",    "https://www.tabula-rasa.pw",       "TABULARASA_API_KEY"),
]

# Private torrent trackers — added only if credentials are set in .env.
# Each entry: (display_name, prowlarr_implementation, {field: env_var, ...})
# These are the best sources for Korean and Japanese content.
PRIVATE_TORRENT_INDEXERS = [
    # Asian content
    ("AvistaZ",         "AvistaZ",         {"username": "AVISTAZ_USER",       "password": "AVISTAZ_PASS"}),
    ("HHD",             "HHD",             {"apiKey":   "HHD_API_KEY"}),        # Korean movies/dramas — get key at homiehelpdesk.net
    # Anime
    ("AnimeTorrents",   "AnimeTorrents",   {"username": "ANIMETORRENTS_USER", "password": "ANIMETORRENTS_PASS"}),
    ("AnimeBytes",      "AnimeBytes",      {"username": "ANIMEBYTES_USER",    "password": "ANIMEBYTES_PASS"}),
]

# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _headers(key):
    return {'X-Api-Key': key, 'Content-Type': 'application/json',
            'User-Agent': 'setup-indexers/1.0'}

def _request(url, headers, method='GET', data=None):
    """Returns (result, status_code, error_body). Never prints."""
    body = json.dumps(data).encode() if data is not None else None
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=15) as resp:
            content = resp.read()
            return json.loads(content) if content else {}, resp.status, None
    except HTTPError as e:
        return None, e.code, e.read().decode(errors='replace')
    except URLError:
        return None, None, None

def _prowlarr_error(body):
    """Extract a clean single-line error message from a Prowlarr JSON error body."""
    try:
        errors = json.loads(body)
        msgs = [e.get('errorMessage', '') for e in (errors if isinstance(errors, list) else [])]
        msgs = [m for m in msgs if m]
        return msgs[0] if msgs else body[:120]
    except Exception:
        return (body or '')[:120]

def GET(base, key, path):
    result, _, _ = _request(f"{base}{path}", _headers(key))
    return result

def POST(base, key, path, data):
    result, status, err = _request(f"{base}{path}", _headers(key), 'POST', data)
    return result, status, err

def PUT(base, key, path, data):
    result, _, _ = _request(f"{base}{path}", _headers(key), 'PUT', data)
    return result

# ── Wait for Prowlarr ─────────────────────────────────────────────────────────

def wait_ready(base, key, retries=24, interval=5):
    sys.stdout.write("  Waiting for Prowlarr ")
    sys.stdout.flush()
    for _ in range(retries):
        if GET(base, key, "/api/v1/system/status") is not None:
            print(f"{GREEN}✔{RESET}"); return True
        sys.stdout.write("."); sys.stdout.flush()
        time.sleep(interval)
    print(f"{RED}✘ timed out{RESET}"); return False

# ── Add indexer ───────────────────────────────────────────────────────────────

def _post_indexer(base, key, name, schema):
    """POST the indexer schema; classify 400 errors into clean messages."""
    result, status, err = POST(base, key, "/api/v1/indexer", schema)
    if result is not None:
        ok(f"{name}")
        return
    if status == 400 and err:
        err_lower = err.lower()
        if 'unique' in err_lower:
            skip(f"{name} (already added)")
        elif 'cloudflare' in err_lower or 'blocked by' in err_lower:
            warn(f"{name}: added but unreachable — blocked by CloudFlare")
        elif 'redirect' in err_lower:
            warn(f"{name}: added but domain is redirecting (may be down)")
        elif 'unable to connect' in err_lower or 'unable to access' in err_lower:
            warn(f"{name}: added but currently unreachable — {_prowlarr_error(err)}")
        else:
            fail(f"{name}: {_prowlarr_error(err)}")
    else:
        fail(f"{name}: request failed (HTTP {status})")

def _find_schema(name, schemas):
    """Find a schema by name, falling back to prefix match for common variations
    like 'Nyaa' → 'Nyaa.si' or 'TorrentGalaxy' → 'TorrentGalaxyClone'."""
    name_lower = name.lower()
    # 1. Exact case-insensitive
    s = next((s for s in schemas if s.get('name', '').lower() == name_lower), None)
    if s:
        return s, name
    # 2. Schema name starts with our name (e.g. "Nyaa" → "Nyaa.si")
    candidates = [s for s in schemas
                  if s.get('name', '').lower().startswith(name_lower)
                  and len(s.get('name', '')) > len(name)]
    if len(candidates) == 1:
        return candidates[0], candidates[0]['name']
    # 3. Our name starts with schema name (e.g. user typed longer name)
    candidates = [s for s in schemas
                  if name_lower.startswith(s.get('name', '').lower())
                  and s.get('name', '')]
    if len(candidates) == 1:
        return candidates[0], candidates[0]['name']
    return None, None

def add_indexer(base, key, name, schemas, existing_names):
    if name.lower() in existing_names:
        skip(f"{name} (already added)"); return

    schema, resolved_name = _find_schema(name, schemas)
    if schema is None:
        needle = name.lower()
        suggestions = [s['name'] for s in schemas
                       if needle in s.get('name', '').lower()
                       or s.get('name', '').lower() in needle]
        hint = f" — did you mean: {', '.join(suggestions[:5])}" if suggestions else ""
        fail(f"{name}: not found in Prowlarr{hint}")
        return

    if resolved_name != name:
        # Re-check with the resolved name before adding
        if resolved_name.lower() in existing_names:
            skip(f"{name} → {resolved_name} (already added)"); return

    schema['name'] = resolved_name
    schema['enable'] = True
    schema['appProfileId'] = 1
    display = f"{name} → {resolved_name}" if resolved_name != name else name
    _post_indexer(base, key, display, schema)

def add_private_indexer(base, key, name, implementation, field_map, schemas, existing_names):
    if name.lower() in existing_names:
        skip(f"{name} (already added)"); return

    schema, resolved_name = _find_schema(implementation, schemas)
    if schema is None:
        fail(f"{name}: implementation '{implementation}' not found in Prowlarr")
        return

    schema['name'] = name
    schema['enable'] = True
    schema['appProfileId'] = 1

    fm = {f['name']: i for i, f in enumerate(schema.get('fields', []))}
    for fname, fval in field_map.items():
        if fname in fm:
            schema['fields'][fm[fname]]['value'] = fval

    _post_indexer(base, key, name, schema)

def apply_public_settings(base, key, public_names,
                           priority=50, seed_time_mins=1):
    """Set priority and seed time on all public (no-login) indexers.
    Runs after adds so it also covers indexers added in previous runs."""
    indexers = GET(base, key, "/api/v1/indexer") or []
    public_lower = {n.lower() for n in public_names}

    for indexer in indexers:
        if indexer.get('name', '').lower() not in public_lower:
            continue

        changed = False

        if indexer.get('priority') != priority:
            indexer['priority'] = priority
            changed = True

        for field in indexer.get('fields', []):
            if field.get('name') == 'seedCriteria.seedTime':
                if field.get('value') != seed_time_mins:
                    field['value'] = seed_time_mins
                    changed = True

        if not changed:
            skip(f"{indexer['name']} (priority={priority}, seedTime={seed_time_mins}m)")
            continue

        result = PUT(base, key, f"/api/v1/indexer/{indexer['id']}", indexer)
        if result:
            ok(f"{indexer['name']}: priority={priority}, seedTime={seed_time_mins}m")
        else:
            fail(f"{indexer['name']}: failed to update settings")

def add_newznab(base, key, name, api_url, api_key, schemas, existing_names):
    if name.lower() in existing_names:
        skip(f"{name} (already added)"); return

    schema = next((s for s in schemas
                   if s.get('implementation', '').lower() == 'newznab'), None)
    if schema is None:
        fail(f"{name}: Newznab implementation not found"); return

    schema = json.loads(json.dumps(schema))  # deep copy — reused across calls
    schema['name'] = name
    schema['enable'] = True
    schema['appProfileId'] = 1

    fm = {f['name']: i for i, f in enumerate(schema.get('fields', []))}
    for fname, fval in [('baseUrl', api_url), ('apiKey', api_key)]:
        if fname in fm:
            schema['fields'][fm[fname]]['value'] = fval

    _post_indexer(base, key, name, schema)

# ── Read .env ─────────────────────────────────────────────────────────────────

def read_env(path):
    env = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, _, v = line.partition('=')
                v = v.split('#')[0].strip()
                if v:
                    env[k.strip()] = v
    except FileNotFoundError:
        pass
    return env

def read_env_merged(script_dir):
    # .env lives in nas/ — walk up if this script is in a subdirectory
    candidates = [script_dir, os.path.dirname(script_dir)]
    env_dir = next((d for d in candidates if os.path.exists(os.path.join(d, '.env'))), script_dir)
    return read_env(os.path.join(env_dir, '.env'))

def read_arr_key(config_xml):
    import xml.etree.ElementTree as ET
    try:
        return ET.parse(config_xml).find('ApiKey').text
    except Exception:
        return None

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    script_dir = os.path.dirname(os.path.realpath(__file__))
    env        = read_env_merged(script_dir)

    LAN_IP       = env.get('LAN_IP', '')
    PROWLARR_KEY = env.get('PROWLARR_API_KEY') or read_arr_key('/volume1/docker/media/prowlarr/config/config.xml')

    if not LAN_IP:
        print("Error: LAN_IP not set in .env"); sys.exit(1)
    if not PROWLARR_KEY:
        print("Error: Prowlarr API key not found — is the container running?")
        sys.exit(1)

    PROWLARR = f"http://{LAN_IP}:49150"

    print(f"\n{BOLD}╔══════════════════════════════════════════╗")
    print("║        Prowlarr Indexer Setup            ║")
    print(f"╚══════════════════════════════════════════╝{RESET}")

    if not wait_ready(PROWLARR, PROWLARR_KEY):
        sys.exit(1)

    # Fetch schemas once — passed to all add_* calls to avoid repeated requests
    schemas = GET(PROWLARR, PROWLARR_KEY, "/api/v1/indexer/schema") or []
    if not schemas:
        print(f"{RED}Error: could not fetch indexer schemas from Prowlarr{RESET}")
        sys.exit(1)

    # Get existing indexer names (lowercase for case-insensitive dedup)
    existing = GET(PROWLARR, PROWLARR_KEY, "/api/v1/indexer") or []
    existing_names = {i['name'].lower() for i in existing}

    # ── Public torrent indexers ───────────────────────────────────────────────

    section("Public Torrent Indexers")
    for name in PUBLIC_TORRENT_INDEXERS:
        add_indexer(PROWLARR, PROWLARR_KEY, name, schemas, existing_names)

    # ── Usenet indexers ───────────────────────────────────────────────────────

    section("Usenet Indexers")
    usenet_added = 0
    for name, api_url, env_key in USENET_INDEXERS:
        api_key = env.get(env_key, '')
        if not api_key:
            skip(f"{name} (no {env_key} in .env)"); continue
        add_newznab(PROWLARR, PROWLARR_KEY, name, api_url, api_key, schemas, existing_names)
        usenet_added += 1

    if usenet_added == 0:
        warn("No usenet API keys found in .env — add NZBGEEK_API_KEY etc. to enable")

    # ── Private torrent trackers ──────────────────────────────────────────────

    section("Private Torrent Trackers")
    private_added = 0
    for name, implementation, field_env_map in PRIVATE_TORRENT_INDEXERS:
        creds = {field: env.get(env_var, '')
                 for field, env_var in field_env_map.items()}
        missing = [env_var for field, env_var in field_env_map.items()
                   if not env.get(env_var)]
        if missing:
            skip(f"{name} (add {', '.join(missing)} to .env to enable)")
            continue
        add_private_indexer(PROWLARR, PROWLARR_KEY, name, implementation,
                            creds, schemas, existing_names)
        private_added += 1

    if private_added == 0:
        warn("No private tracker credentials in .env — see header comments to enable")

    # ── Public indexer settings ───────────────────────────────────────────────

    section("Public Indexer Settings")
    apply_public_settings(PROWLARR, PROWLARR_KEY, PUBLIC_TORRENT_INDEXERS)

    # ── Summary ───────────────────────────────────────────────────────────────

    print(f"\n{'═' * 52}")
    if errors == 0:
        print(f"{GREEN}{BOLD}  All done — no errors.{RESET}")
    else:
        print(f"{RED}{BOLD}  Done with {errors} error(s) — review output above.{RESET}")
    print(f"{'═' * 52}\n")
    sys.exit(0 if errors == 0 else 1)


if __name__ == '__main__':
    main()
