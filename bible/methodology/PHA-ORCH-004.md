---
phase_id: PHA-ORCH-004
node_type: Phase
domain: process
scope: session
trigger: "Final phase of PBK-PROC-ORCHESTRATOR-001. Fires after the test-skeletons gate is approved."
statement: "Dispatch the writ-implementer worker (foreground) to write production code and update capabilities. Workers bypass mode/gate checks (is_subagent=true); the master integrates the result."
rationale: "Implementation lands last and in isolation; the worker writes freely because the master already secured both approvals, so no gate is bypassed that the user did not clear."
tags: [process, orchestrator, implement, phase, dispatch]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-02
staleness_window: 180
evidence: peer-reviewed
source_attribution: "writ-native"
source_commit: null
position: 4
name: "Implement"
description: |
  Foreground-dispatch writ-implementer (ROL-IMPLEMENTER-001) to write production code + update capabilities.md. Corresponds to work-mode implementation (PHA-WORK-003).
parent_playbook_id: PBK-PROC-ORCHESTRATOR-001
edges: []
category: CAT-PROC-DISPATCH-001
---

# Phase: Implement

Non-retrievable structural node of PBK-PROC-ORCHESTRATOR-001 (phase 4 of 4), surfaced via CONTAINS.
