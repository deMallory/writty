---
phase_id: PHA-WORK-001
node_type: Phase
domain: process
scope: session
trigger: "First gate of PBK-PROC-WORK-WORKFLOW-001. Fires when Work mode begins a feature, refactor, or bug-fix task."
statement: "Enter /plan, write plan.md (the four required sections) and capabilities.md to the project root WHILE STILL IN /plan mode and BEFORE ExitPlanMode, exit, present a summary, then stop and wait for the user to type 'approved'."
rationale: "The plan is the contract the user inspects and steers before any code is committed. Skipping it means the user reviews a finished implementation instead of a design."
tags: [process, work-mode, plan, phase, gate]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-02
staleness_window: 180
evidence: peer-reviewed
source_attribution: "writ-native"
source_commit: null
position: 1
name: "Plan"
description: |
  Write plan.md (## Files, ## Analysis, ## Rules Applied, ## Capabilities) and capabilities.md to the project root while still in /plan mode. Exit /plan, present a chat summary, and wait for the explicit user "approved". The phase-a gate denies every non-plan.md write until then.
parent_playbook_id: PBK-PROC-WORK-WORKFLOW-001
edges: []
category: CAT-PROC-001
---

# Phase: Plan

Non-retrievable structural node of PBK-PROC-WORK-WORKFLOW-001 (gate 1 of 3), surfaced via CONTAINS.
Advance criterion: user types "approved" (the hook creates the phase-a gate file).
