#!/usr/bin/env bash
# Writ bootstrap for Grok Build. Reuses the Claude plugin venv/daemon when they
# already exist. Does not write ~/.claude/settings.json.
#
# Usage:
#   bash scripts/bootstrap-grok.sh
#   bash scripts/bootstrap-grok.sh --patch-compat   # also write [compat.claude] hooks=false
#   bash scripts/bootstrap-grok.sh --preflight
set -euo pipefail

PREFLIGHT=0
PATCH_COMPAT=0
for arg in "$@"; do
    case "$arg" in
        --preflight) PREFLIGHT=1 ;;
        --patch-compat) PATCH_COMPAT=1 ;;
        *) echo "Unknown argument: $arg (accepted: --preflight, --patch-compat)" >&2; exit 1 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WRIT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WRIT_DATA="${GROK_PLUGIN_DATA:-${CLAUDE_PLUGIN_DATA:-$HOME/.cache/writ}}"
VENV_DIR="${WRIT_DATA}/.venv"

echo "Writ Grok bootstrap"
echo "  WRIT_DIR=$WRIT_DIR"
echo "  WRIT_DATA=$WRIT_DATA"

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 is required" >&2
    exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: docker is required (Neo4j runs in a container)" >&2
    exit 1
fi

if [ "$PREFLIGHT" -eq 1 ]; then
    echo "preflight ok"
    exit 0
fi

mkdir -p "$WRIT_DATA"
if [ ! -x "$VENV_DIR/bin/python" ]; then
    python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install -e "$WRIT_DIR" >/dev/null

if curl -sf --connect-timeout 0.5 --max-time 2 http://127.0.0.1:8765/health >/dev/null 2>&1; then
    echo "daemon already healthy on :8765"
else
    echo "starting daemon via scripts/ensure-server.sh"
    bash "$WRIT_DIR/scripts/ensure-server.sh" || true
fi

if command -v grok >/dev/null 2>&1; then
    echo "Install the plugin with:"
    echo "  grok plugin install \"$WRIT_DIR\" --trust"
else
    echo "grok CLI not on PATH. Install Grok Build, then:"
    echo "  grok plugin install \"$WRIT_DIR\" --trust"
fi

echo
echo "To avoid double-firing Claude-compat hooks, add this to ~/.grok/config.toml:"
echo
echo "[compat.claude]"
echo "hooks = false"
echo

if [ "$PATCH_COMPAT" -eq 1 ]; then
    CONFIG="${GROK_HOME:-$HOME/.grok}/config.toml"
    mkdir -p "$(dirname "$CONFIG")"
    if [ -f "$CONFIG" ] && grep -q '\[compat.claude\]' "$CONFIG"; then
        echo "compat.claude already present in $CONFIG (not rewritten)"
    else
        printf '\n[compat.claude]\nhooks = false\n' >> "$CONFIG"
        echo "appended [compat.claude] hooks = false to $CONFIG"
    fi
fi
