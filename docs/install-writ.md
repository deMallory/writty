# Installing Writ

> **New in v2.0.0**: Writ is now distributable as a Claude Code plugin.
> See the README "Install as a Claude Code plugin" section for the
> plugin install path. The instructions below cover the standalone-skill
> install at `~/.claude/skills/writ/`, which remains supported.

Writ is a Claude Code skill at `~/.claude/skills/writ/`. After cloning
the skill repo there, two install touch-points wire it into the Claude
Code runtime so the hooks and slash commands work from any project
directory.

## 1. Sync hook permissions and registrations

The active settings file Claude Code reads at session start is
`~/.claude/settings.json`. The skill's canonical hook registrations
live in `~/.claude/skills/writ/templates/settings.json`. To install:

```bash
cp ~/.claude/skills/writ/templates/settings.json ~/.claude/settings.json
```

Or, if you have non-Writ entries in your active settings you want to
preserve, merge by hand. The Writ-specific blocks are:
- All `Bash(bash $HOME/.claude/skills/writ/.claude/hooks/*.sh)` lines
  in `permissions.allow`
- All entries under `hooks` whose `command` paths point at
  `$HOME/.claude/skills/writ/.claude/hooks/`

## 2. Install user-level slash commands

Claude Code discovers slash commands from `~/.claude/commands/` (user
level) and `<project>/.claude/commands/` (project level). The Writ
skill's own `.claude/commands/` directory is only discovered when the
active session's cwd is the skill itself, so `/writ-approve` etc. will
not work from your normal project directories without this step.

```bash
bash ~/.claude/skills/writ/scripts/install-user-commands.sh
```

This is idempotent. It copies every `.md` file from
`~/.claude/skills/writ/templates/commands/` to `~/.claude/commands/`.
Re-run after pulling skill updates that add or change a command.

After running, restart Claude Code (or open a new session) to pick up
the new commands.

## Verify install

```bash
test -f ~/.claude/commands/writ-approve.md && echo "/writ-approve installed"
grep -q writ-memory-policy-guard ~/.claude/settings.json && \
    echo "memory-policy-guard hook registered"
```

Both should print confirmation lines. If neither does, re-run the
relevant step above.

## Update path

When the skill is updated (`git pull` or equivalent in
`~/.claude/skills/writ/`), re-run both steps:

```bash
cp ~/.claude/skills/writ/templates/settings.json ~/.claude/settings.json
bash ~/.claude/skills/writ/scripts/install-user-commands.sh
```

Settings sync is destructive (overwrites). Commands install is
idempotent. If you have local `~/.claude/settings.json` customizations,
back up before sync.

## 3. Restart the writ daemon (when server.py changes)

When `writ/server.py` changes (new endpoints, modified routes), the
running uvicorn process keeps serving the old module until restarted.
PSR-005 caught a `/dashboard` 404 traced to exactly this: the route
was wired in code but the daemon predated the change.

```bash
pkill -f "writ.*serve" || true
nohup writ serve > /tmp/writ-server.log 2>&1 &
```

Verify with `curl -sf http://localhost:8765/health`. Restart is only
required when `server.py` (or any FastAPI route module it imports)
changes; routine ingest, query, or hook updates do not need it.

## Known limitations

- The settings sync replaces your active `~/.claude/settings.json`
  wholesale. Custom permissions or hooks outside the Writ template are
  lost. Merge by hand if you have them.
- The user-commands installer overwrites identically-named files in
  `~/.claude/commands/`. If you have a non-Writ `writ-approve.md`
  there for some reason, it gets replaced.
- Restarting Claude Code is required after install changes for the
  settings/commands to take effect in a running session.