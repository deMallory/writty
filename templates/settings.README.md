# templates/settings.json — legacy install template

This file is consumed by `scripts/install-harness-config.sh` when Writ is
installed as a standalone skill at `~/.claude/skills/writ/`. The script
substitutes `$HOME` and renders the JSON into `~/.claude/settings.json`,
registering all 31 hooks against the user's global Claude Code config.

**Plugin installs do not use this file.** When Writ is installed via
`/plugin install writ@writ`, Claude Code reads the hook configuration from
`hooks/hooks.json` (at the plugin root), which uses `${CLAUDE_PLUGIN_ROOT}`
paths so registrations remain valid across plugin upgrades.

Keep the hook registrations in `hooks/hooks.json` and `templates/settings.json`
in sync until the standalone install path is sunset. After every change to one,
update the other.

## Standalone-only rendering: permissions and CLAUDE.md

`scripts/install-harness-config.sh` renders two files from this directory into
the user's `~/.claude/` during a standalone install: `templates/settings.json`
(producing the global `~/.claude/settings.json` with hook registrations,
permissions, and other harness wiring) and `templates/CLAUDE.md` (producing
the global Claude Code instructions file). The plugin install path renders
neither. The plugin manifest schema does not carry a permissions field, and
the plugin lifecycle does not touch `~/.claude/CLAUDE.md`. Plugin users would
otherwise miss the Writ-specific Bash allowlist plus the `AskUserQuestion`
deny entry, and the mandatory-workflow instructions that Writ relies on.

`scripts/patch-global-config.sh` closes both gaps in a single run. Plugin
users invoke it once after `bootstrap-plugin.sh`. The settings step merges
the cross-mode allow/deny entries into `~/.claude/settings.json`; the
CLAUDE.md step renders this directory's `CLAUDE.md` into `~/.claude/CLAUDE.md`.
Both steps back up any pre-existing file before overwriting and no-op when
the target is already in sync.

The cross-mode allow/deny subset uses wildcard patterns (`*writ/...`) so a
single entry matches both standalone (`$HOME/.claude/skills/writ/...`) and
plugin (`${CLAUDE_PLUGIN_ROOT}/...`) command paths. When changing the
allow/deny lists in this file, mirror any cross-mode entries in the
`ALLOW`/`DENY` arrays inside `scripts/patch-global-config.sh` so plugin users
do not regress. Standalone-only entries (anything hardcoding
`$HOME/.claude/skills/writ/.claude/hooks/...`) belong only here.

`templates/CLAUDE.md` is a single source of truth for both install paths:
edits land for standalone users via `install-harness-config.sh` and for
plugin users via `patch-global-config.sh`, with no manual duplication.
