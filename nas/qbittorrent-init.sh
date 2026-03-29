#!/bin/bash
# ── qBittorrent Credential Init ──
#
# Runs inside the qBittorrent container at startup via /custom-cont-init.d.
# Sets the WebUI username and password from WEBUI_USERNAME / WEBUI_PASSWORD
# environment variables. Only runs once — skips if credentials are already set.

[ -z "$WEBUI_PASSWORD" ] && exit 0

CONF_DIR="/config/qBittorrent"
CONF_FILE="$CONF_DIR/qBittorrent.conf"

mkdir -p "$CONF_DIR"

# Don't overwrite credentials that have already been configured
if grep -q "Password_PBKDF2" "$CONF_FILE" 2>/dev/null; then
    echo "[init] qBittorrent credentials already set — skipping"
    exit 0
fi

USERNAME="${WEBUI_USERNAME:-admin}"

# Generate PBKDF2-HMAC-SHA512 hash — this is qBittorrent's WebUI password format
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
    # No config yet — create a minimal one with credentials and legal notice pre-accepted
    printf '[LegalNotice]\nAccepted=true\n\n[Preferences]\nWebUI\\Username=%s\nWebUI\\Password_PBKDF2="%s"\n' \
        "$USERNAME" "$HASH" > "$CONF_FILE"
else
    # Config exists but has no password — append credentials
    printf '\nWebUI\\Username=%s\nWebUI\\Password_PBKDF2="%s"\n' \
        "$USERNAME" "$HASH" >> "$CONF_FILE"
fi

echo "[init] qBittorrent WebUI credentials configured (user: $USERNAME)"
