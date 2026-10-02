#!/usr/bin/env bash
# Phase 2: enforce spec-review-before-code-quality-review (ENF-PROC-SDD-001).
#
# PreToolUse on Task when the dispatched subagent is a code reviewer.
# Denies dispatch if spec-reviewer for the current task hasn't completed.
# Feature-flag gated.
set -euo pipefail

# Phase 4c: capture stderr (Python tracebacks etc.) to debug log so
# next-occurrence diagnostics are readable. tee preserves stderr
# propagation so behavior is unchanged.
exec 2> >(tee -a /tmp/writ-hook-debug.log >&2)
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
WRIT_DIR="$(cd "$HOOK_DIR/../.." && pwd)"
SESSION_HELPER="$WRIT_DIR/bin/lib/writ-session.py"
source "$WRIT_DIR/bin/lib/common.sh"
hook_instrument "writ-sdd-review-order"

PARSED=$(parse_hook_stdin)
SESSION_ID=$(detect_session_id "$PARSED")
[ -z "$SESSION_ID" ] && exit 0

is_work_mode "$SESSION_ID" || exit 0

# Pass $PARSED to Python via env var rather than heredoc substitution.
# Heredoc substitution preserves raw control characters (newlines/tabs
# embedded in tool_input fields), which Python's triple-quoted string
# accepts but json.loads rejects -- causing the SDD review-order gate
# to fall open silently with a non-blocking traceback. PSR-008 surfaced
# this on every subagent dispatch. Same bug class as commit db58ec1.
DENY=$(WRIT_PARSED_ENVELOPE="$PARSED" python3 <<PY
import json, os, sys
sys.path.insert(0, "$WRIT_DIR/bin/lib")
from importlib import util
spec = util.spec_from_file_location('writ_session', "$SESSION_HELPER")
mod = util.module_from_spec(spec); spec.loader.exec_module(mod)
raw = os.environ.get("WRIT_PARSED_ENVELOPE", "")
try:
    parsed = json.loads(raw)
except (json.JSONDecodeError, ValueError) as _e:
    sys.stderr.write(
        f'[writ-hook json.loads recovery] WRIT_PARSED_ENVELOPE in writ-sdd-review-order.sh: {_e}\\n'
        f'  len={len(raw)} sample={raw[:200]!r}\\n'
    )
    sys.exit(0)
ti = parsed.get("tool_input") or {}
# A plugin install dispatches the reviewer as writ:writ-code-quality-reviewer.
agent_type = (ti.get("subagent_type") or "").lower().removeprefix("writ:")
if "code-review" not in agent_type and agent_type not in ("writ-code-quality-reviewer",):
    sys.exit(0)
from review_findings import review_order_key, spec_review_done
session = mod._read_cache("$SESSION_ID")
if not spec_review_done(session, ti.get("task_id")):
    key = review_order_key(session, ti.get("task_id"))
    print(f"ENF-PROC-SDD-001: code-quality review dispatched before spec-compliance review completed for task '{key}'. Run writ-spec-reviewer first; its completion is recorded when it stops. Then dispatch writ-code-quality-reviewer.")
PY
)

if [ -n "$DENY" ]; then
    emit_deny "$DENY"
fi
exit 0
