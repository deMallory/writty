#!/usr/bin/env bash
# Writ patch-permissions installer
#
# Merges the Writ-specific cross-mode allow/deny entries into the user's
# ~/.claude/settings.json. Idempotent: re-running adds nothing new.
#
# Why this exists. Standalone-skill installs render templates/settings.json
# into ~/.claude/settings.json via scripts/install-harness-config.sh, so the
# permissions block ships automatically. Plugin installs do not: the plugin
# manifest does not carry a permissions field, and hooks/hooks.json only
# registers hook events. Plugin users would otherwise hit a permission prompt
# every time the agent runs a read-only Writ command, defeating the point of
# the allowlist.
#
# This script is safe to run on either install path: the allow/deny patterns
# use wildcards (*writ/...) so a single entry matches both standalone
# ($HOME/.claude/skills/writ/...) and plugin (${CLAUDE_PLUGIN_ROOT}/...)
# command paths.
#
# Usage:
#   bash scripts/patch-permissions.sh            # patch
#   bash scripts/patch-permissions.sh --dry-run  # preview, no write
#
# Override target with WRIT_SETTINGS_TARGET=/path/to/settings.json.
#
# Exit codes:
#   0  patched (or already up to date, or dry-run success)
#   1  missing prerequisite (jq) or target file
#   2  write failure

set -euo pipefail

TARGET="${WRIT_SETTINGS_TARGET:-$HOME/.claude/settings.json}"
DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then
    DRY_RUN=1
fi

# Cross-mode allow rules. Wildcards match both standalone and plugin paths.
ALLOW=(
    "Bash(python3 *writ-session.py *)"
    "Bash(bash *writ/bin/check-gates.sh*)"
    "Bash(bash *writ/bin/verify-files.sh*)"
    "Bash(bash *writ/bin/scan-deps.sh*)"
    "Bash(bash *writ/bin/run-analysis.sh*)"
    "Bash(bash *writ/bin/validate-handoff.sh*)"
    "Bash(*writ/bin/writ query *)"
    "Bash(*writ/bin/writ status*)"
    "Bash(*writ/bin/writ role-prompt *)"
    "Bash(*writ/bin/writ validate*)"
    "Bash(*writ/bin/writ analyze-friction*)"
    "Bash(*writ/bin/writ audit-session*)"
    "Bash(bash *writ/scripts/bootstrap.sh*)"
    "Bash(bash *writ/scripts/bootstrap-plugin.sh*)"
    "Bash(bash *writ/scripts/ensure-server.sh*)"
    "Bash(bash *writ/scripts/install-harness-config.sh*)"
    "Bash(bash *writ/scripts/install-user-commands.sh*)"
    "Bash(bash *writ/scripts/stop-server.sh*)"
)

DENY=(
    "AskUserQuestion"
)

if ! command -v jq >/dev/null 2>&1; then
    echo "ERROR: jq is required but not found on PATH." >&2
    echo "Install jq (apt/brew/dnf install jq) and retry." >&2
    exit 1
fi

if [ ! -f "$TARGET" ]; then
    echo "ERROR: target settings file not found: $TARGET" >&2
    echo "Hint: pass WRIT_SETTINGS_TARGET=/path/to/settings.json if it lives elsewhere." >&2
    exit 1
fi

TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT

ALLOW_JSON=$(printf '%s\n' "${ALLOW[@]}" | jq -R . | jq -s .)
DENY_JSON=$(printf '%s\n' "${DENY[@]}" | jq -R . | jq -s .)

# Append only entries not already present. Preserves the user's existing
# ordering -- no sort, no unique_by reorder.
jq --argjson new_allow "$ALLOW_JSON" --argjson new_deny "$DENY_JSON" '
    # Append only entries not already present. existing/incoming are bound
    # to values (not filters) so they survive the map/select context switch
    # where . becomes a single string from incoming.
    def append_new($existing; $incoming):
        $existing + ($incoming | map(select(. as $i | ($existing | index($i)) | not)));
    .permissions = (.permissions // {}) |
    .permissions.allow = append_new(.permissions.allow // []; $new_allow) |
    .permissions.deny  = append_new(.permissions.deny  // []; $new_deny)
' "$TARGET" > "$TMP"

if cmp -s "$TARGET" "$TMP"; then
    echo "No changes needed: $TARGET already contains the Writ permission entries."
    exit 0
fi

if [ "$DRY_RUN" = "1" ]; then
    echo "[dry-run] would write merged settings to $TARGET. Diff:"
    diff -u "$TARGET" "$TMP" || true
    exit 0
fi

BACKUP="${TARGET}.bak.$(date -u '+%Y%m%d%H%M%S')"
cp "$TARGET" "$BACKUP" || { echo "ERROR: failed to create backup at $BACKUP" >&2; exit 2; }
mv "$TMP" "$TARGET" || { echo "ERROR: failed to write $TARGET" >&2; exit 2; }
trap - EXIT

echo "Patched $TARGET"
echo "Backup: $BACKUP"
