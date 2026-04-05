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
        echo "  ✘ Step $step failed."
        FAIL=$((FAIL + 1))
    fi
}

abort_if_failed() {
    if [ $FAIL -gt 0 ]; then
        echo ""
        echo "============================================="
        echo "  Setup halted — fix errors above and re-run."
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
    echo "  Waiting for containers (up to ${max_wait}s — longer on first run while images download)..."

    while [ $elapsed -lt $max_wait ]; do
        local all_up=true
        for svc in $services; do
            local state
            state=$(docker inspect --format='{{.State.Status}}' "$svc" 2>/dev/null || echo "missing")
            if [ "$state" != "running" ]; then
                all_up=false
                break
            fi
        done

        if $all_up; then
            echo "  ✔ All containers running (${elapsed}s elapsed)"
            echo "  Giving services 20s to initialise..."
            sleep 20
            return 0
        fi

        sleep $interval
        elapsed=$((elapsed + interval))
        printf "  %ds elapsed...\n" "$elapsed"
    done

    echo "  ✘ Containers did not start within ${max_wait}s"
    echo "  Check:  docker-compose logs"
    return 1
}

# ── Pre-flight ────────────────────────────────────────────────────────────────

echo "============================================="
echo "  Media Stack Setup"
echo "============================================="

run_step 1 "Set file permissions"               bash "$SCRIPT_DIR/setup-chmod.sh"
run_step 2 "Create folders and set permissions" bash "$SCRIPT_DIR/setup-folders.sh"
run_step 3 "Apply firewall rules"               bash "$SCRIPT_DIR/setup-firewall.sh"
run_step 4 "Fetch NordVPN WireGuard key"        bash "$SCRIPT_DIR/setup-nordvpn.sh"
run_step 5 "Validate configuration"             bash "$SCRIPT_DIR/setup-validate.sh"

abort_if_failed

# ── Stack ─────────────────────────────────────────────────────────────────────

run_step 6 "Start the stack" \
    bash -c "cd '$SCRIPT_DIR' && docker-compose up -d"

abort_if_failed

wait_for_services || { FAIL=$((FAIL + 1)); abort_if_failed; }

# ── API Configuration ─────────────────────────────────────────────────────────

run_step 7 "Configure services"          python3 "$SCRIPT_DIR/setup-arr-config.py"
run_step 8 "Add Prowlarr indexers"       python3 "$SCRIPT_DIR/indexers/setup-indexers.py"
run_step 9 "Enable Bazarr providers"     python3 "$SCRIPT_DIR/indexers/setup-bazarr-providers.py"

# ── Summary ───────────────────────────────────────────────────────────────────

LAN_IP=$(grep -m1 '^LAN_IP=' "$SCRIPT_DIR/.env" 2>/dev/null | cut -d'=' -f2- | tr -d '\r')

echo ""
echo "============================================="
echo "  Results: $PASS passed, $FAIL failed"
echo "============================================="

if [ $FAIL -gt 0 ]; then
    echo ""
    echo "  One or more steps failed. Review the output above."
    echo "  All steps are idempotent — re-run this script after fixing issues."
    exit 1
fi

echo ""
echo "  Setup complete!"
echo ""
echo "  One manual step remaining — Seerr needs its setup wizard:"
echo "    1. Open http://${LAN_IP:-<NAS-IP>}:5056"
echo "    2. Connect Plex: http://plex:32400"
echo "    3. Complete the wizard, then re-run:"
echo "       python3 $SCRIPT_DIR/setup-arr-config.py"
echo ""
echo "  For updates:"
echo "    cd $SCRIPT_DIR && docker-compose pull && docker-compose up -d"
