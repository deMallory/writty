# Handoff pack: replay the live graph, fix the stale docs, ship 1.7.4

Written 2026-09-29, at the end of the session that merged PRs 21 and 22. Read this first. It
continues `docs/handoff/verify-1.7.3/README.md`, which still holds the full stale-docs list,
the reference facts and the older gotchas. Claims were checked on that date. "Not verified"
marks the rest.

Resume prompt: `read docs/handoff/replay-and-docs/README.md, start task A`.

**Commits and PRs are in English from 2026-09-29.** Same format, `type(domain): imperative
subject`, one line that says why. This overrides the French rule in
`docs/handoff/openwiki-port/README.md:42`.

## Resume point

| What | State | Next |
|---|---|---|
| `main` | `0717265`: PRs 21 to 23 merged | None |
| Installed plugin | 1.7.3. `main` still says 1.7.3, so PRs 21 and 22 are not live | Task C |
| Live graph (port 7687) | Done 2026-09-29: replayed, matches the dump in content | None |
| Stale writty docs | Done 2026-09-29 on `docs/stale-docs` | Merge its PR, then task C |
| Workshop vault (raggidy) | 9 files modified, 1 new, uncommitted; last commit `14fbc8c` | Task D |
| Test graph (port 7688) | `writ-test-neo4j` running | `make test-graph-down` when done |

Suggested order: A, B, C, D. C after B, so 1.7.4 ships the doc fixes too. The workshop is
around 2026-10-09.

## What landed this session

| PR | Merge commit | What |
|---|---|---|
| 21 | `e9eabb3` | The corpus round-trips. Full suite, test graph up: 36 failed before, 1 after (`test_plugin_manifest`) |
| 22 | `13c6e36` | The code-quality reviewer is admitted once `writ-spec-reviewer` stops. It was refused forever in Work mode |

PR 22 needed `e6f2843`, a merge of `main` into its branch: both PRs added CHANGELOG entries.
CI passed on that head (`test` 15 min, `bench` 4 min), and `main` has the same tree. The full
suite was not re-run locally after both merges. Expected: 1 failure, plus the timing test
under load (see gotchas).

## Task A: replay the dump into 7687

**Done 2026-09-29.** Backup before: `../writty-live-backup-20260929-pre-replay.cypher` (536
nodes, 1,435 edges). A content diff, blind to property order, found nothing only in 7687: the 84
live values that differed each matched an older committed dump. The owner ran steps 3 and 4.
Export after: `../writty-live-post-replay-20260929.cypher`, 0 node, property or edge
differences against `writ-corpus.cypher`, compared blind to property order (the order differs
on 468 lines). `/health`: 336 rules, 36 mandatory. It counts from
Neo4j on each request (`writ/server/routes/query.py:524`), so it shows the replay even before
the restart. Its route census lost `ride_along` 1 and `scoped` 4, and `pull` went from 3 to 4:
expected, since `a0dcb35` changed those Category routes in the dump. Counters reset:
`last_seen` and `times_seen_positive` on 119 nodes each.

**Why.** The live graph lacks 4 nodes the dump has: ENF-PROC-FIXLOOP-001,
TEC-PROC-CONDITION-WAIT-001, TEC-PROC-DEFENSE-DEPTH-001, TEC-PROC-TEST-POLLUTION-001.

**Cost.** The runtime counters reset: 112 `last_seen` values and the `times_seen` counts, as of
2026-09-29. Records survive: the replay deletes everything except the record labels
(`writ/graph/dump.py:115`).

**Warning.** `writ import-cypher` takes no target option. It connects to `WRIT_NEO4J_URI`, else
`writ.toml`, else `bolt://localhost:7687` (`writ/config.py:171`). With nothing set, it hits the
live graph. The wipe guard does not stop it: that guard fires only when nothing is preserved
(`writ/graph/db/maintenance_store.py:38`), and the replay preserves records.

**Steps.** Claude never writes to 7687; the owner runs steps 3 and 4.

1. Take a fresh backup, since the runtime keeps writing:
   `writ export-cypher ../writty-live-backup-<date>.cypher`. The 2026-09-29 one stays as a
   second copy.
2. Check that nothing lives only in 7687. Run in a scratch folder:
   ```
   grep -o "_dump_id: '[^']*'" ../writty-live-backup-<date>.cypher | sort -u > live.ids
   grep -o "_dump_id: '[^']*'" writ-corpus.cypher | sort -u > dump.ids
   comm -23 live.ids dump.ids
   ```
   Expected: empty. On 2026-09-29 the only live-only nodes were the two split reviewer roles,
   which are now in the dump. Anything listed would be lost: stop, and add it to the dump
   first.
3. From the repo root, with `WRIT_NEO4J_URI` unset: `writ import-cypher writ-corpus.cypher`.
4. Restart the daemon: `bash scripts/stop-server.sh; bash scripts/ensure-server.sh`. It builds
   its search index at startup. Whether it would pick up the replay without a restart is not
   verified.
5. Check `curl -s localhost:8765/health`. Expected: `rule_count` 336 and `mandatory_count` 36,
   the counts in the dump. That `/health` counts the same way is not verified.
6. Export again and repeat step 2 both ways (`comm -3`). Expected: no difference.

## Task B: stale docs

**Done 2026-09-29** on `docs/stale-docs`. One correction to the older handoff: a failed
validation does spend the token (`writ/server/routes/gate.py:173`), so `HANDBOOK.md` was right
and the handoff was wrong. The hook-code items from that list moved to the open threads of
`openwiki/operations/project-log.md`.

The list is task 4 of `docs/handoff/verify-1.7.3/README.md`. Two additions from today:

- `openwiki/operations/project-log.md` must now cover PRs 21 and 22, and the suite state above.
- In that older handoff, the "Code follow-ups" entry on `writ-sdd-review-order.sh` is done
  (PR 22), and its resume table is superseded by this file.

One doc-only PR. Once a mode is set, every `*.md` file passes the write gate in any phase. With
no mode set, the gate refuses every write, `*.md` included (`ENF-GATE-MODE`).

## Task C: release 1.7.4

Hooks load from the plugin cache, one folder per version. PR 21's read-gate fix and PR 22's
reviewer-order fix reach installed plugins only after a version bump.

- Copy the shape of `4540ba7`, the 1.7.3 bump: `.claude-plugin/marketplace.json`,
  `.claude-plugin/plugin.json`, `pyproject.toml`, `tests/test_version_consistency.py`, and a
  dated CHANGELOG section from `[Unreleased]`.
- Then the owner updates the marketplace and the plugin, and restarts Claude Code and the
  daemon. The exact update commands are not recorded here.
- Live check for PR 22: dispatch `writ-spec-reviewer`, then `writ-code-quality-reviewer`, in
  Work mode. The second must go through.

## Task D: workshop vault

Vault `/Users/david.malinen/Documents/job/flatchr/raggidy/Library/DevDocs/writty/`. Commit the
10 changed files. Ask before pushing. Open decisions are under task 3, "Still open", in the
older handoff. The workshop machine needs the plugin update too.

## Code follow-ups still open

- Sort property keys in `_render_props`: an export from 7687 reorders most lines of the dump.
- The RULE-START import overwrites the runtime and provenance fields of a rule; the full list
  is in the project log's open threads.
- `ROL-REVIEWER-001` and `agents/writ-reviewer.md` still say "Replaces the separate
  spec/code-quality reviewers."
- `test_plugin_manifest`: the exec form of the hook commands, its own PR.
- `gate_denial` rows for the Bash gate's state-dir, review-record, state-file and strict-mode
  refusals, so `writ audit-session` lists them.
- The review-order flag is never cleared. By design: one spec review unlocks the phase, and a
  new phase gets a new key.
- The dotfiles project-scope install is pinned at 1.7.0.
- Pre-existing ruff errors in three test files, listed in the older handoff.

## Gotchas learned this session

- **The Bash gate reads command text.** `writ-bash-write-gate.sh` refuses any Bash command
  whose text names the verdict recorder (`review_findings`) followed by `record` or
  `spec-done`, even inside a heredoc or a grep. Write such text with Write, search with Grep.
- **Plan format.** Every Files line needs `(create)`, `(modify)` or `(delete)`, and the plan
  needs Analysis, Rules Applied and Capabilities (`templates/plan-template.md`). A rejected
  plan spends the approval. Check first with
  `.venv/bin/python -c "from writ.session.approval_workflow import _validate_phase_a; print(_validate_phase_a('.', '<session_id>'))"`.
  `None` means it passes.
- **No `git stash` while a suite runs in the background.** The run sees the stashed tree.
- **A branch made from `origin/main` tracks `origin/main`.** Run `git branch --unset-upstream`,
  then push with `-u origin <branch>`.
- **`gh pr checks --watch`** can exit at once on "no checks reported" right after a push.
  Run it again.
- **`python` is not on PATH.** Use `.venv/bin/python`.
- **Timing test.** `test_graph_proximity.py::TestGraphBoostRegression::test_benchmark_suite_still_passes`
  failed once in a full run and passed three times alone (p95 9.0, 10.6, 11.4 ms, budget 15).

## Housekeeping

- `plan.md` and `capabilities.md` hold the PR 22 plan. Replace them for the next task.
- `../writty-bible-aside-20260928` and `../writty-bible-aside-20260929` hold old `bible/`
  folders. PR 21 has landed, so they can go. Ask first.
- `/tmp/canary/.env` (fake values) is still there. Delete when done.
- Merged local branches from older PRs: `docs/handoff-verify-1.7.3`,
  `docs/openwiki-pr15-merged`, `feat/openwiki`, `fix/credential-denials-audited`,
  `fix/plugin-role-names`, `fix/session-start-timeout`, `fix/timeout-guard-signal-arg`. Not
  checked whether each is fully merged. Ask before deleting.
