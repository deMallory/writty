# Rulebook Audit — Live Graph vs Public Out-of-the-Box Target

**Source target:** `out-of-the-box-rules.md` (220 rules across 12 domains, 16 mandatory).
**Source live:** Neo4j graph as of 2026-05-10 (73 rules across 10 prefix groups, 11 mandatory).
**Goal:** identify what already exists, what needs to be modified, what still needs to be added, then implement.

## 1. Summary at a glance

| Domain (target) | Target rules | Already covered | Needs mod | Needs new |
|---|---:|---:|---:|---:|
| Security | 73 | 4 (SEC-UNI-001..004) + 1 partial (ENF-SEC-001) | 4 (rename / refactor) | ~64 |
| Clean Code | 25 | 4 (ARCH-FUNC-001, ARCH-CONST-001, ARCH-ERR-001, ARCH-COMP-001) | 4 (clarify wording) | ~21 |
| DRY | 8 | 2 (ARCH-DRY-001, ARCH-SSOT-001) | 2 | ~6 |
| SOLID | 12 | 3 (ARCH-DI-001, ARCH-EXT-001, ARCH-ORG-001) | 3 | ~9 |
| Architecture | 15 | 1 (ARCH-ORG-001 layer rule) | 0 | ~14 |
| Testing | 20 | 3 (TEST-ISO-001, TEST-INT-001, TEST-TDD-001) | 3 | ~17 |
| Error Handling | 12 | 3 (PHP-ERR-001/002, PHP-TRY-001 are PHP-specific) | 3 | ~10 |
| Performance & Caching | 15 | 5 (PERF-IO-001, PERF-BIGO-001, PERF-LAZY-001, PERF-OPT-001, PERF-QBUDGET-001) | 5 | ~10 |
| Scaling | 10 | 0 | 0 | 10 |
| API Design | 12 | 0 (some implicit overlap with FW-M2-RT-* but Magento-specific) | 0 | 12 |
| Process & Lifecycle | 10 | 7 (ENF-PROC-* rules: BRAIN, PLAN, SDD, TDD, VERIFY, WORKTREE, DEBUG) | 7 | ~3 |
| Documentation | 8 | 1 (ARCH-TYPE-001) | 1 | ~7 |
| **Total** | **220** | **~33** | **32** | **~183** |

(Counts are first-pass estimates. Final counts will be confirmed during per-rule mapping in §3.)

## 2. Live corpus inventory (73 rules)

| Prefix | Count | Notes |
|---|---:|---|
| ARCH | 10 | Architecture / SOLID-ish principles. Mostly maps to target Clean Code, SOLID, Architecture, DRY domains. |
| DB | 3 | SQL authoring style. Not in target rulebook (target SQL rules are in language-specific extensions). |
| ENF | 26 | Mix of mandatory v2 enforcement rules (PROC, GATE, POST) and workflow advisories. Most should stay as Writ-specific workflow rules; some (ENF-OPS, ENF-SEC, ENF-SYS) overlap with target domains. |
| FW | 12 | Magento 2 framework rules. Not in target (target is language/framework-agnostic). Maintainer's own bundle, retained as-is. |
| META | 2 | Skill-authoring meta-rules (META-AUTH-001/002). Writ-specific. Keep. |
| PERF | 5 | Maps cleanly to target Performance domain. |
| PHP | 4 | PHP-specific. Maintainer's bundle. Keep, tag as PHP extension. |
| PY | 4 | Python-specific. Maintainer's bundle. Keep, tag as Python extension. |
| SEC | 4 | Universal security rules. Maps to target Security domain (small subset). |
| TEST | 3 | Maps to target Testing domain. |

**Mandatory (11):** ENF-CTX-003, ENF-GATE-007, ENF-POST-003, ENF-POST-007, ENF-PROC-BRAIN-001, ENF-PROC-PLAN-001, ENF-PROC-SDD-001, ENF-PROC-TDD-001, ENF-PROC-VERIFY-001, ENF-PROC-WORKTREE-001, ENF-SEC-001.

The target rulebook proposes 16 mandatory; ours has 11. The two sets overlap on the workflow rules but the target adds universal security mandatories (SQL injection, XSS, CSRF, secret hardcoding, etc.) we have not yet structured.

## 3. Per-rule mapping (target → live)

### 3.1 Security (target 73; live ≈5 mapped)

#### 1A. Injection Prevention (target 17)

| Target | Live equivalent | Action |
|---|---|---|
| SEC-INJ-SQL-001 (parameterized queries, no concat) | DB-SQL-001 (named binds) | **MODIFY**: rename DB-SQL-001 → SEC-INJ-SQL-001, broaden statement from "named binds" to "parameterized queries; no concat or interpolation" |
| SEC-INJ-SQL-002 (ORM raw query bound params) | — | **NEW** |
| SEC-INJ-SQL-003 (stored procedure parameterized) | — | **NEW** |
| SEC-INJ-XSS-001 (framework escaping) | — | **NEW** |
| SEC-INJ-XSS-002 (no dangerouslySetInnerHTML, v-html) | — | **NEW** |
| SEC-INJ-XSS-003 (DOM manipulation prohibited with user data) | — | **NEW** |
| SEC-INJ-CMD-001 (subprocess argument lists, no shell=True) | — | **NEW** |
| SEC-INJ-CMD-002 (no exec/eval with dynamic strings) | — | **NEW** |
| SEC-INJ-PATH-001 (path traversal) | — | **NEW** |
| SEC-INJ-LDAP-001 | — | **NEW** |
| SEC-INJ-SSRF-001 | — | **NEW** |
| SEC-INJ-SSTI-001 | — | **NEW** |
| SEC-INJ-HEADER-001 (CRLF) | — | **NEW** |
| SEC-INJ-LOG-001 (log injection) | — | **NEW** |
| SEC-INJ-DESER-001 (no unsafe deserialization) | — | **NEW** |
| SEC-INJ-REDIR-001 (open redirect) | — | **NEW** |
| SEC-INJ-CSRF-001 | — | **NEW** |

**1A net: 1 modify, 16 new.** Mandatory candidates: SEC-INJ-SQL-001, SEC-INJ-XSS-001, SEC-INJ-CMD-001, SEC-INJ-DESER-001, SEC-INJ-SSRF-001, SEC-INJ-CSRF-001.

#### 1B. Authentication (target 10)

All 10 are **NEW**. Mandatory candidates: SEC-AUTH-HASH-001, SEC-AUTH-TOKEN-001.

#### 1C. Authorization (target 9)

| Target | Live equivalent | Action |
|---|---|---|
| SEC-AUTHZ-ENFORCE-001 (every endpoint has authz check) | SEC-UNI-001 (auth+ownership) + ENF-SEC-001 (Access Boundary Declaration) | **MODIFY** SEC-UNI-001 → split into SEC-AUTHZ-ENFORCE-001 (mandatory, every endpoint authz) and SEC-AUTHZ-IDOR-001 (object access verified) |
| SEC-AUTHZ-IDOR-001 (object-level access checks) | SEC-UNI-002 (ownership rule code path) | **MODIFY** SEC-UNI-002 → SEC-AUTHZ-IDOR-001 |
| SEC-AUTHZ-PRIV-001 (re-auth for privilege escalation) | — | **NEW** |
| SEC-AUTHZ-SCOPE-001 (token scopes minimum) | — | **NEW** |
| SEC-AUTHZ-RBAC-001 (role checks at service layer) | — | **NEW** |
| SEC-AUTHZ-DEFAULT-001 (deny by default) | — | **NEW** mandatory |
| SEC-AUTHZ-TENANT-001 (multi-tenant filter at data layer) | — | **NEW** mandatory |
| SEC-AUTHZ-FUNC-001 (admin separation) | — | **NEW** |
| SEC-AUTHZ-MASS-001 (mass assignment allowlists) | — | **NEW** mandatory |

**1C net: 2 modify (SEC-UNI-001, SEC-UNI-002), 7 new.**

#### 1D. Input Validation (target 8)

| Target | Live equivalent | Action |
|---|---|---|
| SEC-VAL-SERVER-001 | — (PY-PYDANTIC-001 is Python-specific) | **NEW** mandatory |
| SEC-VAL-TYPE-001 (typed schema validation) | PY-PYDANTIC-001 (Python only) | **NEW** language-agnostic version + keep PY rule as Python extension |
| Remaining 6 | — | **NEW** |

**1D net: 0 modify, 8 new.**

#### 1E. Cryptography & Secrets (target 8)

| Target | Live equivalent | Action |
|---|---|---|
| SEC-CRYPTO-KEY-001 (no hardcoded secrets) | SEC-UNI-004 | **MODIFY** SEC-UNI-004 → SEC-CRYPTO-KEY-001 |
| Remaining 7 | — | **NEW** |

**1E net: 1 modify, 7 new.** Mandatory candidates: SEC-CRYPTO-KEY-001, SEC-CRYPTO-RAND-001.

#### 1F-1I. HTTP headers, rate limiting, data protection, dependencies (target 21)

| Target | Live equivalent | Action |
|---|---|---|
| SEC-DATA-PII-002 (response field filtering) | SEC-UNI-003 + ENF-SEC-002 | **MODIFY** SEC-UNI-003 → SEC-DATA-PII-002; **DELETE** ENF-SEC-002 (duplicate) |
| Remaining 20 | — | **NEW** |

**1F-1I net: 1 modify, 1 delete, 20 new.**

**Security domain total: 5 modify, 1 delete, 67 new = 73 target rules.**

### 3.2 Clean Code (target 25; live ≈4 mapped)

| Target | Live equivalent | Action |
|---|---|---|
| CLEAN-FUNC-002 (functions ≤ 50 lines) | ARCH-FUNC-001 (≤ 30 lines) | **MODIFY** rename + adjust threshold (or keep 30) |
| CLEAN-MAGIC-001 (no magic numbers) | ARCH-CONST-001 | **MODIFY** rename |
| CLEAN-ERR-001 (no empty catches) | ARCH-ERR-001 (preserve original exception) | **MODIFY** broaden + rename. Keep original ARCH-ERR-001 too if distinct. |
| CLEAN-NEST-001 (max 3 nesting levels) | ARCH-COMP-001 (inheritance depth ≤ 2) | partial overlap; keep both |
| Remaining 21 | — | **NEW** |

**Clean Code net: 4 modify, 21 new.**

### 3.3 DRY (target 8; live 2)

| Target | Live equivalent | Action |
|---|---|---|
| DRY-DUP-001 (no duplicated logic ≥ 5 lines) | ARCH-DRY-001 | **MODIFY** rename |
| DRY-CONFIG-001 (single config source) | ARCH-SSOT-001 | **MODIFY** rename |
| Remaining 6 | — | **NEW** |

**DRY net: 2 modify, 6 new.**

### 3.4 SOLID (target 12; live 3)

| Target | Live equivalent | Action |
|---|---|---|
| SOLID-SRP-001/002/003 | ARCH-ORG-001 (layered architecture) | **MODIFY/SPLIT**: ARCH-ORG-001 covers SRP-002/003; new SRP-001 for class-level SRP |
| SOLID-OCP-001 | ARCH-EXT-001 (use framework extension) | **MODIFY** rename + broaden |
| SOLID-DIP-001/002 | ARCH-DI-001 (constructor injection of interfaces) | **MODIFY** rename to SOLID-DIP-002, add SOLID-DIP-001 separately |
| Remaining 8 | — | **NEW** |

**SOLID net: 3 modify, 9 new.**

### 3.5 Architecture (target 15; live ~3)

| Target | Live equivalent | Action |
|---|---|---|
| ARCH-LAYER-001 (layer boundaries enforced) | ARCH-ORG-001 | shares concept with SOLID-SRP; one concrete map |
| Remaining 14 | — | **NEW** |

**Architecture net: 0 modify (ARCH-ORG covers SOLID, separate target arch rules needed), 14 new + ARCH-IDEMPOTENT-001 etc.**

### 3.6 Testing (target 20; live 3)

| Target | Live equivalent | Action |
|---|---|---|
| TEST-EXIST-001 (every public fn has a test) | TEST-TDD-001 partial | **MODIFY** TEST-TDD-001 → TEST-EXIST-001 (or split) |
| TEST-ISOLATE-001 (no cross-test state) | TEST-ISO-001 | **MODIFY** rename TEST-ISO-001 → TEST-ISOLATE-001 |
| TEST-EDGE-001 (error paths tested) | TEST-INT-001 partial | **MODIFY** TEST-INT-001 stays as integration-test rule, add TEST-EDGE-001 |
| Remaining 17 | — | **NEW** |

**Testing net: 3 modify, 17 new.**

### 3.7 Error Handling (target 12; live 3 PHP-specific)

| Target | Live equivalent | Action |
|---|---|---|
| ERR-HANDLE-001 (every external call wrapped) | PHP-TRY-001 (PHP-only catch \Throwable) | **NEW** language-agnostic ERR-HANDLE-001; keep PHP-TRY-001 as PHP extension |
| ERR-HANDLE-003 (user-facing errors) | PHP-ERR-002 | similar |
| ERR-VALIDATION-001 | PHP-ERR-001 | similar |
| Remaining 9 | — | **NEW** |

**Error Handling net: 0 modify (PHP rules stay as language extensions), 12 new at the language-agnostic level.**

### 3.8 Performance (target 15; live 5)

| Target | Live equivalent | Action |
|---|---|---|
| PERF-ASYNC-001 (I/O async) | PERF-IO-001 | **MODIFY** PERF-IO-001 → PERF-ASYNC-001 (or keep both — PERF-IO is hot-path-specific) |
| PERF-LAZY-001 (lazy loading) | PERF-LAZY-001 | **MATCH** (rare!) — adjust wording if needed |
| PERF-QUERY-004 (pagination on list endpoints) | PERF-QBUDGET-001 partial | **MODIFY** PERF-QBUDGET-001 → PERF-QUERY-004 + keep budget concept |
| PERF-QUERY-001 (no N+1) | — | **NEW** mandatory |
| PERF-QUERY-002 (indexes on WHERE/JOIN) | PERF-BIGO-001 partial | **MODIFY** broaden |
| PERF-OPT-001 (don't optimize without measure) | PERF-OPT-001 (matches!) | **MATCH** — but target rulebook doesn't have this rule. Keep as Writ-specific advisory. |
| Remaining 9 | — | **NEW** |

**Performance net: 4 modify, 10 new.**

### 3.9 Scaling (target 10; live 0)

All 10 are **NEW**. (SCALE-STATELESS-001 mandatory candidate.)

### 3.10 API Design (target 12; live 0)

All 12 are **NEW**.

### 3.11 Process & Lifecycle (target 10; live 7 in ENF-PROC-*)

| Target | Live equivalent | Action |
|---|---|---|
| PROC-PLAN-001 (Work mode requires plan) | ENF-PROC-PLAN-001 (mandatory) + ENF-PROC-BRAIN-001 (mandatory) | **MODIFY**: keep ENF-PROC-PLAN-001 (Writ-specific mechanism) and add the public PROC-PLAN-001 as a less specific advisory? Or treat ENF-PROC-PLAN-001 as the implementation of PROC-PLAN-001 and don't duplicate. Recommend: **leave ENF-PROC-* as-is, add PROC-PLAN-001 only if it adds different content**. |
| PROC-TEST-001 (test skeletons before impl) | ENF-PROC-TDD-001 (mandatory) | **same as above** |
| PROC-REVIEW-001 (code reviewed before merge) | ENF-PROC-SDD-001 (sub-agent review order) | not the same — ENF-PROC-SDD-001 is order-of-review. PROC-REVIEW-001 is "must be reviewed". **NEW** |
| PROC-COMMIT-001 (commit message format) | — | **NEW** |
| PROC-BRANCH-001 | — | **NEW** |
| PROC-CHANGELOG-001 | — | **NEW** |
| PROC-DEPLOY-001 | — | **NEW** |
| PROC-ROLLBACK-001 | — | **NEW** |
| PROC-ENV-001 (no creds in code/chat) | — — adjacent to SEC-CRYPTO-KEY-001 | **NEW** |
| PROC-INCIDENT-001 | — | **NEW** |

**Process net: 0 modify (ENF-PROC-* are orthogonal Writ-specific rules), 8 new.** PROC-PLAN-001 and PROC-TEST-001 might be redundant with ENF-PROC-* — pending decision.

### 3.12 Documentation (target 8; live 1)

| Target | Live equivalent | Action |
|---|---|---|
| DOC-TYPE-001 (public functions have type annotations) | ARCH-TYPE-001 | **MODIFY** rename ARCH-TYPE-001 → DOC-TYPE-001 |
| Remaining 7 | — | **NEW** |

**Documentation net: 1 modify, 7 new.**

## 4. Rules to keep as Writ-specific (not in target rulebook)

These should stay because they cover Writ workflow or maintainer's bundles:

- **ENF-PROC-* (7 rules)** — Writ workflow gates, mandatory, with real mechanical paths.
- **ENF-CTX-003, ENF-GATE-007, ENF-POST-003, ENF-POST-007, ENF-SEC-001 (5 rules)** — additional mandatory rules with real mechanical paths.
- **META-AUTH-001/002 (2 rules)** — skill-authoring meta-rules.
- **DB-SQL-002, DB-SQL-003 (2 rules)** — SQL authoring style (vertical formatting, single-heredoc). Maintainer style; not in target.
- **FW-M2-* (12 rules)** — Magento framework bundle. Maintainer's example.
- **PHP-* (4 rules)** — PHP language extension. Keep.
- **PY-* (4 rules)** — Python language extension. Keep. (PY-PYDANTIC-001 might overlap with target SEC-VAL-TYPE-001; resolve.)
- **PERF-OPT-001, PERF-QBUDGET-001** — Writ-specific perf rules; PERF-OPT-001 is universal advisory.
- **ENF-OPS-001/002, ENF-SYS-002/003/005/006, ENF-PRE-001..004, ENF-POST-004/005, ENF-COMMS-001** — advisory remnants from cleanup. **Reconsider:** any of these duplicates of target rules?
   - ENF-OPS-001 (perf claims need evidence) — not in target. Keep advisory.
   - ENF-OPS-002 (queue config completeness) — Magento-specific. Keep.
   - ENF-SYS-002 (don't re-evaluate authoritative decisions) — Magento-flavored but generic concurrency principle. Keep.
   - ENF-SYS-003 (state transitions need atomicity) — could overlap with SCALE-QUEUE-002 (idempotent consumers). Distinct enough. Keep.
   - ENF-SYS-005, ENF-SYS-006 — keep advisory.
   - ENF-PRE-001..004 — Magento-specific. Keep advisory.
   - ENF-POST-004/005 — keep advisory.
   - ENF-COMMS-001 — keep advisory.

**Total Writ-specific to keep: ~40 rules.**

## 5. Implementation phases (recommended)

The 220 target is a big lift. Suggest phasing by domain priority:

**Phase 1: Security domain (highest stakes, 73 rules).**
- 5 rule modifications (SEC-UNI-* renames, ENF-SEC-002 delete)
- 67 new rules
- 16 new mandatory
- Touches: bible/security/*, mechanical paths via PHPStan/code review
- Effort: largest single phase. Probably 2-3 sub-batches (injection, auth+authz+val, crypto, headers+rate+data+deps).

**Phase 2: Foundational domains (Clean Code + DRY + SOLID + Architecture).**
- 12 rule modifications
- ~50 new rules
- 0 new mandatory (most are advisory)
- Effort: medium.

**Phase 3: Testing + Error Handling + Performance.**
- 10 rule modifications
- ~39 new rules
- 1 new mandatory (PERF-QUERY-001 N+1)
- Effort: medium.

**Phase 4: Scaling + API Design + Documentation.**
- 1 rule modification (DOC-TYPE-001 rename from ARCH-TYPE-001)
- ~29 new rules
- 1 new mandatory (SCALE-STATELESS-001)
- Effort: small-to-medium.

**Phase 5: Process & Lifecycle reconciliation.**
- 0 rule modifications
- ~8 new rules
- Decide: do PROC-PLAN-001 / PROC-TEST-001 add value beyond ENF-PROC-PLAN-001 / ENF-PROC-TDD-001?
- Effort: small.

**Phase 6: Run tests + benchmarks + update docs.**
- Re-run pytest (full suite, expect 1192+ test functions)
- Re-run benchmarks/bench_targets.py contractual gates
- Re-run scale_benchmark.py if methodology graph stable
- Update HANDBOOK.md, README.md, PROMOTIONAL-BRIEF.md, SCALE_BENCHMARK_RESULTS.md, SKILL.md with new counts
- Effort: small relative to phases 1-5.

## 6. Final state target (post-implementation)

| Metric | Current | After Phase 5 |
|---|---:|---:|
| Total rules | 73 | ~260 |
| Of which language-agnostic public | ~33 mapped | 220 (the canonical rulebook) |
| Of which Writ-specific (ENF-PROC, META, DB-SQL-002/003, FW-M2-*, PHP-*, PY-*, ENF-PRE/SYS/POST/COMMS/OPS) | ~40 | ~40 unchanged |
| Mandatory | 11 | ~27 (11 current + ~16 new from target's "Mandatory candidates" lists) |

## 7. Open questions for the user

1. **PROC-PLAN-001 vs ENF-PROC-PLAN-001**: do we keep ENF-PROC-* as the v2 mechanical implementations and skip the public PROC-* duplicates, or add both and link with edges?
2. **Severity threshold-only definitions**: target rulebook uses `critical/high/medium/low`. We use `Severity` enum with same values. No mismatch.
3. **Rule body / examples**: target rulebook gives one-line statements. Our rules require non-empty `violation`, `pass_example`, `enforcement`, `rationale`. We need to author all those fields for ~150 new rules. **Significant content authoring beyond the audit.**
4. **Mandatory selection**: target proposes 16 mandatory candidates explicitly. Should I default to those exact 16, or also keep the 5 mandatory ENF-* not in the public set (ENF-CTX-003, ENF-GATE-007, ENF-POST-003, ENF-POST-007, ENF-SEC-001)? Recommend: keep both; final mandatory set = 16 + 5 + 6 ENF-PROC-* = 27.
5. **Phasing**: do you want each phase as a separate commit, or one big rule-corpus-expansion commit?
6. **Mechanical paths for new mandatory rules**: many target mandatory rules need static-analysis paths (e.g. SEC-INJ-SQL-001 needs a SQL-string-concat detector in `bin/run-analysis.sh`). Do we add those analyzers, or mark these mandatory rules with a "needs-tooling" flag?
