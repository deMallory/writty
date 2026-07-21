---
phase_id: PHA-ORCH-001
node_type: Phase
domain: process
scope: session
trigger: "First phase of PBK-PROC-ORCHESTRATOR-001. Fires after the master sets Work mode with --orchestrator."
statement: "Dispatch the writ-explorer worker (foreground) to gather the codebase facts a planner needs: structure, framework, conventions, and the files relevant to the task. The worker runs on its own Writ session and RAG budget."
rationale: "Exploration is its own dispatch so the planner receives unbiased codebase facts and the master's context stays clean for coordination."
tags: [process, orchestrator, explore, phase, dispatch]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-02
staleness_window: 180
evidence: peer-reviewed
source_attribution: "writ-native"
source_commit: null
position: 1
name: "Explore"
description: |
  Foreground-dispatch writ-explorer (ROL-EXPLORER-001) to report structure, patterns, and relevant files. No user gate; feeds the plan phase.
parent_playbook_id: PBK-PROC-ORCHESTRATOR-001
edges: []
category: CAT-PROC-DISPATCH-001
---

# Phase: Explore

Non-retrievable structural node of PBK-PROC-ORCHESTRATOR-001 (phase 1 of 4), surfaced via CONTAINS.
Folds into work-mode planning (PHA-WORK-001); the orchestrator splits it out as its own worker.
