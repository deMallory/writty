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

## Permissions are standalone-only by default

The `permissions.allow` and `permissions.deny` blocks in this file are rendered
into the user's `~/.claude/settings.json` during a standalone install. The
plugin install path has no equivalent: `plugin.json` does not carry a
permissions field, and `hooks/hooks.json` only registers hook events. Plugin
users would miss the Writ-specific Bash allowlist that suppresses permission
prompts for read-only and onboarding commands, and the `AskUserQuestion`
deny entry.

`scripts/patch-permissions.sh` closes this gap. Plugin users run it once and
the cross-mode allow/deny entries are merged into their `~/.claude/settings.json`.
The cross-mode subset uses wildcard patterns (`*writ/...`) so a single entry
matches both standalone (`$HOME/.claude/skills/writ/...`) and plugin
(`${CLAUDE_PLUGIN_ROOT}/...`) command paths.

When changing the allow/deny lists in this file, mirror any cross-mode entries
in the `ALLOW`/`DENY` arrays inside `scripts/patch-permissions.sh` so plugin
users do not regress. Standalone-only entries (anything hardcoding
`$HOME/.claude/skills/writ/.claude/hooks/...`) belong only here.
