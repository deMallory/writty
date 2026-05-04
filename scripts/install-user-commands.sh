#!/usr/bin/env bash
# Install Writ slash commands at user level (~/.claude/commands/).
#
# Why: Claude Code discovers slash commands from ~/.claude/commands/
# (user-level) and <project>/.claude/commands/ (project-level). The
# Writ skill's own .claude/commands/ directory is only discovered when
# the active session's cwd is the skill itself. Running this script
# once after install propagates the commands so /writ-approve etc.
# work from any project directory.
#
# Idempotent: safe to re-run; copies overwrite previous installs so a
# changed command propagates on next run.
#
# Usage:
#   bash scripts/install-user-commands.sh           # default: ~/.claude/commands
#   USER_COMMANDS_DIR=/path bash scripts/install-user-commands.sh

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE_DIR="${SKILL_DIR}/templates/commands"
TARGET_DIR="${USER_COMMANDS_DIR:-${HOME}/.claude/commands}"

if [ ! -d "$SOURCE_DIR" ]; then
    echo "error: source directory missing: $SOURCE_DIR" >&2
    exit 1
fi

mkdir -p "$TARGET_DIR"

count=0
for src in "$SOURCE_DIR"/*.md; do
    [ -e "$src" ] || continue
    name="$(basename "$src")"
    cp "$src" "$TARGET_DIR/$name"
    echo "installed: $TARGET_DIR/$name"
    count=$((count + 1))
done

if [ "$count" -eq 0 ]; then
    echo "warning: no .md files found in $SOURCE_DIR" >&2
    exit 0
fi

echo
echo "$count slash command(s) installed to $TARGET_DIR"
echo "Restart Claude Code (or open a new session) to pick up the changes."
