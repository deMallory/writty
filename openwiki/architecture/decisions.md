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
| `docs/adr/ADR-db-store-mixins.md` | Neo4jConnection composed from store mixins | accepted |
| `docs/adr/ADR-integrity-check-mixins.md` | IntegrityChecker composed from check mixins | accepted |
| `docs/adr/ADR-session-and-project-isolation.md` | Session and project isolation, and a tripwire for the external cause | accepted in part |
| `docs/adr/ADR-test-graph-isolation.md` | The test suite gets its own Neo4j instance, and the tripwire is deleted | accepted |

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
