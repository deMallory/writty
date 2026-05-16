#!/usr/bin/env bash
# Writ PostCompact hook -- fires after context window compaction
#
# Clears loaded_rule_ids_by_phase[current_phase] so rules will be
# re-injected on the next UserPromptSubmit. Resets remaining_budget
# to DEFAULT_SESSION_BUDGET (8000). This is the authoritative compaction
# signal; the Cycle A heuristic in writ-rag-inject.sh stays as fallback.
#
# Hook type: PostCompact
# Exit: always 0 (cannot block compaction)

set -euo pipefail

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
WRIT_DIR="$(cd "$HOOK_DIR/../.." && pwd)"
SESSION_HELPER="$WRIT_DIR/bin/lib/writ-session.py"
source "$WRIT_DIR/bin/lib/common.sh"

HOOK_START_NS=$(hook_timer_start)

# Session ID: prefer the stdin envelope (Claude Code passes session_id), fall
# back to grandparent PID, then to the deterministic cwd+user hash.
STDIN_DATA=$(cat 2>/dev/null || true)
SESSION_ID=""
if [ -n "$STDIN_DATA" ]; then
    SESSION_ID=$(echo "$STDIN_DATA" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
except Exception:
    data = {}
print((data.get('agent_id') or data.get('session_id') or '').strip())
" 2>/dev/null || echo "")
fi
if [ -z "$SESSION_ID" ]; then
    SESSION_ID=$(ps -o ppid= -p $PPID 2>/dev/null | tr -d ' ')
fi
if [ -z "$SESSION_ID" ]; then
    SESSION_ID=$(echo "${PWD}:${USER}" | md5sum | cut -c1-12)-$(date +%Y%m%d)
fi

# Reset phase exclusion list and budget. cmd_reset_after_compaction also
# clears context_warning_emitted_at_pct so the v1.2.0 context-watcher
# 50%/75% bands re-arm on the next crossing after compaction.
_writ_session reset-after-compaction "$SESSION_ID" \
    >> "/tmp/writ-postcompact-${SESSION_ID}.log" 2>/dev/null || true

# Phase 4c (PSR-004 follow-up): emit a verify-discipline directive so
# the model treats recalled verification output as second-hand after
# compaction. Without this, "Is it working?" post-compact gets answered
# from pre-compact memory ("last run was N tests passing") rather than
# fresh evidence. See docs/pressure-runs/2026-04-22/PSR-004/analysis.md.
cat <<'DIRECTIVE'
[Writ: context compacted]
Until the next compaction, treat any pre-compact verification output (test counts,
"passing" claims, file reads) as second-hand evidence.

If asked "is it working?" / "is it done?" / "did it pass?":
  1. Re-run the relevant verification (tests, lint, typecheck, smoke command) FIRST.
  2. If the re-run is BLOCKED (tool rejection, permission denied, env unavailable):
       STOP. Do NOT answer "yes", "passing", or "should be working".
       Respond instead: "Re-verification was blocked by [reason]. I cannot confirm
       post-compact. Pre-compact context says X but I have no fresh evidence.
       Want me to verify another way?"
  3. Only answer affirmatively with fresh test/lint output cited inline.

Saying "yes" / "passing" / "all good" without fresh evidence is a forbidden response
in this state. Recalled output is not fresh evidence.
DIRECTIVE

hook_timer_end "$HOOK_START_NS" "writ-postcompact" "$SESSION_ID" ""
exit 0
