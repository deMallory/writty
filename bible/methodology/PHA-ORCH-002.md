---
phase_id: PHA-ORCH-002
node_type: Phase
domain: process
scope: session
trigger: "Second phase of PBK-PROC-ORCHESTRATOR-001. Fires after the explorer worker returns."
statement: "Dispatch the writ-planner worker (foreground) to write plan.md + capabilities.md from the exploration results. When it returns, the master presents the plan and waits for the user's 'approved' (the master, not the worker, owns approvals)."
rationale: "The planner runs in isolation so the plan is a complete reviewable artifact; only the master interacts with the user so workers cannot desync the gate."
tags: [process, orchestrator, plan, phase, dispatch, gate]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-02
staleness_window: 180
evidence: peer-reviewed
source_attribution: "writ-native"
source_commit: null
position: 2
name: "Plan"
description: |
  Foreground-dispatch writ-planner (ROL-PLANNER-001); master presents the returned plan and waits for "approved". Corresponds to work-mode planning (PHA-WORK-001).
parent_playbook_id: PBK-PROC-ORCHESTRATOR-001
edges: []
category: CAT-PROC-DISPATCH-001
---

# Phase: Plan

Non-retrievable structural node of PBK-PROC-ORCHESTRATOR-001 (phase 2 of 4), surfaced via CONTAINS.
