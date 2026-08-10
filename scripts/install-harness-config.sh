#!/usr/bin/env bash
# Writ harness-config installer
#
# Renders templates/settings.fork.json (the fork's .claude/hooks registration
# seed; templates/settings.json is the generated plugin mirror and carries no
# fork registrations) and templates/CLAUDE.md with $HOME substitution and
# writes them into ~/.claude/ (or $WRIT_INSTALL_TARGET).
#
# Safe to run repeatedly:
#   - Backs up existing files to <name>.bak.<timestamp> before overwriting
#   - Skips write + backup entirely when rendered content matches target
#   - --dry-run prints rendered content to stdout, changes nothing
#
# Usage:
#   bash scripts/install-harness-config.sh            # install
#   bash scripts/install-harness-config.sh --dry-run  # preview only
#
# Exit codes:
#   0  success (or dry-run success)
#   1  missing template
#   2  write failure

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TEMPLATES_DIR="$SKILL_DIR/templates"
TARGET_DIR="${WRIT_INSTALL_TARGET:-$HOME/.claude}"

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then
    DRY_RUN=1
fi

for tmpl in settings.fork.json CLAUDE.md; do
    if [ ! -f "$TEMPLATES_DIR/$tmpl" ]; then
        echo "ERROR: template missing: $TEMPLATES_DIR/$tmpl" >&2
        exit 1
    fi
done

mkdir -p "$TARGET_DIR" 2>/dev/null || true

timestamp() { date -u '+%Y%m%d%H%M%S'; }

render() {
    # Only $HOME is substituted -- other $... in JSON strings stay literal.
    # python3, not gettext: python3 is already a hard prerequisite everywhere,
    # so this script adds no tool requirement of its own.
    python3 -c '
import os, sys
home = os.environ["HOME"]
sys.stdout.write(sys.stdin.read().replace("${HOME}", home).replace("$HOME", home))
' < "$TEMPLATES_DIR/$1"
}

install_one() {
    local name="$1"
    local target_name="${2:-$1}"
    local target="$TARGET_DIR/$target_name"
    local rendered
    rendered="$(render "$name")"

    if [ $DRY_RUN -eq 1 ]; then
        printf '=== %s ===\n%s\n' "$target" "$rendered"
        return 0
    fi

    if [ -f "$target" ]; then
        # Idempotent: skip if content already matches
        if printf '%s' "$rendered" | diff -q - "$target" >/dev/null 2>&1; then
            echo "unchanged: $target"
            return 0
        fi
        local backup="$target.bak.$(timestamp)"
        cp -p "$target" "$backup"
        echo "backed up: $backup"
    fi

    printf '%s' "$rendered" > "$target" || { echo "ERROR: write failed: $target" >&2; exit 2; }
    echo "installed: $target"
}

if [ $DRY_RUN -eq 1 ]; then
    echo "# DRY RUN -- no files will be changed"
fi

install_one settings.fork.json settings.json
install_one CLAUDE.md

if [ $DRY_RUN -eq 0 ]; then
    echo
    echo "Done. Claude Code will pick up the new config on next session start."
fi
