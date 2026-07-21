---
phase_id: PHA-WORK-003
node_type: Phase
domain: process
scope: session
trigger: "Third phase of PBK-PROC-WORK-WORKFLOW-001. Fires after the test-skeletons gate (PHA-WORK-002) is approved."
statement: "Implement files in dependency order, fleshing out the approved test skeletons, and check off completed items in capabilities.md as [x]. Only now may non-test files be written."
rationale: "Implementation lands last so the user has already approved both the design and the test contract; the gates guarantee nothing was written ahead of review."
tags: [process, work-mode, implementation, phase]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-02
staleness_window: 180
evidence: peer-reviewed
source_attribution: "writ-native"
source_commit: null
position: 3
name: "Implementation"
description: |
  Write production code in dependency order against the approved skeletons; update capabilities.md checkboxes. No gate follows; verification and finishing are separate playbooks.
parent_playbook_id: PBK-PROC-WORK-WORKFLOW-001
edges: []
category: CAT-PROC-001
---

# Phase: Implementation

Non-retrievable structural node of PBK-PROC-WORK-WORKFLOW-001 (phase 3 of 3), surfaced via CONTAINS.
