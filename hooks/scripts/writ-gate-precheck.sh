#!/usr/bin/env bash
# Stop hook, work mode: a reply that asks the user for an approval the pending gate would
# refuse goes back to the model with the reason. A refused approval spends the user's
# token, so this runs the same check (_gate_precheck) before the user is asked, and the
# slip costs the model one edit instead.
#
# Only a reply carrying an approval request (approval_evidence.REQUEST_MARKERS) is
# checked; every other turn ends untouched. The reply comes from last_assistant_message
# (Mistty, through the bridge) or the transcript (Claude Code). Loop-safe: a continuation
# Stop exits first, and Vibe caps its re-runs at 3. Writes no state, claims no token.
set -euo pipefail
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
WRIT_DIR="$(cd "$HOOK_DIR/../.." && pwd)"
source "$WRIT_DIR/bin/lib/common.sh"
hook_instrument "writ-gate-precheck"

STDIN_JSON=$(cat 2>/dev/null || echo '{}')
# Keyed before the exits below so hook_instrument's exit trap files this hook's rows under
# the session (see writ-comms-output-gate.sh).
SESSION_ID="$(printf '%s' "$STDIN_JSON" | json_transform '.session_id // empty' \
    "d.get('session_id')" 2>/dev/null || true)"

stop_hook_active "$STDIN_JSON" && exit 0
WRIT_HOOK_LOG_SINK="$(hook_log_sink)"

# The envelope travels in the environment, never into the python source.
PROBLEM=$(WRIT_STOP_ENVELOPE="$STDIN_JSON" python3 - "$WRIT_DIR/bin/lib" <<'PY' 2>>"$WRIT_HOOK_LOG_SINK" || true
import json, os, sys
from importlib import util

lib = sys.argv[1]
try:
    env = json.loads(os.environ.get("WRIT_STOP_ENVELOPE") or "{}")
except ValueError:
    raise SystemExit(0)
sid = env.get("session_id") or ""
if not isinstance(sid, str) or not sid:
    raise SystemExit(0)
sys.path.insert(0, lib)
import approval_evidence

last = env.get("last_assistant_message") or env.get("lastAssistantMessage")
if isinstance(last, str) and last:
    asked = approval_evidence.has_request_marker(last)
else:
    # Zero trailing user rows: at Stop the newest assistant text must be this turn's.
    asked = approval_evidence.evidence_flags(
        env.get("transcript_path") or "", trailing_user_rows=0)[0]
if not asked:
    raise SystemExit(0)
spec = util.spec_from_file_location("writ_session", os.path.join(lib, "writ-session.py"))
mod = util.module_from_spec(spec)
spec.loader.exec_module(mod)
cache = mod._read_cache(sid)
# The root the approval claim hashes, so both judge the same plan.
root = cache.get("project_root")
gate = mod._next_pending_gate(cache, sid)
if not gate or not isinstance(root, str) or not root:
    raise SystemExit(0)
problem = mod._gate_precheck(root, sid, gate)
if problem:
    print(problem)
PY
)
[ -z "$PROBLEM" ] && exit 0
printf '[Writ: gate precheck] The approval you asked for would be refused, and a refused approval is spent. Fix this, then ask again. %s\n' \
    "$PROBLEM" >&2
exit 2
