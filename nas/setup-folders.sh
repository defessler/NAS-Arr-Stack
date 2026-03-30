#!/bin/bash
# ── Media Stack Folder Setup ──
#
# Creates all required directories for the stack and sets correct ownership.
# Safe to run multiple times — skips folders that already exist.
#
# Usage:
#   sudo bash /volume1/docker/media/setup-folders.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

# Read PUID/PGID from .env — required, no fallback
if [ ! -f "$ENV_FILE" ]; then
    echo "Error: .env not found at $ENV_FILE"
    echo "Run setup-nordvpn.sh first, or create .env with PUID and PGID set."
    exit 1
fi

PUID=$(grep -m1 '^PUID=' "$ENV_FILE" | cut -d'=' -f2-)
PGID=$(grep -m1 '^PGID=' "$ENV_FILE" | cut -d'=' -f2-)

if [ -z "$PUID" ] || [ -z "$PGID" ]; then
    echo "Error: PUID and PGID must both be set in $ENV_FILE"
    exit 1
fi

echo "Using PUID=$PUID PGID=$PGID (from ${ENV_FILE})"
echo ""

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
    /volume1/docker/media/qbittorrent/config/.cache/qBittorrent
    /volume1/docker/media/qbittorrent/custom-cont-init.d
    /volume1/docker/media/sabnzbd/config
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
    /volume1/Data/Downloads/Torrents/ToFetch
    /volume1/Data/Downloads/Torrents/InProgress
    /volume1/Data/Downloads/Torrents/Completed/tv-sonarr
    /volume1/Data/Downloads/Torrents/Completed/radarr
    /volume1/Data/Downloads/Usenet/incomplete
    /volume1/Data/Downloads/Usenet/complete
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
    chmod -R 755 "$dir"
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
    chmod -R 755 "$dir"
done

echo ""
echo "Deploying qBittorrent credential init script..."
INIT_DST="/volume1/docker/media/qbittorrent/custom-cont-init.d/set-credentials.sh"
cat > "$INIT_DST" << 'INITEOF'
#!/bin/bash
# Sets qBittorrent WebUI credentials from environment variables.
# Runs inside the container at startup via /custom-cont-init.d.
# Only runs once — uses a sentinel file so container restarts never
# overwrite the config (which would cause qBittorrent to lose its
# torrent list from BT_Backup on next boot).

[ -z "$WEBUI_PASSWORD" ] && exit 0

CONF_DIR="/config/qBittorrent"
CONF_FILE="$CONF_DIR/qBittorrent.conf"
SENTINEL="/config/.credentials-set"

# Already initialised — never touch the config again
if [ -f "$SENTINEL" ]; then
    echo "[init] qBittorrent already initialised — skipping"
    exit 0
fi

mkdir -p "$CONF_DIR"

USERNAME="${WEBUI_USERNAME:-admin}"

# Generate PBKDF2-HMAC-SHA512 hash — qBittorrent's WebUI password format
HASH=$(python3 <<'PYEOF'
import hashlib, os, base64
password = os.environ.get('WEBUI_PASSWORD', '').encode('utf-8')
salt = os.urandom(16)
key = hashlib.pbkdf2_hmac('sha512', password, salt, 100000)
print('@ByteArray(' + base64.b64encode(salt).decode() + ':' + base64.b64encode(key).decode() + ')')
PYEOF
)

if [ -z "$HASH" ]; then
    echo "[init] WARNING: failed to generate password hash — credentials not set"
    exit 1
fi

if [ ! -f "$CONF_FILE" ]; then
    printf '[LegalNotice]\nAccepted=true\n\n[BitTorrent]\nSession\DefaultSavePath=/downloads/Completed\nSession\TempPath=/downloads/InProgress\nSession\TempPathEnabled=true\n\n[Preferences]\nDownloads\SavePath=/downloads/Completed\nDownloads\TempPath=/downloads/InProgress\nDownloads\TempPathEnabled=true\nWebUI\\Username=%s\nWebUI\\Password_PBKDF2="%s"\nWebUI\\AuthSubnetWhitelistEnabled=true\nWebUI\\AuthSubnetWhitelist=192.168.1.0/24\n' \
        "$USERNAME" "$HASH" > "$CONF_FILE"
else
    printf '\nWebUI\\Username=%s\nWebUI\\Password_PBKDF2="%s"\nWebUI\\AuthSubnetWhitelistEnabled=true\nWebUI\\AuthSubnetWhitelist=192.168.1.0/24\n' \
        "$USERNAME" "$HASH" >> "$CONF_FILE"
fi

# Mark as done — this file's presence prevents any future runs
touch "$SENTINEL"
echo "[init] qBittorrent WebUI credentials and download paths configured (user: $USERNAME)"
INITEOF
chown $PUID:$PGID "$INIT_DST"
chmod 755 "$INIT_DST"
echo "  Deployed: $INIT_DST"

echo ""
echo "Done. All folders are ready."
