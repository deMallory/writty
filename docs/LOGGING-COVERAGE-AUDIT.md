# Writ logging coverage audit (2026-07-22)

Complete inventory of what Writ should be logging and is not. Grounded in an AST walk of every
`.py` under `writ/`, `bin/`, `scripts/`, a scan of all 38 hook scripts against `hooks/hooks.json`,
and a count of every event live in `var/logs/`. Companion to `docs/LOGGING-BLUEPRINT.md`, which
covers transport (streams, rotation, retention) but never covered coverage.

Headline: transport is built, coverage is not. 18 of 37 wired hooks emit nothing at all, 181 of 224
exception handlers record nothing, and one shipped metric can only ever report zero.

---

## A. Uninstrumented hooks (highest severity)

18 of the 37 hooks wired in `hooks/hooks.json` never call `log_friction_event`, `hook_timer_end`,
or `friction-append`. They run, they decide, and they leave no trace.

Gates and validators (these make allow/deny decisions with zero audit record):

| Hook | What goes unrecorded |
|---|---|
| `writ-bash-write-gate.sh` | Bash-mediated write allow/deny |
| `writ-comms-output-gate.sh` | Stop-hook output rejections |
| `writ-debug-code-gate.sh` | Debug-mode source-edit blocks |
| `writ-verify-before-claim.sh` | Unverified-claim interventions |
| `writ-dispatch-discipline.sh` | Sub-agent dispatch steering and force-swaps |
| `writ-worktree-safety.sh` | Worktree safety blocks |
| `validate-file.sh`, `pre-validate-file.sh` | Per-file validation outcomes |
| `validate-test-file.sh` | Test-file validation outcomes |
| `validate-design-doc.sh` | Design-doc gate outcomes |
| `validate-handoff.sh` | Handoff validation outcomes |

Injectors and capture (no timing, no success/failure signal):

`writ-read-rag.sh`, `inject-tier-workflow.sh`, `session-start-bootstrap.sh`,
`writ-bible-authoring-push.sh`, `writ-blackbox-capture.sh`, `writ-quality-judge.sh`,
`writ-web-capture.sh`.

Two consequences. First, the run ledger cannot answer "was this gate active" for any of them.
Second, this compounds a known contract: a gate ALLOW is already silent by design (deny-only JSON
back to Claude Code), so for these 18 there is no record of either branch.

**Fix:** every wired hook calls `hook_timer_end` before every exit path, and every gate emits a
decision event (`{gate, decision, reason, target}`) on both allow and deny. `hook_timer_end` already
exists at `bin/lib/common.sh:353`; this is wiring, not new machinery.

---

## B. Exception handling

AST walk of `writ/`, `bin/`, `scripts/`:

| Class | Count | Meaning |
|---|---:|---|
| silent | 122 | body is exactly `pass` / `return` / `continue` / `break` |
| quiet-fallback | 59 | substitutes a default, records nothing |
| raise | 29 | re-raised or wrapped, caller sees it |
| logged | 14 | mentions emit / log / echo |
| **total** | **224** | |

52 of the 181 non-logging handlers catch broad `Exception` or bare `except`, which is where real
defects hide.

### B1. Correctness-critical silence

| Site | Handler | Why it matters |
|---|---|---|
| `writ/session/gates.py:595` | `except Exception` -> `{"can_read": True}` fail-open | A crash in the read gate is indistinguishable from a legitimate allow |
| `writ/session/gates.py:540` | `except Exception: pass` | Gate evaluation partial failure, no signal |
| `writ/session/gate_token.py:44,68,74,78` | 4x `except OSError` silent | Token claim/consume failures vanish; directly adjacent to the known advance-phase token race |
| `writ/session/cache.py:56,66,75,87` | 4x `except Exception: pass` | Session-cache write path; this is the layer PR #37 fixed for concurrency |
| `writ/session/cache.py:203` | parse error -> `_default_cache()` | A corrupt cache silently becomes a blank session, wiping mode and gates |
| `writ/retrieval/pipeline.py:806` | HNSW cache miss -> `_logger.debug` | Degraded retrieval, invisible at default log level |
| `writ/retrieval/embeddings.py:282,306,320,328` | 4x `except OSError: pass` | Embedding persistence failures; silent retrieval degradation |
| `writ/server/routes/query.py:350,371` | `-> 0` and `-> {}` | Query route returns empty on error, looks like "no rules matched" |

`writ/session/cache.py:203` deserves specific attention: a corrupt cache silently returning
`_default_cache()` produces exactly the `mode=None` symptom that PR #37 chased. It would have been a
one-line log away from obvious.

### B2. Acceptable silence, leave alone

`writ/session/doctor.py` (21 handlers) catches by design; the diagnostic is the output.
`writ/graph/methodology_ingest.py` (9) mostly appends to `report.errors`, which is a real record.
Most `json.JSONDecodeError` handlers on hook stdin are correct fail-open behavior, though they
should count.

**Fix:** add an `errors` stream plus `emit_exception(component, exc, session_id, **ctx)` recording
`component`, `exc_type`, `message`, truncated `traceback`, `writ_version`. Handlers keep swallowing;
they just stop being invisible. Convert B1 first (roughly 20 sites), then hook entrypoints, then
server routes. Skip B2.

---

## C. Taxonomy defects

`STREAM_MAP` has 44 entries. 34 distinct events are live in `var/logs/`.

### C1. One metric is structurally broken

`write_failure` is mapped (`writ/shared/logging.py:79`) and consumed by
`writ/analysis/friction.py:288`, but no emitter exists anywhere in the codebase. The write-failure
count in every friction report is hardcoded zero by absence. This is worse than not logging: it
reports a confident wrong answer.

### C2. Dead taxonomy entries

- `pre_write_decision` was deliberately retired in 1.3 (`hooks/scripts/writ-pre-write-dispatch.sh:168`)
  but is still in `STREAM_MAP` and still read at `writ/analysis/friction.py:278`.
- `instructions_loaded` is in `STREAM_MAP:93` with no emitter anywhere.
- `compaction_detected` has no emitter and is not even in `STREAM_MAP`, yet appears 1580 times in
  the pre-migration log.

### C3. Live events missing from the map

Four events are live and unmapped, so they silently take the `_DEFAULT_STREAM = "friction"` fallback:

- `pre_compaction`, `post_compaction` - the blueprint does assign these to friction, so the routing
  is right by accident; they should be explicit.
- `subagent_rules_injected` - this is telemetry and belongs in `metrics`, not `friction`. It is
  currently the single largest unmapped contributor (803 rows).
- `logroot_smoke_test` - a test artifact writing into the real log tree. Should never reach
  production logs.

### C4. What is genuinely fine

Normalizing for the different time spans (legacy file covers about 10 weeks to 2026-07-01, streams
cover about 3 weeks after), `hook_execution`, `rag_query`, `write_attempt`, `subagent_start/complete`,
and `read_blocked` all carry through at comparable or higher rates. The dramatic-looking drops in
`mode_change` (28827 to 173), `gate_denial` (3790 to 21), and `memory_policy_deny` (2240 to 1) are
test contamination in the legacy file, not lost emitters: pytest wrote to the repo-root
`workflow-friction.log` while real work now routes to `var/logs/`. Emitters for all three verified
present. This matches the known ~86% test-synthetic contamination of the legacy log.

---

## D. Blueprint items not finished

1. **Rotate timer not installed.** RESOLVED 2026-07-22: installed and enabled via the same steps as
   `scripts/install-server-service.sh:81-100`. First run reported
   `rotated=7 gzipped=7 pruned=0 scratch_cleaned=0`. The units already existed in the installer, so
   the earlier install had silently skipped them: that block is wrapped in a subshell whose failure
   is swallowed by `|| echo WARNING`, another instance of finding B.

   Archives land at `<project>/archive/<stream>-<date>.jsonl.gz` (`writ/shared/logging.py:125`), not
   the `<root>/archive/<project>/` layout drawn in the blueprint section 2. The code layout is the
   better one; amend the blueprint rather than the code.

### D1a. Rotation blinds every analyzer (found by proving D1)

`read_streams` (`writ/shared/logging.py:346`) resolves only the live `stream_path` and never reads
`archive/*.gz`. Rotation therefore removes history from the analyzers' view the moment it runs.

Measured immediately after the first sweep:

| Project | Rows visible to analyzers | Rows in archives |
|---|---:|---:|
| `bitbucket.org/2ndswing/writ` | 0 | (all of it) |
| `bitbucket.org/2ndswing/ai-stack` | 5540 | |
| `github.com/infinri/Writ` | 189 | |
| **total archived, unreadable** | | **15729** |

No data is lost; the gzip archives are intact. But `writ metrics`, `analyze-friction`, and
`audit-session` all now under-report, and the flagship project reads as empty. Because the timer is
`OnCalendar=daily` with `Persistent=true`, this would have fired on its own within a day.

This makes the item E fix insufficient on its own: pointing the CLI at the streams delivers a nearly
empty result unless `read_streams` also unions the archives. The two must ship together.
2. **`debug` stream never built.** Blueprint section 1 and the section 2 layout both specify
   `debug.jsonl`. `STREAM_MAP` has no debug entries. Debug is still `/tmp` text files
   (`writ-hook-debug.log`, `writ-hooks.log`, `writ-prompt-debug.log`), now correctly gated behind
   `WRIT_DEBUG`. Spam is solved; durability is not.
3. **`calibration.jsonl` unrouted.** Sits at `var/logs/calibration.jsonl`, outside any project dir
   and outside the taxonomy. Was blueprint item 10.

---

## E. Live bug: analyzers read a dead file

`writ analyze-friction` and `writ audit-session` pass `Path("workflow-friction.log")` as a Typer
default (`writ/cli.py:41`, `writ/cli.py:194`), so the `path is None` branch in `_read_raw_rows`
(`writ/analysis/friction.py:136`) that correctly unions the split streams is never taken from the
CLI.

Verified: `writ analyze-friction --json` returns `hook_execution: 32143`, matching the legacy file,
whose last event is `2026-07-01T19:19:02Z`. The streams are live through `2026-07-21T21:45:16Z`.
Three weeks of real data are invisible by default.

Fix is two lines: default both to `None`. `read_streams` and `resolve_project` already work
(`writ/session/metrics.py:345` uses them correctly).

---

## E1. The mode-wipe bug, narrowed by the new instrumentation (2026-07-23)

The `mode=None` wipe reproduced live on a session resumed a day later. What the new `errors` stream
bought us is a set of eliminations, which is exactly what it was built for:

- The session cache went from 17818 bytes to 1020 (a fresh `_default_cache()`, 39 keys, `mode=None`,
  `files_written=[]`, `project_root=''`), rewritten during the resume turn.
- **No `exception` row was written.** So `_read_cache` did NOT take its corrupt-file branch. The
  "corrupt cache silently becomes a blank session" hypothesis is now ruled out, not just doubted.
- **No `mode_change` event was written** either, though the three earlier transitions for this
  session are all present. So the wipe did not go through the mode-set path.

Therefore: some writer persisted a default cache over a live one, without reading a corrupt file and
without a mode transition. That points at a read-then-write path that got a default (missing file, or
a different session id resolved mid-turn) and wrote it back.

Ruled out separately: the P2 sweep. `SCRATCH_GLOBS` only covers
`writ-{precompact,postcompact,feedback,coverage}-*.log`, never `writ-session-*.json`.

Two sessions were writing caches minutes apart (`9af27889...` at 16:01, this one at 16:06), so the
next step is to instrument the cache WRITE path (`_write_cache` / `mutate_cache`) with a
default-shaped-write warning, rather than to keep instrumenting reads.

## F. Not yet covered anywhere

Beyond fixing the above, these produce no events today and are worth adding:

- **Daemon request outcomes.** No per-request event for `/query`, `/pre-write-check`, `/gate`.
  Latency, abstention, and error rate per route are unobservable.
- **Retrieval quality signals.** The S4 abstention gate fires with no event. Empty result sets,
  below-threshold scores, and HNSW rebuilds are unrecorded.
- **Neo4j connection failures.** No event distinguishes "graph unreachable" from "no rules matched".
- **Subprocess failures.** 22 `subprocess.run`/`Popen`/`check_output` call sites in `writ/`; non-zero
  exits are largely unchecked and unrecorded.
- **Config resolution.** Which `writ.toml` was loaded, which env overrides won. Currently
  undiagnosable after the fact.
- **Verification evidence.** `verification_evidence` and `citation_log` live only in the session
  cache; they never reach a durable stream, so they die with the cache.

---

## Prioritized worklist

**P0 -- COMPLETE 2026-07-22**
1. DONE. CLI default-path fix (E) plus archive-aware `read_streams` (D1a), shipped together since
   either alone leaves the analyzers on an incomplete corpus. `read_streams` now unions
   `archive/<stream>-*.jsonl.gz` with the live file, oldest generation first. `--rotate` keeps the
   legacy single-file resolution via `resolve_log_path`, since it acts on one file and the stream
   tree has its own sweep.
   Recovered: `bitbucket.org/2ndswing/writ` went from 0 visible rows to 15146.
2. DONE. `write_failure` counter removed (C1), plus the `write_failure` and `pre_write_decision`
   entries in `STREAM_MAP`. Both events still route to friction via `_DEFAULT_STREAM`, so a
   late-arriving row is captured; they just no longer claim to be a measured signal. This reverses
   a prior decision that kept the counter as "dormant infra"; see the note in
   `tests/test_pol5b2c_removal.py`.
3. DONE. Rotate timer installed and proven. Doing it surfaced D1a.

Verification: 415 tests pass across every file touching the changed code
(`test_logging_router`, `test_logging_delegation`, `test_pol5b2c_removal`, `test_log_rotation`,
`test_cleanup_cycle`, `test_orchestrator_hardening`, `test_phase4_analyze_friction`,
`test_phase5_cli`, `test_metrics`, `test_writ_audit_session`, and the rest of the dependent set).

**P1, the coverage core**
4. DONE 2026-07-22. `errors` stream (365-day retention, matching audit) plus `emit_exception`,
   and 12 converted call sites.

   SCOPE CORRECTION: the plan said ~20-28 sites from an AST classification. Reading each one showed
   most are intended fallbacks, not hidden defects, and converting them would emit noise:
   `embeddings.py`'s four `OSError` handlers are temp-file cleanups inside blocks that re-raise;
   `cache.py:56,66,75,87` are a documented resolution chain whose third candidate raises
   `FileNotFoundError` every normal turn; `approval_workflow.py:189,210` skip unreadable files during
   a glob scan; `mode_engine.py:177` guards a logging call. Converted instead: `cache.py:203`,
   `gates.py:129,540,595`, `gate_token.py:31,44,74,78`, `mode_engine.py:115`, `query.py:350,371`.
   Three of those needed the anomalous case split from the routine one (an absent gate token is
   normal; a present-but-unreadable one is not) rather than a blanket convert.

   Also fixed while here: `emit` called `json.dumps` without `default=str`, so a non-JSON-native
   field raised `TypeError` at the call site, contradicting its own "never raises" docstring.

   DEFERRED: `pipeline.py:806,831` (HNSW cache miss / save failure). They already call `_logger`, so
   they are the least silent of the set, and reaching them needs a full `build_pipeline` run.
5. DONE 2026-07-23. All 18 hooks instrumented. `hook_instrument <name>` (`bin/lib/common.sh`)
   installs ONE `trap ... EXIT` per hook rather than editing each of the **96 `exit` statements**
   across those files. The trap covers what a per-`exit` edit cannot: `set -e` aborts and
   command-not-found crashes, the class that made the sub-agent start-hook failure invisible.
   Verified against all five exit shapes (`exit 0` / `exit 2` / `set -e` / crash / fallthrough), each
   preserving the real exit code, which matters because Claude Code reads exit 2 as deny.
   `hook_timer_end` gained an optional 5th `exit_code` arg (optional, so pre-existing 4-arg callers
   are untouched).

   `log_gate_decision` emits `gate_decision` to the **audit** stream on BOTH branches for the 6 gates
   and 5 validators. Deny-only logging would have preserved the original blind spot, since a gate
   ALLOW is already silent by design. reason/target carry tool input, so they are passed through the
   environment into `json.dumps` rather than interpolated into a JSON string.

   **MEASURED COST: +28ms per instrumented hook run** (6ms bare, 34ms with `hook_instrument`), which
   is the `friction-append` python spawn. Against the existing instrumented-hook medians (70-268ms)
   that is roughly 10-40%. `writ-read-rag.sh` is per-prompt and is the one to watch. A/B'd
   `test_hook_perf_floors` three times to confirm no regression to hooks NOT in the 18: before
   240/239/239ms, after 238/241/237ms (noise). That test's pre-existing failure (p95 239ms vs a
   220ms floor) reproduces with these changes stashed and is unrelated.

   Two hooks did not source `common.sh` and now do so defensively (`|| true` plus a `type` guard), so
   a missing `common.sh` degrades to an uninstrumented but working hook. `session-start-bootstrap.sh`
   is instrumented after its `CLAUDE_PLUGIN_ROOT` check, not before: the early exit means "not under
   the plugin loader, nothing to bootstrap", a genuine no-op.
6. DONE 2026-07-22. `pre_compaction`/`post_compaction` mapped to friction explicitly,
   `subagent_rules_injected` to metrics, dead `instructions_loaded` dropped. `logroot_smoke_test`
   turned out to be a one-off manual smoke test with no emitter in the tree, so there was nothing to
   fix. A router test now derives the valid stream vocabulary from `RETENTION_DAYS`, which is how the
   old hardcoded `("audit", "friction", "metrics")` tuple silently failed to cover a new stream.

**P2, new observability**
7. Daemon per-request events, retrieval quality signals, Neo4j failure events (F).
8. Debug stream, or an explicit ADR that debug stays `/tmp`-only and the blueprint is amended (D2).
9. Persist verification evidence to a durable stream (F), which the run ledger then consumes.

Item 1 gates everything. Items 4 and 5 are independent and can run in parallel.