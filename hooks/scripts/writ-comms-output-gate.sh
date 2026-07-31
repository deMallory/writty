#!/usr/bin/env bash
# ENF-COMMS-OUTPUT-001 punctuation floor: block em-dash slop in the agent's final
# response. The user forbids em dashes, en-dash-as-punctuation, and " -- " used as an
# em-dash substitute. Advisory rule-text alone failed, so this is a deterministic
# lexical backstop (zero false positives: the char is present or it is not).
#
# Stop hook, ALL modes. Loop-safe: surfaces via stderr + exit 1 (the verify-before-
# claim pattern), guarded by stop_hook_active so a continuation Stop is a no-op. Reads
# the last assistant message from transcript_path; strips code spans first so an em
# dash inside quoted code or a `git checkout --` example is not flagged.
set -euo pipefail
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
WRIT_DIR="$(cd "$HOOK_DIR/../.." && pwd)"
source "$WRIT_DIR/bin/lib/common.sh"
hook_instrument "writ-comms-output-gate"

STDIN_JSON=$(cat 2>/dev/null || echo '{}')
stop_hook_active "$STDIN_JSON" && exit 0          # block at most once; never loop

TP=$(printf '%s' "$STDIN_JSON" \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('transcript_path',''))" 2>/dev/null || echo "")
[ -n "$TP" ] && [ -f "$TP" ] || exit 0

# NOTE: the transcript path is passed via env (WRIT_TP) and read INSIDE python.
# We cannot pipe `tail` into `python3 - <<'PY'`: a stdin heredoc makes the script
# its own stdin, so the piped transcript would never be seen. The forbidden chars
# are written as \u escapes (NOT literal em/en dash) to avoid any encoding mangling.
VIOLATION=$(WRIT_TP="$TP" python3 - <<'PY' 2>/dev/null
import os, json, re
EM = chr(0x2014)  # em dash, ASCII-safe source (no literal char in this file)
EN = chr(0x2013)  # en dash, ASCII-safe source
tp = os.environ.get("WRIT_TP", "")
try:
    with open(tp, encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()
except Exception:
    raise SystemExit(0)
lines = lines[-400:]  # bound the scan: only the tail of the transcript
last_text = ""
for line in lines:
    if '"assistant"' not in line:
        continue
    try:
        d = json.loads(line)
    except Exception:
        continue
    if d.get("type") != "assistant":
        continue
    content = (d.get("message") or {}).get("content")
    if isinstance(content, list):
        last_text = "".join(b.get("text", "") for b in content
                            if isinstance(b, dict) and b.get("type") == "text")
    elif isinstance(content, str):
        last_text = content
if not last_text:
    raise SystemExit(0)
# strip fenced + inline code so code / CLI examples are never scanned
prose = re.sub(r"```.*?```", "", last_text, flags=re.DOTALL)
prose = re.sub(r"`[^`]*`", "", prose)
hits = []
if EM in prose: hits.append("em dash (" + EM + ")")
if EN in prose: hits.append("en dash (" + EN + ")")
if re.search(r" -- ", prose): hits.append('" -- " (double hyphen as em-dash)')
if hits:
    print("; ".join(hits))
PY
) || true

if [ -n "$VIOLATION" ]; then
    log_gate_decision "comms-output" "deny" "$VIOLATION" "assistant-response"
    echo "[ENF-COMMS-OUTPUT-001] Your last response used forbidden punctuation: $VIOLATION. \
The user forbids em dashes and em-dash-substitute double hyphens. Re-send the SAME content using \
commas, colons, semicolons, or parentheses for clause breaks, and hyphens only to join words." >&2
    exit 1
fi
log_gate_decision "comms-output" "allow" "no forbidden punctuation" "assistant-response"
exit 0
