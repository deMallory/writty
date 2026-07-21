# Resume after /compact

## >>> CURRENT PHASE: token efficiency. FULL PLAN = `WRIT-TOKEN-BLUEPRINT.md` <<<
Read that blueprint first (it survived 4 rounds of adversarial review; the THESIS at its top is the
finding: you cannot cost-optimize a correctness system without measuring correctness, and measuring
it is expensive). Architecture = two instruments: FOOTPRINT observer (denominator, cheap) + EFFICACY
A/B harness (numerator, expensive, gates the dangerous levers). Gate = minimize cost SUBJECT TO a
coverage floor (never single-objective).

**P0 DONE + committed (branch regression-fixes, NOT pushed): `d31aeef` observer + `9ba2a67` reread
fix.** `writ token-audit` (writ/analysis/token_audit.py + CLI + tests/test_token_audit.py, 14 pass)
is the footprint observer: schema canary (fail loud), cost-weighting, compounding curve,
measured-vs-attributed split. MEASURED baseline (this session, ~5.7k turns): ~$1,870; cache_read =
61% of cost (compounding re-read dominates, measured). Reread attribution is now per-segment +
clamped (upper bound), no longer the impossible 1.17B.

**NEXT (pick one):** (a) finish P0's remaining TODOs -- inject-time REAL tokenization (kill bytes/4
in the numerator), precise per-turn resident-block reread (replace the upper-bound triangular),
baseline an ai-stack + a runaway-audit session (more than one draw); OR (b) P0.5 = build the EFFICACY
A/B harness (`writ efficacy-ab`: planted-defect arm + CLEAN arm for false-positive cost) -- the
prerequisite before shipping ANY lever (summary-mode / read-gate / Layer 0), since all three are
efficacy-affecting and gate on it, not the footprint observer. P1 Layer 0 has a binary cache_read
acceptance test + a compaction-cadence test (it has been deflated 3x; let the A/B decide it).

---

## PRIOR PHASE (COMPLETE): hook optimization. FULL PLAN = `docs/HOOK-OPTIMIZATION-PLAN.md`
**#7, #2, #N2, #1, #3, count-recon, #4, #5, #6, and #8 are DONE** (verified by triggering). The
HOOK-OPTIMIZATION backlog is COMPLETE. Black-box map (`docs/WRIT-BLACKBOX-MAP.md`) is the verified
contract it built on. (Commits: 5d4f3d7 #7, eabbcda #2, 889fde4 #N2, e057ca8 #1, f031864 #3,
f3be3ef count, d165bbd #4, eaedf94 #5, 518bb44 #6, d4f48db #8 -- all local on regression-fixes.)

## #8 DONE (rag-inject: 3 channels -> ONE warm /prompt-bundle call; 646ms -> 274ms p50)
MEASURE-FIRST corrected the plan AND a prior decision: the plan said "combine the 3 HTTP curls"
and B2 had REJECTED a daemon endpoint as "~zero latency win". Measurement: the 3 retrieval curls are
~39ms (warm localhost) but **28 cold python3 spawns are ~420ms of the 646ms** -- B2 under-weighted the
local parse cost. So the lever is moving parse/render to the WARM daemon, not combining HTTP.
- NEW endpoint `POST /prompt-bundle` (`writ/server.py`): AWAITS the existing query_rules /
  always_on_bundle / methodology_companion handlers IN-PROCESS (zero retrieval re-impl), renders via
  pure helpers `writ/retrieval/prompt_bundle.py` (render_always_on / compute_nudge /
  extract_rule_objects / split_format), applies the SAME cmd_update cache mutations, returns the three
  rendered pieces SEPARATELY (always_on_block / rules_text / methodology_block / nudge / *_meta) so the
  hook keeps the legacy emit order around the bash-side mode reminders. Early-returns on /query error
  (matches the legacy abort). Endpoint count 41 -> 42 (test_phase51 + ARCHITECTURE.md prose+comment).
- HOOK `writ-rag-inject.sh` main path: replaced steps 3-8 + 11 + 11c with ONE curl to /prompt-bundle +
  jq extracts of the rendered pieces. Friction stays CLIENT-SIDE (cwd-relative per-project log): one
  builder spawn -> `friction-append.py --stdin-jsonl` (NEW batch mode; canonical single-source path
  resolution -- no inline marker-walk, which test_friction_isolation forbids). Orchestrator branch
  UNCHANGED (still its own bash path; its argv json.loads got a recovery-marker guard).
- DAEMON-DOWN: retrieval ALREADY required the daemon pre-#8, so daemon-down still degrades to
  "[Writ: server unavailable]" exactly as before -- NO new floor risk (B2's only valid objection moot).
VERIFIED by triggering: output BYTE-IDENTICAL vs the legacy hook across all 5 modes (golden-diff);
cache parity (queries/loaded/last_injected); friction parity (rag_query broad+methodology +
always_on_inject, event_name=UserPromptSubmit mechanism=stdout effort preserved, project-local log);
latency 646 -> 274ms p50 (58%); python3 spawns 28 -> 8. Tests: tests/test_prompt_bundle.py (16) +
11 old-structure ripple tests repointed to server.py / rewritten to the bundle reality. Full suite:
3232 passed; 3 failures are the known pre-existing set (2 flaky phase2 gate tests, 1 pre-write-dispatch
single-spawn -- all unrelated to #8). Daemon restarted after the server.py edits.

## #6 DONE (Bash write-redirect gate + universal credential guard)
THE GAP: Bash writes (`echo > src/x.py`, `tee`, `dd of=`, `cp/mv/install`, `sed -i`) bypassed the
Write/Edit gate stack (those hooks fire only on the Write/Edit/NotebookEdit TOOLS). Fix = two parts:
- **Credential guard** (`gates.py _is_credential_path`, wired FIRST in `_can_write_check`): denies writes
  to secret paths in EVERY mode, ahead of all exemptions, path-ONLY (never opens the file -- org ban).
  Universal: covers Write/Edit/NotebookEdit AND Bash. Dir-segment-first (/.ssh//secrets//secret//.gnupg//.kube/),
  case-insensitive, `.pub`-precise (public keys OK unless stem is a key file), `credentials.py` carve-out
  (source modules are NOT secrets via code-extension check), additive patterns (*.ppk/.asc/.gpg/*.env/
  .npmrc/.pypirc/.dockercfg/kubeconfig). Template allow-list (.env.example, example.env, ...).
- **`writ-bash-write-gate.sh`** (NEW PreToolUse Bash hook; count 38->39): QUOTE-AWARE extractor
  (shlex posix=False so a quoted `>` is not a redirect), suppresses `[[ ]]`/`[ ]`/`test`/`(( ))`
  comparison+arith spans, skips process-sub `>(`, handles `>|` clobber + `cp/mv/install -t DIR` +
  `sed -i` last-positional. Credential targets -> local deny (any mode); project-local targets ->
  the SAME `/can-write` gate the Write tool uses (scratch outside the repo is not work-gated).
  IMPORTS `gates._is_credential_path` (SINGLE SOURCE -- no mirror drift; minimal inline fallback only
  if the package import fails).
VERIFIED: 38-case extractor matrix + cross-mode e2e + emit-once contract (at most ONE JSON; credential
deny wins, location-independent). ADVERSARIAL REVIEW (background workflow, 33 agents): found 20 confirmed
bugs (false-positives like `grep '>' file.pem`, `[[ $a > $b ]]`; in-scope false-negatives `>|` and `-t`;
credential gaps: ordering/case/.pub/credentials.py) -- ALL fixed + regression-tested.
Tests: test_bash_write_gate.py (90 pass, 2 daemon-skipped). Count guards 38->39 (3 test sites + HANDBOOK).
CAVEAT: the new matcher binds on a FRESH CC session; gate logic + server credential guard are live now
(daemon restarted). Coverage LIMIT (documented, not a bug): obfuscated writes (python -c, eval/base64,
var-indirection, here-docs, glued `foo>bar`) evade -- narrows the hole, does not seal it.

## #5 DONE (gate Glob)
Glob (file enumeration) skipped the runtime-lens read gate two ways: absent from the Grep|Read
matcher, and the gate's tool switch fell through to allow for non-Grep/Read tools. Fix: gates.py
`tool=="Glob"` branch classifies the PATTERN by extension (reuses _classify_runtime_read) -> source
hunt `**/*.py` blocked premature; `**/*.log`/`src/**`/docs allowed (fail-open on no-extension);
_resolve_read_search_dir uses Glob `path`; hooks.json matcher Grep|Read -> Grep|Read|Glob (count
stays 38; daemon restarted). Verified: debug-lens `**/*.py`->DENY, `**/*.log`/`src/**`->allow,
investigate->allow. Tests: test_glob_gating (6). CAVEAT: matcher binding needs FRESH CC session;
gate logic live now.

## #4 DONE (gate NotebookEdit)
NotebookEdit (notebook_path/new_source) bypassed the write stack: the hook parser AND the server gate
(_parse_file_path_from_envelope) read file_path only -> empty path -> work gate (blocks ALL writes
pre-plan) allowed it. Fixed: parse-hook-stdin.py (file_path<-notebook_path, content<-new_source),
gates.py _parse_file_path_from_envelope (+notebook_path; daemon restarted), pre-write-dispatch
PARSED_INPUT + WRITE_CTX, hooks.json matchers Write|Edit -> Write|Edit|NotebookEdit on
pre-write-dispatch + posttool-rag (no new registration; count stays 38). Verified: work mode -> DENY
(ENF-GATE-PLAN), investigate -> allow + SEC-AUTH-HASH-001 injected. Tests: test_notebook_edit_gating
(8). CAVEAT: hooks.json matcher binding needs a FRESH CC session; parser + gate fixes are live now.
Pre-existing RED (not #4): test_pre_write_dispatch_parsing single-spawn (5 python3 -c, asserts <=4;
5 at HEAD too -- a separate consolidation item).

## Count-guard reconciliation DONE
The 4 registration-count tests had been RED since before this work (asserted 35; reality drifted to
40). After #1+#3 removed 2 dead entries the true count is 38. Updated HANDBOOK "registers **38 hook
scripts**" + the 3 count assertions to 38 (de-magic-numbered: "bump when adding/removing a
registration"); renamed the two `_35_` test methods. All 4 now GREEN.

## #3 DONE (track-failed-writes dead matcher)
Verified dead by triggering: PostToolUseFailure fires only for Read/Bash, never Write/Edit (2560
blackbox captures + a fresh failing Edit raised none). Write failures aren't hook-observable in
2.1.183. Removed the matcher + the orphaned script; rewrote the false-green test_pol5b2c (it claimed
the telemetry was "live") to assert removal; updated test_pol5b2b NUANCED + HANDBOOK list. Kept the
generic friction write_failure counter as dormant infra. Registration count: 40 -> 38 across this
session (#1 removed TodoWrite, #3 removed track-failed-writes).

## #1 DONE (re-anchor ENF-PROC-VERIFY-001)
writ-verify-before-claim.sh re-anchored from dead `PreToolUse TodoWrite` to Stop (hook was
already Stop-wired; old Stop branch was a gutted exit-0 stub, so live via .sh edit -- no fresh
session). Loop-safe: stderr + exit 1 (writ-run-pending-tests pattern), never additionalContext on
Stop; stop_hook_active-guarded; work mode only; POL-5e (fires only on a Gate-5 quality artifact
<3 unoverridden, live feeder = #2-fixed quality-judge). Removed dead PreToolUse TodoWrite matcher
from hooks.json. Fixed rule node enforcement+path (factual); flagged statement/examples (TodoWrite-
worded, authority:human) for human re-authoring. Verified 5 trigger cases. KNOWN pre-existing RED:
4 registration-count tests (drifted 35->40 before this work, now 39 after removal) -- reconcile +
HANDBOOK is a separate hygiene item, NOT caused by #1.

## #N2 DONE (always-on applicability filter re-enabled, default ON)
Flipped WRIT_ALWAYS_ON_FILTER default to ON in rag-inject + pre-write-dispatch (disable with =0).
Parity re-run (tests/test_always_on_parity.py, 3 tests, live-graph) caught a real strand:
ENF-COMMS-OUTPUT-001 had empty scope + 11 spurious trigger_keywords -> keyword gate dropped it from
the prompt path. Fixed source -> applicability_scope=["universal"], trigger_keywords=[] (reingested,
--no-export). Parity PASS: 10 prompt-active + 25 write-reachable, 0 stranded, 0 false-positives.
LIVE-CONFIRMED this session: per-prompt block shrank (filter ON); a password-keyword edit delivered
SEC-AUTH-HASH-001 via additionalContext (write-time filter, reaches model). Daemon restarted after
reingest. GAINS: ~75% per-prompt always-active cut (~20K tokens/session) WITH write-scoped rules now
actually reaching the model (#2 unblocked delivery).

## #2 DONE (inert injectors -> additionalContext)
All 5 sites (read-rag, posttool-rag, pre-write-dispatch allow, inject-tier, quality-judge) now
deliver via hookSpecificOutput.additionalContext (additive, NO permissionDecision -> reaches model
without touching any gate). OBSERVED: PreToolUse additionalContext-only reaches the model (probe ->
"PreToolUse:Read hook additional context" system-reminder). Reclassification proven: read-rag tokens
now bucket as `model` in analyze-friction. Linter now flags ONLY postcompact (inert, PostCompact
delivery UNCONFIRMED) + validate-exit-plan (review, real bare heredoc on allow path). GAINS (measured,
upgrade.example-client + ai-stack): ~1,700 rule-tokens/session delivered that were inert (~16% of fetched),
coverage 84%->100%, ~0 latency. Savings lever is #N2 (always-on filter, ~20K tokens/session).

## #7 DONE (delivery-aware measurement)
- `writ/shared/delivery.py classify_delivery(event,mechanism)` = single source of the delivery rule.
- Runtime: `log_rag_query_event` (common.sh) + always_on emit + a NEW pre-write allow-path emit now
  carry `event_name`+`mechanism`; `writ analyze-friction` + `writ audit-session` bucket tokens as
  model vs **debug-log (INERT)**. Triggered live: PreToolUse/stdout -> INERT, UPS/stdout -> model.
- Static: `writ/hooks_lint.py` wired into `writ validate` (WARNING-only). INERT = read-rag,
  posttool-rag, inject-tier-workflow, quality-judge, **postcompact**; REVIEW = pre-write-dispatch,
  **validate-exit-plan**. Two C1 false positives rejected (validate-rules=stderr, cwd-changed=comment).
- Tests: test_delivery.py + test_hooks_lint.py + test_delivery_telemetry.py (31 green).
- For #2: postcompact PostCompact-stdout delivery is UNCONFIRMED (appeared in-context this session but
  may be the /compact echo) -- needs a controlled trigger before trusting either way.

## State
- **Branch `regression-fixes`**, HEAD `a6e48f9` (pushed). Uncommitted: `writ-rag-inject.sh` +
  `writ-pre-write-dispatch.sh` = the always-on filter **reverted to default OFF** (its write-time
  injection used bare stdout, which does NOT reach the model; see plan #2/#N2). Commit with task #7.
- Always-on filter: built, but OFF until #2 moves write injection to additionalContext. Per-turn
  blanket injection (works, reaches model) is the live baseline.
- KEY LESSON (the audit's #1 was a FALSE positive): verify by TRIGGERING, not code-reading.
  `HOOK_ENVELOPE` is NORMALIZED (flattens content/file_path to top-level), so `get('content')` works.
- Run tests with `.venv/bin/python -m pytest`. Restart daemon after server.py / pipeline.py /
  gates.py edits: `systemctl --user restart writ-server`. Black box ON.

## Done this session (the 10 commits)
- Fixed 2 hook backtick bugs (`mode get` / `or` command-not-found log spam).
- **Black box**: `blackbox_log()` in common.sh; logs raw CC↔hook payloads to
  `~/.claude/writ-blackbox.jsonl`. Enabled via sentinel `~/.claude/writ-blackbox.on` (ON now).
  Wired on rag-inject / pre-write-dispatch / subagent-start (only 3 of 35 hooks).
- **Auto-work-mode**: implementation prompts now auto-enter work mode (was investigate-only).
  Triggers: keyword classifier (`writ_mode_hint.py`), `permission_mode==plan`, transcript tail.
- **Force-swap (the discovery)**: `writ-dispatch-discipline.sh` rewrites generic Task dispatches →
  `writ-*` role via PreToolUse `updatedInput` (was deny+retry). **Verified live.**
- `[UNKNOWN]` rules fix (abstraction render), `effort` telemetry on rag_query.
- **Black-box map**: `docs/WRIT-BLACKBOX-MAP.md` (lean CC hook contract + force-swap recipe) +
  Artifact https://claude.ai/code/artifact/c116277a-894e-48d3-8486-980af680f0f6

## DONE: always-on applicability filter (built + measured + LIVE, default ON)
Built the §3.5 applicability filter for always-on Rules. **Filter is ON by default; disable with
`WRIT_ALWAYS_ON_FILTER=0`.** Daemon reingested + restarted; keywords tuned; parity verified.
- **Schema/parser/exporter**: Rules gained `applicability_scope` + `trigger_keywords` (round-trips;
  fail-open empty defaults). `writ/graph/schema.py`, `writ/graph/ingest.py`, `writ/export.py`.
- **Matcher**: `writ/retrieval/always_on_filter.py` (`select_always_on`, whole-word, no weights/drop,
  fail-open universal). Tests: `tests/test_always_on_filter.py`, `tests/test_always_on_routing_fields.py`.
- **Endpoint**: `/always-on?at=prompt|write&context=...` (back-compat when `at` absent). `writ/server.py`.
- **Migration**: 25 RULE-START content rules → `write` scope + keywords. `scripts/migrate_always_on_applicability.py`.
- **Hooks (flag-gated)**: rag-inject injects at `at=prompt`; pre-write-dispatch injects at `at=write`
  (path+content). Stop NOT used (Stop additionalContext blocks turns).
- **MEASURED live (2.1.183):** per-prompt **3,556 → 793 tokens (78% cut, ~184K/session)**; write-time
  injection correct (a SQL+password write surfaced SEC-INJ-SQL/HASH/CRYPTO-KEY/PERF/VAL-SERVER).
- Design doc: `docs/always-on-applicability-classification.md`. 232 affected tests pass.

**Keyword tuning DONE** (`scripts/retune_always_on_keywords.py`): 25 write rules use distinctive
code tokens (lib/function names, multi-word phrases). Matcher gotcha learned: whole-word `\b...\b`
can't match keywords with leading non-word chars (`.claude/handoffs`) or trailing-underscore splits
(`secrets.token` vs `secrets.token_hex`) -> fixed those. **PARITY VERIFIED via endpoint harness:
25/25 deferred rules reachable by a representative write; 0 false-positives on 5 real non-security
writes; per-turn 3,556 -> 874 tokens (75%).** Live proof: each UserPromptSubmit now shows ~11
always-active rules instead of 37.

**Remaining (optional):**
1. Real-world recall accrues over use: a write using an obscure synonym could miss a keyword.
   18/25 deferred rules are ALSO hard-gated (safe regardless); watch the 7 advisory-only ones.
2. The 4 work-gated ENF-PROC rules + comms rules stay fail-open universal (YAML methodology nodes /
   hard-gated); migrate to write-scope later if desired (needs the frontmatter format, not RULE-START).

## Open decision
1. Push the branch (now includes black-box map + always-on filter, many uncommitted commits)?
