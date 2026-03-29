#!/bin/bash
# ── NordVPN WireGuard Key Setup ──
#
# Fetches your WireGuard private key from the NordVPN API and writes
# it into the .env file automatically.
#
# Usage:
#   bash /volume1/docker/media/setup-nordvpn.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "  ✘ .env file not found at $ENV_FILE"
    exit 1
fi

# Read access token from .env if set
ACCESS_TOKEN=$(grep -m1 '^NORDVPN_ACCESS_TOKEN=' "$ENV_FILE" | cut -d'=' -f2)

if [ -z "$ACCESS_TOKEN" ]; then
    echo ""
    echo "  NORDVPN_ACCESS_TOKEN not set in .env — enter it manually."
    echo "  To get your access token:"
    echo "  1. Go to https://my.nordaccount.com/dashboard/nordvpn/manual-configuration/"
    echo "  2. Click Access Tokens → Generate new token"
    echo "  3. Paste it below (or add it to .env to skip this prompt next time)"
    echo ""
    read -rp "  NordVPN access token: " ACCESS_TOKEN
fi

if [ -z "$ACCESS_TOKEN" ]; then
    echo "  ✘ No token provided."
    exit 1
fi

echo ""
echo "  Fetching private key from NordVPN API..."
PRIVATE_KEY=$(curl -s -u "token:$ACCESS_TOKEN" https://api.nordvpn.com/v1/users/services/credentials | grep -o '"nordlynx_private_key":"[^"]*"' | cut -d'"' -f4)

if [ -z "$PRIVATE_KEY" ]; then
    echo "  ✘ Failed to fetch private key. Check your access token and try again."
    exit 1
fi

echo "  ✔ Private key retrieved."

# WireGuard private keys are 32 bytes = 44 base64 chars with padding.
# NordVPN's API sometimes returns 43 chars (missing trailing =). Pad it.
if [ ${#PRIVATE_KEY} -eq 43 ]; then
    PRIVATE_KEY="${PRIVATE_KEY}="
    echo "  ℹ Key was 43 chars — padded to 44 (NordVPN API omits trailing = on some accounts)"
fi

KEY_LEN=${#PRIVATE_KEY}
if [ "$KEY_LEN" -ne 44 ]; then
    echo "  ✘ Key length is $KEY_LEN — expected 44. The API may have returned an unexpected format."
    exit 1
fi

# Update NORDVPN_PRIVATE_KEY in .env
sed -i "s|NORDVPN_PRIVATE_KEY=.*|NORDVPN_PRIVATE_KEY=$PRIVATE_KEY|" "$ENV_FILE"

echo "  ✔ .env updated with private key (44 chars)."
