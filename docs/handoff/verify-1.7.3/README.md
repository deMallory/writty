# Handoff pack: verify 1.7.3, the 93 red tests, the workshop

Written 2026-09-28, at the end of the session that went from the operations wiki section to
PR 18. Read this first. It continues `docs/handoff/openwiki-port/README.md`: the steps, ground
rules and gate mechanics there still hold, and this file lists only what changed or was
learned since. Claims were checked on that date. "Not verified" marks the rest.

## Resume point

| What | State | Next |
|---|---|---|
| Plugin 1.7.3 (PRs 11 to 18) | In the user-scope cache: `~/.claude/plugins/cache/writty/writty/1.7.3/` has `bin/lib/run-bounded.py`, the read gate, and the `gate_denial` write in `bin/lib/credential_read.py` | Restart Claude Code, then the daemon (task 1) |
| Live check of the credential audit | Not done | Task 1 |
| 93 failing tests | Pre-existing: the same 93 on `main` and on the PR 18 branch | Task 2, list in `docs/handoff/verify-1.7.3/failing-tests.txt` |
| Workshop vault (raggidy) | 9 files modified, 1 new, nothing committed | Task 3, after task 1 |
| Online deck and sources | Not updated: they live on another claude.ai account | The owner, by hand |
| Stale writty docs | Listed below, not fixed | Task 4 |
| Wiki step 2 (integrations, testing), steps 3 and 4 | Not started | See the previous handoff |

The workshop is around 2026-10-09. Task 1 decides what the workshop text says about the
audit, so do it first.

## What landed this session

| PR | Branch | Commits | Merge commit | What |
|---|---|---|---|---|
| 14 | `feat/openwiki` | `e00dc0f` operations pages, `70a2d17` handoff, `d746401` wiki after PR 15 | `461afbd` | Wiki sections workflows, architecture, operations |
| 15 | `fix/session-start-timeout` | `0faf853`, `b250b0e` (Copilot bot, widened the guard regex) | `c144c31` | Hooks stop using GNU `timeout`, which macOS lacks: new `bin/lib/run-bounded.py` |
| 16 | `docs/openwiki-pr15-merged` | `185626e` | `c301fc7` | Wiki records PRs 14 and 15 |
| 17 | `fix/timeout-guard-signal-arg` | `0ab1578` | `4e6c9e6` | The guard also catches `timeout -s KILL 60` |
| 18 | `fix/credential-denials-audited` | `0414324` fix, `4540ba7` version 1.7.3 | `f57bcf5` | Credential refusals now reach `writ audit-session` |

`8e02109` ("Refine grep pattern for import detection") is the owner's own commit on `main`,
between PRs 14 and 15.

### PR 18 in short

`writ audit-session` lists only `gate_denial` rows as refusals (`writ/analysis/friction.py:983`).
None of the three credential guards wrote one:

| Refusal | Code | Row written before PR 18 |
|---|---|---|
| Read, Grep or Bash reading a `.env` (SEC-CREDENTIAL-READ) | `bin/lib/credential_read.py`, called by `hooks/scripts/writ-read-credential-gate.sh` | none |
| Bash writing a `.env` (SEC-CREDENTIAL-WRITE) | `hooks/scripts/writ-bash-write-gate.sh` | none |
| Write or Edit on a `.env` (SEC-CREDENTIAL-WRITE) | `writ/session/gates.py` | `write_attempt` only, no rule |

Each now writes a `gate_denial` row with `rule_id`, `file_path` and `gate`.

- The read gate logs after the refusal is printed and flushed, inside a `try`, so a logging
  failure never turns a refusal into an allow.
- The Bash gate builds the row with `jq -n -c --arg`, so a quote in the path cannot forge a
  field. It has no python fallback on purpose: the inline-python ratchet
  (`tests/test_json_transform_equivalence.py`, `TestNoInlinePythonLeftOnTheWritePath`) holds
  this hook at one snippet. Without jq the row keeps the rule and loses the path. The plan
  said "JSON built by python"; the PR body states the change.
- Known side effect: `analyze_rule_effectiveness` counts these refusals as "stuck", since
  nothing ever approves them.
- Tests: `TestDenialIsAudited` in `tests/test_read_credential_gate.py` (5), and three
  `test_credential_*` tests in `tests/test_bash_write_gate.py`. Before the merge those files
  plus the version and ratchet tests gave 257 passed, 2 skipped. Re-run them; that number is
  from before the context compaction.

## Task 1: make 1.7.3 live and verify the audit

1. Restart Claude Code. Hooks load from the plugin cache at startup.
2. Restart the daemon: `bash scripts/stop-server.sh; bash scripts/ensure-server.sh`. The
   Write/Edit refusal runs in the daemon (`writ/session/gates.py`). The one running at hand-off
   (pid 70562, started 15:26) predates `0414324`.
3. Make a canary file. **Fake values only**: whatever Claude reads leaves the machine. The
   gates refuse Claude's own writes to `.env`, so the owner creates it, for example
   `! mkdir -p /tmp/canary && printf 'FAKE_TOKEN=canary-0000\n' > /tmp/canary/.env`.
4. Ask Claude for four things, each should be refused: Read `/tmp/canary/.env`; Bash
   `cat /tmp/canary/.env`; Bash `echo X >> /tmp/canary/.env`; Write to `/tmp/canary/.env`.
5. Run `writ audit-session <session_id>`. Expected: two `SEC-CREDENTIAL-READ` and two
   `SEC-CREDENTIAL-WRITE` refusals. The exact output line was not seen live. The session id
   is in `/tmp/writ-current-session`; read it with the Read tool, since a Bash command that
   touches it is denied (ENF-GATE-STATE).
6. Daemon down (`bash scripts/stop-server.sh`): repeat the Write attempt. A sandbox check this
   session showed the refusal still fires through the `writ-session.py can-write` fallback,
   which contradicts a demo review claiming it is silently allowed. Confirm live and close
   that claim. Whether the fallback also writes the `gate_denial` row is not verified.

## Task 2: the 93 failing tests

The same 93 fail on `main` and on the PR 18 branch: the list was replayed on both sides
before the merge. None is in a file PR 18 touched. The full list is in
`docs/handoff/verify-1.7.3/failing-tests.txt`; compare against it after any fix.

**Why the wiki says 4.** `openwiki/operations/project-log.md` counts four red tests. Those runs
used `--noconftest` on hook and wiki tests only, with the test graph down (inferred from the
commands used, not proven). The full suite needs the test Neo4j on port 7688:
`make test-graph-up`. Its container, `writ-test-neo4j`, was still running at hand-off.

**By file.**

| Tests | Count | What the failure says |
|---|---|---|
| `tests/test_cycle_f_corpus.py` | 29 | ENF-PROC-FIXLOOP-001, TEC-PROC-CONDITION-WAIT-001 and others "do not exist in the graph yet" |
| `tests/test_methodology_migration.py` | 16 | Front matter lacks `authority`, `confidence`, `last_validated` on SKL-PROC-MODE-001, SKL-PROC-WRIT-FAILURE-001, PBK-PROC-WORK-WORKFLOW-001, PBK-PROC-ORCHESTRATOR-001; role tools lack Edit; `dispatched_by` wrong; PBK-EDIT-ELENCHUS-001 unclassified |
| `tests/test_import_markdown_unified.py` | 11 | `import-markdown bible/` failed |
| `tests/test_fix5_role_coverage.py` | 6 | Role coverage |
| `tests/test_phase6efg_corpus_promotion.py` | 3 | TEC 18 of 21, ENF 11 of 12, Methodology 152 of 156 |
| `tests/test_phase19_route_delivery_closure.py` | 3 | CAT-DISC-001 routes |
| `tests/test_debug_retrieval_keywords.py` | 3 | Retrieval keywords |
| `tests/test_inc2_edge_direction.py`, `tests/test_compress_on_ingest.py` | 2 each | Edges; `import-markdown` on a copied `bible/` |
| 18 other files | 1 each | See the list below |

The single failures: `tests/plugin/test_hooks_routing.py` and
`tests/test_pol5b4_context_tracker_removed.py` pin 48 hook registrations, there are 49;
`tests/test_hook_instrumentation.py` (the read gate never calls `hook_instrument`);
`tests/test_plugin_manifest.py` (strict validation warns on 49 unquoted
`${CLAUDE_PLUGIN_ROOT}` and on the untracked root `CLAUDE.md`); `tests/test_phase3b_export_subagent_roles.py`
(export drift on `writ-explorer.md`); `tests/test_phase35b_field_edge_parity.py`
(`dispatched_by`); `tests/test_phase17a_floors.py` (ANT-PROC-VERIFY-001 missing from floors);
`tests/test_phase1_corrections.py` (edge SKL-PROC-PLAN-001 PRECEDES SKL-PROC-EXEC-001
missing); `tests/test_phase0_migration_is_not_destructive.py` (CAT-DISC-001 trigger);
`tests/test_inc11_methodology_check.py` (12 ENF expected); and
`tests/test_phase_abstraction_parity.py`, `tests/test_multi_node_ingest.py`,
`tests/test_phase18a_push_by_action.py`, `tests/test_dispatch_prose_parity.py`,
`tests/test_graph_integrity_all_types.py`, `tests/test_fix6_corpus_integrity.py`,
`tests/test_phase52a_field_drift.py`, `tests/test_pol1b_tier_migration.py` (reasons not
recorded).

**Two groups.**

- Real drift, fix in code or tests: the two 48-pins, the missing `hook_instrument`, the
  manifest warnings. `tests/test_phase51_doc_counts.py:12` also says 48 in its docstring,
  while its code already expects 49 (line 121); it passes.
- Corpus state, most of the rest. Hypothesis, untested: the local corpus sources are stale.
  `bible/` is gitignored (`.gitignore:58`), its 229 `.md` files date from 2026-09-05, and
  `writ-corpus.cypher` from 2026-09-14. That explains the tests that read `bible/` files or
  run `import-markdown bible/`. It does not directly explain the graph ones: on an isolated
  run, `tests/conftest.py:309-314` warms the test graph from `writ-corpus.cypher`, not
  `bible/`. And the live graph lacks ENF-PROC-FIXLOOP-001 too (335 rules against 336 in the
  dump), so an export from the live graph would carry the same gap.

**First step.** Read what `writ export` reads and writes before running it. Back up `bible/`,
regenerate it, re-run the suite, diff against `failing-tests.txt`. Memory from the 1.7 sync
says "bible/ untracked, regenerate via writ export".

**Not in the 93.** `tests/test_pol5e_hook_noise.py::TestRunPendingTestsBehavior::test_implementation_phase_still_nags`
is listed as failing in the wiki and in the previous handoff, yet it is absent from the full
run with the test graph up. Not investigated.

Tip: never pipe the full suite through `tail`, the failure list is lost. Use `--lf`, or write
the output to a file.

## Task 3: the workshop

**Vault.** `/Users/david.malinen/Documents/job/flatchr/raggidy/Library/DevDocs/writty/`. Git root
`/Users/david.malinen/Documents/job/flatchr/raggidy`, remote `git@github.com:deMallory/raggidy.git`,
last commit `14fbc8c`. Modified, uncommitted: `atelier-defi.md`, `demo-live.md`,
`sources-du-deck.md`, and `deck/slides/` `fin.html`, `gardefous.html`, `neo4j.html`,
`portes.html`, `recherche.html`, `writty.html`. New: `maj-artefacts-en-ligne.md`. Ask before
pushing.

**Done in the vault.**

- The approval word, in `portes.html` (line and notes), `demo-live.md`, `sources-du-deck.md`.
- Numbers: `writty.html:10` 45 scripts on 12 events, `writty.html:20` 297 code rules,
  `recherche.html` 32 essential rules and 297 rules, `neo4j.html:11` 538 elements and 1 454
  links, 50 commits "de nous" in `sources-du-deck.md:80`.
- `fin.html`: the first column points at `openwiki/index.md` instead of `README.md`.
- `demo-live.md`: `HANDBOOK.md:119` for the rule-ID check; a failed validation does not spend
  the token.
- `maj-artefacts-en-ligne.md`: per-slide old and new text for both online artifacts.

**Now stale because 1.7.3 is installed (fix after task 1).**

- `atelier-defi.md:19`: says the read gate is not active on this machine (1.7.2).
- `atelier-defi.md:53`: says the transcript decides the challenge, not `writ audit-session`,
  because the hooks log nothing. Wrong even before PR 18: the Write/Edit refusal appeared only
  as a `write_attempt`, never as a refusal. Rewrite from the task 1 result.
- `demo-live.md:13`: says the installed copy is 1.7.2 and lacks the fixes.
- `demo-live.md:28`: the audit step. Check what the timeline really shows.
- `maj-artefacts-en-ligne.md`, section "À décider avant de republier": it offers two options for
  slide 12. The first (make Writty log them) is PR 18. Rewrite once task 1 confirms it.

**Still open.**

- `gardefous.html:24`: "Chaque autorisation et chaque refus est gardé 365 jours." Credential
  refusals now log. Other Bash-gate refusals (gate state, egress) do not write `gate_denial`,
  and whether the "plan absent" refusal shown on the same card does is not verified. The 365
  days were not re-checked this session. Decide: keep "chaque" or soften it.
- `fin.html`: the HANDBOOK and `docs/architecture/` columns. No decision yet.
- Rule-count basis. Slides use the dump: 297 code rules plus 39 editorial (336). The live
  `/health` says 335, with 36 mandatory. `sources-du-deck.md:122` dates the dump figures and
  says to recount in `writ-corpus.cypher` the day before the workshop.
- `demo-live.md` has never been rehearsed end to end.
- The workshop machine needs the plugin update to 1.7.3.

**Online artifacts.** Deck, version 7: https://claude.ai/artifact/7Yodjr2RtmbLt9eYhqxtuZ. Sources,
revision 18: https://claude.ai/code/artifact/ba67fa68-0e8c-413f-bfda-49beae8a0403. Both return
"not found" from this account; the owner updates them by hand from `maj-artefacts-en-ligne.md`,
then re-exports `Writty gouvernance IA.pdf` and updates the versions in `index.md`.

## Reference facts

**Numbers** (checked at `4e6c9e6` unless stated):

| Fact | Value | Source |
|---|---|---|
| Hooks | 49 registrations, 45 scripts, 12 events | `hooks/hooks.json` |
| Rules in the dump | 336: 297 code, 39 editorial (`EDIT-`); mandatory 32 code plus 4 editorial | `writ-corpus.cypher`, 2026-09-14 |
| Rules live | 335, 36 mandatory, 23 categories (ENF-PROC-FIXLOOP-001 missing) | `curl localhost:8765/health`, re-checked at hand-off |
| Graph | 538 nodes, 1 454 edges in the dump; 575 and 1 475 live | `CREATE` count; live query |
| Commits | Lucio 336 (329 plus 7 under his full name), David 50 (40 plus 10), Copilot bot 1 | `git shortlog -sn main` |
| Search | 0.923 at k=5; about 2 000 tokens per turn | `README.md:237`, `README.md:239`, not re-measured |
| Upstream | 146 commits ahead, release 1.10.1 (`a9af41f`), merge base `e608659` | `git log` on `upstream/main` |

The numbers sub-agent's report was cut from the transcript; every figure above was re-checked
directly afterwards.

**Approval matcher** (run live, `bin/lib/approval_match.py`, unchanged since `b73c2ed`):
"approuvé" alone passes. "approuvé !" fails: the cleaner at lines 52-53 strips the trailing
"!" but not the space before it. "oui", "validé", "c'est bon", "d'accord", "vas-y" fail. An
approval word inside a sentence ("le plan est approuvé") fails. The deck was wrong from day one.

**Validation does not spend the token.** `writ/session/approval_workflow.py:465-468` returns on
a failed validation before `claim_gate_token` at line 504. After fixing `plan.md`, retype
`approved`; the token is still on disk.

**Five fork-only hooks** (against `upstream/main:hooks/scripts/`): `writ-agent-hotswap.sh`,
`writ-sdd-review-order.sh`, `writ-output-rewrite.sh`, `writ-bash-failure.sh`,
`writ-read-credential-gate.sh`. Upstream has since added `writ-output-compress.sh`; its overlap
with `writ-output-rewrite.sh` is not checked. Upstream has the same GNU `timeout` bug
(`hooks/scripts/session-start-bootstrap.sh:149`, `timeout 0.5`).

**`bin/lib/run-bounded.py`** (PR 15): `python3 "$WRIT_DIR/bin/lib/run-bounded.py" SECONDS CMD
[ARG...]`. Exits with the command's status, 124 on expiry. Kills the whole process group and
forwards SIGTERM, SIGHUP, SIGINT. Stdlib only.

## Task 4: stale docs in writty

- `openwiki/operations/project-log.md`: "Current state" says PRs 12 to 15 are merged and not
  live; line 17 says the deck announces "approuvé" as refused; line 25 counts four red tests.
  Rewrite after tasks 1 and 2.
- `openwiki/workflows/work-gates.md:66`: the `approuvé | advances` row lacks the "approuvé !"
  caveat.
- `HANDBOOK.md:126` and `HANDBOOK.md:143`: say a failed validation spends the token. Wrong,
  see above.
- `HANDBOOK.md` section 18 gives the log path as `<install>/var/logs`; since 1.7.2 it is
  `~/.cache/writ/logs` (`writ/shared/logging.py:181-184`).
- `HANDBOOK.md` section 16 and `docs/install.md` present systemd as the main path; it is Linux
  only.
- `README.md:141` and `README.md:258` say 288 rules.
- `docs/reference/graph-schema.md` says 468 nodes and 1 268 edges (last touched `2bb2603`,
  2026-08-14).
- `docs/adr/ADR-session-and-project-isolation.md`: the status line contradicts its own Pending
  section.
- Carried from the previous handoff, still open: `hooks/scripts/writ-rag-inject.sh:184` (stale
  comment) and `:354` (bare `writ-explorer`); `writ-dispatch-discipline.sh` and
  `writ-agent-hotswap.sh` both return `updatedInput`; `HANDBOOK.md` section 8 "five roles";
  `docs/reference/session-and-gates.md` section 5 on token minting; `docs/inventory-workflow.md`
  says `inventory/` is gitignored; `docs/install.md` has upstream's commands and an old hook
  count.

## Code follow-ups

- Log `gate_denial` for the Bash gate's other refusals (gate state, egress), so the audit and
  slide 12 agree.
- Add `hook_instrument` to `hooks/scripts/writ-read-credential-gate.sh`.
- Update the 48 pins to 49.
- The dotfiles repo's project-scope install is pinned at 1.7.0 (`1042412`) and does not follow
  the user-scope one.
- ruff flags an unused `re` in `tests/test_bash_write_gate.py:21`. Pre-existing on `main`.

## Gotchas learned this session

These add to the list in the previous handoff.

- **Mode flips.** Each sub-agent hand-back message flips the Writ mode between investigate and
  work (through the prompt hook). Reset with
  `python3 bin/lib/writ-session.py mode set work <session_id>` before gated work.
- **gh.** Always pass `-R deMallory/writty`; without it `gh` resolves to upstream. `gh pr edit`
  fails (Projects classic deprecation); use
  `gh api -X PATCH repos/deMallory/writty/pulls/N -F body=@file`.
- **Gate state file.** A Bash command that touches `/tmp/writ-current-session` is denied
  (ENF-GATE-STATE). The Read tool works.
- **A heredoc with the word "secrets"** was blocked by a gate. Write the file with Write or
  Edit.
- **Worktrees.** `git worktree add` must target the absolute scratchpad path, or
  ENF-PROC-WORKTREE-001 denies it.
- **zsh.** Quote globs (`--include='*.sh'`). `git show X^1:path` fails; use `X~1`.
- **Inline-python ratchet.** Each hook has a budget of `python3 -c` JSON snippets. Build JSON
  with `jq -n -c --arg`, as `writ_critical` does in `bin/lib/common.sh`.
- **ugrep.** A pattern like `.{0,80}` around UTF-8 text hits a complexity limit. Use `grep -F`.
- **Local `main` lags.** `git fetch origin` before trusting it.
- **Vault edits.** Read a file before editing it, even an HTML slide.

## Housekeeping

- Local branches merged and deletable (ask first): `docs/openwiki-pr15-merged`,
  `feat/openwiki`, `fix/credential-denials-audited`, `fix/plugin-role-names`,
  `fix/session-start-timeout`, `fix/timeout-guard-signal-arg`. Their remote copies too.
- `plan.md` and `capabilities.md` at the repo root hold the PR 18 plan. Replace them for the
  next task.
- Stop the test graph when done: `make test-graph-down`.
