# 09 — Configuration and Deployment

## A. `writ.toml` — Service Configuration

### `[source]`
```toml
[source]
canonical = "neo4j"
exported_view = "bible/"
```
Read by `writ/export.py` and ingest pipeline. ARCH-SSOT-001.

### `[service]`
```toml
[service]
host = "localhost"
port = 8765
timeout_ms = 50
log_level = "INFO"
```
Read by `writ/server.py` and bash hooks. `timeout_ms = 50` is the per-request budget.

### `[neo4j]`
```toml
[neo4j]
uri = "bolt://localhost:7687"
user = "neo4j"
password = "writdevpass"
database = "neo4j"
```

### `[embedding]`
```toml
[embedding]
model = "all-MiniLM-L6-v2"
dimensions = 384
```

### `[vector]` and `[vector.qdrant]`
```toml
[vector]
backend = "hnswlib"
ef_construction = 200
ef_search = 50
M = 16

[vector.qdrant]
url = "http://localhost:6333"
collection = "writ_rules"
```
Qdrant config inert until backend switches.

### `[hnsw]`
Reserved section; `writ/config.py:get_hnsw_cache_dir()` expands `~`.

### `[tantivy]`
```toml
[tantivy]
fields = ["trigger", "statement", "tags"]
```

### `[ranking]`
```toml
[ranking]
w_bm25 = 0.198
w_vector = 0.594
w_severity = 0.099
w_confidence = 0.099
w_graph = 0.01

[ranking.severity_values]
critical = 1.0
high = 0.75
medium = 0.5
low = 0.25

[ranking.confidence_values]
battle-tested = 1.0
production-validated = 0.8
peer-reviewed = 0.6
speculative = 0.3
```

### `[context_budget]`
```toml
[context_budget]
summary_threshold = 2000
standard_threshold = 8000
```

### `[ingestion]`
```toml
[ingestion]
bible_dir = "bible/"
auto_export = true
```

### `[validation]`
```toml
[validation]
query_rule_ratio_warning = 10
staleness_default_days = 365
```

### `[authority]`
```toml
[authority]
preference_threshold = 0.0749
ai_provisional_confidence_ceiling = "speculative"
ai_promoted_confidence_ceiling = "peer-reviewed"
```

### `[gate]`
```toml
[gate]
novelty_threshold = 0.85
redundancy_threshold = 0.95
```

### `[review]`
```toml
[review]
unreviewed_warning_percentage = 0.10
unreviewed_warning_floor = 5
```

### `[frequency]`
```toml
[frequency]
graduation_threshold = 50
graduation_ratio_minimum = 0.75
zero_frequency_window_days = 90
```

### `[origin_context]`
```toml
[origin_context]
db_path = "~/.cache/writ/origin_context.db"
```

## B. `pyproject.toml` — Build / Package Metadata

### `[project]`
| Key | Value |
|---|---|
| `name` | `writ` |
| `version` | `0.1.0` |
| `description` | `Hybrid RAG knowledge retrieval service for AI coding rule enforcement` |
| `requires-python` | `>=3.11` |
| `license` | `MIT` |
| `license-files` | `["LICENSE"]` |
| `authors` | `Lucio Saldivar` |

### Runtime dependencies (production)
| Package | Version pin | Purpose |
|---|---|---|
| `fastapi` | `>=0.115,<1` | HTTP API framework |
| `uvicorn` | `>=0.32,<1` | ASGI server for `writ serve` |
| `neo4j` | `>=5.0,<6` | Bolt driver for graph |
| `tantivy` | `>=0.22,<1` | Rust BM25 index |
| `sentence-transformers` | `>=3.3,<4` | Embeddings (all-MiniLM-L6-v2) |
| `hnswlib` | `>=0.8,<1` | ANN vector index |
| `httpx` | `>=0.27,<1` | Async HTTP client (hooks → server) |
| `pydantic` | `>=2.9,<3` | Schemas |
| `typer` | `>=0.13,<1` | CLI framework |
| `rich` | `>=13,<14` | Terminal output |

### `[project.optional-dependencies]`
**`dev`**: pytest>=8,<9, pytest-benchmark>=4,<5, pytest-asyncio>=0.23,<1, mypy>=1.11,<2, ruff>=0.6,<1.
**`benchmark`**: pytest>=8,<9, pytest-benchmark>=4,<5, memory-profiler>=0.61,<1.

### `[project.scripts]`
```toml
writ = "writ.cli:app"
```

### `[tool.setuptools.packages.find]`
```toml
include = ["writ*"]
```

### `[build-system]`
```toml
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
```

### Notable absences
No `[tool.ruff]`, `[tool.black]`, `[tool.mypy]`, or `[tool.pytest.ini_options]` sections.

## C. `.claude-plugin/plugin.json` — Plugin Manifest

```json
{
  "name": "writ",
  "version": "2.0.0",
  "description": "Hybrid RAG rule retrieval + enforcement layer. Injects relevant coding rules via a 5-stage pipeline (BM25 + vector + graph traversal + RRF ranking) and enforces mode-based workflow gates.",
  "permissions": ["read"],
  "defaultEnabled": true,
  "lifecycle": {
    "Init": ["./scripts/ensure-server.sh"],
    "Shutdown": ["./scripts/stop-server.sh"]
  }
}
```

Plugin version `2.0.0` is distinct from `pyproject.toml`'s package version `0.1.0`.

## D. `docker-compose.yml`

Single service `neo4j`:

| Setting | Value |
|---|---|
| Image | `neo4j:5` |
| Container name | `writ-neo4j` |
| Restart | `unless-stopped` |
| Port `7474:7474` | HTTP browser UI |
| Port `7687:7687` | Bolt protocol |
| Env `NEO4J_AUTH` | `neo4j/writdevpass` |
| Env `NEO4J_PLUGINS` | `[]` (no APOC) |
| Volume | `writ-neo4j-data:/data` |

Healthcheck:
```yaml
test: ["CMD-SHELL", "cypher-shell -u neo4j -p writdevpass 'RETURN 1' || exit 1"]
interval: 10s
timeout: 5s
retries: 5
start_period: 30s
```

## E. `Makefile`

```makefile
.PHONY: test bench check

test:
	python3 -m pytest tests/ -x -q

bench:
	python3 -m pytest benchmarks/bench_targets.py -x -q

check: test bench
	@echo "All checks passed."
```

`.pre-commit-config.yaml` runs `make bench` on `pre-push` stage. No formatting/lint hooks.

`.gitignore` highlights: `__pycache__/`, `.venv/`, runtime artifacts (`workflow-friction.log`, `.claude/gates/`, `.friction-snapshot`, `plan.md`, `capabilities.md`).

## F. Scripts (12 files)

### `scripts/bootstrap.sh` (206 lines)
End-to-end machine setup. Idempotent. Constants: `NEO4J_WAIT_SECONDS=60`, `DAEMON_WAIT_SECONDS=10`, `MIN_PYTHON_MAJOR=3`, `MIN_PYTHON_MINOR=11`.

Sequence: prereq checks → Python ≥3.11 → docker info → venv → `pip install -e .` → `install-harness-config.sh` → symlink rules+agents → `docker compose up -d neo4j` (poll bolt port up to 60s) → `writ import-markdown` → `writ serve` (poll /health up to 10s) → ready banner.

### `scripts/demote_mandatory_rules.py` (111 lines)
Phase 1 audit. Flips `mandatory: true → false` on rules listed in `docs/mandatory-rule-audit.md`. Final verification counts remaining `mandatory=true` rules with NULL `mechanical_enforcement_path`; non-empty → exit 1 (Phase 2 blocker).

### `scripts/ensure-server.sh` (74 lines)
Plugin-Init lifecycle hook. Brings up Neo4j and Writ daemon if absent. Non-fatal. Polls `localhost:7687` (10s) and `/health` (5s).

### `scripts/export_onnx.py` (66 lines)
Exports `sentence-transformers/all-MiniLM-L6-v2` to ONNX (HuggingFace `optimum`, optimization level O2 fused attention). Default output: `~/.cache/writ/models/onnx`. Requires `optimum` + `transformers` (not in core deps).

### `scripts/export_subagent_roles.py` (119 lines)
Inverse of ingest. Exports `SubagentRole` nodes from Neo4j to `.claude/agents/*.md`. Cypher fetches all SubagentRole nodes; output is YAML front-matter + `prompt_template` body. `--check` mode exits 1 if files drift from graph.

### `scripts/friction-log-delta.py` (112 lines)
Snapshot/delta tooling. State file `.friction-snapshot` containing `<offset>:<sha1-fingerprint>`. Detects log rotation: either `current_size < offset` or fingerprint mismatch.

### `scripts/ingest_subagent_roles.py` (143 lines)
Forward direction. Parses `.claude/agents/*.md`, MERGEs `SubagentRole` nodes. role_id = `ROL-{NAME}-001` (uppercase, `WRIT-` prefix stripped). Hardcoded `DISPATCHED_BY` map.

### `scripts/install-harness-config.sh` (92 lines)
Renders `templates/settings.json` and `templates/CLAUDE.md` with `envsubst '$HOME'` substitution; installs into `~/.claude/`. Idempotent (diff-q skip + .bak.{UTC-timestamp} backup).

### `scripts/install-user-commands.sh` (47 lines)
Copies `templates/commands/*.md` into `~/.claude/commands/`. Always exits 0.

### `scripts/migrate.py` (255 lines)
One-time migration of Markdown rules → Neo4j. Supports both rule corpus and methodology fixtures. Calls `db.apply_constraints()`, then for each parsed rule: `db.create_rule(clean)`. Methodology nodes routed via `db.create_methodology_node`. Filters dangling edge endpoints. Idempotent (MERGE).

### `scripts/populate_mechanical_paths.py` (121 lines)
Sets `mechanical_enforcement_path` on the 21 has-path + 2 could-have-path mandatory rules (Phase 2 release blocker). Hardcoded `PATHS: dict[str, str]`.

### `scripts/profile_hotpath.py` (67 lines)
Profiles retrieval pipeline with `pyinstrument` (100 queries: 10 fixed × 10 iterations).

### `scripts/stop-server.sh` (31 lines)
Plugin-Shutdown lifecycle hook. `lsof -ti :8765` → SIGTERM (poll 2s) → SIGKILL. Does NOT stop Neo4j.

## G. `writ/export.py` — Markdown Export (192 lines)

### Module constants
- `EXPORT_TIMESTAMP_FILE = ".export_timestamp"`
- `SECTION_ORDER = ("trigger", "statement", "violation", "pass_example", "enforcement", "rationale")`
- `SECTION_HEADERS` — `pass_example → "### Pass"`
- `GRAPH_ONLY_FIELDS = {"mandatory", "confidence", "evidence", "staleness_window", "last_validated"}` — re-derived on re-ingest, never written
- `METADATA_FIELDS = ("domain", "severity", "scope")` — written as `**Bold**:` lines

### `rule_to_markdown(rule: dict) -> str`
Markers (`<!-- RULE START: {rule_id} -->`/`<!-- RULE END: {rule_id} -->`) match `ingest.py:RULE_START_PATTERN`.

### `group_rules_by_file(rules, bible_dir) -> dict[Path, list[dict]]`
Preserves existing file structure; falls back to domain-derived path.

### `export_rules_to_markdown(db, output_dir, bible_dir=None) -> dict[str, int]` (async)
The main entry point. Pulls `db.get_all_rules()`, groups by file, writes each, calls `write_export_timestamp`. Idempotent (deterministic sort + group keys).

### Timestamp helpers
- `write_export_timestamp(output_dir)` — JSON `{"exported_at": <ISO-8601 UTC>}`.
- `read_export_timestamp(output_dir) -> datetime | None`.
- `check_export_staleness(output_dir, last_graph_write) -> bool` (UTC-normalized).

## H. `writ/analysis/*` — Analysis Pipeline

This is the layer behind `/analyze` HTTP endpoint and `validate-rules.sh` hook.

### H.1 `analysis/__init__.py` (41 lines) — Pydantic schemas

**`AnalyzeRequest`**: `code: str`, `file_path: str`, `phase: str` (`"planning"|"code_generation"|"testing"|"review"`), `context: str`.

**`Finding`**: `rule_id: str`, `source: str` (`"pattern"|"llm"`), `status: str` (`"violated"|"pass"|"uncertain"`), `line: int | None`, `confidence: str | None` (`"high"|"medium"|"low"|None`), `evidence: str = ""`, `suggestion: str = ""`.

**`AnalyzeResponse`**: `verdict: str` (`"pass"|"fail"|"warn"`), `findings: list[Finding]`, `rules_checked: list[str]`, `analysis_method: str = "pattern"` (`"pattern"|"llm"|"hybrid"|"calibration"`), `retrieval_scores: dict[str, float]`, `summary: str`.

### H.2 `analysis/analyzer.py` (159 lines) — Orchestrator

`async def run_analysis(code, file_path, phase, context, pipeline, llm_client, instrumentation) -> AnalyzeResponse`:

1. Retrieve rules — `pipeline.query(query_text=f"{context} {file_path}")`. Empty → `pass`.
2. Pattern match — `extract_violations(rules)` → `scan_code(code, patterns)`.
3. Decide escalation — `instrumentation.get_mode()` and `should_escalate(...)`.
4. LLM call (conditional):
   - Calibration mode: always; `analysis_method = "calibration"`.
   - Production with escalation: `analysis_method = "hybrid"` if pattern findings, else `"llm"`.
   - Capped at `MAX_RULES_PER_CALL = 10` rules sorted by retrieval score.
5. Build verdict + summary.

`_compute_verdict(findings, escalation_failed) -> str`:
- No findings → `"pass"`.
- Any `violated`: if all violations are pattern source with medium/low confidence AND escalation failed → `"warn"`; else `"fail"`.
- Any `uncertain` → `"warn"`. Else `"pass"`.

### H.3 `analysis/friction.py` (810 lines) — Friction log analytics

The largest analysis module. Powers `writ analyze-friction` CLI and `/dashboard`.

Module-level: `__all__` lists `load_events`, `summarize`, `rotate_if_needed`, `format_report`, `FrictionEvent`, `parse_log`, `aggregate_by_rule`, `aggregate_by_event`, `log_friction_event`, `resolve_log_path`, the six Phase 5 result models, the six analyzers.

Constants: `DEFAULT_ROTATION_THRESHOLD_BYTES = 5 * 1024 * 1024`, `_STUCK_WINDOW = timedelta(minutes=30)`.

`FrictionEvent` (Pydantic) with `extra="allow"`. Declared fields: `ts, session, event, mode, rule_id, gate`.

Path resolution: `resolve_log_path(explicit=None) -> Path` — order: explicit arg → `WRIT_FRICTION_LOG` env → `./workflow-friction.log`.

`log_friction_event(session_id, mode, event, log_path=None, **fields)` — fire-and-forget JSONL append. Server-side equivalent of bash `bin/lib/common.sh:log_friction_event`.

Parsers: `parse_log` (typed), `aggregate_by_rule`, `aggregate_by_event`, `load_events` (untyped), `_filter_since` (UTC cutoff), `_percentile`.

`summarize(events, top=10, since_days=None) -> dict` aggregates: total_events, event_counts, hook_p95_ms, top_rules, pre_write_decisions, subagent_completions, sessions_with_denials, write_failures, phase_transitions, approval_matches.

`format_report(summary) -> str` renders to fixed-column text.

`rotate_if_needed(log_path, threshold_bytes=5MB) -> bool` renames to `.1`.

#### Phase 5 result models (Pydantic)
- `RuleEffectivenessRow`: rule_id, activations, stuck_denials, denial_stick_rate, rationalizations.
- `SkillUsageRow`: skill_id, loads, completions, completion_rate.
- `PlaybookComplianceRow`: playbook_id, runs, compliant_runs, common_skip_points: list[str].
- `GraduationCandidate`: rule_id, days_stable, current_tier, recommended_tier, denial_stick_rate.
- `TrimCandidate`: entity_id, entity_type ("rule"|"skill"), last_activation, activations_in_window, recommendation.
- `QualityJudgeOverride`: rubric, total_fails, overrides, override_rate.

#### Phase 5 analyzers
1. `analyze_rule_effectiveness(events, since_days=30, top=50)` — per rule: activations + stuck_denials (gate_denial unresolved within 30min same-session) + rationalizations (`repeated_denial`).
2. `analyze_skill_usage(events, since_days=60, top=50)` — sessions where loaded vs final `playbook_step_complete`.
3. `analyze_playbook_compliance(events, since_days=30, top=50)` — runs, compliant runs, common skip points.
4. `analyze_graduation_candidates` — filters: `activations >= 5`, `denial_stick_rate >= 0.85`, `rationalizations < 5`.
5. `analyze_trim_candidates(events, since_days=90, rule_min_activations=5, skill_min_loads=2, top=100)`.
6. `analyze_quality_judge_false_positives(events, since_days=30, top=50)` — per rubric override rates.

### H.4 `analysis/instrumentation.py` (115 lines) — Calibration / escalation

Constants: `CALIBRATION_THRESHOLD = 100`, `RELEVANCE_SCORE_THRESHOLD = 0.6`, `DEFAULT_LOG_PATH = "/tmp/writ-calibration.jsonl"`.

`Instrumentation` class:
- `__init__(log_path=DEFAULT_LOG_PATH)` — counts existing JSONL lines.
- `get_mode() -> str` — `"calibration"` if counter < 100 else `"production"`.
- `should_escalate(matches, retrieval_scores) -> bool`:
  - Calibration: always True (paired logging).
  - Production: True if any match `confidence in ("medium", "low")`.
  - Production no matches: True if any retrieval score > 0.6.
- `log_calibration(...)` — JSONL with both verdicts, agreement bool.

### H.5 `analysis/llm.py` (262 lines) — LLM client (Anthropic)

Constants: `MAX_RULES_PER_CALL = 10`, `DEFAULT_MODEL = "claude-haiku-4-5-20251001"`, `PLANNING_MODEL = "claude-sonnet-4-6-20250514"`, `LLM_TIMEOUT = 10.0`.

Two prompt templates: with-findings (verify+augment) and no-findings (fresh analysis). Both ask for JSON array of `{rule_id, status, line, evidence, suggestion}`.

Helpers:
- `_format_rules(rules)` — caps at 10; `[RULE-ID]` with WHEN/RULE/VIOLATION/CORRECT.
- `_format_pattern_findings(findings)`.
- `build_prompt(code, file_path, phase, rules, pattern_findings)` — caps `code` at 8000 chars.
- `select_model(phase, config_model=None)` — config_model → planning Sonnet → otherwise Haiku.
- `parse_llm_response(raw)` — strips fences, parses JSON, validates list.
- `findings_from_llm_response(raw_findings)`.

`LlmAnalyzer` class:
- `_get_client()` — lazy `import anthropic; AsyncAnthropic(api_key, timeout)`. ImportError → returns None + warning.
- `async analyze(code, rules, phase, file_path="", pattern_findings=None) -> list[Finding]`:
  - Empty rules → `[]`.
  - No SDK → uncertain Findings (capped at 10).
  - `client.messages.create(model, max_tokens=2000, temperature=0)` (deterministic).
  - On any exception → uncertain Finding per rule.

### H.6 `analysis/patterns.py` (186 lines) — Regex pattern extraction

Module-level: `_SKIP_METHODS` (frozenset of generic names like `get`, `set`, `create`, `init`); `_COMMENT_PREFIXES = ("//", "#")`; `ViolationPattern` dataclass (frozen) with `rule_id, pattern, label`.

`extract_violations(rules) -> list[ViolationPattern]` — per rule.violation, four pattern types:
1. Method calls — `(?:->|::)(\w+)\s*\(` → `(?:->|::){call}\s*\(`.
2. Instantiations — `\bnew\s+(\w+)\s*\(` → `\bnew\s+{cls}\s*\(`.
3. Magento Factory chain — if violation contains `"Factory->create()->load"` or `"Factory->create()->loadBy"`.
4. Hardcoded secrets — `sk_live_`, `AKIA`, or `password\s*=`.

`_assess_confidence(...)` — substring/comment/string-literal context → `"low"|"medium"|"high"`.

`scan_code(code, patterns) -> list[Finding]` — per match: `Finding(source="pattern", status="violated", line, confidence, evidence)`.

## I. Startup Sequence

1. `pyproject.toml [project.scripts]` defines `writ = "writ.cli:app"`.
2. FastAPI lifespan: opens `Neo4jConnection`, `apply_constraints()`, `build_pipeline(db)`. Closes on shutdown.
3. Background invocation: `nohup writ serve > /tmp/writ-server.log 2>&1 &`. Polls `/health` (curl --connect-timeout 0.5).
4. Cold-start latency: ~0.6s at 80 rules. Budget: 5s in `ensure-server.sh` (50 × 100ms).

### Fallback: HTTP-first / subprocess-fallback (`_writ_session` pattern)
Bash hooks query the Writ server via httpx with `timeout_ms = 50`. On timeout/refusal/5xx, fallback to invoking `writ` CLI subcommand directly via subprocess.
- Hot path: ~10ms HTTP roundtrip.
- Cold path: ~300-700ms subprocess startup.
- Hooks never block — gate decisions degrade open with `[Writ] server unavailable` note.

## J. Files Read

| File | Lines |
|---|---|
| `writ/export.py` | 192 |
| `writ/analysis/__init__.py` | 41 |
| `writ/analysis/analyzer.py` | 159 |
| `writ/analysis/friction.py` | 810 |
| `writ/analysis/instrumentation.py` | 115 |
| `writ/analysis/llm.py` | 262 |
| `writ/analysis/patterns.py` | 186 |
| `writ.toml` | 89 |
| `pyproject.toml` | 46 |
| `.claude-plugin/plugin.json` | 11 |
| `docker-compose.yml` | 23 |
| `Makefile` | 10 |
| `.gitignore` | 48 |
| `.pre-commit-config.yaml` | 9 |
| `scripts/bootstrap.sh` | 206 |
| `scripts/demote_mandatory_rules.py` | 111 |
| `scripts/ensure-server.sh` | 74 |
| `scripts/export_onnx.py` | 66 |
| `scripts/export_subagent_roles.py` | 119 |
| `scripts/friction-log-delta.py` | 112 |
| `scripts/ingest_subagent_roles.py` | 143 |
| `scripts/install-harness-config.sh` | 92 |
| `scripts/install-user-commands.sh` | 47 |
| `scripts/migrate.py` | 255 |
| `scripts/populate_mechanical_paths.py` | 121 |
| `scripts/profile_hotpath.py` | 67 |
| `scripts/stop-server.sh` | 31 |
| **Total** | **3,445** |

## K. Cross-References Noted

- `writ.toml [neo4j]` ↔ `docker-compose.yml` — credentials must match. Migration scripts hardcode credentials at module scope rather than reading TOML.
- `pyproject.toml [project.scripts]` — every script ending in `nohup writ serve` depends on `pip install -e .`.
- `plugin.json:lifecycle` ↔ `scripts/ensure-server.sh`/`stop-server.sh`.
- `writ.toml [embedding]` ↔ `scripts/export_onnx.py` — both reference `all-MiniLM-L6-v2`.
- `writ.toml [ranking]` weights consumed by `writ/retrieval/ranking.py` — sum to 1.0.
- `writ/export.py:rule_to_markdown` ↔ `writ/graph/ingest.py:RULE_START_PATTERN` — round-trip invariant (INV-RT). `GRAPH_ONLY_FIELDS` excluded from export are re-derived.
- `writ/analysis/analyzer.py` ↔ `writ/retrieval/pipeline.py` — analyzer uses `pipeline.query(query_text=...)`.
- `writ/analysis/friction.py:resolve_log_path` ↔ `bin/lib/common.sh` — both honor `WRIT_FRICTION_LOG`.
- `writ/analysis/llm.py` model IDs: `claude-haiku-4-5-20251001` and `claude-sonnet-4-6-20250514` are pinned in code.
- `scripts/migrate.py` ↔ `tests/test_retrieval/conftest.py` — conftest calls migrate.py to restore methodology corpus after pipeline_db wipes shared graph (commit 2d7c028).
- `scripts/populate_mechanical_paths.py` runs AFTER `scripts/demote_mandatory_rules.py` — Phase 2 release-blocker chain.
- `scripts/ingest_subagent_roles.py` and `export_subagent_roles.py` — bidirectional sync of `.claude/agents/*.md` ↔ `SubagentRole` nodes.
- `Makefile bench` ↔ `.pre-commit-config.yaml stages: [pre-push]`.
