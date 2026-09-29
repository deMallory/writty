---
type: Guide
title: "Project log"
description: Where Writty stands, the open threads, and a dated timeline of what landed, newest first. The page to read when coming back.
---

# Project log

Read this first when coming back to the project. "Current state" is what is true on its date; the timeline lists what landed on `main`, newest first.

## Current state as of 2026-09-29

- `main` on GitHub has PRs 12 to 23; the last merge is `0717265`.
- The installed plugin is 1.7.3 (PR 18). PRs 21 and 22 also fix hooks, but `main` still says 1.7.3, so they reach installed plugins only with 1.7.4: hooks load from the plugin cache, one folder per version.
- Full suite with the test graph up, measured on PR 21's branch: 1 failure, `tests/test_plugin_manifest.py` (36 before). Not re-run on `main` after PRs 21 and 22 merged.
- The live graph (port 7687) was replayed from `writ-corpus.cypher` on 2026-09-29. A fresh export matches the dump in content: 540 nodes, 1,458 edges, the same property values; property order differs on 468 lines; `/health` reports 336 rules, 36 mandatory. The runtime counters (`last_seen`, `times_seen_positive`) restarted from zero.
- Wiki sections left: integrations, then testing. Plan and gate notes: `docs/handoff/openwiki-port/README.md`.
- Upstream is 146 commits ahead, at release 1.10.1 (re-checked 2026-09-29, merge base `e608659`). Since the merge base it added `writ-output-compress.sh`, next to the fork's `writ-output-rewrite.sh`; how the two overlap is not checked. How to sync: [Upstream sync](upstream-sync.md).
- Workshop for the dev team around 2026-10-09. The deck fixes are made in the vault, not committed.
- Resume point: `docs/handoff/replay-and-docs/README.md`. Next: release 1.7.4, then commit the vault.

## Open threads

- `tests/test_plugin_manifest.py`: strict validation warns on 49 unquoted `${CLAUDE_PLUGIN_ROOT}`. Quoting breaks the hook lint and `writ doctor`; the exec form of the hook commands needs its own PR.
- An export from 7687 reorders most lines of the dump, because each graph stores properties in its own order. Sort the keys in `_render_props`.
- The RULE-START import overwrites a rule's `confidence`, `authority`, `times_seen_positive`, `times_seen_negative`, `last_seen`, `evidence`, `staleness_window` and `last_validated`, and sets `mandatory` to false when the file does not declare it (`writ/graph/ingest.py`, the block after the `**Mandatory**` comment).
- `agents/writ-reviewer.md` and the `ROL-REVIEWER-001` description still say the two-pass reviewer "Replaces the separate spec/code-quality reviewers." The corpus carries the split reviewers since PR 21.
- The Bash gate's state-dir, review-record, state-file and strict-mode refusals write a `gate_decision` row but no `gate_denial` row, and `writ audit-session` lists only `gate_denial` rows.
- `writ-sdd-review-order.sh` looks for the spec review under the dispatch's `task_id` when one is sent, but the spec review is always recorded under the phase (`record_spec_review` in `bin/lib/review_findings.py`). Its header says "Feature-flag gated"; no flag exists.
- `tests/test_pol5e_hook_noise.py::TestRunPendingTestsBehavior::test_implementation_phase_still_nags` runs only when a daemon already answers on the suite's port 8799 at collection, so full runs skip it. With one up, it fails: the Stop hook prints nothing. Pointing `WRIT_CACHE_DIR` at the marker's directory does not fix it, so the cache-dir explanation in `docs/handoff/openwiki-port/README.md` is wrong; the cause is not found (checked 2026-09-29). Its fixture also leaves the session file behind: cleanup looks in the temp dir, not in `WRIT_CACHE_DIR`.
- `hooks/scripts/writ-rag-inject.sh`: the comment above the auto-route block says only investigate is auto-set, but `mode init "$MODE_HINT"` sets any hinted mode. Its auto-route message names the bare `writ-explorer`; a plugin install calls it `writ:writ-explorer`.
- `writ-dispatch-discipline.sh` and `writ-agent-hotswap.sh` both return `updatedInput` on the same dispatch. Which one wins is not checked.
- The dotfiles repo's project-scope install is pinned at 1.7.0.

## Timeline

- 2026-09-29: PR 23, the handoff for the live graph replay, the stale docs and 1.7.4 (`53be1d1`).
- 2026-09-29: PR 22, the code-quality reviewer is admitted once `writ-spec-reviewer` stops. In Work mode it was refused forever: nothing recorded the spec review (`038bfb7`).
- 2026-09-29: PR 21, the corpus round-trips. `export-cypher` renders DateTime, so the live graph can be backed up (`18df244`); the export keeps authored fields (`48f968f`); the dump carries the two split reviewers, dispatched by `PBK-PROC-SDD-001` (`c9e864d`). Full suite: 36 failures down to 1.
- 2026-09-29: PR 20, wiki pages that teach each piece of the stack (core stack, Neo4j, ONNX, hnswlib, Tantivy) with an example to run (`c815a5f`, `24bb7b3`, `3f2908a`).
- 2026-09-28: PR 19, the handoff after PR 18 (`0dc4fa8`).
- 2026-09-28: PR 18, 1.7.3. The three credential refusals now write `gate_denial` rows, so `writ audit-session` lists them (`0414324`, `4540ba7`).
- 2026-09-28: PR 17, the timeout guard also catches `timeout -s KILL 60` (`0ab1578`).
- 2026-09-28: PR 16, the wiki records PRs 14 and 15 (`185626e`).
- 2026-09-28: PR 14, the workflows, architecture and operations sections of the wiki (`1c584f1`, `82bd2a9`, `e00dc0f`).
- 2026-09-28: PR 15, two hooks stop calling GNU `timeout`, which stock macOS lacks. SessionStart skipped the daemon start and the realign, and the Stop hook ran no pending test (`0faf853`).
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
