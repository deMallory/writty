#!/usr/bin/env bash
# Writ PreCompact hook -- fires before context window compaction
#
# Drops the now-stale loaded_rules full objects from the session cache,
# keeping loaded_rule_ids and loaded_rule_ids_by_phase for feedback/coverage
# and exclusion logic.
#
# NOTE: the session cache is a separate /tmp file. It is
# not part of the compacted context, so this does not shrink what the
# summarizer compresses; it is boundary hygiene (the conversation those
# objects annotated is being summarized away). A PreCompact hook also cannot
# steer compaction: its stdout is not injected into the summary and it has no
# additionalContext. PostCompact (writ-postcompact.sh) is the only hook whose
# output reaches the next turn.
#
# Hook type: PreCompact
# Exit: always 0 (cannot block compaction)

set -euo pipefail

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
WRIT_DIR="$(cd "$HOOK_DIR/../.." && pwd)"
SESSION_HELPER="$WRIT_DIR/bin/lib/writ-session.py"
source "$WRIT_DIR/bin/lib/common.sh"

HOOK_START_NS=$(hook_timer_start)

# Session ID: from the stdin envelope (agent_id or session_id). load_hook_env
# applies the PPID/md5 fallback internally when no envelope is present.
load_hook_env
SESSION_ID="$HOOK_SESSION_ID"

# Clear full rule objects, keep IDs
_writ_session clear-rules-for-compaction "$SESSION_ID" \
    >> "/tmp/writ-precompact-${SESSION_ID}.log" 2>/dev/null || true

# Mode for hook_execution telemetry (audit #5).
MODE=$(_writ_session "mode get" "$SESSION_ID" 2>/dev/null || echo "")
MODE=$(echo "$MODE" | tr -d '[:space:]')
hook_timer_end "$HOOK_START_NS" "writ-precompact" "$SESSION_ID" "${MODE:-}"
exit 0
