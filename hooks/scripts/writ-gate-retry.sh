#!/usr/bin/env bash
# Gate retry -- PostToolUse hook (matcher: Write|Edit).
#
# Closes the loop "the user typed approved, the validator rejected a format detail,
# the user had to type approved again". The advance route KEEPS the token on a
# rejected artifact (gate.py), so when the agent rewrites plan.md (planning) or a
# test file (testing) while a live token exists, this hook re-posts the same advance
# with the same token. One human approval, one advance, no second "approved".
#
# Silent (no stdout) and exit 0 unless ALL hold: the written file is plan.md or a
# test-category file, mode is work, phase is planning or testing, and a token file
# exists (the server judges expiry; this hook never reads or removes the token
# itself beyond handing it to writ_post_advance). Reads the session cache file
# directly (no daemon round-trip for the guard), so a dead daemon costs nothing.
#
# Exit: always 0.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
source "$SKILL_DIR/bin/lib/common.sh"
hook_instrument "writ-gate-retry"

# One python spawn for the four fields; cwd is not in load_hook_env's field set and
# the server needs it to resolve the project root.
PARSED=$(python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    ti = d.get('tool_input') or {}
    print(d.get('session_id', ''))
    print(d.get('tool_name', ''))
    print(ti.get('file_path', ''))
    print(d.get('cwd', ''))
except Exception:
    print('\n\n\n')
" 2>/dev/null) || exit 0

SESSION_ID=$(printf '%s\n' "$PARSED" | sed -n '1p')
TOOL_NAME=$(printf '%s\n' "$PARSED" | sed -n '2p')
FILE_PATH=$(printf '%s\n' "$PARSED" | sed -n '3p')
HOOK_CWD=$(printf '%s\n' "$PARSED" | sed -n '4p')

[ -n "$SESSION_ID" ] && [ -n "$FILE_PATH" ] || exit 0
case "$TOOL_NAME" in
  Write|Edit) ;;
  *) exit 0 ;;
esac

# Cheapest guard first: no token, nothing to retry (the dominant case on every write).
[ -f "/tmp/writ-gate-token-${SESSION_ID}" ] || exit 0

# Artifact guard: plan.md (phase-a gate) or a test-category file (test-skeletons gate).
BASENAME=$(basename "$FILE_PATH")
IS_ARTIFACT="no"
case "$BASENAME" in
  plan.md|test_*.*|*_test.*|*.test.*|*.spec.*|*_spec.*|*Test.php|*Test.java) IS_ARTIFACT="yes" ;;
esac
case "$FILE_PATH" in
  */tests/*|*/test/*|*/Test/*) IS_ARTIFACT="yes" ;;
esac
[ "$IS_ARTIFACT" = "yes" ] || exit 0

# Mode + phase straight from the cache file (same store every other hook writes).
CACHE_FILE="$(writ_session_cache_dir)/writ-session-${SESSION_ID}.json"
STATE=$(python3 -c "
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print((d.get('mode') or '') + '\t' + (d.get('current_phase') or ''))
except Exception:
    print('\t')
" "$CACHE_FILE" 2>/dev/null || printf '\t')
MODE=$(printf '%s' "$STATE" | cut -f1)
PHASE=$(printf '%s' "$STATE" | cut -f2)
[ "$MODE" = "work" ] || exit 0
case "$PHASE" in
  planning|testing) ;;
  *) exit 0 ;;
esac
# plan.md only re-tries the plan gate; a test file only the skeleton gate.
if [ "$BASENAME" = "plan.md" ] && [ "$PHASE" != "planning" ]; then exit 0; fi
if [ "$BASENAME" != "plan.md" ] && [ "$PHASE" != "testing" ]; then exit 0; fi

[ -n "$HOOK_CWD" ] || HOOK_CWD="$(pwd -P)"
RESP=$(writ_post_advance "$SESSION_ID" "$HOOK_CWD" || echo "")
[ -n "$RESP" ] || exit 0

OUTCOME_RAW=$(printf '%s' "$RESP" | python3 "$SKILL_DIR/bin/lib/gate_advance_outcome.py" 2>/dev/null || printf 'none\t\t\t\t')
OUTCOME=$(printf '%s' "$OUTCOME_RAW" | head -1 | cut -f1)
MSG=""
case "$OUTCOME" in
  advanced)
    ADVANCED_TO=$(printf '%s' "$OUTCOME_RAW" | head -1 | cut -f2)
    VALIDATED=$(printf '%s' "$OUTCOME_RAW" | head -1 | cut -f3)
    MSG="[Writ: ${PHASE} gate approved -> ${ADVANCED_TO}] (the user's earlier approval was kept and re-applied after your write to ${BASENAME}; no agent self-approval)"
    [ -n "$VALIDATED" ] && MSG="${MSG}
[Writ: ${VALIDATED}]"
    ;;
  rejected)
    GATE_ERROR=$(printf '%s' "$OUTCOME_RAW" | cut -f5-)
    MSG="[Writ: ${PHASE} gate REJECTED -- not advanced] ${GATE_ERROR}
The approval is still kept (token not consumed): fix ${BASENAME} and this retries on your next write to it."
    ;;
esac
[ -n "$MSG" ] || exit 0

# PostToolUse: bare stdout only reaches the debug log. The model sees the outcome
# only through hookSpecificOutput.additionalContext.
WRIT_RETRY_MSG="$MSG" python3 - <<'PY'
import json, os
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": os.environ.get("WRIT_RETRY_MSG", ""),
    }
}))
PY

exit 0
