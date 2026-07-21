---
phase_id: PHA-FANOUT-003
node_type: Phase
domain: process
scope: session
trigger: "Third phase of PBK-PROC-AUDIT-FANOUT-001. Fires after partition-scope tiles the scope."
statement: "The main chat dispatches one worker sub-agent per partition. Each worker freezes partition.files as ITS scope, audits it, and returns its coverage-map -- workers never spawn sub-agents. A partition that still exceeds budget is re-partitioned by the main chat and dispatched as more workers (the re-partition loop is the orchestrator's, one level), instead of overflowing."
rationale: "Each worker holds only its partition plus the rules its own RAG surfaces; nothing accumulates in the main chat. Re-partitioning by the main chat bounds every worker's working set."
tags: [audit, fan-out, delegate, workers, phase, process]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-02
staleness_window: 180
evidence: peer-reviewed
source_attribution: "writ-native"
source_commit: null
position: 3
name: "Delegate"
description: |
  The main chat dispatches one worker per partition; each freezes its partition, audits, returns a coverage-map. Over-budget partitions are re-partitioned by the main chat and dispatched as more workers.
parent_playbook_id: PBK-PROC-AUDIT-FANOUT-001
edges: []
category: CAT-PROC-DISPATCH-001
---

# Phase: Delegate

Non-retrievable structural node of PBK-PROC-AUDIT-FANOUT-001 (phase 3 of 4), surfaced via CONTAINS.
