# Codebase inventory workflow

A repeatable Claude Code dynamic workflow that produces a fine-grained,
machine-readable inventory of this repository as raw material for
visualization. It is deliberately **not** a prose report: every dataset is one
row per thing (per file, per hook, per corpus node, per log event), with
aggregation left undone so the consumer decides it.

Script: [`scripts/inventory-workflow.mjs`](../scripts/inventory-workflow.mjs)

## What it does

Writty is four overlapping systems, so the workflow fans out one read-only
survey agent per subsystem, adversarially verifies each survey, then
synthesizes a joined report:

| Phase | Agents | Output |
|---|---|---|
| Survey | `service`, `harness`, `corpus`, `tests`, `periphery`, `trace` (parallel) | one record per module / hook / node / test file / artifact; the trace agent emits a normalization spec for the two log surfaces |
| Verify | one adversarial verifier per survey | independently re-derives a sample of each survey's numeric claims and reports mismatches (prompted to refute, not confirm) |
| Synthesize | one agent | cross-subsystem join map, headline structural facts, and an explicit gaps list |

Design principles: **grain** (one row per thing, never a pre-aggregated
count), **evidence** (every numeric claim carries the command or `file:line`
it came from), **adversarial verify** (numbers that don't survive re-derivation
are reported, not silently reconciled), and **off-disk only** (works with Neo4j
and the Writ server both down; no `docker`, no `writ serve`).

## How to run

From the repo root, invoke the Claude Code `Workflow` tool with:

```
{ scriptPath: "scripts/inventory-workflow.mjs" }
```

The workflow returns `{ subsystems, synthesis }`. The orchestrator writes the
datasets into `inventory/` (gitignored — regenerable raw output):

| File | Grain | Notes |
|---|---|---|
| `service.json` | one record per `writ/*.py` module | + its adversarial verification |
| `harness.json` | one record per hook script / library | event, matcher, HTTP paths curled, tmp files, blocking vs fail-open |
| `corpus.json` | one record per `bible/` node | full parse attached to `survey.records` |
| `tests.json` | one record per test file | test count (AST-based), markers, subprocess-driven |
| `periphery.json` | one record per script / doc / config / template | kind + entry-point flag |
| `trace.json` | normalization spec + sample rows | the survey does not return the full event table (see below) |
| `events.json` | one row per log event, both sources normalized | materialized mechanically by the orchestrator from the two raw logs |
| `synthesis.json` | join map, headline shapes, gaps | |
| `manifest.json` | run metadata | git sha/branch/dirty, per-dataset row counts, verification verdicts, `corrections[]`, `gaps[]` |

## Known limits (by construction, not bugs)

- **Corpus survey caps its own output.** At ~430 nodes, returning every record
  through the agent schema overflows the 64k output-token limit. The survey
  dumps the full parse to disk (via the repo's own `writ.graph.ingest` parser)
  and returns samples + breakdowns; the orchestrator attaches the full dump.
- **Trace survey returns a spec, not the table.** It emits a precise
  `normalization_spec` and sample rows; the orchestrator materializes the full
  `events.json` mechanically from `workflow-friction.log` +
  `~/.cache/writ/server.log` using that spec.
- **`server.log` is a snapshot, not longitudinal.** It is truncated fresh on
  every SessionStart (`hooks/scripts/session-start-bootstrap.sh`), so its
  access-line layer covers one server lifetime only.
- **The friction log is live-appending.** Any single row count is stale the
  moment it is read; datasets derived from it need an explicit "as of" anchor.
- **Three session-id shapes coexist** in both logs — 36-char UUID, 17-hex
  subagent id, and bare PID (from a `ps`-based fallback in hooks that get no
  stdin envelope) — so `events.json` carries a `session_shape` field. Anything
  grouping by session must know which shape it is looking at.

## Cross-subsystem joins

The datasets are designed to join, not just coexist. Key edges (see
`synthesis.json.join_map` for the full, field-level list):

- harness `http_paths` → service endpoints (`writ/server.py` routes) → trace
  `event_or_path` (the same path strings, static ↔ runtime).
- corpus `edges[].target` → corpus `id` (the knowledge graph, self-joined).
- corpus `id` → trace `rule_ids[]` (which rules actually fired at runtime).
- tests filename → service module (1:1 by naming convention).
- session id → the same id across both `events.json` sources (join-tested).
