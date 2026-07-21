#!/usr/bin/env bash
# Universal passive black-box capture. Reads the raw stdin envelope, logs it (gated by the
# blackbox sentinel / WRIT_BLACKBOX), emits NOTHING, exits 0. Registered first on tool and
# lifecycle events so every event's raw input is captured regardless of which functional hook
# (if any) also handles it. Behavior-neutral: never writes stdout, never blocks, never fails.
#
# When capture is OFF this exits before sourcing common.sh: just one sentinel stat + a stdin
# drain, so the permanent hot-path cost is a single cheap bash spawn per tool call.
[ "${WRIT_BLACKBOX:-}" = "1" ] || [ -f "${HOME:-}/.claude/writ-blackbox.on" ] || { cat >/dev/null 2>&1; exit 0; }
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
WRIT_DIR="$(cd "$HOOK_DIR/../.." && pwd)"
source "$WRIT_DIR/bin/lib/common.sh" 2>/dev/null || { cat >/dev/null 2>&1; exit 0; }
blackbox_log in writ-blackbox-capture "" || true
exit 0
