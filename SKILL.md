---
name: writ
description: >
  Claude Code harness with two co-equal layers: a hybrid-RAG knowledge service
  that retrieves the coding rules an AI agent needs for the current task in well
  under a millisecond, plus a session-aware enforcement layer that blocks risky
  writes until the user has approved a plan and tests. The knowledge service runs
  a five-stage pipeline (domain filter, BM25 keyword via Tantivy, ANN vector via
  hnswlib, graph traversal via a pre-computed adjacency cache, and weighted
  ranking) over a Neo4j-backed knowledge graph. The enforcement layer is wired
  into Claude Code via 30 hook scripts and a session state machine. Activates on
  every software engineering task: code generation, code review, design,
  research, auditing, debugging, testing, planning, and architecture decisions.
  The knowledge base is always queried; task complexity only determines the
  level of ceremony, not whether Writ activates.
metadata:
  author: lucio-saldivar
  version: "1.0.1"
---

# Writ: Hybrid RAG knowledge retrieval plus workflow enforcement

## Two layers, one harness

Writ is the full Claude Code harness in this repository. It is not a single service. The repository composes three things:

**Knowledge layer (the librarian).** A stateless FastAPI service on `localhost:8765` that answers "what rules apply to this context?" via a five-stage retrieval pipeline (BM25 plus vector plus graph traversal plus reciprocal rank fusion plus context budget). Rules are facts; they do not change based on workflow state.

**Enforcement layer (the process keeper).** A session-aware workflow engine made of 30 hook scripts under `.claude/hooks/`, a state machine in `bin/lib/writ-session.py` (about 2,000 lines), slash commands under `.claude/commands/`, and 6 sub-agent role files under `.claude/agents/`. Owns mode state, phase state, gate criteria, file classification, and the audit trail. Hooks are thin clients that delegate decisions to the state machine.

**Canonical store (Neo4j).** Holds the rulebook itself: every rule, every methodology node, every relationship between them. The librarian builds its in-memory indexes from Neo4j when the service starts and serves queries from those indexes. Neo4j is the source of truth. The `bible/` directory is a human-readable Markdown export, not a runtime data source.

## How rules reach you

Rules are injected automatically by `writ-rag-inject.sh` on every user turn:

1. Takes the user's prompt as a natural language query (or a keyword extract for long prompts).
2. Reads the session cache for mode, current phase, loaded rule IDs, and remaining token budget.
3. POSTs to `http://localhost:8765/query` with `{query, exclude_rule_ids, prefer_rule_ids, budget_tokens}`.
4. Writ's pipeline ranks rules by relevance using the live indexes built from Neo4j.
5. Returns rules formatted as a `--- WRIT RULES ---` block in your context.

If no rules appear, either the server is down (you will see a warning), the prompt was too short (under 10 characters), the budget was exhausted, or the context is over 75 percent full.

Rules are phase-aware: only current-phase rule IDs are excluded from re-injection. When a phase advances, previously loaded rules can be re-injected for the new phase.

## What the rules look like

```
--- WRIT RULES (N rules, <mode> mode) ---

[RULE-ID] (severity, authority, domain) score=N.NNN
WHEN: trigger condition
RULE: what must be done
VIOLATION: example of doing it wrong
CORRECT: example of doing it right

--- END WRIT RULES ---
```

## Rule authority

- **human.** Highest trust, manually authored.
- **ai-promoted.** AI-proposed, then promoted by a human reviewer via `writ review --promote`. Confidence is bumped to `peer-reviewed`.
- **ai-provisional.** AI-proposed, not yet reviewed. Lowest trust, capped at `confidence: speculative`.

Human rules outrank AI rules at equal relevance (a hard preference, not a weight, configured via `authority_preference_threshold`).

## Mode system

Every session operates in one of four modes. The mode determines workflow ceremony, RAG strategy, and whether code generation is allowed. All modes receive rule injection.

| Mode         | Purpose                                  | Gates                       | Code generation |
|--------------|------------------------------------------|-----------------------------|------------------|
| Conversation | Discussion, brainstorming, questions     | None                        | No               |
| Debug        | Investigating a problem                  | None                        | No               |
| Review       | Evaluating code against rules            | None                        | No               |
| Work         | Building or modifying code               | phase-a plus test-skeletons | Yes              |

No mode declared means all writes are blocked except `plan.md`.

Set the mode via the `mode set` subcommand of `bin/lib/writ-session.py`. The RAG inject hook prints the exact command with paths filled in. Legacy `tier set [0-3]` commands are recognized by `inject-tier-workflow.sh` for backward compatibility (tier 0 maps to conversation, tiers 1, 2, 3 map to work).

## Gate enforcement

`bin/lib/writ-session.py` is the sole authority on phase state:

- **can-write.** Decides whether a file write is allowed. Reads the tool input envelope, classifies the file against `gate-categories.json`, checks the session's approved gates. Returns allow or deny. Hooks that need to make this decision delegate to this function.

- **advance-phase.** Validates artifacts (plan.md sections, test files), records the phase transition in the audit trail, creates a gate file. Requires a one-time token written by `auto-approve-gate.sh` only when the user actually types an approval phrase. Self-approval by the agent via raw bash is denied with `agent_self_approval_blocked`.

- **current-phase.** Returns the authoritative current phase from session state.

Gate files at `.claude/gates/*.approved` are artifacts created by `advance-phase`. They contain the session ID. Stale gates from previous sessions are rejected.

### Gate criteria (what the validator checks)

**phase-a (plan gate).** Work mode. Requires `plan.md` with sections `## Files`, `## Analysis`, `## Rules Applied` (rule IDs cited must match rules actually loaded in the session, no hallucinated IDs), and `## Capabilities` (checkboxes). The ExitPlanMode hook validates the format automatically.

**test-skeletons (test gate).** Work mode. Requires at least one test file with a recognizable test method signature and real assertions.

## Session management

`bin/lib/writ-session.py` manages per-session state in temporary files under `${WRIT_CACHE_DIR}` (default `tempfile.gettempdir()`):

- **Mode** (conversation, debug, review, work).
- **Current phase** (planning, testing, implementation, complete; Work mode only).
- **Gates approved** (source of truth, not inferred from disk).
- **Loaded rule IDs by phase** (for exclude-list scoping).
- **Phase transitions** (audit trail with timestamps and triggers).
- **Token budget** (starts at 8,000, decrements per query).
- **Always-on budget** (separate cap of 5,000 tokens for mandatory rules).
- **Context pressure** (skips RAG queries when context is over 75 percent).
- **Analysis results** (per-file pass or fail from static analysis).
- **Pending violations** (rule violations awaiting phase-boundary routing).
- **Invalidation history** (gate invalidation records for escalation detection).

## Hook inventory

Writ ships 30 hook scripts under `.claude/hooks/`, all wired into Claude Code via `templates/settings.json`. (Three legacy hooks tied to the deprecated Phase A-D / completion-matrix gate workflow were removed on 2026-05-10: `check-gate-approval.sh`, `enforce-final-gate.sh`, and `writ-pretool-rag.sh`.)

| Hook                          | Event                          | Role |
|-------------------------------|--------------------------------|------|
| `writ-rag-inject.sh`          | UserPromptSubmit               | RAG query, rule injection, mode and workflow reminders |
| `auto-approve-gate.sh`        | UserPromptSubmit               | Approval pattern detection; writes the gate token |
| `writ-rag-inject.sh` (always-on) | UserPromptSubmit            | Loads mandatory rule bundle from `/always-on` |
| `writ-pre-write-dispatch.sh`  | PreToolUse Write or Edit       | Consolidated gate check plus final-gate check plus RAG via `/pre-write-check` |
| `pre-validate-file.sh`        | PreToolUse Write or Edit       | Static analysis before write |
| `validate-exit-plan.sh`       | PreToolUse ExitPlanMode        | Plan format validation plus task phase reset |
| `validate-test-file.sh`       | PreToolUse Write               | Requires real assertions in test files |
| `validate-design-doc.sh`      | PreToolUse Write               | Validates `*-design.md` artifact structure |
| `writ-memory-policy-guard.sh` | PreToolUse Write               | Blocks rule-weakening edits to memory files |
| `writ-read-rag.sh`            | PreToolUse Read                | RAG query in Review or Debug mode only |
| `writ-verify-before-claim.sh` | PreToolUse TodoWrite plus Stop | Blocks completion claims without verification evidence |
| `writ-sdd-review-order.sh`    | PreToolUse Task                | Enforces spec review before code review for SDD |
| `writ-worktree-safety.sh`     | PreToolUse Bash                | Validates worktree paths inside `.gitignore` |
| `inject-tier-workflow.sh`     | PostToolUse Bash               | Workflow reminder after `mode set` or `tier set` |
| `validate-file.sh`            | PostToolUse Write or Edit      | Static analysis after write |
| `validate-rules.sh`           | PostToolUse Write or Edit      | Rule compliance via `/analyze`; can invalidate gates at boundary |
| `validate-handoff.sh`         | PostToolUse Write or Edit      | Handoff JSON schema validation |
| `writ-posttool-rag.sh`        | PostToolUse Write or Edit      | Code-derived RAG query for additional file-specific rules |
| `writ-quality-judge.sh`       | PostToolUse Write              | Self-review rubric directive for plans, designs, tests |
| `track-failed-writes.sh`      | PostToolUseFailure Write or Edit | Records denied writes for telemetry |
| `friction-logger.sh`          | Stop                           | Captures gate denials, mode changes, phase transitions |
| `enforce-violations.sh`       | Stop                           | Blocks Stop in Work mode if pending violations exist |
| `writ-context-tracker.sh`     | Stop                           | No-op stub kept for compatibility |
| `writ-session-end.sh`         | SessionEnd                     | Auto-feedback, coverage, gate-approval metrics, session rollup |
| `writ-pressure-audit.sh`      | SessionEnd                     | Pressure run audit (PSR cadence) |
| `writ-precompact.sh`          | PreCompact                     | Clears `loaded_rules` (full objects) before context compaction |
| `writ-postcompact.sh`         | PostCompact                    | Resets per-phase rule list, restores budget, emits verify-discipline directive |
| `writ-cwd-changed.sh`         | CwdChanged                     | Detects domain (php, python, javascript, rust, go) from cwd files |
| `writ-instructions-loaded.sh` | InstructionsLoaded             | Captures rule IDs already present in CLAUDE.md to avoid double injection |
| `writ-subagent-start.sh`      | SubagentStart                  | Creates isolated session cache; sets `is_subagent: true` |
| `writ-subagent-stop.sh`       | SubagentStop                   | Records subagent rollup metrics |

## Sub-agents

Workers spawned from an orchestrator get an isolated session cache keyed on `agent_id`, with their own 8,000 token RAG budget and `is_subagent: true` set. Workers bypass mode and gate checks entirely (the orchestrator already cleared the human-approval flow). PostToolUse RAG still fires inside workers so they get rule injection on every file write.

The orchestrator master sets Work mode with the `--orchestrator` flag, which sets `is_orchestrator: true`. That flag tells `writ-rag-inject.sh` to suppress the broad rule injection on every UserPromptSubmit and emit a compact status line instead. The orchestrator does not need rule guidance turn by turn; the workers do.

## Supported languages and frameworks

Gate categories support: PHP, Python, JavaScript, TypeScript, Go, Rust, Java, Ruby, GraphQL, XML. Framework-specific patterns: Magento 2, Django, Rails, Spring, NestJS, Express, Laravel. Add new patterns via `bin/lib/gate-categories.json`.

Static analysis routes by file extension: PHPStan, ESLint, ruff, xmllint, cargo check, go vet. Add new analyzers via `bin/run-analysis.sh`.

## Proposing new rules

Propose a rule when any of these occur:

1. **Bug fix reveals a missing guard.** You fixed a bug that a rule should have prevented. Propose for the root cause pattern, not the symptom.
2. **Architectural decision with no prior art.** You made a design choice with no matching rule in the injected set, and it would benefit future tasks.
3. **User corrects your approach.** The user says "do not do X" or "always do Y" and no injected rule covers it.
4. **Framework or library gotcha.** A non-obvious constraint that would trap future agents.

Do not propose for: one-off project decisions (use project memory instead), obvious language usage, or duplicates of already-injected rules.

```bash
curl -X POST http://localhost:8765/propose -H 'Content-Type: application/json' -d '{
  "rule_id": "DOMAIN-CATEGORY-NNN",
  "domain": "architecture",
  "severity": "medium",
  "scope": "function",
  "trigger": "when this situation occurs",
  "statement": "what must be done",
  "violation": "example of doing it wrong",
  "pass_example": "example of doing it right",
  "enforcement": "how to verify compliance",
  "rationale": "why this matters",
  "last_validated": "YYYY-MM-DD",
  "task_description": "what you were doing when you discovered this",
  "query_that_triggered": "the prompt that led here"
}'
```

Rule ID convention: `{DOMAIN}-{CATEGORY}-{NNN}` where DOMAIN is a broad area (ARCH, PY, PHP, FW, DB, TEST, PERF, SEC, ENF, OPS). Check existing rules to avoid ID collisions.

Proposed rules enter as `ai-provisional` with `confidence: speculative` and must pass the structural gate (schema, mechanical-enforcement-path for mandatory rules, specificity, redundancy, novelty, conflict checks).

### Recording feedback

When a rule directly influenced your implementation (you followed it, or it prevented an error), record positive feedback:

```bash
curl -X POST http://localhost:8765/feedback -H 'Content-Type: application/json' \
  -d '{"rule_id": "RULE-ID-HERE", "signal": "positive"}'
```

Negative feedback (rule was present but did not prevent an error) is recorded automatically by the enforcement hooks at phase boundaries.

## Server requirements

Writ requires:
- Neo4j at `bolt://localhost:7687` (credentials in `writ.toml` or `docker-compose.yml`).
- Writ server: `writ serve` (default `localhost:8765`).
- Bible rules imported: `writ import-markdown` (initial bootstrap only).
- Hooks installed (standalone): `bash scripts/install-harness-config.sh`. Renders `templates/settings.json` and `templates/CLAUDE.md` into `~/.claude/`.
- Global config installed (plugin): `bash scripts/patch-global-config.sh`. Plugin installs do not render the templates automatically; this script merges the cross-mode allow/deny entries into `~/.claude/settings.json` and renders `templates/CLAUDE.md` into `~/.claude/CLAUDE.md`. Idempotent, backup-on-write.

When loaded as a plugin, `scripts/ensure-server.sh` starts Neo4j (Docker) and the Writ server automatically via the Init lifecycle hook.

## Architecture reference

- Server: `writ/server.py` (FastAPI, async; 36 endpoints).
- Pipeline: `writ/retrieval/pipeline.py` (5-stage hybrid).
- Schema: `writ/graph/schema.py` (Rule, Abstraction, methodology nodes, edge models).
- Config: `writ.toml` (all tunable parameters).
- Session engine: `bin/lib/writ-session.py` (phase state, gate management, audit trail).
- Hook parser: `bin/lib/parse-hook-stdin.py` (normalizes Claude Code stdin envelope).
- Gate categories: `bin/lib/gate-categories.json` (language and framework file patterns).
- Checklists: `bin/lib/checklists.json` (phase exit criteria).
- Static analysis: `bin/run-analysis.sh` (multi-language router).
- Verification: `bin/verify-files.sh` (batch file-existence checks).
- Hooks: `.claude/hooks/` (30 hooks, all wired; see inventory above).
- Plugin manifest: `.claude-plugin/plugin.json` (auto-discovery, lifecycle hooks).
- Lifecycle: `scripts/ensure-server.sh`, `scripts/stop-server.sh`.
- Install (standalone): `scripts/install-harness-config.sh` (renders `~/.claude/settings.json` and `~/.claude/CLAUDE.md` from templates, with backups).
- Install (plugin): `scripts/patch-global-config.sh` (merges cross-mode allow/deny entries into `~/.claude/settings.json` and renders `~/.claude/CLAUDE.md` from template; idempotent).
- Full spec: `HANDBOOK.md`.
