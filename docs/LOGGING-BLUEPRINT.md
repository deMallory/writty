# Writ Logging & Audit: architecture blueprint (for review)

Enterprise logging for Writ: split the one overloaded log into typed streams, put them in one
durable place, and add rotation + compression + 1-year retention + backup. Design for sign-off; no
code yet. Grounded in a full emission-site inventory (Python + bash) done 2026-07-01.

## Status: what exists today (the mess)

Writ has **10 logging mechanisms**, written by Python and bash, almost none bounded:

1. `workflow-friction.log` (per-project root, or `$WRIT_FRICTION_LOG`) - THE event log. Overloaded:
   it holds compliance events, improvement signals, AND high-volume telemetry all mixed. Live size
   in this repo: **22.6 MB / 125,278 lines**, never rotated. Written by FOUR writers:
   - `writ/session/friction.py::_log_friction_event` (session-side; marker-walk path resolution)
   - `writ/analysis/friction.py::log_friction_event` (server-side; cwd-relative default)
   - `bin/lib/common.sh::log_friction_event` -> `bin/lib/friction-append.py` (bash hooks)
   - fallback `/tmp/writ-friction-fallback.log` (`friction-append.py:38`) when the primary is
     unwritable - safety-critical: it is the only thing preventing silent loss of security events
     like `memory_policy_deny`.
2. Blackbox capture `~/.claude/writ-blackbox.jsonl` (`common.sh:76-101`) - raw CC<->hook wire
   payloads. Durable, and correctly GATED (`WRIT_BLACKBOX=1` or `~/.claude/writ-blackbox.on`). This
   one is already close to right.
3. `/tmp/writ-hook-debug.log` - 4 hooks `exec 2> >(tee -a ...)` their entire stderr, **always-on**.
4. `/tmp/writ-hooks.log` (`$WRIT_HOOK_LOG`) - stderr sink for ~12 python heredocs, **always-on**.
5. `/tmp/writ-rag-debug.log` - `writ-rag-inject.sh` `debug()`, ~22 lines **every prompt**, **always-on**.
6. `/tmp/writ-prompt-debug.log` - `auto-approve-gate.sh` logs every prompt (200 chars), **always-on**.
7. Session-keyed `/tmp/writ-{precompact,postcompact,feedback,coverage}-<sid>.log` - one file per
   session, **never cleaned up**.
8. Payload capture `/tmp/writ-subagent{,-stop}-payloads.jsonl` - diagnostic scaffolding, 50-line cap
   only (caps lines, not bytes; never aged).
9. Daemon output - `/tmp/writ-server.log` OR `${CLAUDE_PLUGIN_DATA}/server.log` OR journald,
   depending on install path (`$WRIT_LOG` has two different defaults; systemd uses journald).
10. Structured trails NOT in a log file: `record_transition()` writes phase transitions into the
    session cache JSON (`cache.py:301`); `session-metrics.md` (per-project `.claude/`, append-only);
    `/tmp/writ-calibration.jsonl` (hardcoded, no knob); in-repo `cache/<sid>/last-test-run.log` and
    `*.lint.json`.

### The four problems
- **Unbounded.** No rotation/compression/retention anywhere (the one `rotate_if_needed()` at
  `analysis/friction.py:368` is invoked manually and has never fired). 22.6 MB and climbing.
- **Overloaded.** One log mixes three concerns. Volume proves it: `hook_execution` 31,962 rows,
  `mode_change` 28,812, `write_attempt` 8,925 - telemetry and compliance in the same file.
- **Scattered + ephemeral.** Most debug lives in `/tmp` (wiped on reboot), always-on (production
  spam), across many hardcoded paths.
- **No audit guarantee.** There is no single durable, complete "what happened" trail for
  compliance; the events exist but are buried in a log that also gets truncated ad hoc.

### Knob gotchas found (must fix, or the redesign silently misbehaves)
- `WRIT_DEBUG_LOG` (`writ-rag-inject.sh:26`) LOOKS like an env knob but is a hardcoded literal - not
  overridable.
- `WRIT_LOG` has two different unset-defaults depending on which script sets it first.
- Debug logs are **unconditional** (no gate) - the main production-spam source.

## Target architecture

### 1. Typed streams (the taxonomy)
Route every event to exactly one stream by its purpose:

| Stream | Purpose | Retention | Examples |
|---|---|---|---|
| **audit** | Immutable compliance trail: what the governance system decided | long (12 mo) | write allow/deny, gate_denial, mode_change, phase_advance, agent_self_approval_blocked, candidate_promoted, quality_judgment, memory_policy_deny, committed_file_not_in_plan, exitplanmode_allow/deny, debug_gate_* |
| **friction** | Signal that something is worth fixing | medium (12 mo) | repeated_denial, hallucinated_rule_ids, approval_pattern_miss, subagent_type_fallback, *_capture_failed, recall_failed, git_hooks_auto_install_failed, pre/post_compaction |
| **metrics** | High-volume operational telemetry (analytics, not compliance) | short (e.g. 90 d) | hook_execution timing, rag_query, always_on_inject, subagent_start/complete, playbook_step_complete, phase_token_summary, pressure_audit, cwd_changed |
| **debug** | Verbose traces/tracebacks, disposable | short (e.g. 14 d) | the `/tmp/writ-*-debug.log` + `writ-hooks.log` content + session-keyed stdout dumps |
| **blackbox** | Raw CC<->hook wire payloads, opt-in | short, opt-in | `writ-blackbox.jsonl` (unchanged) |

Note: this is your approved audit/friction/debug/blackbox split PLUS a recommended 5th **metrics**
stream - see Open Decision 1. `hook_execution` alone is 31,962 of the 125K rows; keeping that out of
`friction` is what keeps friction small and signal-rich.

Not logs (leave as state/scratch, just add cleanup): `writ-current-session`, gate tokens,
`pending-tests`, `cache/<sid>/*`, `session-metrics.md` (already a durable per-project audit rollup).

### 2. One place, per project (central, Writ-owned)
```
<skill>/var/logs/       # skill install's var/logs (e.g. ~/.claude/skills/writ/var/logs)
  <project>/            # project = the same scope key decision-memory uses (name<->remote_url)
    audit.jsonl
    friction.jsonl
    metrics.jsonl
    debug.jsonl
  writ/                 # Writ itself is always-on -> its own project scope
    audit.jsonl ...
  blackbox.jsonl        # global, opt-in
  archive/              # rotated + gzipped generations land here
    <project>/audit-2026-07-01.jsonl.gz ...
```
Durable (off `/tmp`), one root to manage, per-project subdirs (matches how `workflow-friction.log`
is already per-project, and how decision-memory scopes by project). The daemon and every hook write
under the same root via the router (below).

### 3. One router (unify the four writers)
A single `writ/shared/logging.py` router: `emit(stream, event, session_id, mode, **fields)` resolves
`<skill>/var/logs/<project>/<stream>.jsonl` and appends one JSON line (same base schema as today:
`ts, session, mode, event, ...`). It is the ONE place that knows paths, streams, and the fallback.
- Python writers (session + server + `record_transition`) call it directly.
- Bash writers call it through `friction-append.py`, which gains a `--stream` argument (default
  `friction` for back-compat) and delegates to the router.
- Preserve the safety-critical fallback: on primary-write failure, append to
  `<skill>/var/logs/_fallback.jsonl` (durable, not `/tmp`), never drop a security event.
This collapses 4 divergent writers + 2 path-resolution schemes into one, and fixes the
`WRIT_LOG`/`WRIT_DEBUG_LOG` inconsistencies by centralizing path logic.

### 4. Hybrid rotation + retention + compression (your call 3)
Two layers so nothing slips through:
- **At the source (Python):** the router uses a size-aware handler - when a stream file crosses the
  threshold it rolls it into `archive/<project>/<stream>-<date>.jsonl` before continuing. Covers
  every Python + daemon write in real time.
- **The sweep (backstop, covers bash-written files too):** `writ logs rotate`, run by a systemd
  user timer (writ already uses systemd), walks the whole log root and:
  1. rotates any stream file over the size trigger OR older than the daily boundary,
  2. gzips rotated generations into `archive/`,
  3. prunes archives past the per-stream retention window,
  4. cleans up stale session-keyed scratch files.
  The sweep is idempotent and file-based, so it catches anything the source-handler cannot (bash
  appends, journald-exported daemon logs, orphaned session files).

Retention (your call 4): rotate at **~50 MB or daily**, gzip (JSON-lines compresses ~10-20x), keep
**12 months** for audit/friction; shorter for metrics/debug (Open Decision 2). A year of audit at
this event rate compresses to well under a GB.

### 5. Backup (your call 5)
`writ logs backup [--dest DIR]` copies the gzipped `archive/` tree to a configurable destination
(default `<skill>/var/logs/archive/` is the live archive; backup copies it elsewhere, e.g. an
external/synced dir). Object storage is intentionally out of scope for a local single-user tool.

### 6. Fix debug spam + knobs
- Gate all debug-stream writes behind `WRIT_DEBUG=1` (default OFF), so production is quiet by
  default (today `writ-rag-debug` alone writes ~22 lines every prompt). See Open Decision 3.
- Make `WRIT_DEBUG_LOG` a real override (or delete the misleading name and route via the router).
- Collapse `WRIT_LOG`'s two defaults into one router-owned path.
- Keep blackbox exactly as-is (already gated + durable).

### 7. Daemon output
Under systemd (the production path) the daemon's raw stdout/stderr goes to **journald**, which
already rotates/retains. The daemon's STRUCTURED events (its `log_friction_event` calls) route
through the router into the files like everything else, so the audit/friction/metrics trail is
complete regardless. Recommendation: leave raw daemon stdout in journald (don't fight it), document
`journalctl --user -u writ-server`, and have `writ logs` optionally surface it. See Open Decision 4.

## Open decisions (need your call)
1. **5th `metrics` stream?** Recommended: yes - split high-volume telemetry out of `friction` so
   friction stays signal-rich. (Your original ask was 4 streams; this adds one.)
2. **Retention per stream.** audit/friction = 12 mo (locked). metrics/debug shorter (rec: metrics 90 d,
   debug 14 d) - confirm or set your own.
3. **Debug default OFF.** Gate debug behind `WRIT_DEBUG` (rec) - this silences current always-on
   debug in production. Confirm you want debug off by default.
4. **Daemon logs.** Leave raw daemon output in journald + document (rec), vs also tee it into the
   central `debug` stream.
5. **Router refactor scope.** Unify all four writers behind one router now (rec, the right
   foundation), vs a lighter touch (only add rotation/retention, leave the four writers in place).

## Phasing (proposed)
- **P1 - Router + streams + layout.** `writ/shared/logging.py`, `friction-append.py --stream`,
  central `~/.claude/writ/logs/<project>/` paths, route every emission site to its stream, preserve
  the fallback, gate debug behind `WRIT_DEBUG`. Back-compat: `WRIT_FRICTION_LOG` still honored;
  existing analyzers (`analysis/friction.py`, `metrics.py`) read the new audit+friction+metrics
  streams.
- **P2 - Rotation + retention + compression.** Source-side size handler + `writ logs rotate` sweep +
  systemd timer + per-stream retention + session-scratch cleanup.
- **P3 - Backup + surfacing.** `writ logs backup`, and a `writ logs [tail|stats|list]` surface
  (folds journald in). Optional: a `writ logs` view that complements the decision-memory knowledge UI.
- **Migration.** One-time: leave existing 22.6 MB `workflow-friction.log` files in place (archive
  them via the first sweep); new events flow to the split streams. No lossy rewrite of history.

## Guarantees
- **Auditability:** every governance decision lands in a durable, append-only `audit.jsonl`, one per
  project, retained 12 months, never silently truncated (rotation archives, never deletes within the
  window).
- **Bounded:** hybrid rotation caps live-file size and total footprint; gzip + pruning bound the year.
- **Fail-open + safe:** a write failure never blocks a hook (unchanged discipline) and never drops a
  security event (durable fallback preserved).
- **Quiet by default:** debug off unless `WRIT_DEBUG=1`.

## ADR: default log root relocated to `<skill>/var/logs` (2026-07-03)

**Context.** P1 shipped the default log root as a fixed home-relative path, `~/.claude/writ/logs`
(see sections 2/3/5 above, as originally written). That location is decoupled from the skill install
dir, so the logs of a Writ install do not travel with it and the tree assumes a single fixed home
layout.

**Decision.** The DEFAULT root now derives from the skill install location:
`writ/shared/logging.py::log_root()` returns `_DEFAULT_LOG_ROOT`, a named module constant computed as
`Path(__file__).resolve().parents[2] / "var" / "logs"` (the skill dir that contains the `writ`
package, e.g. `~/.claude/skills/writ/var/logs`). `log_root()` is the single source of the root; every
other path (`stream_path`, `archive_dir`, `archive_path`, `_fallback`) derives from it, so this one
change propagates everywhere with no deriver edits (DRY-DUP-003).

**Alternative considered.** Keep the fixed central home root `~/.claude/writ/logs`. Rejected: it does
not co-locate logs with the install, and it hardcodes a home layout rather than following `__file__`.

**Trade-off.** Co-location with the install (logs follow the skill, standard `var/` runtime
convention) at the cost of orphaning any pre-existing tree at the old path.

**Contract preserved.** The `WRIT_LOG_ROOT` env override is unchanged and still checked FIRST, so any
operator or test that sets it is unaffected.

**Migration.** Pre-existing logs under `~/.claude/writ/logs` are left in place (orphaned); code does
not move them. After this ships, restart the daemon so new writes land under the new root:
`systemctl --user restart writ-server`. The old tree may be moved, archived, or removed manually. The
in-repo runtime tree is gitignored (`var/`).
