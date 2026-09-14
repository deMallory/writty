#!/usr/bin/env bash
# PostToolUse(Bash) hook -- rewrites the tool result the model sees via
# hookSpecificOutput.updatedToolOutput (2.1.183 force-swap family):
# secret redaction plus oversize-output truncation. Zero token cost; the
# swap happens in the harness, not the prompt. Runs in every mode because
# redaction is a safety property, not a workflow one.
#
# Hook type: PostToolUse (matcher: Bash). Exit: always 0 (never blocks).

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
WRIT_DIR="$(cd "$HOOK_DIR/../.." && pwd)"
source "$WRIT_DIR/bin/lib/common.sh"

# The rewriter needs the whole payload, so buffer stdin once and key this
# hook's telemetry on the same envelope (agent_id first, then session_id);
# otherwise every hook_instrument row landed under "unknown".
INPUT=$(cat)
SESSION_ID=$(printf '%s' "$INPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print(''); sys.exit(0)
print((d.get('agent_id') or d.get('session_id') or '').strip())
" 2>/dev/null || echo "")
hook_instrument "writ-output-rewrite"

printf '%s' "$INPUT" | python3 "$WRIT_DIR/bin/lib/output-rewrite.py" 2>/dev/null || true
exit 0
