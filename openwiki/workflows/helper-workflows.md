---
type: Guide
title: "Helper workflows"
description: The two Claude Code Workflow scripts shipped with Writty, dialectic review and codebase inventory, what each gives you and how to run it.
---

# Helper workflows

Writty ships two scripts for Claude Code's Workflow tool. Each fans out several agents over the repo, and neither edits source. Run them from the repo root.

| Workflow | Script | Gives you | Details |
|---|---|---|---|
| Dialectic review | `scripts/dialectic-review-workflow.mjs` | a verdict on a plan or a diff: confirmed findings, rejected critiques and trade-offs, each finding re-checked against the repo | `docs/dialectic-review-workflow.md` |
| Inventory | `scripts/inventory-workflow.mjs` | a machine-readable map of the repo, one row per file, hook, graph node, test file and log event | `docs/inventory-workflow.md` |

## Dialectic review

Use it on a large plan before you approve it, or on a diff before merge. One agent makes the strongest case for the work. Two others attack it without seeing each other: one grounded in the rule graph, one reading the work cold, like a newcomer. Verifiers then re-check every finding against the repo, and a last stage reconciles the two sides. It only reports.

```
{ scriptPath: "scripts/dialectic-review-workflow.mjs",
  args: { mode: "plan", target: "plan.md" } }
```

For a diff, pass `mode: "code"`, a `target` (paths, a branch, or `"."`) and a `base` ref (default `HEAD~1`). It uses the rule graph when the local service answers, and a built-in rule set when it does not. The report says which one it used.

## Inventory

Use it to find your way around the codebase, or to feed a visualization. Every dataset is one row per thing, with no totals precomputed, and every survey is re-checked by a second agent. It reads files and logs only, so it runs with Neo4j and the local service stopped.

```
{ scriptPath: "scripts/inventory-workflow.mjs" }
```

The session that runs it saves the datasets under `inventory/`, with a `manifest.json` naming the commit they describe. A map from an older commit is for orientation, not for facts.

## Where to read more

- `docs/dialectic-review-workflow.md`: phases, arguments, output shape, known limits.
- `docs/inventory-workflow.md`: datasets, their grain, how they join.
