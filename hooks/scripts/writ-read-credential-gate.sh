#!/bin/bash
# WRIT-READ-CREDENTIAL-GATE: refuse reads of secret files (SEC-CREDENTIAL-READ).
#
# PreToolUse (matcher: Read|Grep|Bash), EVERY mode, subagents included, no daemon
# call. Whatever Claude reads leaves the machine, so the read is the leak; the
# write side is SEC-CREDENTIAL-WRITE in writ/session/gates.py. Classification lives
# in bin/lib/credential_read.py (path only, the file is never opened).
# Exit: always 0; a deny is the JSON on stdout.
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=/dev/null
. "$SKILL_DIR/bin/lib/common.sh" 2>/dev/null || exit 0

HIT=$(WRIT_DIR="$SKILL_DIR" python3 "$SKILL_DIR/bin/lib/credential_read.py" 2>/dev/null)
[ -n "$HIT" ] || exit 0

emit_deny "[SEC-CREDENTIAL-READ] Refusing to read '$HIT': secret files must not enter the conversation, their content would leave this machine. Read a template (.env.example) or ask the user for the variable names."
exit 0
