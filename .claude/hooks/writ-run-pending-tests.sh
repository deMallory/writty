#!/usr/bin/env bash
# Stop hook. Runs tests for files marked by writ-mark-pending-test.sh.
# Silent on pass. On failure, emits one-line summary via emit-summary.py.
# All test-path knowledge lives in bin/lib/test_paths.py (config-driven).
set -euo pipefail
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
WRIT_DIR="$(cd "$HOOK_DIR/../.." && pwd)"
source "$WRIT_DIR/bin/lib/common.sh"
TEST_PATHS_HELPER="$WRIT_DIR/bin/lib/test_paths.py"

PARSED=$(parse_hook_stdin)
SESSION_ID=$(detect_session_id "$PARSED")
[ -z "$SESSION_ID" ] && exit 0
is_work_mode "$SESSION_ID" || exit 0

MARKER="$WRIT_DIR/cache/$SESSION_ID/pending-tests.txt"
[ -f "$MARKER" ] || exit 0

# Resolve every marker entry to a test file (or empty) via the helper.
TEST_FILES=$(while IFS= read -r p; do
    [ -z "$p" ] && continue
    python3 "$TEST_PATHS_HELPER" resolve-test "$p" 2>/dev/null
done < "$MARKER" | awk 'NF && !seen[$0]++')

: > "$MARKER"

RESOLVED_COUNT=$(printf '%s' "$TEST_FILES" | awk 'NF' | wc -l)

if [ -z "$TEST_FILES" ]; then
    log_friction_event "$SESSION_ID" "work" "hook_execution" \
        "{\"hook_name\":\"writ-run-pending-tests\",\"result_code\":0,\"resolved_count\":0}" \
        2>/dev/null || true
    exit 0
fi

LOG_DIR="$WRIT_DIR/cache/$SESSION_ID"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/last-test-run.log"
: > "$LOG"

# Group test files by runner. Bash 4+ associative arrays.
declare -A RUNNER_CMD RUNNER_CFG RUNNER_FILES RUNNER_FMT
while IFS= read -r tf; do
    [ -z "$tf" ] && continue
    INFO=$(python3 "$TEST_PATHS_HELPER" runner-for "$tf" 2>/dev/null)
    CMD=$(echo "$INFO" | sed -n '1p')
    CFG=$(echo "$INFO" | sed -n '2p')
    [ -z "$CMD" ] && continue
    KEY="${CMD}|${CFG}"
    RUNNER_CMD["$KEY"]="$CMD"
    RUNNER_CFG["$KEY"]="$CFG"
    RUNNER_FILES["$KEY"]="${RUNNER_FILES["$KEY"]:-}${RUNNER_FILES["$KEY"]:+ }$tf"
    case "$CMD" in
        *pytest*)    RUNNER_FMT["$KEY"]=pytest  ;;
        *phpunit*)   RUNNER_FMT["$KEY"]=phpunit ;;
        *"go test"*) RUNNER_FMT["$KEY"]=gotest  ;;
        *)           RUNNER_FMT["$KEY"]=pytest  ;;
    esac
done <<< "$TEST_FILES"

OVERALL_RC=0
SUMMARY_FMT=""

run_group() {
    local fmt="$1"; shift
    local cmd="$*"
    # `|| rc=$?` puts the redirected group into a `||` chain, which suspends
    # `set -e`. Without it, a non-zero exit from the runner (PHPUnit warnings,
    # test failures, etc.) aborts the script BEFORE we capture the rc -- so
    # the friction event and summary-emission below never run.
    local rc=0
    {
        echo "===== $fmt: $cmd ====="
        timeout 60s bash -c "$cmd" 2>&1
    } >> "$LOG" || rc=$?
    if [ $rc -ne 0 ]; then
        OVERALL_RC=$rc
        [ -z "$SUMMARY_FMT" ] && SUMMARY_FMT="$fmt"
    fi
}

for KEY in "${!RUNNER_CMD[@]}"; do
    CMD="${RUNNER_CMD[$KEY]}"
    CFG="${RUNNER_CFG[$KEY]}"
    FILES="${RUNNER_FILES[$KEY]}"
    FMT="${RUNNER_FMT[$KEY]}"
    if [ -n "$CFG" ]; then
        CMDLINE="$CMD -c $CFG $FILES"
    else
        CMDLINE="$CMD $FILES"
    fi
    run_group "$FMT" "$CMDLINE"
done

log_friction_event "$SESSION_ID" "work" "hook_execution" \
    "{\"hook_name\":\"writ-run-pending-tests\",\"result_code\":$OVERALL_RC,\"resolved_count\":$RESOLVED_COUNT}" \
    2>/dev/null || true

[ $OVERALL_RC -eq 0 ] && exit 0

# Decide pass/fail by parsing the log, not by trusting the runner's exit code.
# PHPUnit (and pytest --strict-warnings) can exit non-zero for environment
# warnings even when no actual tests failed. emit-summary.py prints only when
# it finds real failures; if its stderr is empty, treat as pass.
SUMMARY=$(python3 "$WRIT_DIR/bin/lib/emit-summary.py" \
    --format "${SUMMARY_FMT:-pytest}" \
    --log "$LOG" \
    --rule "ENF-TEST-001" \
    --label "test failure(s)" 2>&1)
[ -z "$SUMMARY" ] && exit 0
echo "$SUMMARY" >&2
exit 1
