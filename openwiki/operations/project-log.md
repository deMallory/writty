---
type: Guide
title: "Project log"
description: Where Writty stands, the open threads, and a dated timeline of what landed, newest first. The page to read when coming back.
---

# Project log

Read this first when coming back to the project. "Current state" is what is true on its date; the timeline lists what landed on `main`, newest first.

## Current state as of 2026-09-28

- `main` on GitHub has PR 12 (plugin agent names, `491657c`) and PR 13 (wiki skeleton and handoff, `7dd0ee0`), both merged 2026-09-28.
- The PR 12 fix is not live on the owner's Mac: the installed plugin is still 1.7.2 without it. PR 12 did not bump the version, so whether `claude plugin update` picks it up is not verified.
- Branch `feat/openwiki` holds three wiki sections not yet pushed: workflows (`1c584f1`), architecture (`82bd2a9`) and operations. Next: integrations, then testing. Plan and gate notes: `docs/handoff/openwiki-port/README.md`.
- Upstream is 146 commits ahead, at release 1.10.1 (fetched 2026-09-28, merge base `e608659`). Since the merge base it added `writ-output-compress.sh`, next to the fork's `writ-output-rewrite.sh`; how the two overlap is not checked. How to sync: [Upstream sync](upstream-sync.md).
- Workshop for the dev team around 2026-10-09. The deck says "approuvé" is refused; the approval matcher accepts it. Fix list: step 5 of the handoff.

## Open threads

- SessionStart probes Neo4j through GNU `timeout` (`hooks/scripts/session-start-bootstrap.sh`, line 84). Stock macOS lacks it, so the probe fails with Neo4j up, and the macOS realign never runs. Reproduced on the owner's Mac 2026-09-28. See [Service lifecycle](service-lifecycle.md).
- `HANDBOOK.md` section 18 places the log streams under `<install>/var/logs/`; since 1.7.2 they live under `~/.cache/writ/logs`.
- `HANDBOOK.md` section 16 and `docs/install.md` present the systemd unit as the main path. systemd is Linux only.
- `docs/install.md` documents upstream's install commands and an older hook count.
- `docs/adr/ADR-session-and-project-isolation.md`: the Status line names Part 5 as pending; its Pending section says Part 5 is done.
- Two tests fail for reasons older than the wiki work: `tests/test_plugin_manifest.py` (strict validation warns on unquoted `${CLAUDE_PLUGIN_ROOT}`) and `tests/test_hook_instrumentation.py` (`writ-read-credential-gate.sh` never calls `hook_instrument`).
- Stale comments and doc lines listed under "Follow-ups outside the steps" in the handoff.

## Timeline

- 2026-09-28: PR 13, the wiki skeleton with its structure checks (`948c357`) and the handoff pack (`8c721dc`).
- 2026-09-28: PR 12, four hooks expect the plugin's `writ:writ-*` agent names. Before, two rewrote dispatches to agents that do not exist and two skipped their check (`0f15365`).
- 2026-09-26: PR 11, a hook refuses reads of secret files, whose content would leave the machine (`7931e57`, `f47e030`).
- 2026-09-14: a hook swaps `grep -P` for `sed`; BSD grep on macOS was dropping the mode directive (`b73c2ed`).
- 2026-09-14: 1.7.2, sync with upstream at `e608659` (`b0ca5d1`).
- 2026-09-13: 1.7.1, the approval survives a gate rejection and the session store is aligned (`d21b84e`). 1.7.2 replaced the approval part with upstream's semantics.
- 2026-09-05: the four surviving fork hooks move into `hooks/hooks.json`; `.claude/hooks/` retired (`0c42727`).
- 2026-09-01: `hooks/hooks.json` restored to upstream's full set. A fork prune had silently disabled 28 registrations (`1042412`).
- 2026-08-11: PR 8 merges upstream's 1.7.0 line (`bf7f385`); PR 9 untracks `bible/` (`a643c78`).
- 2026-08-01: fork rebuilt on upstream's recreated history; old main kept as tag `backup/pre-upstream-sync-2026-08-01`.

## How to add an entry

- When you stop, update "Current state": change the date in its heading and rewrite the bullets. Keep only what is true now.
- One timeline bullet per merge or release, added at the top, shaped `YYYY-MM-DD: what changed and why (commit)`.
- A fixed open thread leaves the list; if it shipped, it gets a timeline bullet.
- `tests/openwiki/test_operations.py` checks that the dates run newest first.
