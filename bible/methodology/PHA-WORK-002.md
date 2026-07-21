---
phase_id: PHA-WORK-002
node_type: Phase
domain: process
scope: session
trigger: "Second gate of PBK-PROC-WORK-WORKFLOW-001. Fires after the plan (PHA-WORK-001) is approved."
statement: "Write all test skeleton files to disk, then present only 'Test skeletons written: ClassName (N tests). Say approved to proceed.' Do not reproduce method names. Stop and wait for 'approved' before any non-test write."
rationale: "Reviewing tests before production code lets the user see the intended behavior contract before it is implemented; it is the TDD RED gate applied to the workflow."
tags: [process, work-mode, test-skeletons, phase, gate, tdd]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-02
staleness_window: 180
evidence: peer-reviewed
source_attribution: "writ-native"
source_commit: null
position: 2
name: "Test skeletons"
description: |
  Write the test skeleton files; present class names and counts only (the user can read the files). The test-skeletons gate denies every non-test write until the user types "approved".
parent_playbook_id: PBK-PROC-WORK-WORKFLOW-001
edges: []
category: CAT-PROC-001
---

# Phase: Test skeletons

Non-retrievable structural node of PBK-PROC-WORK-WORKFLOW-001 (gate 2 of 3), surfaced via CONTAINS.
Advance criterion: user types "approved" (the hook creates the test-skeletons gate file).
