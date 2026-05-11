# Changelog

All notable changes to Writ are documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
