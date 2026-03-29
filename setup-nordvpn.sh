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

echo ""
echo "  To get your access token:"
echo "  1. Go to https://my.nordaccount.com/dashboard/nordvpn/manual-configuration/"
echo "  2. Click Access Tokens → Generate new token"
echo "  3. Paste it below"
echo ""
read -rp "  NordVPN access token: " ACCESS_TOKEN

if [ -z "$ACCESS_TOKEN" ]; then
    echo "  ✘ No token entered."
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

# Update NORDVPN_PRIVATE_KEY in .env
sed -i "s|NORDVPN_PRIVATE_KEY=.*|NORDVPN_PRIVATE_KEY=$PRIVATE_KEY|" "$ENV_FILE"

echo "  ✔ .env updated with private key."
