#!/bin/bash
# Consolidated PreToolUse Write|Edit dispatcher
#
# Replaces check-gate-approval.sh + enforce-final-gate.sh + writ-pretool-rag.sh
# with a single HTTP call to POST /pre-write-check.
#
# On deny: emits hookSpecificOutput with deny/ask decision.
# On allow: injects RAG rules via stdout.
# Fallback: if server unreachable, calls individual checks.
#
# Hook type: PreToolUse (matcher: Write|Edit)
# Exit: always 0

# PSR-003c follow-up: capture any stderr (Python tracebacks etc.) to a
# debug log so the next time a hook traceback shows in the Claude Code
# UI we can read the actual exception. tee preserves stderr propagation
# so behavior is unchanged.
exec 2> >(tee -a /tmp/writ-hook-debug.log >&2)

SKILL_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
SESSION_HELPER="$SKILL_DIR/bin/lib/writ-session.py"
source "$SKILL_DIR/bin/lib/common.sh"

HOOK_START_NS=$(hook_timer_start)

# Read stdin once
STDIN_DATA=$(cat)

# Item 4c: one python3 spawn parses stdin into session_id + check_body. Was
# two separate calls in v1.1.0 (session_id parse, then envelope parse).
PARSED_INPUT=$(python3 -c "
import sys, json
raw = sys.argv[1] or '{}'
skill_dir = sys.argv[2] or ''
try:
    data = json.loads(raw)
except (ValueError, json.JSONDecodeError):
    data = {}
sid = (data.get('agent_id') or data.get('session_id') or '').strip()
ti = data.get('tool_input', {})
if isinstance(ti, str):
    try:
        ti = json.loads(ti)
    except (ValueError, json.JSONDecodeError):
        ti = {}
file_path = ti.get('file_path', ti.get('path', ''))
body = json.dumps({
    'session_id': sid,
    'tool_input': ti if isinstance(ti, dict) else {},
    'skill_dir': skill_dir,
    'file_path': file_path,
})
print(sid)
print(body)
" "$STDIN_DATA" "$SKILL_DIR" 2>/dev/null)

SESSION_ID=$(echo "$PARSED_INPUT" | head -1)
CHECK_BODY=$(echo "$PARSED_INPUT" | tail -n +2)

if [ -z "$SESSION_ID" ]; then
    SESSION_ID=$(detect_session_id "")
fi

if [ -z "$CHECK_BODY" ]; then
    hook_timer_end "$HOOK_START_NS" "writ-pre-write-dispatch" "$SESSION_ID" ""
    exit 0
fi

# Single HTTP call to /pre-write-check
RESULT=$(_writ_session pre-write-check "$CHECK_BODY" 2>/dev/null || echo "")

if [ -z "$RESULT" ]; then
    hook_timer_end "$HOOK_START_NS" "writ-pre-write-dispatch" "$SESSION_ID" ""
    exit 0
fi

# Item 4c: single python3 spawn computes decision + reason + file_path + payload
# + hookSpecificOutput JSON + RAG metadata. Was three sequential json.load() spawns
# plus an inline hookSpecificOutput builder. Output is tab-separated lines the
# shell reads with `mapfile` to avoid further parsing spawns.
DENIAL_COUNT_VAL=""
if [ -n "$SESSION_ID" ]; then
    DENIAL_COUNT_VAL=$(_writ_session read "$SESSION_ID" 2>/dev/null | python3 -c "
import sys, json
try:
    cache = json.load(sys.stdin)
except Exception:
    cache = {}
counts = cache.get('denial_counts', {}) or {}
print(max(counts.values()) if counts else 2)
" 2>/dev/null || echo "2")
fi

DISPATCH_BLOB=$(python3 -c "
import json, sys
result_raw = sys.argv[1] or '{}'
body_raw = sys.argv[2] or '{}'
denial_count = sys.argv[3] or '2'
try:
    result = json.loads(result_raw)
except (ValueError, json.JSONDecodeError):
    result = {}
try:
    body = json.loads(body_raw)
except (ValueError, json.JSONDecodeError):
    body = {}
decision = result.get('decision', 'allow') or 'allow'
reason = result.get('reason', '') or ''
file_path = body.get('file_path', '') or ''
rag_rules = result.get('rag_rules', '') or ''
rag_meta = result.get('rag_meta', {}) or {}
rule_ids = rag_meta.get('rule_ids', []) or []
tokens = rag_meta.get('tokens', 0)

payload = json.dumps({
    'decision': decision,
    'reason': reason,
    'file_path': file_path,
})
if decision == 'ask':
    hook_output = json.dumps({
        'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'permissionDecision': 'ask',
            'permissionDecisionReason': '[Writ: repeated gate violation #' + denial_count + '] ' + (reason or 'Gate approval required'),
        }
    })
elif decision == 'deny':
    hook_output = json.dumps({
        'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'permissionDecision': 'deny',
            'permissionDecisionReason': reason or 'Gate approval required',
            'additionalContext': 'IMPORTANT: This write was denied by a Writ gate. Do NOT attempt more writes to other files -- the denial applies to ALL files until the gate advances. Read the denial reason and follow the workflow: present your work to the user and wait for approval.',
        }
    })
else:
    hook_output = ''

sys.stdout.write(decision + '\n')
sys.stdout.write(file_path + '\n')
sys.stdout.write(payload + '\n')
sys.stdout.write(hook_output + '\n')
sys.stdout.write(rag_rules.replace('\n', ' ') + '\n')
sys.stdout.write(json.dumps(rule_ids) + '\n')
sys.stdout.write(str(tokens) + '\n')
" "$RESULT" "$CHECK_BODY" "$DENIAL_COUNT_VAL" 2>/dev/null || echo "")

DECISION=$(echo "$DISPATCH_BLOB" | sed -n '1p')
DECISION_FILE=$(echo "$DISPATCH_BLOB" | sed -n '2p')
DECISION_PAYLOAD=$(echo "$DISPATCH_BLOB" | sed -n '3p')
HOOK_OUTPUT=$(echo "$DISPATCH_BLOB" | sed -n '4p')
RAG_RULES_RAW=$(echo "$DISPATCH_BLOB" | sed -n '5p')
NEW_RULE_IDS=$(echo "$DISPATCH_BLOB" | sed -n '6p')
COST=$(echo "$DISPATCH_BLOB" | sed -n '7p')

DECISION="${DECISION:-allow}"
DECISION_PAYLOAD="${DECISION_PAYLOAD:-{}}"
log_friction_event "$SESSION_ID" "" "pre_write_decision" "$DECISION_PAYLOAD"

if [ "$DECISION" = "deny" ] || [ "$DECISION" = "ask" ]; then
    [ -n "$HOOK_OUTPUT" ] && echo "$HOOK_OUTPUT"
else
    # RAG_RULES_RAW arrives flattened (newlines collapsed to spaces) so the
    # 7-field transport above stays single-line per field. Render as-is.
    if [ -n "$RAG_RULES_RAW" ]; then
        echo ""
        echo "[Writ: file-context rules for $(basename "${DECISION_FILE:-unknown}")]"
        printf '%s\n' "$RAG_RULES_RAW"
    fi
    if [ -n "$NEW_RULE_IDS" ] && [ "$NEW_RULE_IDS" != "[]" ]; then
        _writ_session update "$SESSION_ID" \
            --add-rules "$NEW_RULE_IDS" \
            --cost "${COST:-0}" \
            --inc-queries 2>/dev/null || true
    fi
fi

hook_timer_end "$HOOK_START_NS" "writ-pre-write-dispatch" "$SESSION_ID" ""
exit 0
