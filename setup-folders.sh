#!/bin/bash
# ── Media Stack Folder Setup ──
#
# Creates all required directories for the stack and sets correct ownership.
# Safe to run multiple times — skips folders that already exist.
#
# Usage:
#   sudo bash /volume1/docker/media/setup-folders.sh

PUID=1034
PGID=100

# ── Config directories ─────────────────────────────────────────────────────────

CONFIG_DIRS=(
    /volume1/docker/media/plex/config
    /volume1/docker/media/tautulli/config
    /volume1/docker/media/seerr/config
    /volume1/docker/media/prowlarr/config
    /volume1/docker/media/sonarr/config
    /volume1/docker/media/radarr/config
    /volume1/docker/media/bazarr/config
    /volume1/docker/media/lidarr/config
    /volume1/docker/media/qbittorrent/config
    /volume1/docker/media/sabnzbd/config
    /volume1/docker/media/sabnzbd/Downloads/incomplete
    /volume1/docker/media/recyclarr/config
    /volume1/docker/media/unpackerr/config
)

# ── Media and download directories ────────────────────────────────────────────

DATA_DIRS=(
    /volume1/Data/Media/Movies
    /volume1/Data/Media/TV\ Shows
    /volume1/Data/Media/Anime/Movies
    /volume1/Data/Media/Anime/TV\ Shows
    /volume1/Data/Media/Music
    /volume1/Data/Downloads/Torrents/InProgress
    /volume1/Data/Downloads/Usenet
)

# ── Create and chown ───────────────────────────────────────────────────────────

echo "Creating config directories..."
for dir in "${CONFIG_DIRS[@]}"; do
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        echo "  Created: $dir"
    else
        echo "  Exists:  $dir"
    fi
    chown -R $PUID:$PGID "$dir"
done

echo ""
echo "Creating data directories..."
for dir in "${DATA_DIRS[@]}"; do
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        echo "  Created: $dir"
    else
        echo "  Exists:  $dir"
    fi
    chown -R $PUID:$PGID "$dir"
done

echo ""
echo "Done. All folders are ready."
