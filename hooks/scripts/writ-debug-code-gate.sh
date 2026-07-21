#!/bin/bash
# INV-9: defer code-reading until runtime evidence -- PreToolUse gate.
#
# In the runtime (debug) lens, blocks code search/reading until debug.md has
# Evidence + Narrowing content (DEBUG-MODE-PROPOSAL.md line 126, hook #2). Reading
# debug.md / logs / non-code stays allowed; runtime data via Bash is untouched.
# Decision is computed by `writ-session.py can-read-code` (fail-open). Emits a deny
# permissionDecision only when that check says deny.
#
# Hook type: PreToolUse (matcher: Grep|Read). Exit: always 0.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
SESSION_HELPER="$SKILL_DIR/bin/lib/writ-session.py"

STDIN_DATA=$(cat)

SID=$(printf '%s' "$STDIN_DATA" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print(''); sys.exit(0)
print((d.get('agent_id') or d.get('session_id') or '').strip())
" 2>/dev/null || echo "")
[ -n "$SID" ] || exit 0

DECISION_JSON=$(printf '%s' "$STDIN_DATA" \
    | python3 "$SESSION_HELPER" can-read-code "$SID" --skill-dir "$SKILL_DIR" 2>/dev/null || echo "")
[ -n "$DECISION_JSON" ] || exit 0

printf '%s' "$DECISION_JSON" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
if d.get('decision') != 'deny':
    sys.exit(0)
print(json.dumps({
    'hookSpecificOutput': {
        'hookEventName': 'PreToolUse',
        'permissionDecision': 'deny',
        'permissionDecisionReason': d.get('reason') or 'Code reading blocked: gather runtime evidence first.',
        'additionalContext': 'Runtime (debug) lens: read debug.md / logs / non-code and gather runtime evidence via Bash first, record Evidence + Narrowing in debug.md, then read code.',
    }
}))
" 2>/dev/null || true

exit 0
