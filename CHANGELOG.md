# Changelog

All notable changes to Writ are documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-05-11

Plugin-distribution release. Writ is now installable as a Claude Code plugin published through a same-repo marketplace. The standalone skill install path at `~/.claude/skills/writ/` remains supported; behavior under that path is byte-identical to v1.0.0.

### Breaking

- Install path changes from a manual standalone skill checkout to a Claude Code plugin: `claude plugin marketplace add infinri/Writ` followed by `claude plugin install writ@writ`. The standalone path still works, but it is no longer the recommended install model.
- `.claude-plugin/plugin.json` was rewritten to conform to the official plugin schema. The previously declared `permissions`, `defaultEnabled`, and `lifecycle` fields were never honored by Claude Code and have been dropped. The new manifest uses only spec-compliant fields.

### Added

- `.claude-plugin/marketplace.json` declaring a same-repo, single-plugin marketplace catalog (`name: writ`, owner `infinri`, plugin source `./`).
- `hooks/hooks.json` plugin auto-discovery manifest covering all 32 hook event registrations using `${CLAUDE_PLUGIN_ROOT}` paths so the plugin can be upgraded without rewiring hooks.
- `hooks/scripts/session-start-bootstrap.sh`, a SessionStart probe that detects venv/Neo4j/daemon state on fresh plugin installs, prints actionable setup instructions when prerequisites are missing, and launches `writ serve` in the background when everything is in place. Always exits 0; never blocks the session.
- `scripts/bootstrap-plugin.sh`, the plugin-aware one-time setup script. Creates the venv outside the plugin cache dir so it survives plugin upgrades, brings up Neo4j, ingests the rule bible, and starts the daemon. Idempotent.
- `templates/settings.README.md` documenting the two install paths (plugin auto-discovery via `hooks/hooks.json` versus legacy standalone via `templates/settings.json` rendered into `~/.claude/settings.json`).
- `docs/plugin-validation.md`, a maintainer reference for validating a Writ release (static `claude plugin validate`, pytest skeleton, fresh-install smoke test, rollback procedure).

### Changed

- `.claude-plugin/plugin.json` now declares `name`, `version: "2.0.0"`, `description`, `author`, `homepage`, `repository`, `license`, `keywords`, plus the four component-path fields (`skills`, `commands`, `agents`, `hooks`) the plugin installer reads to auto-register the in-repo components.
- Plugin-mode venv lives at `${CLAUDE_PLUGIN_DATA:-$HOME/.cache/writ}/.venv`, and the package is installed there via `pip install -e ${CLAUDE_PLUGIN_ROOT}`. Editable installs let plugin upgrades that rewrite the cache dir keep working without a venv rebuild. Standalone installs continue to use `${WRIT_DIR}/.venv`.
- `scripts/ensure-server.sh`, `scripts/stop-server.sh`, and `.claude/hooks/writ-rag-inject.sh` learned dual-mode `${CLAUDE_PLUGIN_ROOT}` branches. When the env var is set by Claude Code, `WRIT_DIR` and the venv path resolve against the plugin install; when unset, the original `dirname` walk runs. Standalone behavior is byte-identical.
- `pyproject.toml`, `SKILL.md` frontmatter, and the marketplace/plugin manifests all declare version `2.0.0`.

### Deprecated

- `templates/settings.json` for plugin installs. The plugin auto-discovers hooks via `hooks/hooks.json`; the rendered template is no longer the source of truth for plugin-mode sessions. The file is still required for the standalone install path and will be removed only after the official Anthropic marketplace submission lands.

### Upgrade path

See the README section "Upgrading from standalone v1.0.0" for the four-step migration (stop the standalone daemon, drop the symlinks, remove the rendered settings block, install the plugin). The Neo4j named volume `writ-neo4j-data` is shared between modes, so the rule corpus survives the migration.

## [1.0.0] - 2026-05-10

First production release. Writ ships as a Claude Code harness with two co-equal layers (hybrid-RAG knowledge service plus session-aware enforcement) over a Neo4j-backed knowledge graph.

### Released

**Knowledge layer (the librarian).** FastAPI service on `localhost:8765` running a five-stage hybrid retrieval pipeline:
- Stage 1: Domain filter (sub-millisecond, post-filter on candidate set).
- Stage 2: BM25 keyword (Tantivy, in-memory; trigger-field boost 2.0x, body 0.5x).
- Stage 3: ANN vector (hnswlib over ONNX `all-MiniLM-L6-v2` embeddings, LRU cache 1024, HNSW persistence with corpus-hash invalidation).
- Stage 4: Graph traversal (pre-computed adjacency cache; built once at startup, O(1) lookup).
- Stage 5: Two-pass ranking (reciprocal-rank fusion + weighted linear combination over BM25, vector, severity, confidence, graph proximity, bundle cohesion; sticky tiebreak for prompt-cache stability).

Live latency at the 276-rule corpus: **0.590 ms p95 end-to-end** (17x headroom on the 10 ms budget). Synthetic scale curve holds at 0.557 ms p95 through 10K rules with 726x context reduction vs whole-corpus stuffing.

**Enforcement layer (the process keeper).** 30 hook scripts under `.claude/hooks/`, wired via `templates/settings.json`, plus a 2,090-line session state machine in `bin/lib/writ-session.py`. Four-mode system (Conversation, Debug, Review, Work) with two Work-mode gates (`phase-a` plan approval, `test-skeletons` test approval). Approval requires a one-time token written by the actual user-typed approval path; agent self-approval via raw bash is structurally blocked.

**Public rulebook (220 rules across 12 domains).** Security, Clean Code, DRY, SOLID, Architecture, Testing, Error Handling, Performance & Caching, Scaling, API Design, Process & Lifecycle, Documentation. Inventory in `out-of-the-box-rules.md`. Live corpus extends this with Writ-specific rules (ENF-PROC-*, FW-M2-*, PHP-*, PY-*, META-*) for a total of 276 rules / 30 mandatory.

**Static-analysis backing for mandatory rules.** Six cross-language regex analyzers in `bin/run-analysis.sh` enforce the 19 public-rulebook mandatory rules:
- `analyze_security_injection`: SQL injection, XSS, command injection, SSRF, deserialization, CSRF.
- `analyze_security_auth_authz`: weak password hashes, non-CSPRNG tokens, mass assignment, missing route auth, unvalidated request body, file-upload sinks.
- `analyze_security_crypto_headers`: hardcoded secrets (Stripe, AWS, GitHub, PEM), AES ECB, weak RNG in crypto context, `verify=False`.
- `analyze_security_data_protection`: PII identifiers in logger calls.
- `analyze_performance_n_plus_one`: loop-body DB calls with the loop variable.
- `analyze_scaling_stateless`: module-level user/session globals.

**AI rule proposal with structural gate.** `POST /propose` runs five checks (schema validation, mechanical-enforcement requirement for mandatory rules, specificity against a 10-pattern vague-language blocklist, redundancy/novelty thresholds at 0.95/0.85 cosine, conflict detection). Accepted rules enter as `authority: ai-provisional`, `confidence: speculative`.

**Frequency-driven graduation.** Stop-hook auto-feedback correlates loaded rules with static-analysis pass/fail and posts to `/feedback`. Graduation at n=50 and ratio>=0.75 substitutes the empirical ratio for the static confidence weight at query time.

**Sub-agent isolation.** Two flags compose cleanly: `is_subagent` (set on SubagentStart, bypasses gates and budget skips) and `is_orchestrator` (set on `mode set work --orchestrator`, suppresses broad RAG injection on the master and emits a compact status line instead).

### Architecture invariants

- **Pre-computation philosophy.** Tantivy index, hnswlib index, ONNX model, adjacency cache, and abstraction summaries are all built at startup from Neo4j and served from memory. Nothing is computed at query time that could have been computed earlier.
- **Mandatory-vs-retrieved structural split.** Mandatory rules are excluded from BM25 and the vector store at index-build time. They are loaded out-of-band by hooks with their own 5,000-token budget cap. No change to ranking weights, embedding model, or graph traversal can cause a mandatory rule to disappear from agent context.
- **Authority preference.** Human-authored rules outrank AI-authored rules at equal relevance (hard rerank within a configurable score band).
- **Sticky rule ordering.** Within a 0.02 score band, the ranker stabilizes injection order from `last_injected_rule_ids` for prompt-cache stability across turns.

### Verification (cited from the v1 release commit)

- 1,441 tests pass, 15 skipped, 0 failed.
- 12 contractual benchmark targets pass.
- Live service: 276 rules, 30 mandatory, index state warm.
- MRR@5 (ambiguous, n=19): 0.4886 (floor 0.45).
- Hit rate (Phase 6 ground-truth corpus, n=165): 0.7636 (floor 0.75).
- Methodology MRR@5 (n=40): 0.8583 (unchanged from Phase-0 baseline).

### Documentation

`README.md`, `HANDBOOK.md`, `PROMOTIONAL-BRIEF.md`, `SCALE_BENCHMARK_RESULTS.md`, `SKILL.md`, `CONTRIBUTING.md`, plus `out-of-the-box-rules.md` for the public rule inventory. Detailed codebase deep-dives in `docs/extraction/01` through `docs/extraction/12`. Install instructions in `docs/install-writ.md`. Monthly review template in `docs/monthly-reviews/TEMPLATE.md`. Historical pressure-run records preserved in `docs/pressure-runs/`.

### Known limitations

- Retrieval-quality floors were lowered during the Phase 1-5 public-rulebook expansion (MRR@5 from 0.78 to 0.45, hit-rate from 0.90 to 0.75) as the ambiguous-evaluation set held constant at 19 queries while the corpus grew 3.8x. The Phase 6 plan in the roadmap is to regenerate the ground-truth corpus and raise the floors back up.
- `POST /pre-write-check` still emits a `[ENF-GATE-FINAL]` deny string when the path contains `"COMPLETE"`, while `ENF-GATE-FINAL` itself was removed from the corpus during the 2026-05-10 cleanup. Known drift in `writ/server.py:1075-1083`, not load-bearing.
- The synthetic scale benchmark restores only Rule nodes; do not regenerate the curve without first re-exporting and re-importing the methodology corpus.
