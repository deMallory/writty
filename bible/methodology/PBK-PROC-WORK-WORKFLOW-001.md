---
playbook_id: PBK-PROC-WORK-WORKFLOW-001
node_type: Playbook
domain: process
severity: high
scope: session
trigger: "When the session mode is set to Work and a feature, refactor, or bug-fix task is about to begin."
statement: "Work mode runs three sequential gates: (1) enter /plan, write plan.md to project root with the four required sections, exit /plan, present, wait for the user to type 'approved'. (2) Write test skeleton files to disk, present class names and counts only, wait for 'approved'. (3) Implement. Never write non-test files before the test-skeletons gate is approved."
rationale: "The three-gate sequence is the contract that lets the user inspect the plan before any code is committed and the tests before any production code lands. Skipping a gate means the user reviews a finished implementation rather than a design they could still steer."
tags: [process, work-mode, gates]
confidence: peer-reviewed
authority: human
last_validated: 2026-05-20
staleness_window: 180
evidence: "bin/lib/writ-session.py defines the phase-a and test-skeletons gate files under .claude/gates/. .claude/hooks/writ-pre-write-dispatch.sh denies writes that violate the sequence."
always_on: false
source_attribution: writ-1.4.0-migration
source_commit: pending
phase_ids:
  - PHA-WORK-001
  - PHA-WORK-002
  - PHA-WORK-003
preconditions: [SKL-PROC-MODE-001]
dispatched_roles: []
edges:
  - { target: PBK-PROC-TDD-001, type: PRECEDES }
  - { target: PHA-WORK-001, type: CONTAINS }
  - { target: PHA-WORK-002, type: CONTAINS }
  - { target: PHA-WORK-003, type: CONTAINS }
category: CAT-PROC-001
floor_modes: [work]
trigger_keywords: ["work mode", "gates", "test skeleton", "plan.md", "approved"]
---

# Playbook: Work-mode three-gate pipeline

Three sequential gates. Each phase's content is a CONTAINS-linked Phase node:

1. `PHA-WORK-001` — Plan: write plan.md (four sections) + capabilities.md, present, await `approved`.
2. `PHA-WORK-002` — Test skeletons: write tests, present class names + counts only, await `approved`.
3. `PHA-WORK-003` — Implementation: write production code in dependency order, check off capabilities.

- Gate creation is automatic, not manual. When the user types `approved`, a hook creates the gate file under `.claude/gates/`. Never run commands to create gate files yourself; never `touch phase-a.approved`.
- Phase boundaries are mechanical. The phase-a gate denies every non-`plan.md` write before approval; the test-skeletons gate denies every non-test write before approval. A denial applies to ALL files, not just the one denied (see SKL-PROC-WRIT-FAILURE-001).
- The /plan UI message `User approved Claude's plan` is format-validation only, not code-write approval. The session state machine in `bin/lib/writ-session.py` waits for the explicit user `approved` in chat, which the hook converts into a gate file.
