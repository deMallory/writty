# 05 — HTTP API (full extraction)

Source: `writ/server.py` (FastAPI). All endpoints `async`. Started via `writ serve` (uvicorn) — defaults `host=localhost`, `port=8765`.

## App construction (server.py:109-113)

```python
app = FastAPI(
    title="Writ",
    description="Hybrid RAG knowledge retrieval service for AI coding rule enforcement.",
    lifespan=lifespan,
)
```

No CORS middleware. No auth middleware. No global exception handler. Errors are returned in the response body as `{"error": "..."}` with HTTP **200** (the implementation does NOT raise `HTTPException`); only Pydantic validation produces 422.

## Lifespan / startup-shutdown (server.py:94-106)

`@asynccontextmanager async def lifespan(app: FastAPI)` pre-warms global module state on startup:
- `_db = Neo4jConnection(get_neo4j_uri(), get_neo4j_user(), get_neo4j_password())` — bolt://localhost:7687 default.
- `_pipeline = await build_pipeline(_db)` — loads BM25 + ANN indexes into memory (PERF-IO-001).
- `_llm_client = LlmAnalyzer()`.
- `_instrumentation = Instrumentation()`.
- `_startup_time = datetime.now()`.

On shutdown: `await _db.close()`.

## Dynamic module import (server.py:33-40)

`writ_session` is loaded as a Python module from disk via `importlib`:
```python
_WRIT_SESSION_PATH = Path(__file__).resolve().parent.parent / "bin" / "lib" / "writ-session.py"
```
Most `/session/*` routes call functions on this module (`_read_cache`, `_write_cache`, `cmd_format`, `cmd_detect_compaction`, `cmd_clear_rules_for_compaction`, `cmd_reset_after_compaction`, `_can_write_check`, `DEFAULT_SESSION_BUDGET`).

## Pydantic request models (server.py:43-322)

| Class | Line | Fields |
|---|---|---|
| `QueryRequest` | 43 | `query: str`, `domain: str\|None=None`, `scope: str\|None=None`, `budget_tokens: int\|None=None`, `exclude_rule_ids: list[str]\|None=None`, `prefer_rule_ids: list[str]\|None=None`, `node_types: list[str]\|None=None` |
| `ProposeRequest` | 55 | `rule_id, domain, severity, scope, trigger, statement, violation, pass_example, enforcement, rationale, last_validated: str`; `task_description: str=""`; `query_that_triggered: str\|None=None` |
| `FeedbackRequest` | 73 | `rule_id: str`, `signal: str` |
| `ConflictsRequest` | 80 | `rule_ids: list[str]` |
| `SessionUpdateRequest` | 261 | strict; `key: str`, `value: str` |
| `SessionModeSetRequest` | 270 | strict; `mode: str`, `orchestrator: bool=False` |
| `SessionCanWriteRequest` | 279 | `tool_input: dict[str,Any]={}`, `skill_dir: str=""` |
| `SessionFormatRequest` | 286 | `query_response: dict[str,Any]` |
| `SessionAutoFeedbackRequest` | 292 | `feedback: str=""` |
| `SessionAddViolationRequest` | 298 | `rule_id: str`, `detail: str=""`, `file: str=""`, `line: int\|None=None` |
| `DetectCompactionRequest` | 307 | strict; `context_percent: int` |
| `PreWriteCheckRequest` | 315 | `session_id: str`, `tool_input: dict[str,Any]={}`, `skill_dir: str=""`, `file_path: str=""`, `prefer_rule_ids: list[str]\|None=None` |

`AnalyzeRequest`/`AnalyzeResponse` come from `writ.analysis`.

## Endpoints

### POST /query (116-129)
Body `QueryRequest`. Calls `_pipeline.query(query_text, domain, budget_tokens, exclude_rule_ids, prefer_rule_ids, node_types)`. Note: `scope` is in the schema but **not forwarded** to the pipeline. Response: pipeline result dict.

### POST /analyze (132-145)
Body `AnalyzeRequest` (`code, file_path, phase, context`). Calls `await run_analysis(code, file_path, phase, context, pipeline=_pipeline, llm_client=_llm_client, instrumentation=_instrumentation)`. Returns `AnalyzeResponse`.

### GET /rule/{rule_id} (148-160)
Path `rule_id`; query `include_graph: bool=False`. Calls `_db.get_rule(rule_id)` and (if requested) `_db.traverse_neighbors(rule_id, hops=1)`. Response: `{"rule": <node>, "graph_context"?: <neighbors>}`.

### POST /propose (163-194)
Builds candidate dict from `ProposeRequest`; calls `await propose_rule(candidate, _pipeline, _db, origin_db_path=DEFAULT_DB_PATH, task_description, query_that_triggered)` from `writ.gate`. Returns `propose_rule`'s result.

### POST /feedback (197-212)
`signal` must be `"positive"` or `"negative"`. Calls `_db.increment_positive(rule_id)` or `_db.increment_negative(rule_id)`. Response: `{"rule_id", "signal", "recorded": True}`.

### POST /conflicts (215-229)
Runs Cypher directly:
```cypher
MATCH (a:Rule)-[:CONFLICTS_WITH]-(b:Rule)
WHERE a.rule_id IN $ids AND b.rule_id IN $ids
AND a.rule_id < b.rule_id
RETURN a.rule_id AS rule_a, b.rule_id AS rule_b
```

### GET /health (232-253)
Verifies:
- `_db.count_rules()` (real Neo4j round-trip).
- Cypher `MATCH (r:Rule) WHERE r.mandatory = true RETURN count(r) AS count` (second round-trip).
- `index_state = "warm"` if `_pipeline` is non-None else `"cold"` (no actual index probe).

Response on success:
```json
{
  "status": "healthy",
  "rule_count": <int>,
  "mandatory_count": <int>,
  "index_state": "warm" | "cold",
  "startup_time": "<ISO datetime>" | null
}
```

### Session endpoints

| Path | Method | Body | What it does |
|---|---|---|---|
| `/session/{session_id}` | GET | — | `_read_cache(session_id)`; returns cache dict with `session_id` injected |
| `/session/{session_id}/update` | POST | `SessionUpdateRequest` | Reads cache, sets `cache[key]=value`, writes |
| `/session/{session_id}/should-skip` | GET | — | `{"should_skip": bool}`. True when `remaining_budget <= 0` or `context_percent >= 75` |
| `/session/{session_id}/mode` | GET | — | `{"mode": str}` (empty if unset) |
| `/session/{session_id}/mode` | POST | `SessionModeSetRequest` | Sets `cache["mode"]`; if `orchestrator=True`, also `is_orchestrator` |
| `/session/{session_id}/can-write` | POST | optional | If `mode != "work"`, returns `mode is not None`; else returns True |
| `/session/{session_id}/advance-phase` | POST | `{confirmation_source}` | See below |
| `/session/{session_id}/current-phase` | GET | — | `{"phase": <str>}` (default `"planning"`) |
| `/session/format` | POST | `SessionFormatRequest` | Pipes JSON to `cmd_format()` stdin; captures stdout including `WRIT_META:<json>` line |
| `/session/{session_id}/coverage` | GET | — | `{"coverage": float}` = `len(loaded_rule_ids) / max(queries, 1)` |
| `/session/{session_id}/check-escalation` | GET | — | `{"escalation": bool}` from `cache["escalation"]["needed"]` |
| `/session/{session_id}/auto-feedback` | POST | — | **No-op**. Returns `{"ok": True}` |
| `/session/{session_id}/clear-pending-violations` | POST | — | Sets `cache["pending_violations"] = []` |
| `/session/{session_id}/add-pending-violation` | POST | `SessionAddViolationRequest` | Appends `{rule_id, detail, file, line}` |
| `/session/{session_id}/invalidate-gate` | POST | — | Sets `cache.setdefault("invalidation_history", {})`. Effectively a no-op |
| `/session/{session_id}/pending-violations` | GET | — | `{"violations": <list>}` |
| `/session/{session_id}/detect-compaction` | POST | `DetectCompactionRequest` | Captures stdout from `cmd_detect_compaction(...)` |
| `/session/{session_id}/clear-rules-for-compaction` | POST | — | Calls `cmd_clear_rules_for_compaction(...)` (PreCompact hook) |
| `/session/{session_id}/reset-after-compaction` | POST | — | Calls `cmd_reset_after_compaction(...)` (PostCompact hook) |
| `/session/{session_id}/active-playbook` | GET | — | `{"active_playbook", "active_phase", "playbook_phase_history"}` |
| `/session/{session_id}/active-playbook` | POST | dict | Sets active playbook/phase; emits friction `playbook_step_complete` |
| `/session/{session_id}/verification-evidence` | POST | dict | Records evidence under `cache["verification_evidence"][todo_id]` |
| `/session/{session_id}/verification-evidence` | GET | `?todo_id=` | Gets evidence (one or all) |
| `/session/{session_id}/quality-judgment` | POST | dict | Records quality judgment; if `overridden=true`, increments override count; emits friction event |
| `/session/{session_id}/quality-judgment` | GET | — | `{"judgments": <dict>, "override_count": <int>}` |

### POST /session/{session_id}/advance-phase (409-506)
Body `{confirmation_source}` ∈ `{"tool", "pattern", "explicit"}` (default `"explicit"`).

- Phase order: `["planning", "testing", "implementation", "complete"]`.
- Default current phase: `"planning"`.
- Refuses to advance past `"complete"` — returns explicit error directing caller to `mode set work`.
- Otherwise advances index by 1 (clamped), appends `{from, to, confirmation_source, ts}` to `cache["phase_transitions"]`.
- Writes a JSONL `phase_advance` entry to `<project_root>/workflow-friction.log`. Project root detected by walking up until `.git`, `pyproject.toml`, or `package.json` (max 8 levels).
- For non-terminal phases, also calls `log_friction_event(event="playbook_step_complete", playbook_id="PBK-PROC-SDD-001", step_id, step_index, total_steps=3)`.

### GET /always-on (915-1009)

Query param `mode: str|None`. Returns the always-on rule bundle.

Logic:
- Pulls `Rule` nodes where `always_on=true` (sorted severity DESC, rule_id).
- Pulls all `ForbiddenResponse` (FRB-*) nodes.
- Pulls `Skill` and `Playbook` nodes where `always_on=true`.
- If `mode` provided and not `"work"`, filters out rules with `domain="process"`.
- Renders summary form: trigger + statement only. Token estimate via 4-chars-per-token heuristic.

Response:
```json
{
  "rules": [{"rule_id", "trigger", "statement", "severity", "est_tokens"}, ...],
  "total_tokens": <int>,
  "cap": 5000,
  "mode_scope": "<mode>" | "universal",
  "render_mode": "summary"
}
```
Cap of 5000 is reported but not enforced server-side.

### GET /subagent-role/{name} (1012-1044)

Lookup by name OR `role_id` OR `'ROL-' + toUpper(replace(name, 'writ-', '')) + '-001'`.
Response: `{"role_id", "name", "prompt_template", "model_preference", "dispatched_by"}`.

### POST /pre-write-check (1047-1160)

Body `PreWriteCheckRequest`. Three-stage check:

1. **Gate approval**: `writ_session._can_write_check(session_id, {tool_input}, skill_dir)`. If denied: `decision = "ask"` when max denial count >= 2, else `"deny"`.
2. **Final-gate**: when `mode == "work"` and `"COMPLETE"` in `file_path`, deny with reason `"[ENF-GATE-FINAL] Cannot mark module complete without ENF-GATE-FINAL verification."`.
3. **RAG query** (if pipeline available and `file_path` present):
   - `exclude_rule_ids` = `loaded_rule_ids_by_phase[current_phase]` if both present, else `loaded_rule_ids`.
   - `max_budget = min(remaining_budget, 1500)`. Skip if `< 200`.
   - Query string built from filename: extension → language label (`.py`→python, `.php`→php, `.js`→javascript, `.ts`→typescript, `.go`→go, `.rs`→rust); plus camel/snake-cased basename words >3 chars; capped at 15 tokens.
   - Skip if query string < 5 chars.
   - Calls `_pipeline.query(...)`, formats via `writ_session.cmd_format()`, splits `WRIT_META:` line for `rag_meta = {rule_ids, tokens}`.
   - RAG failures caught and silently swallowed (non-fatal).

Response (always HTTP 200):
```json
{
  "decision": "allow" | "deny" | "ask",
  "reason": "<text>" | null,
  "rag_rules": "<formatted text>",
  "rag_meta": {"rule_ids": [...], "tokens": <int>}
}
```

### GET /dashboard (1166-1181)

Response class `HTMLResponse`. Returns `render_dashboard()` from `writ.dashboard`. Auto-refreshes every 60s.

The dashboard reads the friction log via `resolve_log_path()` (env `WRIT_FRICTION_LOG` or `./workflow-friction.log`), parses via `parse_log()` to `FrictionEvent` list, renders sections via `_table()`/`_section()`:
- Live counts (total events, distinct sessions, top 10 event types).
- Rule effectiveness (last 30d, top 10).
- Skill usage (last 60d, top 10).
- Playbook compliance (last 30d, top 10).
- Graduation candidates (top 10).
- Trim candidates (last 90d, top 20).
- Quality-judge false positives (last 30d, top 10).

## Module-level state (server.py:86-92)

```python
_pipeline: RetrievalPipeline | None = None
_db: Neo4jConnection | None = None
_startup_time: datetime | None = None
_llm_client: LlmAnalyzer | None = None
_instrumentation: Instrumentation | None = None
```

## Internal-call summary

| Endpoint | Pipeline | DB / Cypher | writ_session | Other |
|---|---|---|---|---|
| `/query` | `query()` | — | — | — |
| `/analyze` | yes (via `run_analysis`) | — | — | `LlmAnalyzer`, `Instrumentation` |
| `/rule/{id}` | — | `get_rule`, `traverse_neighbors` | — | — |
| `/propose` | yes | yes | — | `writ.gate.propose_rule`, `DEFAULT_DB_PATH` |
| `/feedback` | — | `increment_positive/negative` | — | — |
| `/conflicts` | — | direct Cypher | — | — |
| `/health` | (state check only) | `count_rules`, mandatory count Cypher | — | — |
| `/session/*` | — | — | most | — |
| `/always-on` | — | direct Cypher (Rule, ForbiddenResponse, Skill, Playbook) | — | — |
| `/subagent-role/{name}` | — | direct Cypher (SubagentRole) | — | — |
| `/pre-write-check` | `query()` | (cache-only) | `_can_write_check`, `_read_cache`, `cmd_format`, `DEFAULT_SESSION_BUDGET` | — |
| `/dashboard` | — | — | — | `writ.dashboard.render_dashboard`, `writ.analysis.friction.*` |

## Background tasks / websockets / streaming

None. No `BackgroundTasks`, no `WebSocket`, no `StreamingResponse`. Friction-log writes happen synchronously within handlers under `asyncio.to_thread`.

## Authentication / authorization

None. Server is unauthenticated and binds to localhost by default.

## Error response format

- Pydantic validation errors → FastAPI 422 (default).
- Logical errors / missing state → HTTP **200** with `{"error": "<msg>"}` body.
- DB failures within Cypher → raise → FastAPI default 500.

**Clients should check for an `error` key in 200 responses, not rely on status codes.**

## Dashboard module (writ/dashboard.py, 163 lines)

Public: `render_dashboard() -> str`. Constants: `REFRESH_SECONDS = 60`. Helpers: `_esc`, `_table(headers, rows)`, `_section(title, body)`, `_safe_load_events()`. Returns a complete `<!doctype html>` page with inline CSS, no JS framework.

## Files Read

- `writ/server.py` (1181 lines)
- `writ/__init__.py` (2 lines, version `0.1.0`)
- `writ/config.py` (73 lines)
- `writ/dashboard.py` (163 lines)

## Cross-References Noted

- `writ.analysis.AnalyzeRequest`, `AnalyzeResponse` — `/analyze` schemas.
- `writ.analysis.analyzer.run_analysis`.
- `writ.analysis.friction.*` — `log_friction_event`, `parse_log`, `resolve_log_path`, `aggregate_by_event`, `analyze_rule_effectiveness`, `analyze_skill_usage`, `analyze_playbook_compliance`, `analyze_graduation_candidates`, `analyze_trim_candidates`, `analyze_quality_judge_false_positives`, `FrictionEvent`.
- `writ.analysis.instrumentation.Instrumentation`.
- `writ.analysis.llm.LlmAnalyzer`.
- `writ.graph.db.Neo4jConnection` — multiple methods.
- `writ.retrieval.pipeline.RetrievalPipeline`, `build_pipeline`.
- `writ.gate.propose_rule`.
- `writ.origin_context.DEFAULT_DB_PATH`.
- `bin/lib/writ-session.py` (loaded via `importlib`): `_read_cache`, `_write_cache`, `_can_write_check`, `cmd_format`, `cmd_detect_compaction`, `cmd_clear_rules_for_compaction`, `cmd_reset_after_compaction`, `DEFAULT_SESSION_BUDGET`.
