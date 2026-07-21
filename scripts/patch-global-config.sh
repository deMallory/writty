#!/usr/bin/env bash
# Writ global-config patcher -- THE post-install step for ~/.claude/
#
# Hooks are owned by the plugin (hooks/hooks.json, the single source of truth);
# the standalone settings.json hook seeder was sunset. This script delivers the
# two things a plugin manifest cannot ship, plus the global instructions:
#   1. Merges the Writ-specific cross-mode allow/deny entries into
#      ~/.claude/settings.json (idempotent, ordering preserved). Does NOT touch
#      the hooks block -- the plugin registers hooks.
#   2. Merges the Writ statusLine into ~/.claude/settings.json. A plugin cannot
#      ship the main statusLine (the manifest has no field; a plugin settings.json
#      honors only agent/subagentStatusLine; no hook can set it), so this patch is
#      the delivery path. Policy: add when absent, refresh when it already points
#      at a writ-statusline.sh (survives plugin-upgrade path changes), and leave a
#      foreign statusLine untouched (never clobber the user's choice).
#   3. Renders templates/CLAUDE.md into ~/.claude/CLAUDE.md (backup-if-exists,
#      skip-if-identical).
#
# Why this exists. The plugin manifest schema has no permissions field,
# hooks/hooks.json only registers hook events, and the plugin lifecycle does not
# touch ~/.claude/CLAUDE.md. Without this patch, users would hit a permission
# prompt for every read-only Writ command and miss the mandatory-workflow
# instructions Writ relies on.
#
# Settings handling. The allow/deny patterns use wildcards (*writ/...) so a
# single entry matches both the plugin (${CLAUDE_PLUGIN_ROOT}/...) and the
# dev/repo run path ($HOME/.claude/skills/writ/...). Existing user entries are
# preserved in their original order; only missing entries are appended.
#
# CLAUDE.md handling. If the existing file matches the template byte-for-byte,
# nothing is written. Otherwise the existing file is backed up to
# CLAUDE.md.bak.<utc-timestamp> and replaced with the template. The template
# contains no env-var references; envsubst is invoked anyway for consistency.
#
# Usage:
#   bash scripts/patch-global-config.sh             # patch
#   bash scripts/patch-global-config.sh --dry-run   # preview, no write
#
# Overrides:
#   WRIT_SETTINGS_TARGET=/path/to/settings.json
#   WRIT_CLAUDE_MD_TARGET=/path/to/CLAUDE.md
#
# Exit codes:
#   0  patched, already up to date, or dry-run success
#   1  missing prerequisite (jq, envsubst) or missing template
#   2  write failure

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TEMPLATES_DIR="$SKILL_DIR/templates"

SETTINGS_TARGET="${WRIT_SETTINGS_TARGET:-$HOME/.claude/settings.json}"
CLAUDE_MD_TARGET="${WRIT_CLAUDE_MD_TARGET:-$HOME/.claude/CLAUDE.md}"
CLAUDE_MD_TEMPLATE="$TEMPLATES_DIR/CLAUDE.md"

# Concrete statusLine command baked at patch time. writ-statusline.sh self-resolves
# its own dir from $0 (no ${CLAUDE_PLUGIN_ROOT} dependency) and degrades cleanly when
# the server is down, so an absolute-path invocation works in any context.
SL_CMD="bash $SKILL_DIR/hooks/scripts/writ-statusline.sh"

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
    "Bash(bash *writ/scripts/install-user-commands.sh*)"
    "Bash(bash *writ/scripts/stop-server.sh*)"
)

DENY=(
    "AskUserQuestion"
    # Gate-approval boundary: the agent must never write a .claude/gates/*.approved
    # file directly -- that would self-approve a human-oversight gate (the north star).
    # Scoped to the gates dir so unrelated paths (e.g. a test file named
    # *gates_approved*) are not collaterally blocked.
    "Bash(touch */.claude/gates/*)"
    "Bash(*>.claude/gates/*)"
    "Bash(*/.claude/gates/*approve*)"
)

# Preconditions
if ! command -v jq >/dev/null 2>&1; then
    echo "ERROR: jq is required but not found on PATH." >&2
    echo "Install jq (apt/brew/dnf install jq) and retry." >&2
    exit 1
fi

if ! command -v envsubst >/dev/null 2>&1; then
    echo "ERROR: envsubst is required but not found on PATH." >&2
    echo "Install the gettext package (apt/brew/dnf install gettext) and retry." >&2
    exit 1
fi

if [ ! -f "$CLAUDE_MD_TEMPLATE" ]; then
    echo "ERROR: template missing: $CLAUDE_MD_TEMPLATE" >&2
    exit 1
fi

timestamp() { date -u '+%Y%m%d%H%M%S'; }

# ─────────────────────────────────────────────────────────────────────────────
# 1. Patch settings.json (permissions)
# ─────────────────────────────────────────────────────────────────────────────
patch_settings() {
    if [ ! -f "$SETTINGS_TARGET" ]; then
        echo "[settings] ERROR: target settings file not found: $SETTINGS_TARGET" >&2
        echo "[settings] Hint: pass WRIT_SETTINGS_TARGET=/path/to/settings.json if it lives elsewhere." >&2
        return 1
    fi

    local tmp
    tmp=$(mktemp)
    local rc=0

    local allow_json deny_json
    allow_json=$(printf '%s\n' "${ALLOW[@]}" | jq -R . | jq -s .)
    deny_json=$(printf '%s\n' "${DENY[@]}" | jq -R . | jq -s .)

    # Inform (do not act) when a non-Writ statusLine is already configured: the
    # merge below leaves it untouched, so point the user at the opt-in command.
    local existing_sl
    existing_sl=$(jq -r '.statusLine.command // ""' "$SETTINGS_TARGET" 2>/dev/null || echo "")
    if [ -n "$existing_sl" ] && ! printf '%s' "$existing_sl" | grep -q 'writ-statusline\.sh'; then
        echo "[settings] An existing (non-Writ) statusLine is configured; leaving it untouched."
        echo "[settings] To use the Writ context meter, set statusLine.command to: $SL_CMD"
    fi

    jq --argjson new_allow "$allow_json" --argjson new_deny "$deny_json" --arg sl_cmd "$SL_CMD" '
        # Append only entries not already present. existing/incoming are bound
        # to values (not filters) so they survive the map/select context switch
        # where . becomes a single string from incoming.
        def append_new($existing; $incoming):
            $existing + ($incoming | map(select(. as $i | ($existing | index($i)) | not)));
        .permissions = (.permissions // {}) |
        .permissions.allow = append_new(.permissions.allow // []; $new_allow) |
        .permissions.deny  = append_new(.permissions.deny  // []; $new_deny) |
        # statusLine: add when absent, refresh when it is already a writ-statusline.sh
        # (upgrade-safe), leave a foreign statusLine untouched.
        .statusLine = (
            if (.statusLine == null) then {"type": "command", "command": $sl_cmd}
            elif ((.statusLine.command // "") | test("writ-statusline\\.sh")) then {"type": "command", "command": $sl_cmd}
            else .statusLine end
        )
    ' "$SETTINGS_TARGET" > "$tmp"

    if cmp -s "$SETTINGS_TARGET" "$tmp"; then
        echo "[settings] No changes needed: $SETTINGS_TARGET already contains the Writ permission + statusLine entries."
        rm -f "$tmp"
        return 0
    fi

    if [ "$DRY_RUN" = "1" ]; then
        echo "[settings] [dry-run] would write merged settings to $SETTINGS_TARGET. Diff:"
        diff -u "$SETTINGS_TARGET" "$tmp" || true
        rm -f "$tmp"
        return 0
    fi

    local backup="${SETTINGS_TARGET}.bak.$(timestamp)"
    cp "$SETTINGS_TARGET" "$backup" || { echo "[settings] ERROR: failed to create backup at $backup" >&2; rm -f "$tmp"; return 2; }
    mv "$tmp" "$SETTINGS_TARGET" || { echo "[settings] ERROR: failed to write $SETTINGS_TARGET" >&2; return 2; }
    echo "[settings] Patched $SETTINGS_TARGET"
    echo "[settings] Backup:  $backup"
    return $rc
}

# ─────────────────────────────────────────────────────────────────────────────
# 2. Install/refresh CLAUDE.md
# ─────────────────────────────────────────────────────────────────────────────
patch_claude_md() {
    local rendered
    rendered=$(mktemp)
    # Only $HOME is substituted; the template currently uses no env vars, but
    # mirror the standalone installer so future template edits stay compatible.
    envsubst '$HOME' < "$CLAUDE_MD_TEMPLATE" > "$rendered"

    if [ -f "$CLAUDE_MD_TARGET" ] && cmp -s "$CLAUDE_MD_TARGET" "$rendered"; then
        echo "[CLAUDE.md] No changes needed: $CLAUDE_MD_TARGET already matches the Writ template."
        rm -f "$rendered"
        return 0
    fi

    if [ "$DRY_RUN" = "1" ]; then
        if [ -f "$CLAUDE_MD_TARGET" ]; then
            echo "[CLAUDE.md] [dry-run] would replace $CLAUDE_MD_TARGET. Diff:"
            diff -u "$CLAUDE_MD_TARGET" "$rendered" || true
        else
            echo "[CLAUDE.md] [dry-run] would create $CLAUDE_MD_TARGET from template ($(wc -l < "$rendered") lines)."
        fi
        rm -f "$rendered"
        return 0
    fi

    mkdir -p "$(dirname "$CLAUDE_MD_TARGET")" 2>/dev/null || true

    if [ -f "$CLAUDE_MD_TARGET" ]; then
        local backup="${CLAUDE_MD_TARGET}.bak.$(timestamp)"
        cp "$CLAUDE_MD_TARGET" "$backup" || { echo "[CLAUDE.md] ERROR: failed to create backup at $backup" >&2; rm -f "$rendered"; return 2; }
        mv "$rendered" "$CLAUDE_MD_TARGET" || { echo "[CLAUDE.md] ERROR: failed to write $CLAUDE_MD_TARGET" >&2; return 2; }
        echo "[CLAUDE.md] Replaced $CLAUDE_MD_TARGET"
        echo "[CLAUDE.md] Backup:   $backup"
    else
        mv "$rendered" "$CLAUDE_MD_TARGET" || { echo "[CLAUDE.md] ERROR: failed to write $CLAUDE_MD_TARGET" >&2; return 2; }
        echo "[CLAUDE.md] Created $CLAUDE_MD_TARGET"
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# Run both phases. Each is independent; surface a non-zero exit if either fails.
# ─────────────────────────────────────────────────────────────────────────────
overall=0
patch_settings || overall=$?
patch_claude_md || overall=$?
exit $overall
