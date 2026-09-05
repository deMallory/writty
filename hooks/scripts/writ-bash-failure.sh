#!/usr/bin/env bash
# PostToolUseFailure hook: log failed Bash commands to the friction log.
# Companion to track-failed-writes.sh (Write|Edit); registered with
# matcher Bash. Telemetry only, never blocks.
#
# Limit (2.1.183 capture): some tool failures never produce a
# PostToolUseFailure envelope at all, so this is a sample, not a census;
# transcript analysis stays the source of truth for failure rates.
#
# Hook type: PostToolUseFailure (matcher: Bash)
# Exit: always 0

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
source "$SKILL_DIR/bin/lib/common.sh"

HOOK_START_NS=$(hook_timer_start)

PARSED=$(parse_hook_stdin)
TOOL_NAME=$(parsed_field "$PARSED" "tool_name")
[ "$TOOL_NAME" = "Bash" ] || exit 0

SESSION_ID=$(detect_session_id "$PARSED")
[ -z "$SESSION_ID" ] && exit 0

MODE=$(_writ_session "mode get" "$SESSION_ID" 2>/dev/null | tr -d '[:space:]' || echo "")

EXTRA=$(echo "$PARSED" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(json.dumps({
    'command': (d.get('command') or '')[:200],
    'reason': (d.get('error') or 'unknown')[:300],
    'tool': 'Bash',
}))
" 2>/dev/null || echo '{}')

log_friction_event "$SESSION_ID" "$MODE" "bash_failure" "$EXTRA" 2>/dev/null || true

hook_timer_end "$HOOK_START_NS" "writ-bash-failure" "$SESSION_ID" "$MODE"
exit 0
