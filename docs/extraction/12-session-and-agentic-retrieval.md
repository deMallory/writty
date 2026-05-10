# 12 — Session and Agentic Retrieval

Source: `bin/lib/writ-session.py` (2090 lines, stdlib-only). Heart of agentic retrieval — owns per-session state for hooks, budget tracking, gate enforcement, sub-agent isolation, compaction recovery, and friction telemetry.

A second client-side helper exists in `writ/retrieval/session.py` (96 lines) — `SessionTracker` — used for in-process multi-query simulation by callers not going through hooks.

## Cache file location and atomicity

```
CACHE_DIR = os.environ.get("WRIT_CACHE_DIR", tempfile.gettempdir())
_cache_path(session_id) = f"{CACHE_DIR}/writ-session-{session_id}.json"
```

Atomic writes: `_write_cache` writes to `path + ".tmp"` then `os.rename(tmp, path)`.

JSON-decode/IO errors fall back silently to the default cache shape (corruption is treated as fresh state, not fatal).

## Cache schema (every key)

Default cache shape from `_read_cache` (lines 67-104). When an existing cache is loaded (lines 107-144), `setdefault` adds any missing keys for forward-compatibility.

| Key | Default | Purpose |
|---|---|---|
| `loaded_rule_ids` | `[]` | **Sorted, deduplicated, flat** list of every rule_id ever loaded in this session. Used for hallucinated-rule-id detection (validate_phase_a) and feedback/coverage. |
| `loaded_rules` | `[]` | Full rule objects (not just IDs). Cleared by `clear-rules-for-compaction`. ~200 tokens each. |
| `remaining_budget` | `8000` (`default_budget`) | Token budget remaining for RAG injection. Decremented by `--cost`. Reset by compaction. |
| `context_percent` | `0` | Last observed Claude context-window fill percent. |
| `queries` | `0` | Total RAG queries this session. |
| `mode` | `None` | `conversation` / `debug` / `review` / `work` (one of `VALID_MODES`). |
| `is_subagent` | `False` | Set by `writ-subagent-start.sh`. Bypasses gates and skip-checks. |
| `is_orchestrator` | `False` | Set when `mode set work --orchestrator`. Suppresses broad RAG injection. |
| `files_written` | `[]` | Sorted set of file paths written this session. |
| `analysis_results` | `{}` | `{filepath: "pass"|"fail"}` from analyzers. Drives feedback. |
| `feedback_sent` | `[]` | Rule IDs already feedback-sent this session (deduped). |
| `pending_violations` | `[]` | List of `{rule_id, file, line, evidence}` triples. Deduped on add. |
| `invalidation_history` | `{}` | `{gate_name: [{cycle, rule_id, file, line, evidence, trace, prior_plan_hash, timestamp}, ...]}` per-gate. |
| `escalation` | `{gate, needed, diagnosis, feedback_sent}` | Set when invalidation cycles >= `MAX_CYCLES_BEFORE_ESCALATION` (3). `diagnosis` ∈ `same-rule` / `different-rules` / `mixed`. |
| `pretool_queried_files` | `[]` | Files for which a PreToolUse RAG query already fired (dedup). |
| `paused_work_state` | `None` | Snapshot of `{phase, gates_approved, loaded_rule_ids_by_phase}` saved when leaving Work mode and restored on return. |
| `failed_writes` | `[]` | Records of denied write attempts. |
| `last_injected_rule_ids` | `[]` | Rule IDs from most recent injection — used as `prefer_rule_ids` for sticky-tiebreak. Cleared on compaction. |
| `detected_domain` | `None` | Cached domain hint. |
| `instructions_rule_ids` | `[]` | Rule IDs surfaced by instructions/methodology lookups. |
| `current_phase` | `None` | `planning` / `testing` / `implementation` for Work mode. |
| `gates_approved` | `[]` | Subset of `GATE_SEQUENCE_WORK = ["phase-a", "test-skeletons"]`. SSOT for gate state. |
| `loaded_rule_ids_by_phase` | `{}` | `{phase: [rule_ids]}` partition. Special `_historical` bucket holds rules from advanced phases. |
| `phase_transitions` | `[]` | Audit trail: `{from, to, ts, trigger, mode, gate, artifacts_validated}`. Triggers: `mode-set`, `mode-switch`, `mode-switch-restore`, `user-approved`, `exit-plan-reset`. |
| `denial_counts` | `{}` | `{gate_name: count}` of consecutive denials. Reset on gate advance. |
| `active_playbook` | `None` | Phase-1 SDD/brainstorm workflow tracking. |
| `active_phase` | `None` | Within-playbook phase. |
| `playbook_phase_history` | `[]` | Past playbook phases. |
| `review_ordering_state` | `{}` | SDD two-stage review ordering. |
| `verification_evidence` | `{}` | Gate-5 Tier-1 verification artifacts. |
| `quality_judgment_state` | `{}` | Gate-5 Tier-2 (Haiku judge) state. |
| `quality_override_count` | `0` | User overrides of judge verdicts. |
| `always_on_budget` | `5000` (`always_on_cap`) | Separate budget for always-on (mandatory-rule) injection. |
| `always_on_tokens_used` | `0` | Counter for always-on tokens. |
| `token_snapshots` | (added by `--token-snapshot`) | Append-only `[{ts, phase, mode, context_percent, context_tokens, ...}]`. Drives `phase_token_summary` events. |

## Budget logic

### Starting budget — loaded from `writ/shared/budget.json` (SSOT)

```python
DEFAULT_SESSION_BUDGET = 8000           # default_budget
APPROX_TOKENS_PER_RULE_FULL = 200       # rule_cost_full
APPROX_TOKENS_PER_RULE_STANDARD = 120   # rule_cost_standard
APPROX_TOKENS_PER_RULE_SUMMARY = 40     # rule_cost_summary
DEFAULT_ALWAYS_ON_CAP = 5000            # always_on_cap
```

`subagent_budget` in JSON is `null` — sub-agents don't have a budget cap.

### What decrements

`cmd_update --cost N` (line 181-184):
```python
cache["remaining_budget"] = max(0, cache["remaining_budget"] - cost)
```

The RAG inject hook calls `cmd_update --cost <n>` after each successful injection. Cost is computed by `_estimate_cost(rules, mode) = len(rules) * APPROX_TOKENS_PER_RULE_<MODE>` (line 291-297) and emitted as a `WRIT_META:` line by `cmd_format` (line 370-372).

`cmd_update --add-always-on-tokens N` (line 240-246) decrements `always_on_budget` separately.

### What resets

- `cmd_detect_compaction` (line 510-535): when context_percent drops > 20 between turns, resets `remaining_budget = DEFAULT_SESSION_BUDGET`, clears the current phase's rule list, clears `last_injected_rule_ids`.
- `cmd_reset_after_compaction` (PostCompact hook, line 627-645): same effect.
- Mode set/switch (`_mode_set` line 847-878): does NOT reset budget — only resets phase, gates_approved, paused_work_state, denial_counts.

### `cmd_should_skip` (line 271-288)

Decides whether the RAG injection hook should skip its query.
```python
if cache.get("is_subagent"):
    return False                         # sub-agents: NEVER skip
if cache.get("remaining_budget") <= 0:
    return True                          # skip: budget exhausted
if cache.get("context_percent") >= threshold:   # default threshold=75
    return True                          # skip: context pressure
return False                             # proceed
```

Shell exit code: `True=skip => exit 0`, `False=proceed => exit 1` (line 1958).

## `loaded_rule_ids` lifecycle

### Adds

`cmd_update --add-rules JSON` (line 168-180):
```python
existing = set(cache.get("loaded_rule_ids", []))
existing.update(new_ids)
cache["loaded_rule_ids"] = sorted(existing)

phase = cache.get("current_phase", "unknown")
by_phase = cache.setdefault("loaded_rule_ids_by_phase", {})
phase_ids = set(by_phase.get(phase, []))
phase_ids.update(new_ids)
by_phase[phase] = sorted(phase_ids)
```

Two parallel data structures — flat (for coverage/feedback/hallucination-checks) and phase-partitioned (for exclude-list scoping).

`cmd_update --add-rule-objects JSON` (line 212-228) appends full rule dicts into `loaded_rules`. Deduped by `rule_id`.

### Scrubs (prompt-cache friendliness)

- `cmd_clear_rules_for_compaction` (line 610-624, PreCompact hook): clears `loaded_rules` (full objects) but keeps `loaded_rule_ids`.
- `cmd_advance_phase` (line 1524-1531): on gate advance, the **current phase's** `loaded_rule_ids_by_phase[old_phase]` are appended to `_historical` and the bucket cleared. The flat `loaded_rule_ids` is **not** scrubbed.
- `cmd_detect_compaction` and `cmd_reset_after_compaction`: clear only `by_phase[current_phase]`. Also clear `last_injected_rule_ids`.

### Why scrub
Stable injection order across turns is required for prompt-cache reuse. The sticky-tiebreak in `pipeline.query` uses `prefer_rule_ids = last_injected_rule_ids` to reorder rules within a 0.02 score band. If the cache window is invalidated by compaction, the prefer list is stale.

## `exclude_rule_ids` derivation

The pipeline's `query()` accepts both `exclude_rule_ids` and `loaded_rule_ids` and **unions** them (no functional difference, just historical naming). Applied as post-filter on both BM25 and vector results.

The hook builds the exclude list from the current phase's `loaded_rule_ids_by_phase[current_phase]` (not the full flat list) — per-phase scoping. Cross-phase queries can re-surface rules already loaded in previous phases.

Client-side `SessionTracker.next_query()` (`writ/retrieval/session.py:49-61`) sends the full accumulated set since `SessionTracker` does not partition by phase.

## Per-phase tracking (`loaded_rule_ids_by_phase`)

Population: `cmd_update --add-rules` writes into both `loaded_rule_ids` (flat) and `by_phase[current_phase]`.

Reset events:
- `cmd_advance_phase` (line 1524-1531):
```python
current_ids = by_phase.get(old_phase, [])
if current_ids:
    by_phase.setdefault("_historical", []).extend(current_ids)
    by_phase[old_phase] = []
by_phase.setdefault(new_phase, [])
```
- `cmd_detect_compaction` (line 511-517): clears only `by_phase[current_phase]`.
- `cmd_reset_after_compaction` (line 631-634): same.
- `cmd_update --reset-task-phase` (line 247-264): on ExitPlanMode validation success, sets `current_phase = "planning"` and `gates_approved = []`.

Phase advance map:
```python
GATE_SEQUENCE_WORK = ["phase-a", "test-skeletons"]
_PHASE_AFTER_GATE_WORK = {
    "phase-a": "testing",
    "test-skeletons": "implementation",
}
_initial_phase_for_mode("work") = "planning"
```

Work-mode phase progression: `planning -> testing -> implementation`, gated by `phase-a` then `test-skeletons`.

## Sub-agent isolation

`writ-subagent-start.sh` sets `is_subagent: true` in the worker's session cache. Workers get fresh `session_id` per agent.

Effects of `is_subagent: True`:
1. **`cmd_should_skip` always returns False** (line 282-283): "sub-agents: unlimited budget, never skip."
2. **`_can_write_check` bypasses all mode/gate checks** (line 1098-1107):
```python
if cache.get("is_subagent"):
    _log_friction_event(..., result="allow", gate_status="subagent_bypass")
    return {"can_write": True, "reason": None}
```

Comment: "Gates exist to stop the master from writing code before plan approval, not to re-police workers the orchestrator has already sanctioned."

PostToolUse RAG still fires inside workers — they get rule injection on every file write, same as the master would.

Sub-agent telemetry: a `subagent_complete` friction event records `{parent_session, agent_id, agent_type, queries, rules_loaded, files_written, denial_count, remaining_budget}`. `cmd_metrics` aggregates per-parent (line 1873-1906).

## Orchestrator session

Triggered by `mode set work <session_id> --orchestrator` (line 1977-1978):
```python
def _mode_set(session_id, mode, is_orchestrator=False):
    cache = _read_cache(session_id)
    cache["mode"] = mode
    if is_orchestrator:
        cache["is_orchestrator"] = True
```

Per `~/.claude/skills/writ/rules/writ-orchestrator.md`: the flag tells `writ-rag-inject.sh` to **suppress the ~1400-token broad RAG injection** on every UserPromptSubmit in the master session and emit a compact status line instead.

## Multi-query simulation / complement mode

There is no built-in "complement mode" parameter. Multi-query simulation is achieved by **sequential queries with accumulating exclude sets**.

### Server-side (hooks)
1. Read cache -> get `loaded_rule_ids_by_phase[current_phase]`.
2. POST `/query` with that as `loaded_rule_ids` (or `exclude_rule_ids`).
3. Pipeline's `exclude = set(exclude_rule_ids or []) | set(loaded_rule_ids or [])` produces a disjoint candidate set.
4. Update cache via `cmd_update --add-rules`.

### Client-side `SessionTracker` (`writ/retrieval/session.py`)

```python
class SessionTracker:
    def __init__(self, initial_budget=DEFAULT_SESSION_BUDGET):
        self._loaded_rule_ids: set[str] = set()
        self._remaining_budget = initial_budget

    def next_query(self, query_text, domain=None) -> dict:
        return {
            "query": query_text,
            "budget_tokens": self._remaining_budget,
            "loaded_rule_ids": sorted(self._loaded_rule_ids),
            **({"domain": domain} if domain else {}),
        }

    def load_results(self, response):
        for rule in response["rules"]:
            self._loaded_rule_ids.add(rule["rule_id"])
            for member_id in rule.get("rule_ids", []):
                self._loaded_rule_ids.add(member_id)   # abstraction members count
        cost = _estimate_token_cost(rules, mode)
        self._remaining_budget = max(0, self._remaining_budget - cost)

    def reset(self):
        self._loaded_rule_ids.clear()
        self._remaining_budget = self._initial_budget
```

Key detail: when an Abstraction is returned, **all its member rule_ids are added to the exclude set**, not just the abstraction id.

## Compaction interaction (PreCompact / PostCompact)

### `cmd_clear_rules_for_compaction` (PreCompact, line 610-624)
Fired BEFORE compaction:
- Clear `loaded_rules` (full rule objects, ~200 tokens each).
- Keep `loaded_rule_ids` (small).
- Log `pre_compaction` friction event with `rules_cleared` and `bytes_freed = rules_cleared * 200`.

### `cmd_reset_after_compaction` (PostCompact, line 627-645)
Fired AFTER compaction:
- Clear `loaded_rule_ids_by_phase[current_phase]`.
- Reset `remaining_budget = DEFAULT_SESSION_BUDGET` (8000).
- Clear `last_injected_rule_ids`.
- Log `post_compaction` friction event with `rules_cleared` and `budget_reset=True`.

The flat `loaded_rule_ids` is preserved across compactions.

### Implicit detection: `cmd_detect_compaction` (line 497-552)
For environments without PreCompact/PostCompact hooks, the inject hook can call this each turn. Compares previous vs current `context_percent`. If drop > 20, performs the same recovery as `reset_after_compaction` and logs `compaction_detected`.

## `writ-approve` mechanism

Files: `templates/commands/writ-approve.md` (template, copied per-project) and `.claude/commands/writ-approve.md` (active in this skill's repo).

Activation: user types `/writ-approve` after Claude presents a plan / test skeletons. Replaces fragile pattern-match on the word "approved" with an explicit tool-confirmed advance (plan Section 8.1).

### Procedure (from the slash-command body)
1. `GET /session/$SESSION_ID/current-phase` — read the authoritative phase.
2. Verify the relevant artifact (plan.md for planning, test skeletons for testing) exists.
3. POST advance:
```bash
curl -sX POST http://localhost:8765/session/$SESSION_ID/advance-phase \
  -H 'Content-Type: application/json' \
  -d '{"confirmation_source": "tool"}'
```
4. Reply: `[Writ: $ARG advanced -> $NEW_PHASE]`.

### Server-side handler -> `cmd_advance_phase` (line 1428-1578)

1. **Token validation** (line 1440-1459): reads `$TMPDIR/writ-gate-token-<session_id>`. The `auto-approve-gate.sh` hook writes this token when the user actually approves; the `--token` arg must match. If missing/mismatched, emits `agent_self_approval_blocked` friction event and returns `{"advanced": false, "reason": "Invalid or missing gate token. Gates can only be advanced by the approval hook, not by the agent."}`. **This prevents the agent from calling advance-phase directly via Bash to self-approve.**
2. Mode check: only Work mode has gates.
3. Find next pending gate from `GATE_SEQUENCE_WORK`.
4. **Validate artifacts**:
   - `phase-a` -> `_validate_phase_a` (line 1223-1291): plan.md exists, has `## Files`, `## Analysis`, `## Rules Applied`, `## Capabilities`. Validates rule IDs in `## Rules Applied` against the session's loaded_rule_ids (logs `hallucinated_rule_ids` event if mismatched). Capabilities must be unchecked `[ ]`.
   - `test-skeletons` -> `_validate_test_skeletons` (line 1362-1421): scans `files_written` for test files matching path patterns; falls back to project-wide glob.
5. On validation pass:
   - Add gate to `gates_approved`.
   - Advance `current_phase` per `_PHASE_AFTER_GATE_WORK`.
   - Reset `denial_counts[gate]`.
   - Move old phase's loaded rules to `_historical`, init new phase bucket.
   - Append `phase_transitions` entry with `trigger="user-approved"`.
   - Emit `phase_token_summary` friction event from accumulated `token_snapshots`.
   - Create artifact gate file at `<project_root>/.claude/gates/<gate>.approved` containing the session_id.
6. Return `{"advanced": true, "gate": ..., "phase": ..., "from_phase": ...}`.

### Gate-file vs cache truth
The `.claude/gates/*.approved` file on disk is an **artifact**, not source of truth. The cache's `gates_approved` array is authoritative. Gate file is created post-validation purely for human/CLI inspection.

### Invalidation -> escalation
`cmd_invalidate_gate` records each invalidation in `invalidation_history[gate]`. When `len(records) >= MAX_CYCLES_BEFORE_ESCALATION` (3), sets:
```python
cache["escalation"] = {
    "gate": gate_name,
    "needed": True,
    "diagnosis": ("same-rule" | "different-rules" | "mixed"),
    "feedback_sent": False,
}
```

`diagnosis` computed from unique rule IDs in cycle records.

## Files Read

- `bin/lib/writ-session.py` — 2090 lines (chunked reads)
- `writ/retrieval/pipeline.py` lines 198-409 — relevant `query()` method
- `writ/retrieval/session.py` — 96 lines (client-side `SessionTracker`)
- `templates/commands/writ-approve.md` — 31 lines

## Cross-References Noted

- Pipeline `query()` 5-stage details — see doc 03.
- `apply_context_budget` and `summary` mode -> doc 03.
- Abstraction member-id expansion in `SessionTracker.load_results` -> doc 10.
- Mandatory-rule injection budget (`always_on_budget` / `always_on_cap = 5000`).
- `writ-subagent-start.sh`, `writ-rag-inject.sh`, `auto-approve-gate.sh` — see doc 06.
- `gate-categories.json` (path-based exclusions, framework detection) consulted by `_can_write_check` -> doc 06.
