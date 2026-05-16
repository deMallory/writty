#!/usr/bin/env bash
# writ-context-watcher.sh
#
# Item 1 (v1.2.0): proactive context-window management.
#
# Reads transcript_path from the Claude Code hook stdin envelope, sums the
# last assistant message's input_tokens + cache_read_input_tokens +
# cache_creation_input_tokens, divides by WRIT_CONTEXT_WINDOW_TOKENS
# (default 200000), and writes the percentage to the session cache.
#
# Registered on:
#   UserPromptSubmit -- compute pct, update cache, emit threshold warning
#                       (one-shot per crossing) when pct >= 50.
#   PreToolUse       -- same as above; runs mid-task so 75% warning surfaces
#                       during long agent runs, not only at the next prompt.
#                       Never blocks (exit 0); warnings only.
#
# Skip entirely when cache.is_subagent is true. Workers run with unlimited
# rule injection and never emit context warnings.
#
# Stdlib only on the shell side; one python3 spawn parses the transcript.

set -euo pipefail

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
WRIT_DIR="$(cd "$HOOK_DIR/../.." && pwd)"
SESSION_HELPER="$WRIT_DIR/bin/lib/writ-session.py"
SKILL_DIR="${SKILL_DIR:-$WRIT_DIR}"
source "$WRIT_DIR/bin/lib/common.sh"

STDIN_DATA=$(cat || true)

# Extract event type, session id, and transcript path in one python3 spawn.
PARSED=$(echo "$STDIN_DATA" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
except Exception:
    data = {}
event = data.get('hook_event_name', '') or ''
sid = (data.get('agent_id') or data.get('session_id') or '').strip()
transcript = data.get('transcript_path', '') or ''
print(event)
print(sid)
print(transcript)
" 2>/dev/null || echo "")

EVENT_TYPE=$(echo "$PARSED" | sed -n '1p')
SESSION_ID=$(echo "$PARSED" | sed -n '2p')
TRANSCRIPT_PATH=$(echo "$PARSED" | sed -n '3p')

if [ -z "$SESSION_ID" ]; then
    SESSION_ID="${SESSION_ID_OVERRIDE:-${SESSION_ID:-}}"
    if [ -z "$SESSION_ID" ]; then
        SESSION_ID="${SESSION_ID_FALLBACK:-}"
    fi
fi
if [ -z "$SESSION_ID" ]; then
    SESSION_ID="${SKILL_DIR##*/}-$$"
fi

# Subagent gate: workers never block or emit directives.
IS_SUBAGENT=$(_writ_session read "$SESSION_ID" 2>/dev/null | python3 -c "
import sys, json
try:
    cache = json.load(sys.stdin)
except Exception:
    cache = {}
print('true' if cache.get('is_subagent') else 'false')
" 2>/dev/null || echo "false")
if [ "$IS_SUBAGENT" = "true" ]; then
    exit 0
fi

# Compute percent from the last type=assistant entry in the transcript.
# WRIT_CONTEXT_WINDOW_TOKENS overrides the 200000 default. Out-of-range or
# unparseable values fall back to 200000 silently here; the server logs the
# warning at startup.
WINDOW="${WRIT_CONTEXT_WINDOW_TOKENS:-200000}"

COMPUTE=$(python3 -c "
import sys, json, os

transcript = sys.argv[1] or ''
try:
    window = int(sys.argv[2])
    if window < 1000 or window > 10_000_000:
        window = 200_000
except (TypeError, ValueError):
    window = 200_000

last_assistant = None
if transcript and os.path.isfile(transcript):
    try:
        with open(transcript) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except (ValueError, json.JSONDecodeError):
                    continue
                if entry.get('type') == 'assistant':
                    last_assistant = entry
    except OSError:
        last_assistant = None

tokens = 0
if last_assistant:
    usage = (last_assistant.get('message') or {}).get('usage') or {}
    tokens = (
        int(usage.get('input_tokens', 0) or 0)
        + int(usage.get('cache_read_input_tokens', 0) or 0)
        + int(usage.get('cache_creation_input_tokens', 0) or 0)
    )

pct = int((tokens * 100) // window) if window else 0
print(pct)
" "$TRANSCRIPT_PATH" "$WINDOW" 2>/dev/null || echo "0")

PCT="${COMPUTE:-0}"

# Read current debounce state to decide whether to emit the soft directive.
EMITTED_AT=$(_writ_session read "$SESSION_ID" 2>/dev/null | python3 -c "
import sys, json
try:
    cache = json.load(sys.stdin)
except Exception:
    cache = {}
print(int(cache.get('context_warning_emitted_at_pct', 0) or 0))
" 2>/dev/null || echo "0")

NEW_EMITTED_AT="$EMITTED_AT"

# Threshold ladder. 75% takes precedence over 50%. Both are non-blocking
# stderr warnings; the agent decides when to come to a stopping point.
# Event-agnostic so the 75% warning surfaces mid-task during long PreToolUse
# chains, not only at the next UserPromptSubmit.
if [ "$PCT" -ge 75 ] && [ "$EMITTED_AT" -lt 75 ]; then
    cat >&2 <<'EOF_75'
[Writ: context 75% threshold]
Your conversation has consumed about 75% of the available context window.
Performance regressions starting. Please come to a stopping point and run
/compact to free the window. The watcher will re-arm automatically after
compaction.
EOF_75
    NEW_EMITTED_AT=75
elif [ "$PCT" -ge 50 ] && [ "$EMITTED_AT" -lt 50 ]; then
    cat >&2 <<'EOF_50'
[Writ: context 50% threshold]
Your conversation has consumed about 50% of the available context window.
Performance regressions are at risk past this point. Run /compact at the
next natural pause to free the window and re-arm the watcher.
EOF_50
    NEW_EMITTED_AT=50
fi

# Push pct + debounce field to cache atomically via HTTP fast path.
_writ_session context-percent "$SESSION_ID" --pct "$PCT" --emitted-at "$NEW_EMITTED_AT" \
    >/dev/null 2>&1 || true

exit 0
