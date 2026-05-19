#!/usr/bin/env bash
# PostToolUse on Write|Edit. Marks src/test files for end-of-turn test run.
# Companion hook: writ-run-pending-tests.sh (Stop) reads the marker.
set -euo pipefail
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
WRIT_DIR="$(cd "$HOOK_DIR/../.." && pwd)"
source "$WRIT_DIR/bin/lib/common.sh"

PARSED=$(parse_hook_stdin)
# Key the marker on the parent session id, not the worker's agent_id.
# In sub-agents the master orchestrator's Stop hook is the one that fires
# and reads cache/<parent-sid>/pending-tests.txt. detect_session_id prefers
# agent_id and would land the marker in the worker's cache, where no Stop
# hook ever reads it. See plan.md "Fix: test hooks no-op under orchestrator".
PARENT_SID=$(echo "$PARSED" | python3 -c "
import sys, json
d = json.load(sys.stdin)
sid = d.get('session_id')
print(str(sid).strip() if sid is not None else '')
" 2>/dev/null)
[ -z "$PARENT_SID" ] && exit 0
is_work_mode "$PARENT_SID" || exit 0
parsed_bool "$PARSED" "is_error" && exit 0

FILE=$(parsed_field "$PARSED" "file_path")
[ -z "$FILE" ] && exit 0

# All path knowledge lives in bin/lib/test_paths.py (config-driven via
# bundled defaults + optional .claude/writ.json per project).
TEST_PATHS_HELPER="$WRIT_DIR/bin/lib/test_paths.py"
MATCH=$(python3 "$TEST_PATHS_HELPER" match-src "$FILE" 2>/dev/null)
[ -z "$MATCH" ] && MATCH=$(python3 "$TEST_PATHS_HELPER" match-test "$FILE" 2>/dev/null)
[ -z "$MATCH" ] && exit 0

MARKER_DIR="$WRIT_DIR/cache/$PARENT_SID"
mkdir -p "$MARKER_DIR"
echo "$FILE" >> "$MARKER_DIR/pending-tests.txt"

# Friction-log telemetry so "did the hook fire?" is answerable from the log.
log_friction_event "$PARENT_SID" "work" "hook_execution" \
    "{\"hook_name\":\"writ-mark-pending-test\",\"file_path\":\"$FILE\"}" \
    2>/dev/null || true
exit 0
