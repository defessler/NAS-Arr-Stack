#!/bin/bash
# ── Media Stack Setup ──
#
# Runs all setup scripts in order and tracks progress.
#
# Usage:
#   sudo bash /volume1/docker/media/setup.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PASS=0
FAIL=0

run_step() {
    local step="$1"
    local description="$2"
    local script="$3"

    echo ""
    echo "┌─────────────────────────────────────────────"
    echo "│ Step $step: $description"
    echo "└─────────────────────────────────────────────"

    if bash "$SCRIPT_DIR/$script"; then
        echo ""
        echo "  ✔ Step $step complete."
        PASS=$((PASS + 1))
    else
        echo ""
        echo "  ✘ Step $step failed (exit code $?)."
        FAIL=$((FAIL + 1))
    fi
}

echo "============================================="
echo "  Media Stack Setup"
echo "============================================="

run_step 1 "Create folders and set permissions" "setup-folders.sh"
run_step 2 "Apply firewall rules"               "setup-firewall.sh"

echo ""
echo "============================================="
echo "  Results: $PASS passed, $FAIL failed"
echo "============================================="

if [ $FAIL -gt 0 ]; then
    echo "  One or more steps failed. Review the output above."
    exit 1
else
    echo "  All steps completed successfully."
    echo ""
    echo "  Next: copy docker-compose.yml and .env to this"
    echo "  directory, fill in .env, then run:"
    echo ""
    echo "    docker-compose up -d"
fi
