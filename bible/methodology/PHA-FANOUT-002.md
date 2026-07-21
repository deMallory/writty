---
phase_id: PHA-FANOUT-002
node_type: Phase
domain: process
scope: session
trigger: "Second phase of PBK-PROC-AUDIT-FANOUT-001. Fires when scope-estimate recommends more than one worker."
statement: "Run partition-scope to tile the frozen scope into per-worker chunks, each within the LOC and file-count budget. A file flagged oversized becomes its own partition, dispatched as its own worker by the main chat."
rationale: "Partitioning to a per-worker budget caps every worker's working set; the tiling is what lets a multi-million-line repo be covered without any agent overflowing."
tags: [audit, fan-out, partition, budget, phase, process]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-02
staleness_window: 180
evidence: peer-reviewed
source_attribution: "writ-native"
source_commit: null
position: 2
name: "Partition"
description: |
  partition-scope tiles the frozen scope into per-worker chunks within the LOC/file budget; oversized files become their own partition, dispatched as their own worker by the main chat.
parent_playbook_id: PBK-PROC-AUDIT-FANOUT-001
edges: []
category: CAT-PROC-DISPATCH-001
---

# Phase: Partition

Non-retrievable structural node of PBK-PROC-AUDIT-FANOUT-001 (phase 2 of 4), surfaced via CONTAINS.
