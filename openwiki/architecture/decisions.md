---
type: Guide
title: "Design decisions"
description: The architecture decision records with their status, the decisions recorded in code or reference docs with a source for each, and how to add an ADR.
---

# Design decisions

Why Writty is built the way it is. The decision records live in `docs/adr/`. Many other decisions are recorded where they apply, in code comments or the reference docs, and are indexed here with their source.

## Decision records

| ADR | Title | Status |
|---|---|---|
| `docs/adr/ADR-alwayson-ranked-field-dedup.md` | field-level dedup between the always-on and ranked channels | accepted |
| `docs/adr/ADR-approval-integrity.md` | approval integrity (an approval must have a referent, and an authority change must have an approval) | accepted |
| `docs/adr/ADR-bash-control-operator-tokenizer.md` | one authored control-operator splitter for both Bash gates, and why `&` is not always an operator | accepted |
| `docs/adr/ADR-blackbox-record-schema.md` | the capture record carries the event, the exit code, and the hook's own pid | accepted |
| `docs/adr/ADR-ci-graph-topology.md` | CI runs two Neo4j instances, and the production one carries a seeded witness | accepted |
| `docs/adr/ADR-credential-literal-value-shape.md` | the credential scanner judges the VALUE's shape, and gives up one thing to do it | accepted |
| `docs/adr/ADR-daemon-leak-guard.md` | a leaked daemon is caught by the process table, not by a source detector | accepted |
| `docs/adr/ADR-db-store-mixins.md` | Neo4jConnection composed from store mixins | accepted |
| `docs/adr/ADR-gate-token-leak-guard.md` | a leaked gate token is reported and never removed, and prevention is opt-in per module | accepted |
| `docs/adr/ADR-guard-input-normalization.md` | a guard normalizes the text it parses, at the parser, not at the producer | accepted |
| `docs/adr/ADR-health-log-destination.md` | `/health` names the file this daemon's rows actually land in | accepted |
| `docs/adr/ADR-hook-exec-argument-boundary.md` | an unbounded value never crosses an exec boundary, in argv or in env | accepted |
| `docs/adr/ADR-hook-out-capture-funnel.md` | hook reply capture sits at the emit site, not at the process boundary | accepted |
| `docs/adr/ADR-integrity-check-mixins.md` | IntegrityChecker composed from check mixins | accepted |
| `docs/adr/ADR-managed-global-settings.md` | Writ ships global settings keys the way it ships hooks | accepted |
| `docs/adr/ADR-orchestrator-injection-channels.md` | which injection channels an orchestrator master keeps, and how one is turned off | accepted |
| `docs/adr/ADR-prewrite-analysis-duplication.md` | the post-write analyzer run is not a duplicate of the pre-write one, and stays | accepted |
| `docs/adr/ADR-project-write-boundary.md` | an approved plan authorizes writes to its project, plus what its Files section declares | accepted |
| `docs/adr/ADR-ranked-header-fields.md` | what the ranked rule header renders (severity always, authority as an exception, domain dropped) | accepted |
| `docs/adr/ADR-read-path-lens-predicate.md` | a cheap predicate in front of the runtime-lens read gate | accepted |
| `docs/adr/ADR-role-write-scope.md` | a sub-agent's write scope is declared by its role and stamped at dispatch | accepted |
| `docs/adr/ADR-session-and-project-isolation.md` | Session and project isolation, and a tripwire for the external cause | accepted in part |
| `docs/adr/ADR-state-root.md` | Writ's durable state lives in the XDG state root, never inside the install | accepted |
| `docs/adr/ADR-subagent-seed-reachability.md` | which layer owns "already seeded", and which way the fast path fails | accepted |
| `docs/adr/ADR-test-graph-isolation.md` | The test suite gets its own Neo4j instance, and the tripwire is deleted | accepted |
| `docs/adr/ADR-token-audit-billing-unit.md` | token-audit bills per API response, prices per model, and adds up the subagent tree | accepted |
| `docs/adr/ADR-write-path-branch-budget.md` | the write path's per-branch process budget, and the one gated stderr tee | accepted |

- **Store mixins.** The one Neo4j class was a god-file. It became the `writ/graph/db/` package: one mixin per domain (rules, nodes, edges, records, and more), methods moved verbatim so behavior could not change. Delegating to store objects was rejected because it rewrites every method body.
- **Check mixins.** The same split, for the same reason, applied to the integrity checker in `writ/graph/integrity/`.
- **Session and project isolation.** A session learns its id from the hook payload or refuses; it never guesses from a machine-wide file. An approval belongs to the session that earned it. Retrieval scopes by node type, so doctrine reaches every project and records stay private ([Rule graph](rule-graph.md)). It also records that a cross-project text leak came from Claude Code, not Writty, and wires a tripwire that logs a recurrence. Part 6, automatic mode routing, is still pending: see the Pending section of the ADR.
- **Test graph isolation.** The test suite runs against its own Neo4j instance, so a test wipe can never destroy decision records, which have no source on disk to rebuild from. `make test` starts that instance; bare `pytest` refuses to run against production. The old guard in `tests/conftest.py` was deleted, not extended: it could not see the path that caused the leak.

## Decisions recorded in code and docs

| Decision | Source |
|---|---|
| Neo4j is canonical. `writ-corpus.cypher` is the tracked form; `bible/` is a derived local export | `docs/reference/architecture.md` section 1, `HANDBOOK.md` section 11 |
| Ingest only adds and updates; `writ reconcile` is the only prune | `docs/reference/architecture.md` section 1 |
| Mandatory rules are never ranked. One predicate pair decides the floor and the ranked pool, and `writ validate` checks the same pair | `writ/graph/predicates.py`, `HANDBOOK.md` section 10 |
| Decision records and memories never enter retrieval | `writ/graph/schema.py`, `docs/reference/decision-memory.md` |
| Only a token from the user's typed approval advances a gate or writes canon. The agent cannot approve its own work | `HANDBOOK.md` section 7 |
| Hooks fail open. The named exceptions fail closed: secret-path denial, the research triangulation gate, token validation on a phase advance | `docs/reference/architecture.md` section 2 |
| Under a reviewer's CRITICAL findings, `git commit` asks the human instead of refusing, because any override the agent could set would reopen the hole | `docs/reference/architecture.md` section 2, `HANDBOOK.md` section 6 |
| The daemon has no authentication and listens on localhost only | `docs/reference/architecture.md` section 1 |
| Abstention is opt-in at the call site: rule injection turns it on, authoring and diagnostics do not | `writ/retrieval/pipeline.py` |
| Ranking weights are code constants, not configuration | `docs/reference/retrieval.md` section 2 |
| Graduation uses a plain ratio of positive observations, with no statistical smoothing, and never promotes on its own | `docs/reference/graph-schema.md` section 5 |
| Scoping by node type is an allowlist written out by hand, so a new type fails closed as private | `writ/retrieval/node_scope.py` |

## Adding a decision record

1. Write `docs/adr/ADR-<topic>.md`, shaped like the others: a `# ADR:` title, a `Status:` line, then Context, Decision, Alternatives considered and Consequences.
2. Add its row to the table above, with the status as its `Status:` line reads up to the first parenthesis, and a one-line summary below the table.
3. Update the row when the status changes. `tests/openwiki/test_architecture.py` fails when an ADR is missing from the table or its status drifts.

A decision small enough to live in a comment or a reference doc still earns a row in the second table, with its source.
