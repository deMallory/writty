---
phase_id: PHA-FANOUT-001
node_type: Phase
domain: process
scope: session
trigger: "First phase of PBK-PROC-AUDIT-FANOUT-001. Fires when the main chat begins an at-scale audit."
statement: "The main chat freezes the whole target as the coverage scope (--freeze-scope) and runs scope-estimate, reporting file_count, total_loc, and recommended_workers = ceil(total_loc / budget). If recommended_workers <= 1, audit directly; otherwise fan out."
rationale: "The frozen scope makes the coverage denominator ungameable; the estimate decides whether one context budget suffices or partitioning is required before any reading begins."
tags: [audit, fan-out, estimate, scope, phase, process]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-02
staleness_window: 180
evidence: peer-reviewed
source_attribution: "writ-native"
source_commit: null
position: 1
name: "Estimate"
description: |
  --freeze-scope the target, run scope-estimate, compute recommended_workers. Decide: audit directly (<=1) or partition.
parent_playbook_id: PBK-PROC-AUDIT-FANOUT-001
edges: []
category: CAT-PROC-DISPATCH-001
---

# Phase: Estimate

Non-retrievable structural node of PBK-PROC-AUDIT-FANOUT-001 (phase 1 of 4), surfaced via CONTAINS.
