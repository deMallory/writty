---
phase_id: PHA-FANOUT-004
node_type: Phase
domain: process
scope: session
trigger: "Final phase of PBK-PROC-AUDIT-FANOUT-001. Fires after the partition workers return their coverage-maps."
statement: "The main chat runs coverage-rollup (global coverage + reconciled + synthesis verdict), then aggregate-findings: dedup overlapping findings, resolve or escalate every contradiction (never average away), and rank regions by coverage gap first then error density. Synthesize only after contradictions are addressed."
rationale: "Roll-up reconstructs whole-project coverage from isolated worker sessions and proves breadth of attention; an under-covered clean-looking region must rank HIGH, not be mistaken for safe."
tags: [audit, fan-out, rollup, aggregate, coverage, synthesis, phase, process]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-02
staleness_window: 180
evidence: peer-reviewed
source_attribution: "writ-native"
source_commit: null
position: 4
name: "Roll up"
description: |
  coverage-rollup + aggregate-findings: dedup, resolve contradictions, coverage-aware attention ranking, then synthesize. reconciled=false means a partition drifted -- investigate before trusting the number.
parent_playbook_id: PBK-PROC-AUDIT-FANOUT-001
edges: []
category: CAT-PROC-DISPATCH-001
---

# Phase: Roll up

Non-retrievable structural node of PBK-PROC-AUDIT-FANOUT-001 (phase 4 of 4), surfaced via CONTAINS.
Roll-up sums PRESENCE signals (breadth), never depth or correctness.
