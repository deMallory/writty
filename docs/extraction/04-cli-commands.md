# 04 — CLI Commands (full extraction)

> **Refresh note (2026-05-10).** Command surface is unchanged. Line-number citations here come from the original extraction pass and may drift by a handful as the file accumulates fixes; the dispatch shape is stable.

Source: `writ/cli.py` (~1,063 lines). Framework: **Typer** (`typer.Typer`). Entry point: `writ.cli:app` (declared in `pyproject.toml [project.scripts]` as `writ = "writ.cli:app"`).

## App construction (cli.py:17-20)

```python
app = typer.Typer(
    name="writ",
    help="Hybrid RAG knowledge retrieval service for AI coding rule enforcement.",
)
```

`if __name__ == "__main__": app()` (cli.py:1062-1063). All commands are sync top-level functions; long-running operations are wrapped in `asyncio.run(_run())` per command.

## Constants (cli.py:13-15)

```python
DEFAULT_BIBLE_DIR = "bible/"
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8765
```

## Commands

### `writ analyze-friction` (23-145)

Summarizes `workflow-friction.log`.

| Flag | Type | Default | Help |
|---|---|---|---|
| `--log` | `Path` | `Path("workflow-friction.log")` | Path to friction log |
| `--since` | `int` | `0` | Only events from last N days (0 = all) |
| `--top` | `int` | `10` | Top-N cap |
| `--rotate` | `bool` | `False` | Rotate log to .1 if > 5MB, then exit |
| `--json` | `bool` | `False` | Emit structured JSON |
| `--rule` | `str\|None` | `None` | Filter to a single rule_id |
| `--rule-effectiveness` | `bool` | `False` | Per-rule denial-stick-rate |
| `--skill-usage` | `bool` | `False` | Skill loads vs playbook completion |
| `--playbook-compliance` | `bool` | `False` | Per-playbook in-order compliance |
| `--graduation-candidates` | `bool` | `False` | Rules ready to graduate |
| `--trim-candidates` | `bool` | `False` | Rules/skills with low activation |
| `--quality-judge-false-positives` | `bool` | `False` | Per-rubric override rates |

Behavior:
- `--rotate`: calls `rotate_if_needed(log)`, prints result, returns.
- Six Phase 5 analyzer flags are mutually exclusive. >1 active → `Exit(2)`.
- Each Phase 5 flag dispatches to the matching `writ.analysis.friction.analyze_*` function. `since_days` defaults: rule-effectiveness=30, skill-usage=60, playbook-compliance=30, trim-candidates=90, quality-judge-fp=30 (graduation-candidates does not pass `since_days`).
- Else with `--json` or `--rule`: prints aggregate `{by_rule, by_event, total}` JSON or text.
- Default: `summarize(events, top, since_days)` + `format_report(...)`.

### `writ audit-session <session_id>` (148-335)

Per-session timeline + summary.

| Argument | Type | Required |
|---|---|---|
| `session_id` | `str` | yes |

| Flag | Type | Default |
|---|---|---|
| `--log` | `Path` | `Path("workflow-friction.log")` |
| `--json` | `bool` | `False` |

Aggregates: `event_counts`, `phase_transitions`, `rule_loads`, `skill_loads` (SKL-*), `playbook_loads` (PBK-*), `gate_denials`, `subagents`, `playbook_completions`, `mode_changes`, `tokens_by_source`, `always_on_injects`, `always_on_tokens`.

### `writ serve` (338-350)

Start FastAPI service via uvicorn.

| Flag | Type | Default |
|---|---|---|
| `--port` | `int` | `8765` |
| `--host` | `str` | `"localhost"` |

Calls `uvicorn.run(fastapi_app, host=host, port=port, log_level="info")`. Logs `"Starting Writ service on {host}:{port}"` and `"Pre-warming indexes..."`.

### `writ import-markdown [path]` (353-388)

| Argument | Type | Default |
|---|---|---|
| `path` | `Path` | `Path("bible/")` |

`Neo4jConnection(...)`, `discover_rule_files(path)`, `parse_rules_from_file`, `validate_parsed_rule`, `db.create_rule(clean)`. After ingest, **if `count > 0 and errors == 0`**, calls `export_rules_to_markdown(db, path)` — auto-export per Phase 7.

### `writ validate` (391-465)

| Flag | Type | Default |
|---|---|---|
| `--review-confidence` | `bool` | `False` |
| `--benchmark` | `bool` | `False` |

`IntegrityChecker(db._driver, db._database).run_all_checks()`. Sections printed: conflicts, orphans, stale, redundant, unreviewed, frequency_stale, graduation_flags. With `--review-confidence`: also `detect_confidence_defaults()`. `Exit(findings["exit_code"])`.

### `writ add` (468-590)

Interactive add-a-new-rule wizard.

`typer.prompt()` collects: `rule_id`, `domain`, `severity`, `scope`, `trigger`, `statement`, `violation`, `pass_example`, `enforcement`, `rationale`. `last_validated` set to today.

Flow:
1. `await check_id_collision(rule_id, db)`. On `RuleIdCollisionError`: print existing statement preview and `Exit(1)`.
2. `Rule(**rule_data)` schema-validate. Failure → `Exit(1)`.
3. Build pipeline + adjacency cache.
4. `check_redundancy(rule_data, pipeline)` (>= 0.95 cosine).
5. `suggest_relationships(rule_data, pipeline)`.
6. `await db.create_rule(rule_data)`.
7. For each suggestion, `typer.confirm`. Edge types: `["DEPENDS_ON", "SUPPLEMENTS", "CONFLICTS_WITH", "RELATED_TO"]`. `db.create_edge`.
8. Rebuild adjacency cache, run `check_conflicts`.
9. Auto-export to `bible/` via `export_rules_to_markdown(db, Path("bible/"))`.

### `writ edit <rule_id>` (593-681)

Interactive edit. If rule not found → `Exit(1)`. Prompts each field with current value as default. Validates via `Rule(**updated)`. `db.create_rule(updated)` (MERGE, idempotent per INV-7). Auto-exports.

### `writ export [output]` (684-700)

| Argument | Type | Default |
|---|---|---|
| `output` | `Path` | `Path("bible/")` |

`await export_rules_to_markdown(db, output)`. **Overwrites the output directory.**

### `writ compress` (703-754)

No flags. `db.get_all_rules()`, filters out mandatory. Loads `SentenceTransformer("all-MiniLM-L6-v2")`. Encodes `f"{trigger} {statement}"` into `np.float32`. Calls `evaluate_both(rule_ids, embeddings)` — runs HDBSCAN and k-means, picks one based on silhouette score. `generate_abstractions(chosen_result, domain_rules)`. `write_abstractions_to_graph(db, abstractions)`. Prints HDBSCAN/k-means cluster counts, silhouette, chosen method + reason, abstractions created, ungrouped count, average compression ratio.

### `writ role-prompt <role>` (757-797)

| Argument | Type | Required |
|---|---|---|
| `role` | `str` | yes |

Cypher (same as `/subagent-role/{name}`):
```cypher
MATCH (r:SubagentRole)
WHERE r.name = $name
   OR r.role_id = $name
   OR r.role_id = 'ROL-' + toUpper(replace($name, 'writ-', '')) + '-001'
RETURN r.role_id, r.name, r.prompt_template, r.model_preference
LIMIT 1
```
Output: `# {role_id}  (name=..., model=...)` + blank line + prompt template body.

### `writ migrate` (800-810)

No flags. Calls `writ.graph.methodology_ingest.ingest_path(Path('bible/'), db, only=None, dry_run=False)` in-process. Backward-compat shim for `writ import-markdown`. Exits with code 1 if any `IngestError`s are reported; 0 otherwise.

### `writ query <query_text>` (813-843)

| Argument | Type | Required |
|---|---|---|
| `query_text` | `str` | yes |

| Flag | Type | Default |
|---|---|---|
| `--domain` | `str\|None` | `None` |
| `--budget` | `int\|None` | `None` |

Builds **fresh** pipeline (not the warm one from `writ serve`). Calls `pipeline.query(query_text, domain, budget_tokens=budget)`. Prints `Mode: {mode} | Candidates: {total_candidates} | Latency: {latency_ms}ms` + numbered list with 100-char preview.

### `writ feedback <rule_id> <signal>` (846-873)

| Argument | Type |
|---|---|
| `rule_id` | `str` |
| `signal` | `str` |

`signal` must be `"positive"` or `"negative"`. **Direct DB call; does not go through the HTTP `/feedback` endpoint.**

### `writ propose` (876-935)

All required `typer.Option(...)` flags:
`--rule-id, --domain, --severity, --scope, --trigger, --statement, --violation, --pass-example, --enforcement, --rationale`. Optional: `--task-description` (default `""`).

`last_validated = today`. Builds pipeline. `await propose_rule(candidate, pipeline, db, origin_db_path=DEFAULT_DB_PATH, task_description=...)`. **Direct gate call; does not go through HTTP `/propose`.**

### `writ review [rule_id]` (938-1045)

| Argument | Type | Required |
|---|---|---|
| `rule_id` | `str\|None` | no |

| Flag | Type | Default |
|---|---|---|
| `--promote` | `bool` | `False` |
| `--reject` | `bool` | `False` |
| `--downweight` | `bool` | `False` |
| `--stats` | `bool` | `False` |

- `--stats`: `count_by_authority()` per-authority + total.
- No `rule_id`: `get_rules_by_authority("ai-provisional")`.
- With `rule_id`:
  - `--promote` (only on ai-provisional): `update_rule_authority(rule_id, "ai-promoted")` + `update_rule_confidence(rule_id, "peer-reviewed")`.
  - `--reject` (only on ai-provisional): `delete_rule(rule_id)`.
  - `--downweight`: `update_rule_confidence(rule_id, "speculative")`.
  - Default: prints rule fields + `OriginContextStore()` task/query/consulted/created_at.

### `writ status` (1048-1059)

Calls `httpx.get(f"http://localhost:8765/health", timeout=5.0)`, prints JSON. On `httpx.ConnectError`: prints `"Service not running. Start with: writ serve"` and `Exit(1)`. **The only CLI command that talks to the HTTP server.**

## Exit codes

| Code | When |
|---|---|
| 0 | Success |
| 1 | Generic failure: rule not found, validation error, ID collision, invalid signal, service down, wrong authority |
| 2 | `analyze-friction` mutually-exclusive flag conflict |
| `findings["exit_code"]` | `validate` propagates the integrity-checker code |
| `result.returncode` | `migrate` propagates the migrate-script code |

## Error formatting

- Plain text via `typer.echo(...)` (stdout) or `typer.echo(..., err=True)` (stderr).
- No structured error format. JSON output is opt-in only on `analyze-friction` and `audit-session`.
- DB connection failures bubble up as Python tracebacks (no graceful handler).

## Config resolution

The CLI uses `writ.config.get_neo4j_uri/user/password()` directly — these read `writ.toml` next to the package and fall back to hardcoded defaults (`bolt://localhost:7687`, `neo4j`, `writdevpass`).

**There are no environment-variable overrides in cli.py or config.py.** No `WRIT_NEO4J_*` envs are read. Config-file resolution is fixed to `<package_root>/writ.toml`.

The dashboard / friction module respects `WRIT_FRICTION_LOG` (via `resolve_log_path()`), but that is internal to `writ.analysis.friction`.

## Commands that bypass the HTTP API

All commands except `writ status` and `writ serve` open their own `Neo4jConnection` and (where needed) build their own `RetrievalPipeline`. This means:
- Running e.g. `writ query foo` while `writ serve` is up creates a second connection and re-warms a separate pipeline (no shared state).
- `writ feedback`, `writ propose`, `writ review` mutate the DB directly without going through `/feedback`, `/propose`, etc.

## Files Read

- `writ/cli.py` (1063 lines)
- `writ/__init__.py` (2 lines)
- `writ/config.py` (73 lines)
- `pyproject.toml` (line 38-39 only)

## Cross-References Noted

- `writ.analysis.friction.*` — load_events, summarize, format_report, rotate_if_needed, parse_log, aggregate_by_rule, aggregate_by_event, analyze_rule_effectiveness, analyze_skill_usage, analyze_playbook_compliance, analyze_graduation_candidates, analyze_trim_candidates, analyze_quality_judge_false_positives.
- `writ.authoring` — RuleIdCollisionError, check_conflicts, check_id_collision, check_redundancy, suggest_relationships.
- `writ.compression.abstractions.generate_abstractions, write_abstractions_to_graph`.
- `writ.compression.clusters.evaluate_both`.
- `writ.export.export_rules_to_markdown`.
- `writ.gate.propose_rule`.
- `writ.graph.db.Neo4jConnection` — many methods.
- `writ.graph.ingest.discover_rule_files, parse_rules_from_file, validate_parsed_rule`.
- `writ.graph.integrity.IntegrityChecker.run_all_checks, detect_confidence_defaults`.
- `writ.graph.schema.Rule`.
- `writ.origin_context.DEFAULT_DB_PATH, OriginContextStore`.
- `writ.retrieval.pipeline.build_pipeline`.
- `writ.retrieval.traversal.AdjacencyCache.build_from_db`.
- `writ.server.app` — imported by `writ serve`.
- `scripts/migrate.py` — thin shim (~71 lines) re-exporting `run_migration` / `run_methodology_migration` for backward compat; the canonical in-process path is `writ.graph.methodology_ingest.ingest_path` called by both `writ import-markdown` and `writ migrate`.
