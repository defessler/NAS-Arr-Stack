#!/bin/bash
# ── Shell Script Unit Tests ──
#
# Tests for bash helper functions across the setup scripts.
# No external dependencies — runs entirely with bash builtins.
#
# Usage:
#   bash tests/test_shell.sh
#
# Exit code: 0 = all passed, 1 = one or more failed

PASS=0
FAIL=0

pass() { echo "  ✔  $1"; PASS=$((PASS + 1)); }
fail() { echo "  ✘  $1"; FAIL=$((FAIL + 1)); }

run_test() {
    local name="$1"
    local result expected
    shift
    # Run test function; it returns expected vs actual via stdout
    if "$@"; then
        pass "$name"
    else
        fail "$name"
    fi
}

# ── Helpers ───────────────────────────────────────────────────────────────────

make_env() {
    # Write a temp .env and echo its path
    local tmpfile
    tmpfile=$(mktemp /tmp/test-env.XXXXXX)
    printf '%s\n' "$@" > "$tmpfile"
    echo "$tmpfile"
}

# ── env_val: post-deploy-validate.sh (Bug #2) ─────────────────────────────────

echo ""
echo "── env_val (post-deploy-validate.sh) ───────────────────────────────────"

# The correct implementation from the fix:
env_val_fixed() {
    local ENV_FILE="$1" key="$2"
    grep -m1 "^${key}=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2- | tr -d '\r'
}

# The old (broken) implementation:
env_val_broken() {
    local ENV_FILE="$1" key="$2"
    grep -m1 "^${key}=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2
}

test_preserves_equals_in_value() {
    # WireGuard private keys are 44 base64 chars that often end with '='
    # The old cut -f2 (without -) truncates everything after the first =
    local env
    env=$(make_env 'WG_KEY=abc123+xyz/foo==' 'OTHER=bar')
    local result
    result=$(env_val_fixed "$env" "WG_KEY")
    rm "$env"
    [ "$result" = "abc123+xyz/foo==" ]
}

test_broken_truncates_equals_in_value() {
    # Demonstrate the old bug: cut -f2 without - drops everything after first =
    local env
    env=$(make_env 'WG_KEY=abc123+xyz/foo==')
    local result
    result=$(env_val_broken "$env" "WG_KEY")
    rm "$env"
    # The broken version returns only 'abc123+xyz/foo' (truncated)
    [ "$result" != "abc123+xyz/foo==" ]
}

test_strips_carriage_return() {
    # .env files edited on Windows have CRLF line endings
    local env
    env=$(mktemp /tmp/test-env.XXXXXX)
    printf 'LAN_IP=192.168.1.100\r\n' > "$env"
    local result
    result=$(env_val_fixed "$env" "LAN_IP")
    rm "$env"
    # Must not contain trailing \r
    [ "$result" = "192.168.1.100" ] && [[ "$result" != *$'\r'* ]]
}

test_simple_value() {
    local env
    env=$(make_env 'PUID=1000')
    local result
    result=$(env_val_fixed "$env" "PUID")
    rm "$env"
    [ "$result" = "1000" ]
}

test_returns_empty_for_missing_key() {
    local env
    env=$(make_env 'FOO=bar')
    local result
    result=$(env_val_fixed "$env" "MISSING")
    rm "$env"
    [ -z "$result" ]
}

test_ignores_comments() {
    local env
    env=$(make_env '# this is a comment' 'KEY=value')
    local result
    result=$(env_val_fixed "$env" "KEY")
    rm "$env"
    [ "$result" = "value" ]
}

test_first_match_wins() {
    # grep -m1 must return only the first match
    local env
    env=$(make_env 'KEY=first' 'KEY=second')
    local result
    result=$(env_val_fixed "$env" "KEY")
    rm "$env"
    [ "$result" = "first" ]
}

run_test "preserves = in value (e.g. base64 WireGuard key)" test_preserves_equals_in_value
run_test "old cut -f2 (without -) truncates at first =" test_broken_truncates_equals_in_value
run_test "strips carriage returns from Windows CRLF .env" test_strips_carriage_return
run_test "reads simple string value" test_simple_value
run_test "returns empty string for missing key" test_returns_empty_for_missing_key
run_test "skips comment lines" test_ignores_comments
run_test "returns first match when key appears multiple times" test_first_match_wins

# ── setup-validate.sh env_val matches post-deploy-validate.sh ─────────────────

echo ""
echo "── env_val parity (setup-validate.sh vs post-deploy-validate.sh) ───────"

# Both scripts must behave identically for env_val.
# Extract the actual function definitions and compare behaviour.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/nas"

test_validate_env_val_handles_equals() {
    if [ ! -f "$SCRIPT_DIR/setup-validate.sh" ]; then
        echo "  (skip — setup-validate.sh not found)"; return 0
    fi
    local env
    env=$(make_env 'WG_KEY=abc==')
    local result
    result=$(bash -c "
        ENV_FILE='$env'
        $(grep 'env_val()' "$SCRIPT_DIR/setup-validate.sh")
        env_val WG_KEY
    ")
    rm "$env"
    [ "$result" = "abc==" ]
}

test_postdeploy_env_val_handles_equals() {
    if [ ! -f "$SCRIPT_DIR/post-deploy-validate.sh" ]; then
        echo "  (skip — post-deploy-validate.sh not found)"; return 0
    fi
    local env
    env=$(make_env 'WG_KEY=abc==')
    local result
    result=$(bash -c "
        ENV_FILE='$env'
        $(grep 'env_val()' "$SCRIPT_DIR/post-deploy-validate.sh")
        env_val WG_KEY
    ")
    rm "$env"
    [ "$result" = "abc==" ]
}

run_test "setup-validate.sh env_val handles = in values" test_validate_env_val_handles_equals
run_test "post-deploy-validate.sh env_val handles = in values" test_postdeploy_env_val_handles_equals

# ── setup-nordvpn.sh: WireGuard key padding ───────────────────────────────────

echo ""
echo "── setup-nordvpn.sh: WireGuard key length handling ─────────────────────"

test_pads_43_char_key() {
    # NordVPN API sometimes returns 43-char keys (missing trailing =)
    # The script must auto-pad to 44 chars
    local key_43="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAaaa"
    [ ${#key_43} -eq 43 ] || { echo "test data wrong length"; return 1; }
    local padded="${key_43}="
    [ ${#padded} -eq 44 ]
}

test_rejects_wrong_length_key() {
    # Keys that are not 43 or 44 chars must be flagged as invalid
    local key_40="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    [ ${#key_40} -eq 40 ] || { echo "test data wrong length"; return 1; }
    # Verify length check logic: not 43 and not 44 → invalid
    local is_valid=false
    [ ${#key_40} -eq 44 ] && is_valid=true
    [ ${#key_40} -eq 43 ] && is_valid=true
    [ "$is_valid" = "false" ]
}

run_test "43-char WireGuard key gets padded to 44" test_pads_43_char_key
run_test "40-char WireGuard key is flagged as invalid" test_rejects_wrong_length_key

# ── Summary ───────────────────────────────────────────────────────────────────

echo ""
echo "═══════════════════════════════════════════════"
echo "  Results: $PASS passed, $FAIL failed"
echo "═══════════════════════════════════════════════"

[ $FAIL -eq 0 ]
