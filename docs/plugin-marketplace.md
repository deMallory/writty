# Plugin marketplace layout

Internal reference: how this repo is wired as a Claude Code plugin marketplace.

## Manifests

- `.claude-plugin/marketplace.json` — top-level catalog (marketplace name `writ`,
  owner `infinri`, single plugin entry `writ` with `source: "./"`).
- `.claude-plugin/plugin.json` — per-plugin manifest. Phase A header only;
  component-path fields land in Phase B.

## Why same-repo marketplace?

One plugin per marketplace is the simplest distribution shape. The marketplace
manifest and plugin manifest both live in this repo. Users:

1. `claude plugin marketplace add infinri/Writ`
2. `claude plugin install writ@writ`

The marketplace name (`writ`) is unreserved per the spec's reserved-list.

## Why was the old plugin.json rewritten?

The pre-2.0 manifest declared `permissions`, `defaultEnabled`,
`lifecycle.Init`, and `lifecycle.Shutdown`. None of those fields exist in
the official plugin schema (`code.claude.com/docs/en/plugins-reference`);
Claude Code silently ignored them. The rewrite uses only spec-compliant
fields. Server lifecycle is handled by a SessionStart hook landing in
Phase C, not the manifest.

## Phase ordering

- A: this file (metadata only; no behavior change)
- B: component auto-discovery (skills/commands/agents/hooks paths)
- C: SessionStart bootstrap + path-portable server start
- D: docs, version bump, validation

See `plan.md` at repo root during active development.
