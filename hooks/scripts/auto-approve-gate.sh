#!/usr/bin/env bash
# Auto-approve gate -- pattern-match defense-in-depth for approval detection.
# UserPromptSubmit: fires at the start of every user turn.
#
# Phase 3b (plan Section 8.1): pattern match does NOT advance the phase.
# It only emits an ask-prompt directive that steers the assistant to the
# /writ-approve slash command, which performs a tool-confirmed advance
# with confirmation_source="tool" in the audit trail.
#
# Why: silent pattern-path advances left no auditable intent record and
# could fire on ambiguous phrasing. The tool path requires the assistant
# to positively confirm via a slash command. Pattern match remains as a
# hint to the assistant, not the primary advance mechanism.
#
# Hook type: UserPromptSubmit
# Exit: always 0 (never block user prompt). Directive (if any) is on stdout.

set -euo pipefail

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
WRIT_DIR="$(cd "$HOOK_DIR/../.." && pwd)"
SESSION_HELPER="$WRIT_DIR/bin/lib/writ-session.py"
FA="$WRIT_DIR/bin/lib/friction-append.py"
source "$WRIT_DIR/bin/lib/common.sh"

# Read stdin once
STDIN_JSON=$(cat)

# Extract session_id and prompt
PARSED=$(echo "$STDIN_JSON" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    sid = data.get('agent_id', '') or data.get('session_id', '')
    agent_id = data.get('agent_id', '')
    prompt = data.get('prompt', data.get('message', data.get('content', '')))
    print(f'{sid}\n{prompt}\n{agent_id}')
except Exception:
    print('\n\n')
" 2>/dev/null) || true

SESSION_ID=$(echo "$PARSED" | head -1)
PROMPT=$(echo "$PARSED" | sed -n '2p')
AGENT_ID=$(echo "$PARSED" | sed -n '3p')

# Fallback session ID
# NO SYNTHESIZED SESSION ID. This used to fall back to the parent PID and then to
# md5(cwd:user)+date. Neither can ever equal the id Claude Code uses, so state written
# under one is written to a session that does not exist and is simply never read again,
# while the hook reports success. Claude Code documents session_id as universal and
# authoritative on every hook event, so an empty one is a broken invariant, not a case to
# paper over: record it and stop.
if [ -z "$SESSION_ID" ]; then
    writ_critical auto-approve-gate "no session_id in hook payload; refusing to synthesize one"
    exit 0
fi

# Publish session ID as backup -- skip inside sub-agents
if [ -z "$AGENT_ID" ]; then
    echo "$SESSION_ID" > /tmp/writ-current-session
fi

# Check approval pattern
PROMPT_LOWER=$(echo "$PROMPT" | tr '[:upper:]' '[:lower:]' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')

# Approval detection delegates to the single source of truth in
# bin/lib/approval_match.py (the hook and the tests bind to one module; no inline
# detector to drift). SEC-INJ-CMD-001: PROMPT_LOWER is passed as an argv element,
# never interpolated into the python string. Exit 0 = approval.
if python3 -c "import sys; sys.path.insert(0, '$WRIT_DIR/bin/lib'); from approval_match import is_approval; sys.exit(0 if is_approval(sys.argv[1]) else 1)" "$PROMPT_LOWER" 2>/dev/null; then
    IS_APPROVAL="yes"
else
    IS_APPROVAL="no"
fi

# Cheap relevance gate first (BJ Fogg): only prompts that ARE or LOOK LIKE an
# approval need the project root (a cwd-walk) and the mode (a server round-trip).
# A normal non-approval prompt -- the dominant every-turn case -- skips both.
LOOKS_LIKE_APPROVAL="no"
if [ "$IS_APPROVAL" != "yes" ] && [ ${#PROMPT} -gt 0 ] && [ ${#PROMPT} -lt 120 ]; then
    LOOKS_LIKE_APPROVAL=$(python3 -c "
import sys
prompt = sys.argv[1].lower()
approval_words = ['approv', 'proceed', 'accept', 'lgtm', 'good', 'go', 'yes', 'ok']
print('yes' if any(w in prompt for w in approval_words) else 'no')
" "$PROMPT_LOWER" 2>/dev/null || echo "no")
fi

# Deferred behind the gate: project root + mode, computed once, only when this
# prompt is approval-related. Both friction-log branches below reuse them.
PROJECT_ROOT=""
CURRENT_MODE=""
if [ "$IS_APPROVAL" = "yes" ] || [ "$LOOKS_LIKE_APPROVAL" = "yes" ]; then
    PROJECT_ROOT=$(detect_project_root "$(pwd -P)")
    CURRENT_MODE=$(_writ_session "mode get" "$SESSION_ID" 2>/dev/null || echo "")
    CURRENT_MODE=$(echo "$CURRENT_MODE" | tr -d '[:space:]')
fi

# Friction logging: approval_pattern_miss (looks-like-approval but did not match).
# NOT gated on PROJECT_ROOT: an unmarked directory resolves to no root, and gating the
# log on it meant approvals in exactly the directories where the gate misbehaves were
# the ones that left no telemetry.
if [ "$IS_APPROVAL" != "yes" ] && [ "$LOOKS_LIKE_APPROVAL" = "yes" ]; then
    # json.dumps keeps the free-form prompt JSON-safe (quotes/backslashes/newlines).
    MISS_EXTRA=$(python3 -c "import json,sys; print(json.dumps({'prompt': sys.argv[1][:120]}))" "$PROMPT" 2>/dev/null || echo '{}')
    log_friction_event "$SESSION_ID" "${CURRENT_MODE:-}" "approval_pattern_miss" "$MISS_EXTRA"
fi

if [ "$IS_APPROVAL" != "yes" ]; then
    # Debug prompt log, gated behind WRIT_DEBUG (default OFF).
    if _writ_debug_enabled; then
        echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') session=$SESSION_ID prompt=$(echo "$PROMPT" | head -c 200)" \
            >> "/tmp/writ-prompt-debug.log" 2>/dev/null || true
    fi
    exit 0
fi

# ---- Pattern matched. The trusted hook advances the gate (the human's
# "approved" is the authorization; the agent never handles the token). ----
#
# The hook writes the single-use gate token AND, when an approval gate is
# genuinely pending, advances the phase with that token. This is NOT agent
# self-approval: the user typed the approval; the hook (trusted infra) executes
# it; the agent is never in the loop. It replaces the broken /writ-approve dance
# where the agent had to read and echo the token back (circular + unworkable).
#
# False-positive guard (what the tool-only design was protecting against):
# auto-advance ONLY in work mode AND ONLY when current_phase is planning or
# testing -- the two phases that await a human approval gate. Implementation has
# no approval gate (finishing is a separate explicit action), and the other
# modes have no gates, so a stray "approved" there is a logged no-op.
GATE_TOKEN_FILE="/tmp/writ-gate-token-${SESSION_ID}"
# Always mint fresh (overwrite). The token expires by mtime (gate_token.py), so an
# old file left behind by an earlier, kept approval must not block this one: a new
# "approved" is a new approval and restarts the clock.
python3 -c "import secrets; print(secrets.token_hex(16))" > "$GATE_TOKEN_FILE" 2>/dev/null
chmod 600 "$GATE_TOKEN_FILE" 2>/dev/null || true

CURRENT_PHASE=$(python3 "$SESSION_HELPER" current-phase "$SESSION_ID" 2>/dev/null \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('phase',''))" 2>/dev/null || echo "")

ADVANCED_TO=""
# Initialized here so the final branch chain is safe under `set -u` even when the
# work/phase guard below is skipped (no advance attempted).
OUTCOME=""
GATE_ERROR=""
VALIDATED=""
TOKEN_SPENT=""
if [ "$CURRENT_MODE" = "work" ] && { [ "$CURRENT_PHASE" = "planning" ] || [ "$CURRENT_PHASE" = "testing" ]; }; then
    # writ_post_advance (common.sh) sends the token and the cwd and lets the SERVER
    # resolve the project root (locators.resolve_project_root: marker dir at or above
    # cwd, else the cwd itself). Sending cwd, not a bash marker walk, keeps ONE root
    # resolver authoritative and makes an unmarked directory workable; the server
    # cannot substitute its own cwd, which is Writ's install dir with its own plan.md.
    # The same helper serves writ-gate-retry.sh, so a kept approval is re-posted with
    # exactly this payload after the agent fixes the artifact.
    ADVANCE_RESP=$(writ_post_advance "$SESSION_ID" "$(pwd -P)" || echo "")
    # Classify the response via the shared stdlib helper (single source; the two
    # inline parses this replaces had drifted). A rejection KEEPS the token: the
    # agent fixes the artifact and the retry hook re-posts on the next write to it.
    OUTCOME_RAW=$(echo "$ADVANCE_RESP" | python3 "$WRIT_DIR/bin/lib/gate_advance_outcome.py" 2>/dev/null || printf 'none\t\t\t\t')
    OUTCOME=$(printf '%s' "$OUTCOME_RAW" | cut -f1)
    # Fields: 1 outcome, 2 phase, 3 what the gate judged, 4 token_spent, 5- the error.
    # The error is last because it is the only unbounded/multi-line field; `head -1`
    # keeps a multi-line error from smearing the fixed fields across its later lines.
    VALIDATED=$(printf '%s' "$OUTCOME_RAW" | head -1 | cut -f3)
    TOKEN_SPENT=$(printf '%s' "$OUTCOME_RAW" | head -1 | cut -f4)
    if [ "$OUTCOME" = "advanced" ]; then
        ADVANCED_TO=$(printf '%s' "$OUTCOME_RAW" | cut -f2)
    elif [ "$OUTCOME" = "rejected" ]; then
        GATE_ERROR=$(printf '%s' "$OUTCOME_RAW" | cut -f5-)
    fi
fi

# Friction log: advanced (hook executed the user's approval), rejected, or ask-prompt
# fallback. Unconditional: this used to be gated on a non-empty PROJECT_ROOT, so an
# approval typed in an unmarked directory -- the case where the gate refuses to advance
# at all -- logged nothing, which is how the defect stayed invisible.
python3 -c "
import json, sys
from datetime import datetime, timezone
advanced_to = sys.argv[4]
rejected = sys.argv[6]
if advanced_to:
    outcome = 'advanced->' + advanced_to
elif rejected:
    outcome = 'rejected'
else:
    outcome = 'ask-prompt-emitted'
entry = {
    'ts': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    'session': sys.argv[1],
    'mode': sys.argv[2] if sys.argv[2] else None,
    'event': 'approval_pattern_match',
    'matched_prompt': sys.argv[3][:120],
    'confirmation_source': 'pattern',
    'outcome': outcome,
    'project_root': sys.argv[5],
}
print(json.dumps(entry))
" "$SESSION_ID" "${CURRENT_MODE:-}" "$PROMPT" "${ADVANCED_TO:-}" "${PROJECT_ROOT:-}" "${GATE_ERROR:-}" \
    2>/dev/null | python3 "$FA" --stdin-json 2>/dev/null || true

if [ -n "$ADVANCED_TO" ]; then
    # Confirm the advance to the assistant/user via next-turn context, NAMING the
    # artifact that was accepted. "approved" alone hid which plan.md the gate read, so a
    # project root resolved from a stray marker file above the work dir could stamp an
    # unrelated plan silently.
    echo "[Writ: ${CURRENT_PHASE} gate approved -> ${ADVANCED_TO}] (advanced by the approval hook on your confirmation; no agent self-approval)"
    [ -n "$VALIDATED" ] && echo "[Writ: ${VALIDATED}] -- if that is not the plan you meant to approve, the project root is wrong: invalidate the gate before continuing."
elif [ -n "$GATE_ERROR" ]; then
    # The server REFUSED the advance. Surface the reason on STDOUT so the agent sees WHY
    # and fixes it -- stderr is not shown in the UserPromptSubmit context, which made
    # refusals look like "no gate pending".
    echo "[Writ: ${CURRENT_PHASE} gate REJECTED -- not advanced] ${GATE_ERROR}"
    # The approval is kept on every refusal the current server produces (a rejected
    # artifact and an unresolvable root both return token_spent=false). Only an older
    # daemon still reports a spent token; say so only when it does.
    if [ "$TOKEN_SPENT" = "true" ]; then
        echo "Fix the issue above in one edit; this daemon spent the prior approval, so the user must approve again."
    else
        echo "Your approval is kept (token not consumed): fix the cause above and the gate retries on the next plan.md/test write. Do not ask the user to approve again."
    fi
elif [ "$OUTCOME" = "noop" ]; then
    # Benign no-op: the server reported no pending gate to advance (not a rejection).
    # Emit the SAME neutral steer as the none/else branch -- no REJECTED text, no
    # "fix the issue", and the approval token is NOT spent.
    cat <<'DIRECTIVE'
[Writ: approval pattern detected]
No approval gate was advanced (no gate is pending in this phase/mode). If you intended
to advance a Work-mode plan/test gate, ensure the server is up; otherwise this approval
needs no gate action.
DIRECTIVE
else
    # No pending gate, or server unreachable: fall back to the steer directive.
    cat <<'DIRECTIVE'
[Writ: approval pattern detected]
No approval gate was advanced (no gate is pending in this phase/mode, or the Writ
server is unreachable). If you intended to advance a Work-mode plan/test gate, ensure the
server is up; otherwise this approval needs no gate action.
DIRECTIVE
fi

# Debug prompt log, gated behind WRIT_DEBUG (default OFF).
if _writ_debug_enabled; then
    echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') session=$SESSION_ID prompt=$(echo "$PROMPT" | head -c 200)" \
        >> "/tmp/writ-prompt-debug.log" 2>/dev/null || true
fi

exit 0
