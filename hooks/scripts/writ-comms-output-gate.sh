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

# Grok fires an observe-only Stop at session end. Gate genuine turn ends only.
# Claude Stop has no reason field; empty reason still runs (Claude path).
# lastAssistantMessage is preferred; transcript_path is the Claude fallback.
VIOLATION=$(WRIT_STOP_ENVELOPE="$STDIN_JSON" python3 - <<'PY' 2>/dev/null
import json, os, re
EM = chr(0x2014)
EN = chr(0x2013)
try:
    env = json.loads(os.environ.get("WRIT_STOP_ENVELOPE") or "{}")
except Exception:
    raise SystemExit(0)
reason = env.get("reason") or ""
if reason and reason != "end_turn":
    raise SystemExit(0)
last_text = env.get("lastAssistantMessage") or env.get("last_assistant_message") or ""
if not last_text:
    tp = env.get("transcript_path") or ""
    if not tp or not os.path.isfile(tp):
        raise SystemExit(0)
    try:
        with open(tp, encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()[-400:]
    except Exception:
        raise SystemExit(0)
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
            last_text = "".join(
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
        elif isinstance(content, str):
            last_text = content
if not last_text:
    raise SystemExit(0)
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
    REASON="[ENF-COMMS-OUTPUT-001] Your last response used forbidden punctuation: $VIOLATION. \
The user forbids em dashes and em-dash-substitute double hyphens. Re-send the SAME content using \
commas, colons, semicolons, or parentheses for clause breaks, and hyphens only to join words."
    echo "$REASON" >&2
    emit_stop_block "$REASON"
    exit 2
fi
log_gate_decision "comms-output" "allow" "no forbidden punctuation" "assistant-response"
exit 0
