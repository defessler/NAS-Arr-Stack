#!/usr/bin/env python3
"""
fix-plex-paths.py — Update Plex library folder paths before first boot

Directly edits the Plex SQLite database to update library folder paths.
Run this BEFORE starting the Plex container — Plex will boot with the
correct paths already in place, no API or rescan needed.

Old paths (stored by native Plex package, host filesystem):
    /volume1/Data/Media/Movies
    /volume1/Data/Media/TV Shows
    /volume1/Data/Media/Anime/Movies
    /volume1/Data/Media/Anime/TV Shows
    /volume1/Data/Media/Music

New paths (inside the Docker container via /media mount):
    /media/Movies
    /media/TV Shows
    /media/Anime/Movies
    /media/Anime/TV Shows
    /media/Music

Usage:
    python3 fix-plex-paths.py           # dry run — shows what would change
    python3 fix-plex-paths.py --apply   # apply the changes
"""

import os
import shutil
import sqlite3
import sys
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────

DB_PATH = ("/volume1/docker/media/plex/config"
           "/Library/Application Support"
           "/Plex Media Server/Plug-in Support/Databases"
           "/com.plexapp.plugins.library.db")

# Old NAS host path (from native Plex package) → new container path (/media mount)
PATH_MAP = {
    "/volume1/Data/Media/Movies":         "/media/Movies",
    "/volume1/Data/Media/TV Shows":       "/media/TV Shows",
    "/volume1/Data/Media/Anime/Movies":   "/media/Anime/Movies",
    "/volume1/Data/Media/Anime/TV Shows": "/media/Anime/TV Shows",
    "/volume1/Data/Media/Music":          "/media/Music",
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

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    apply = "--apply" in sys.argv

    print(f"\n{BOLD}Plex Library Path Fix{RESET}")
    if not apply:
        print(f"  {YELLOW}Dry run — no changes will be made.{RESET}")
        print(f"  Run with --apply to apply.\n")
    else:
        print(f"  {GREEN}Applying changes.{RESET}\n")

    # ── Check database exists ─────────────────────────────────────────────────

    if not os.path.exists(DB_PATH):
        print(f"{RED}Error:{RESET} Plex database not found at:")
        print(f"  {DB_PATH}")
        print("\nMake sure Plex has started at least once to initialise its database.")
        sys.exit(1)

    # ── Backup before touching anything ──────────────────────────────────────

    if apply:
        backup = DB_PATH + ".bak." + datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(DB_PATH, backup)
        print(f"  Backup: {os.path.basename(backup)}")

    # ── Read current paths ────────────────────────────────────────────────────

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # section_locations holds the folder path for each library
    cur.execute("SELECT id, root_path FROM section_locations")
    rows = cur.fetchall()

    changes_needed = 0
    changes_done   = 0

    print()
    for row_id, root_path in rows:
        new_path = PATH_MAP.get(root_path)
        if new_path:
            changes_needed += 1
            info(f"{root_path}")
            print(f"       → {new_path}")
            if apply:
                cur.execute(
                    "UPDATE section_locations SET root_path = ? WHERE id = ?",
                    (new_path, row_id)
                )
                changes_done += 1
        else:
            print(f"  {root_path}  (no change)")

    print()

    if apply and changes_done > 0:
        con.commit()
    con.close()

    # ── Summary ───────────────────────────────────────────────────────────────

    if changes_needed == 0:
        print("All library paths are already correct — nothing to do.")
    elif not apply:
        print(f"{YELLOW}{changes_needed} path(s) would be updated.{RESET}  Run with --apply to apply.")
    else:
        ok(f"{changes_done} path(s) updated.")
        print()
        print("You can now start Plex:")
        print("  docker-compose up -d plex")


if __name__ == "__main__":
    main()
