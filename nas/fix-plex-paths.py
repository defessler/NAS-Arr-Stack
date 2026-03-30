#!/usr/bin/env python3
"""
fix-plex-paths.py — Update Plex library folder paths

Updates library folder locations after the Plex volume mount changed
from individual folders to a single /media mount.

Old mounts:
    /volume1/Data/Media/Movies       → /movies
    /volume1/Data/Media/TV Shows     → /tv/shows
    /volume1/Data/Media/Anime/Movies → /anime/movies
    /volume1/Data/Media/Anime/TV     → /anime/tv
    /volume1/Data/Media/Music        → /music  (if it was mounted)

New mount:
    /volume1/Data/Media              → /media
    So paths become /media/Movies, /media/TV Shows, etc.

Usage:
    python3 fix-plex-paths.py           # dry run — shows what would change
    python3 fix-plex-paths.py --apply   # apply the changes
"""

import json
import os
import sys
import xml.etree.ElementTree as ET
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode, quote

# ── Config ────────────────────────────────────────────────────────────────────

PLEX_BASE = "http://localhost:32400"

PREFS_PATH = ("/volume1/docker/media/plex/config"
              "/Library/Application Support"
              "/Plex Media Server/Preferences.xml")

# Old container path → new container path
PATH_MAP = {
    "/movies":       "/media/Movies",
    "/tv/shows":     "/media/TV Shows",
    "/anime/movies": "/media/Anime/Movies",
    "/anime/tv":     "/media/Anime/TV Shows",
    "/music":        "/media/Music",
}

# ── Colours ───────────────────────────────────────────────────────────────────

GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):   print(f"  {GREEN}✔{RESET}  {msg}")
def fail(msg): print(f"  {RED}✘{RESET}  {msg}")
def info(msg): print(f"  {YELLOW}→{RESET}  {msg}")

# ── Plex API helpers ──────────────────────────────────────────────────────────

def plex_headers(token):
    return {
        "X-Plex-Token":             token,
        "X-Plex-Client-Identifier": "fix-plex-paths",
        "X-Plex-Product":           "fix-plex-paths",
        "Accept":                   "application/json",
    }

def plex_get(token, path):
    req = Request(f"{PLEX_BASE}{path}", headers=plex_headers(token))
    try:
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except HTTPError as e:
        print(f"    HTTP {e.code}: {e.read().decode(errors='replace')[:150]}")
        return None
    except Exception as e:
        print(f"    Error: {e}")
        return None

def plex_request(token, method, path):
    req = Request(f"{PLEX_BASE}{path}", headers=plex_headers(token),
                  method=method)
    if method == "POST":
        req.data = b""
    try:
        with urlopen(req, timeout=10) as resp:
            resp.read()
            return True
    except HTTPError as e:
        body = e.read().decode(errors='replace')
        print(f"    HTTP {e.code}: {body[:150]}")
        return False
    except Exception as e:
        print(f"    Error: {e}")
        return False

# ── Token ─────────────────────────────────────────────────────────────────────

def read_plex_token(prefs_path):
    """Read the Plex auth token from Preferences.xml."""
    try:
        root = ET.parse(prefs_path).getroot()
        return root.get("PlexOnlineToken")
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"Error reading Preferences.xml: {e}")
        return None

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    apply = "--apply" in sys.argv

    print(f"\n{BOLD}Plex Library Path Fix{RESET}")
    if not apply:
        print(f"  {YELLOW}Dry run — no changes will be made.{RESET}")
        print(f"  Re-run with --apply to apply changes.\n")
    else:
        print(f"  {GREEN}Applying changes.{RESET}\n")

    # ── Token ─────────────────────────────────────────────────────────────────

    token = read_plex_token(PREFS_PATH)
    if not token:
        print(f"{RED}Error:{RESET} Could not read Plex token from:")
        print(f"  {PREFS_PATH}")
        print("\nMake sure the Plex container is running and has started at least once.")
        sys.exit(1)
    print(f"  Token: {token[:8]}...")

    # ── Fetch libraries ───────────────────────────────────────────────────────

    data = plex_get(token, "/library/sections")
    if not data:
        print(f"\n{RED}Error:{RESET} Could not reach Plex API at {PLEX_BASE}")
        print("  Is the Plex container running?")
        sys.exit(1)

    sections = data.get("MediaContainer", {}).get("Directory", [])
    if not sections:
        print("No libraries found.")
        sys.exit(0)

    changes_needed = 0
    changes_done   = 0

    print()
    for section in sections:
        key       = section["key"]
        title     = section["title"]
        lib_type  = section.get("type", "")
        locations = section.get("Location", [])

        print(f"{BOLD}{title}{RESET}  (key={key}, type={lib_type})")

        for loc in locations:
            old_path = loc["path"]
            new_path = PATH_MAP.get(old_path)

            if new_path:
                changes_needed += 1
                info(f"{old_path}  →  {new_path}")

                if apply:
                    # Add the new path first, then remove the old one
                    add_url  = f"/library/sections/{key}/location?path={quote(new_path, safe='')}"
                    del_url  = f"/library/sections/{key}/location?path={quote(old_path, safe='')}"

                    if plex_request(token, "POST", add_url):
                        ok(f"Added   {new_path}")
                        if plex_request(token, "DELETE", del_url):
                            ok(f"Removed {old_path}")
                            changes_done += 1
                        else:
                            fail(f"Could not remove old path {old_path} — remove it manually in Plex UI")
                    else:
                        fail(f"Could not add {new_path}")
            else:
                print(f"         {old_path}  (no change needed)")

        print()

    # ── Summary ───────────────────────────────────────────────────────────────

    if changes_needed == 0:
        print("All library paths are already correct — nothing to do.")
    elif not apply:
        print(f"{YELLOW}{changes_needed} path(s) need updating.{RESET}  Re-run with --apply to apply.")
    else:
        if changes_done == changes_needed:
            print(f"{GREEN}Done — {changes_done} path(s) updated.{RESET}")
        else:
            print(f"{YELLOW}Done — {changes_done}/{changes_needed} path(s) updated. Review errors above.{RESET}")
        print()
        print("Plex will rescan the updated libraries automatically.")
        print("If libraries still show errors, trigger a manual scan:")
        print("  Plex → Libraries → ⋮ → Scan Library Files")


if __name__ == "__main__":
    main()
