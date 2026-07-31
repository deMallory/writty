#!/bin/bash
# INV-7b: WebFetch/WebSearch auto-capture -- PostToolUse hook.
#
# In investigate mode, records the URL(s) the agent fetched + a content excerpt as
# `url` citations in the session citation_log, so the INV-7a triangulation-gate
# enforces over captured (not self-reported) web evidence. The web analog of the
# 7a Bash command-capture. Best-effort; exit 0 always (never blocks the web call).
#
# Hook type: PostToolUse (matcher: WebFetch|WebSearch)
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
source "$SKILL_DIR/bin/lib/common.sh"
hook_instrument "writ-web-capture"
SESSION_HELPER="$SKILL_DIR/bin/lib/writ-session.py"

load_hook_env
TOOL_NAME="$HOOK_TOOL_NAME"
case "$TOOL_NAME" in
  WebFetch|WebSearch) ;;
  *) exit 0 ;;
esac

# Direct helper calls (not _writ_session) so mode + capture honor the session's own
# cache dir (WRIT_CACHE_DIR / tmp), independent of any running server.
SID="$HOOK_SESSION_ID"
[ -n "$SID" ] || exit 0

MODE=$(python3 "$SESSION_HELPER" mode get "$SID" 2>/dev/null | tr -d '[:space:]' || echo "")
[ "$MODE" = "investigate" ] || exit 0

# Build the add-citation payloads (one NDJSON line each) from the tool envelope.
# Quoted heredoc -> the Python is verbatim (no bash interpolation); PARSED is argv[1].
ADDS=$(python3 - "$HOOK_ENVELOPE" 2>/dev/null <<'PYEOF'
import sys, json, re
try:
    d = json.loads(sys.argv[1])
except Exception:
    sys.exit(0)
ti = d.get('tool_input') or {}
ti = ti if isinstance(ti, dict) else {}
raw = d.get('tool_output')
out = raw if isinstance(raw, str) else (json.dumps(raw) if raw is not None else '')
tool = d.get('tool_name', '')
cites = []
if tool == 'WebFetch':
    url = ti.get('url') or ''
    if url:
        cites.append({'ref': url, 'excerpt': out[:480]})
elif tool == 'WebSearch':
    query = (ti.get('query') or '')[:200]
    seen = set()
    for m in re.findall(r'https?://\S+', out):
        m = m.rstrip('.,);]>"\'')
        if not m or m in seen:
            continue
        seen.add(m)
        cites.append({'ref': m, 'excerpt': 'search: ' + query})
        if len(cites) >= 8:
            break
for c in cites:
    print(json.dumps({'artifact_type': 'url', 'ref': c['ref'], 'excerpt': c.get('excerpt', '')}))
PYEOF
) || ADDS=""

if [ -n "$ADDS" ]; then
  while IFS= read -r CITE; do
    [ -n "$CITE" ] || continue
    python3 "$SESSION_HELPER" update "$SID" --add-citation "$CITE" >/dev/null 2>&1 || true
  done <<< "$ADDS"
fi

exit 0
