#!/usr/bin/env bash
# PostToolUse on plan.md: run the phase-a check at write time. At approval a failed
# check spends the user's token; here it costs the model one edit. Context only, never
# a decision. _validate_phase_a writes no state and claims no token.
set -euo pipefail
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
WRIT_DIR="$(cd "$HOOK_DIR/../.." && pwd)"
source "$WRIT_DIR/bin/lib/common.sh"
hook_instrument "writ-validate-plan-draft"
WRIT_HOOK_LOG_SINK="$(hook_log_sink)"

load_hook_env
SESSION_ID="$HOOK_SESSION_ID"
[ -z "$SESSION_ID" ] && exit 0
# The path test costs no process; most writes stop here.
case "$HOOK_FILE_PATH" in */plan.md) ;; *) exit 0 ;; esac
is_work_mode "$SESSION_ID" || exit 0
CWD=$(pwd -P 2>/dev/null || printf '')
[ -z "$CWD" ] && exit 0

# Values travel through argv, never into the python source (see validate-exit-plan.sh).
AC_REPLY=$(python3 -c "
import json, os, sys
from importlib import util
helper, sid, cwd, written = sys.argv[1:5]
sys.path.insert(0, os.path.dirname(helper))
spec = util.spec_from_file_location('writ_session', helper)
mod = util.module_from_spec(spec)
spec.loader.exec_module(mod)
root, _tier = mod.resolve_project_root(start=cwd)
if not root:
    raise SystemExit
gate_plan = mod._find_plan_md(root, sid)
if gate_plan and os.path.realpath(gate_plan) != os.path.realpath(written):
    text = f'The approval reads {gate_plan}, not {written}. Write the plan there.'
else:
    error = mod._validate_phase_a(root, sid)
    text = (f'{error} The approval runs this same check, so fix it before presenting.'
            if error else 'plan.md passes the phase-a structure check.')
print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PostToolUse',
                                         'additionalContext': '[Writ: plan check] ' + text}}))
" "$WRIT_DIR/bin/lib/writ-session.py" "$SESSION_ID" "$CWD" "$HOOK_FILE_PATH" \
    2>>"$WRIT_HOOK_LOG_SINK") || AC_REPLY=""
[ -n "$AC_REPLY" ] && emit_hook_reply "$AC_REPLY"
exit 0
