#!/bin/bash
# ── Media Stack Setup ──
#
# Complete first-time setup in one command.
# Safe to re-run — all steps are idempotent.
#
# Usage:
#   sudo bash /volume1/docker/media/setup.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PASS=0
FAIL=0

# ── Helpers ───────────────────────────────────────────────────────────────────

run_step() {
    local step="$1" description="$2"
    shift 2

    echo ""
    echo "┌─────────────────────────────────────────────"
    echo "│ Step $step: $description"
    echo "└─────────────────────────────────────────────"

    if "$@"; then
        echo ""
        echo "  ✔ Step $step complete."
        PASS=$((PASS + 1))
    else
        echo ""
        echo "  ✘ Step $step failed — fix errors above and re-run."
        FAIL=$((FAIL + 1))
    fi
}

abort_if_failed() {
    if [ $FAIL -gt 0 ]; then
        echo ""
        echo "============================================="
        echo "  Setup halted."
        echo "  All steps are safe to re-run after fixing."
        echo "============================================="
        exit 1
    fi
}

wait_for_services() {
    local max_wait=600
    local interval=10
    local elapsed=0
    local services="sonarr radarr lidarr prowlarr sabnzbd bazarr"

    echo ""
    echo "  Waiting for containers to start..."
    echo "  (First run pulls images — this may take several minutes)"
    echo ""

    while [ $elapsed -lt $max_wait ]; do
        local all_up=true
        local status_line="  ${elapsed}s  "

        for svc in $services; do
            local state
            state=$(docker inspect --format='{{.State.Status}}' "$svc" 2>/dev/null || echo "missing")
            if [ "$state" = "running" ]; then
                status_line+="$svc ✔  "
            else
                status_line+="$svc … "
                all_up=false
            fi
        done

        echo "$status_line"

        if $all_up; then
            echo ""
            echo "  ✔ All containers running — waiting 20s for web UIs to initialise..."
            sleep 20
            return 0
        fi

        sleep $interval
        elapsed=$((elapsed + interval))
    done

    echo ""
    echo "  ✘ Containers did not start within ${max_wait}s"
    echo "  Check logs:  docker-compose logs"
    return 1
}

# ── Pre-flight ────────────────────────────────────────────────────────────────

echo "============================================="
echo "  Media Stack Setup"
echo "============================================="
echo "  This script runs the full first-time install."
echo "  Safe to re-run — all steps skip what's already done."

run_step 1 "Set file permissions" \
    bash "$SCRIPT_DIR/setup-chmod.sh"

run_step 2 "Create data and config directories" \
    bash "$SCRIPT_DIR/setup-folders.sh"

run_step 3 "Apply firewall rules" \
    bash "$SCRIPT_DIR/setup-firewall.sh"

echo "  Note: fetches your WireGuard private key from the NordVPN API"
run_step 4 "Fetch NordVPN WireGuard key" \
    bash "$SCRIPT_DIR/setup-nordvpn.sh"

run_step 5 "Validate configuration" \
    bash "$SCRIPT_DIR/setup-validate.sh"

abort_if_failed

# ── Stack ─────────────────────────────────────────────────────────────────────

echo ""
echo "  Note: first run will pull all Docker images — this can take 5-15 minutes"
run_step 6 "Start the stack" \
    bash -c "cd '$SCRIPT_DIR' && docker-compose up -d"

abort_if_failed

wait_for_services || { FAIL=$((FAIL + 1)); abort_if_failed; }

# ── API Configuration ─────────────────────────────────────────────────────────

echo ""
echo "  Note: configuring Sonarr, Radarr, Lidarr, Prowlarr, SABnzbd, Bazarr, Seerr,"
echo "        Unpackerr, and Recyclarr via their APIs — skips anything already set up"
run_step 7 "Configure all services" \
    python3 "$SCRIPT_DIR/setup-arr-config.py"

echo ""
echo "  Note: adding public torrent indexers (1337x, YTS, Nyaa, TPB...) and any"
echo "        usenet/private indexers whose credentials are set in .env"
run_step 8 "Add Prowlarr indexers" \
    python3 "$SCRIPT_DIR/indexers/setup-indexers.py"

echo ""
echo "  Note: enabling free subtitle providers (YIFY, Podnapisi, Subscene...) and any"
echo "        account-based providers (OpenSubtitles, Addic7ed) configured in .env"
run_step 9 "Enable Bazarr subtitle providers" \
    python3 "$SCRIPT_DIR/indexers/setup-bazarr-providers.py"

# ── Summary ───────────────────────────────────────────────────────────────────

LAN_IP=$(grep -m1 '^LAN_IP=' "$SCRIPT_DIR/.env" 2>/dev/null | cut -d'=' -f2- | tr -d '\r')
IP="${LAN_IP:-<NAS-IP>}"

echo ""
echo "============================================="
echo "  Results: $PASS passed, $FAIL failed"
echo "============================================="

if [ $FAIL -gt 0 ]; then
    echo ""
    echo "  One or more steps failed — review the output above."
    echo "  Fix the issue and re-run:  sudo bash $SCRIPT_DIR/setup.sh"
    exit 1
fi

echo ""
echo "  ✔ Setup complete!"
echo ""
echo "  ── One remaining manual step ─────────────────"
echo "  Seerr requires its setup wizard before it can"
echo "  be connected to Sonarr and Radarr:"
echo ""
echo "    1. Open http://${IP}:5056"
echo "    2. Connect Plex when prompted: http://plex:32400"
echo "    3. Finish the wizard, then run:"
echo "       python3 $SCRIPT_DIR/setup-arr-config.py"
echo ""
echo "  ── Service URLs ──────────────────────────────"
echo "  Plex         http://${IP}:32400/web"
echo "  Sonarr       http://${IP}:49152"
echo "  Radarr       http://${IP}:49151"
echo "  Lidarr       http://${IP}:49154"
echo "  Prowlarr     http://${IP}:49150"
echo "  SABnzbd      http://${IP}:49155"
echo "  qBittorrent  http://${IP}:49156"
echo "  Bazarr       http://${IP}:49153"
echo "  Seerr        http://${IP}:5056"
echo "  Tautulli     http://${IP}:8181"
echo ""
echo "  ── For updates ───────────────────────────────"
echo "  cd $SCRIPT_DIR"
echo "  docker-compose pull && docker-compose up -d"
