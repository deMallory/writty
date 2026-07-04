#!/usr/bin/env bash
# Phase 2: enforce verification-before-completion (ENF-PROC-VERIFY-001).
#
# PreToolUse on TodoWrite + Stop.
# TodoWrite: deny completion claims without fresh verification evidence
# recorded via POST /session/{sid}/verification-evidence.
# Stop: exit 2 (blocks the stop, continues the turn per the 2.1.183
# envelope map) while any artifact holds a Gate 5 quality judgment below 3
# that is neither fixed nor overridden. stop_hook_active guards against
# re-block loops: a persistent failure blocks at most once per stop chain.
set -euo pipefail
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
WRIT_DIR="$(cd "$HOOK_DIR/../.." && pwd)"
SESSION_HELPER="$WRIT_DIR/bin/lib/writ-session.py"
source "$WRIT_DIR/bin/lib/common.sh"

PARSED=$(parse_hook_stdin)
SESSION_ID=$(detect_session_id "$PARSED")
[ -z "$SESSION_ID" ] && exit 0

is_work_mode "$SESSION_ID" || exit 0

TOOL=$(parsed_field "$PARSED" "tool_name")
EVENT=$(parsed_field "$PARSED" "event")

if [ "$EVENT" = "Stop" ]; then
    FAILING=$(python3 <<PY
import json
from importlib import util
spec = util.spec_from_file_location('writ_session', "$SESSION_HELPER")
mod = util.module_from_spec(spec); spec.loader.exec_module(mod)
session = mod._read_cache("$SESSION_ID")
judgments = session.get("quality_judgment_state") or {}
failing = [
    path for path, j in judgments.items()
    if isinstance(j, dict) and j.get("score", 5) < 3 and not j.get("overridden")
]
if failing:
    print(", ".join(sorted(failing)))
PY
    )
    if [ -n "$FAILING" ]; then
        echo "Gate 5 Tier 2: cannot stop while these artifacts hold quality scores below 3 (fix them or override via POST /session/{sid}/quality-judgment): $FAILING" >&2
        if parsed_bool "$PARSED" "stop_hook_active"; then
            exit 1
        fi
        exit 2
    fi
    # Main-agent completion-claim gate: the 2.1.199 Stop envelope carries
    # last_assistant_message (verified live 2026-07-04; not in the 2.1.183
    # map), so the same claim-vs-disk check that gates writer subagents
    # applies here. One forced continuation per stop chain.
    MISSING=$(echo "$PARSED" | python3 "$WRIT_DIR/bin/lib/claim-check.py" 2>/dev/null || echo "")
    if [ -n "$MISSING" ]; then
        echo "ENF-PROC-VERIFY-001 Stop gate: your last message names files that do not exist on disk: $MISSING. Create them or correct the claim before stopping." >&2
        if parsed_bool "$PARSED" "stop_hook_active"; then
            exit 1
        fi
        exit 2
    fi
    exit 0
fi

# Only evaluate on TodoWrite marking a todo completed, or on Stop events.
# For TodoWrite: parse the tool_input.todos and check if any transition to
# "completed" lacks verification_evidence.
DENY_REASON=""
if [ "$TOOL" = "TodoWrite" ]; then
    DENY_REASON=$(python3 <<PY
import json, sys
sys.path.insert(0, "$WRIT_DIR/bin/lib")
from importlib import util
spec = util.spec_from_file_location('writ_session', "$SESSION_HELPER")
mod = util.module_from_spec(spec); spec.loader.exec_module(mod)
session = mod._read_cache("$SESSION_ID")
evidence = session.get("verification_evidence") or {}
judgments = session.get("quality_judgment_state") or {}
parsed = json.loads('''$PARSED''')
tool_input = parsed.get("tool_input") or {}
todos = tool_input.get("todos") or []
for t in todos:
    tid = t.get("id") or t.get("content", "")[:40]
    status = t.get("status") or ""
    if status != "completed":
        continue
    # Check 1: verification_evidence required (ENF-PROC-VERIFY-001).
    if tid not in evidence:
        print(f"ENF-PROC-VERIFY-001: completion claim for '{tid}' has no verification_evidence. Run the check, then POST /session/{{sid}}/verification-evidence before marking completed.")
        break
    # Check 2: any artifact with a Gate 5 quality judgment below 3 blocks
    # completion unless explicitly overridden (hook-directive self-review;
    # the judge POSTs its score to /session/{sid}/quality-judgment).
    failing_artifacts = [
        path for path, j in judgments.items()
        if isinstance(j, dict) and j.get("score", 5) < 3 and not j.get("overridden")
    ]
    if failing_artifacts:
        print(f"Gate 5 Tier 2: cannot mark '{tid}' completed while the following artifacts have quality scores below 3 (fix or override): {failing_artifacts}")
        break
PY
    )
fi

if [ -n "$DENY_REASON" ]; then
    python3 -c "
import json
print(json.dumps({
    'hookSpecificOutput': {
        'hookEventName': 'PreToolUse',
        'permissionDecision': 'deny',
        'permissionDecisionReason': '''$DENY_REASON'''
    }
}))"
fi
exit 0
