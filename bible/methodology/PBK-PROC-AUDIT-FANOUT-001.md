---
playbook_id: PBK-PROC-AUDIT-FANOUT-001
node_type: Playbook
domain: process
severity: high
scope: session
trigger: "When auditing or exploring a codebase too large for one agent's context window -- the main chat sizes the work and dispatches one level of worker sub-agents over a frozen, tiled scope, re-partitioning oversized chunks itself, so even multi-million-line repositories get a full, verifiable audit."
statement: "The main chat is the only orchestrator (one level deep). It freezes the whole project as the coverage scope, runs scope-estimate, and if the work fits one context budget audits it directly; otherwise it runs partition-scope and dispatches one worker sub-agent per partition. Each worker freezes its partition, audits it, and returns a coverage-map -- workers never spawn sub-agents (a dispatched agent has no Task tool). If a partition still exceeds budget the main chat re-partitions it and dispatches more workers; the re-partition loop is the orchestrator's, never the worker's. The main chat coverage-rollup's the workers' coverage-maps into global coverage and the synthesis gate."
rationale: "No single agent can hold a million lines in context. Partitioning to a per-worker LOC/file budget caps every worker's working set; the frozen scope makes the denominator ungameable; the roll-up reconstructs whole-project coverage from isolated worker sessions. Workers inherit the hook system via writ-subagent-start, so each queries the RAG on demand with its own budget -- the main chat does not pre-load rules it will never use. Nesting is impossible by construction: sub-agents have no Task tool, so only the main chat dispatches, one level deep."
tags: [audit, fan-out, sub-agents, orchestration, scale, coverage, playbook, process]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-01
staleness_window: 180
evidence: "writ-session.py scope-estimate / partition-scope / coverage-rollup are deterministic; .claude/hooks/writ-subagent-start.sh gives each worker an agent_id-keyed session, fresh RAG budget, gate-bypass, and PostToolUse RAG injection."
source_attribution: "writ-native"
source_commit: null
phase_ids:
  - PHA-FANOUT-001
  - PHA-FANOUT-002
  - PHA-FANOUT-003
  - PHA-FANOUT-004
preconditions: [PBK-PROC-RESEARCH-001, PBK-PROC-ORCHESTRATOR-001]
dispatched_roles: [ROL-EXPLORER-001]
edges:
  - { target: PBK-PROC-ORCHESTRATOR-001, type: PRECEDES }
  - { target: PBK-PROC-RESEARCH-001, type: RELATED_TO }
  - { target: ROL-EXPLORER-001, type: DISPATCHES }
  - { target: PHA-FANOUT-001, type: CONTAINS }
  - { target: PHA-FANOUT-002, type: CONTAINS }
  - { target: PHA-FANOUT-003, type: CONTAINS }
  - { target: PHA-FANOUT-004, type: CONTAINS }
category: CAT-PROC-DISPATCH-001
floor_modes: [investigate]
trigger_keywords: ["fan-out", "sub-agents", "coverage", "auditing"]
---

# Playbook: Self-sizing hierarchical audit fan-out

The at-scale execution of the investigation spine (PBK-PROC-RESEARCH-001) for the
code lens. Audit/explore is one engine over a source type; this playbook is how
that engine covers a codebase larger than any single context window.

## The re-partition loop (the main chat owns it, one level deep)

Each phase's content is a CONTAINS-linked Phase node. The main chat re-partitions and
re-dispatches when a partition still exceeds budget -- workers never spawn workers (a
dispatched sub-agent has no `Task` tool):

1. `PHA-FANOUT-001` — Estimate: the main chat `--freeze-scope`, `scope-estimate`, decide fan-out.
2. `PHA-FANOUT-002` — Partition: `partition-scope` tiles the scope to per-worker LOC/file budgets.
3. `PHA-FANOUT-003` — Delegate: the main chat dispatches one worker per partition; each freezes + audits + returns a coverage-map; the main chat re-partitions any over-budget partition and dispatches more workers.
4. `PHA-FANOUT-004` — Roll up: `coverage-rollup` + the synthesis verdict from the workers' coverage-maps.

## Aggregate, reconcile, rank (after roll-up)

Coverage roll-up answers "was it all examined". `aggregate-findings` answers "what did
the workers find, and do they agree". After `coverage-rollup`, the main chat pipes the workers'
reports (each a `coverage_map` + structured findings `{ref, rule, severity, message,
subject?, stance?}`) into `aggregate-findings`:

- **Dedup** findings seen by overlapping workers (by `ref` + `rule` + `message`).
- **Contradictions:** a `subject` carrying >=2 distinct `stance` values means two workers
  reached opposing conclusions about the same thing. Resolve or escalate every
  contradiction -- never average it away or silently drop one side.
- **Coverage-aware attention ranking:** regions are ranked by coverage gap first, then
  error density. A clean-looking region that was barely examined ranks HIGH, not low --
  do not mistake "few findings" in an under-covered partition for "safe".

Synthesize only after the contradictions are addressed and the attention ranking is
reviewed. The roll-up + aggregate together are the main chat's evidence base.

## Why workers, not one big read

Partitioning to a budget is the context-safety bound. Each worker holds only its
partition plus the rules its own RAG queries surface; nothing accumulates in the
main chat. This is what lets a multi-million-line audit finish without any agent hitting
its context limit.

## The honest ceiling

Roll-up sums PRESENCE signals (files examined per partition over a frozen, tiled
denominator). It proves breadth of attention, never depth or correctness. A green
roll-up means "every region was examined and the tiling reconciled", not "the audit
found every issue". `reconciled=false` means a partition's scope drifted -- investigate
before trusting the global number.

## Red flags

- One agent reading the whole repo "to be thorough" (it will truncate or overflow).
- Synthesizing a global verdict from workers that did not all report (partitions_reported < expected).
- Trusting `global_coverage_pct` when `reconciled` is false.
