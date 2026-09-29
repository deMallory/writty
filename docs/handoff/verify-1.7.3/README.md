# Handoff pack: verify 1.7.3, the 93 red tests, the workshop

Written 2026-09-28, at the end of the session that went from the operations wiki section to
PR 18. Read this first. It continues `docs/handoff/openwiki-port/README.md`: the steps, ground
rules and gate mechanics there still hold, and this file lists only what changed or was
learned since. Claims were checked on that date. "Not verified" marks the rest.

**Updated 2026-09-29.** Task 1 done and verified live. Task 2 diagnosed, not fixed. Task 3
done in the vault, not committed. Task 4 not started. The sections below say what each
found; the original task text is kept where it still guides the next step.

## Resume point

| What | State | Next |
|---|---|---|
| Plugin 1.7.3 (PRs 11 to 18) | Live on this machine: Claude Code and the daemon restarted on 1.7.3 | Install on the workshop machine |
| Live check of the credential audit | Done: 5 refusals tried, 5 listed by `writ audit-session`, one with the daemon stopped | None |
| Failing tests | Diagnosed: stale `bible/`, a lossy export, stale test pins, gaps in the dump. `bible/` now rebuilt from the dump. The two reviewer roles stay | Fix PR, see code follow-ups for the order |
| Live graph (port 7687) | Stale against the dump, and cannot be backed up (`writ export-cypher` crashes) | Fix the export first, see task 2 |
| Workshop vault (raggidy) | Stale lines fixed from the task 1 result; 9 files modified, 1 new, nothing committed | Commit, ask before pushing |
| Online deck and sources | Not updated: they live on another claude.ai account | The owner, by hand |
| Stale writty docs | Listed below, not fixed | Task 4 |
| Wiki step 2 (integrations, testing), steps 3 and 4 | Not started | See the previous handoff |

The workshop is around 2026-10-09.

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

**Result, 2026-09-28, session `cfb6a27b`.** Done. `writ audit-session` printed:

```
Gate denials: 5
  2026-09-28T20:44:22Z  denied: SEC-CREDENTIAL-READ
  2026-09-28T20:44:22Z  denied: SEC-CREDENTIAL-READ
  2026-09-28T20:44:23Z  denied: SEC-CREDENTIAL-WRITE
  2026-09-28T20:44:28Z  denied: SEC-CREDENTIAL-WRITE
  2026-09-28T20:44:44Z  denied: SEC-CREDENTIAL-WRITE
```

- The first four are step 4's Read, `cat`, `echo X >>` and Write, in that order.
- The fifth is the Write with the daemon stopped (step 6). The `can-write` fallback refuses
  it and writes the `gate_denial` row. The demo review's "silently allowed" claim is wrong.
- A Bash command touching `/tmp/writ-current-session` (ENF-GATE-STATE) was refused in the
  same session. It shows as a `gate_decision` row in "Top event types", not under "Gate
  denials". That is the remaining gap for slide 12, see code follow-ups.
- The text report has no rule-injection section. `writ audit-session --json <id>` has it,
  field `rule_loads`.

The steps, kept for the workshop machine:

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

**Result, 2026-09-29.** A stale `bible/` caused most of the 93. Rebuilt from the dump, 36
fail. Nothing is fixed in code yet. Full suite, test graph up, each row a fresh run:

| `bible/` | Failed | Passed | Skipped |
|---|---|---|---|
| Old, 2026-09-05 (now at `../writty-bible-aside-20260928`) | 94 | 7 887 | 158 |
| None | 5 | 7 273 | 861 |
| Rebuilt from `writ-corpus.cypher` | 49 | 7 932 | 158 |
| Rebuilt, plus the two fork reviewer roles (current) | 36 | 7 945 | 158 |

- The 94th in the first row is the timing test, see gotchas. It passed in the last run.
- Without `bible/`, 703 tests skip instead of running. The 5 left are the four known-drift
  tests below, plus the timing test.
- The current 36 are in `failing-tests-rebuilt.txt`. All but one were already in the 93;
  the new one is the TEC pin.

**How `bible/` was rebuilt.** `rebuild_bible.py` (this folder) replays the dump into the test
graph on 7688, then calls `export_graph_to_markdown`. It refuses any other port, since the
replay wipes its target. Output: 1 993 statements, 538 nodes, 1 454 edges, 232 files. Then
`ROL-CODE-QUALITY-REVIEWER-001.md` and `ROL-SPEC-REVIEWER-001.md` were copied back from the
old folder: the dump (`b0ca5d1`, 2026-09-14) has 5 roles, the fork ships 7 agent files.
Adding them fixed 17 tests and broke 4. Most of the fork's tests, including the
self-heal completeness check, expect 7 roles.

**The 36 by cause.**

| Cause | Tests | Fix |
|---|---|---|
| Lossy export. `GRAPH_ONLY_FIELDS` (`writ/export.py:39-50`) drops hand-authored fields such as `authority`, `confidence`, `last_validated`. The 62 Abstraction nodes export as `ABS-*.md` files that fail validation, so `import-markdown bible/` fails | 19: `test_import_markdown_unified` (11), `test_methodology_migration` front matter (4), `test_compress_on_ingest` (2), `test_multi_node_ingest`, `test_fix6_corpus_integrity` | Make the full export lossless and skip Abstraction |
| Two fork roles with no playbook that dispatches them; tests disagree on 5 or 7 roles | 4: `test_fix5_role_coverage` `test_role_is_dispatched_by_a_playbook` (2), `test_methodology_migration` `test_exactly_five_subagent_role_files_on_disk`, `test_graph_integrity_all_types` (orphaned SubagentRole: 2) | Decided 2026-09-29: keep both reviewers, drop nothing. Add a playbook edge that dispatches each, move the 5-pin to 7 |
| Stale pins | 4: hooks 48 against 49 (`tests/plugin/test_hooks_routing.py`, `test_pol5b4_context_tracker_removed`); TEC files 18 against 21 (`test_inc12_verify_parallel`); PBK-EDIT-ELENCHUS-001 unclassified (`test_methodology_migration`) | Update the pins |
| Gaps in the dump | 4: `SKL-PROC-PLAN-001 PRECEDES SKL-PROC-EXEC-001` missing (`test_phase1_corrections`); COUNTERS edges to `ANIM-GSAP-*` rules that do not exist (`test_inc2_edge_direction`, 2); `bible/enforcement/reasoning-discipline.md` missing (`test_pol1b_tier_migration`) | Regenerate the dump |
| Known drift | 2: `test_hook_instrumentation` (read gate), `test_plugin_manifest` (strict warnings) | See single failures below |
| Cause not read | 3: `test_phase_abstraction_parity` and `test_phase18a_push_by_action` (`run_all_checks` exits 1; both appeared once the two roles were added, so the orphans are the suspect, unproven); `test_phase52a_field_drift` (source-null, graph-non-null not reported as drift) | Read before the fix PR |

**The live graph (7687) is stale too, and cannot be backed up.**

- It lacks ENF-PROC-FIXLOOP-001, TEC-PROC-CONDITION-WAIT-001, TEC-PROC-DEFENSE-DEPTH-001 and
  TEC-PROC-TEST-POLLUTION-001. It still has the two reviewer roles. Counts on 2026-09-28:
  Rule 335, Technique 18, SubagentRole 7, Decision 26, Memory 12, Project 2.
- `writ export-cypher` crashes on it: `TypeError: cypher_literal: unsupported type DateTime`.
  110 Rule nodes carry a `last_seen` ZONED DATETIME. Upstream has the same code
  (`writ/graph/dump.py:20`).
- Do not replay today's dump into it. The replay wipes the graph first, would drop the two
  roles, and no backup is possible until `cypher_literal` handles DateTime.

**Why the wiki says 4.** `openwiki/operations/project-log.md` counts four red tests. Those runs
used `--noconftest` on hook and wiki tests only, with the test graph down (inferred from the
commands used, not proven). The full suite needs the test Neo4j on port 7688:
`make test-graph-up`. Its container, `writ-test-neo4j`, was still running at hand-off.

**The original 93, by file** (kept for the record; list in `failing-tests.txt`). They failed
the same on `main` and on the PR 18 branch.

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

`tests/test_phase51_doc_counts.py:12` also says 48 in its docstring, while its code already
expects 49 (line 121); it passes.

**Corrections to the 2026-09-28 notes.** The graph tests did depend on `bible/`: the self-heal
imports it first when present (see gotchas), so the stale folder also fed the test graph.
`writ export` cannot regenerate `bible/`: it writes rules only. Memory from the 1.7 sync was
wrong on that point.

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

**Fixed 2026-09-28 from the task 1 result.**

- `atelier-defi.md`: the summary, line 19 (read gate active on this machine), line 39 (check
  that the `1.7.3/` cache folder exists), line 53 (`writ audit-session` decides the refusals,
  five of five listed), line 55 (daemon down is no longer out of scope: Write stays refused).
- `demo-live.md:13`: set the plugin to 1.7.3 before the rehearsal; lists PRs 11, 12, 15, 18.
- `demo-live.md:28`, step 5: run the audit in a separate terminal, since Claude is refused on
  the session file. "Gate denials" lists refusals, "Phase progression" the approvals, and the
  injected rule is only in `--json`, field `rule_loads`. Approvals were not seen live, only
  read in the code (`writ/analysis/friction.py:1066-1070`).
- `demo-live.md:35`: the step 1 refusal reaches the audit, through Write or Bash.
- `maj-artefacts-en-ligne.md`, "À décider avant de republier": rewritten with the task 1
  result and a proposal for slide 12.

**Still open.**

- `gardefous.html:24`: "Chaque autorisation et chaque refus est gardé 365 jours." Every
  refusal seen is kept: credential refusals as `gate_denial`, ENF-GATE-STATE as
  `gate_decision`. 365 days is `writ/session/log_rotation.py:46`. Only the display lags:
  `writ audit-session` lists `gate_denial` rows alone. Not verified: that every hook writes a
  row. Proposal in the vault: keep the text. The owner decides.
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

- Log `gate_denial` for the Bash gate's other refusals (gate state, egress), or make
  `writ audit-session` list denied `gate_decision` rows, so the audit and slide 12 agree.
- Add `hook_instrument` to `hooks/scripts/writ-read-credential-gate.sh`.
- The task 2 fix PR, in this order: `cypher_literal` learns DateTime; back up the live graph;
  give the two reviewer roles a dispatching playbook (they stay, owner's call 2026-09-29);
  regenerate the dump with them; make the full export lossless; update the stale pins.
  Details in task 2.
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
- **No `writ export-full`.** A sub-agent claimed it exists; `writ --help` has no such command.
  `export_graph_to_markdown` (`writ/export.py:407`) exports every node type but has no CLI
  entry. `writ export` writes rules only.
- **`import-cypher` wipes its target.** `import_cypher_dump` deletes everything except
  `RECORD_LABELS` (Memory, Decision, FileChange, Commit, Project;
  `writ/graph/db/_common.py:47`) before the replay. Never point it at 7687 without a backup.
- **The test graph self-heals from `bible/` first.** `tests/_corpus.py` `ensure_corpus` does
  nothing when `is_complete()` is true; otherwise it imports `bible/` if the folder exists,
  and replays `writ-corpus.cypher` only when it does not. A run on a stale `bible/` leaves a
  complete but stale test graph, and the next run keeps it. Reset with `rebuild_bible.py`
  (below) after changing `bible/`.
- **Moving `bible/` is refused** by the auto-mode classifier as irreversible. Ask the owner.
- **Timing test.** `tests/test_graph_proximity.py::TestGraphBoostRegression::test_benchmark_suite_still_passes`
  fails under full-suite load (p95 73 ms against 15 ms) and passes alone.

## Housekeeping

- Local branches merged and deletable (ask first): `docs/openwiki-pr15-merged`,
  `feat/openwiki`, `fix/credential-denials-audited`, `fix/plugin-role-names`,
  `fix/session-start-timeout`, `fix/timeout-guard-signal-arg`. Their remote copies too.
- `plan.md` and `capabilities.md` at the repo root hold the PR 18 plan. Replace them for the
  next task.
- Stop the test graph when done: `make test-graph-down`. Still running on 2026-09-29.
- The old `bible/` is at `../writty-bible-aside-20260928` (234 files), plus a tarball in the
  session scratchpad that will not survive. Delete once the fix PR lands, not before.
- The canary `/tmp/canary/.env` was created with only `FAKE_TOKEN=canary-0000`; every write
  to it was refused. Delete when done.
