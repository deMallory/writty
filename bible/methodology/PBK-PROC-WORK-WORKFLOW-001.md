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
phase_ids: [planning, testing, implementation]
preconditions: [SKL-PROC-MODE-001]
dispatched_roles: []
edges:
  - { target: SKL-PROC-WRIT-FAILURE-001, type: TEACHES }
  - { target: ENF-PROC-PLAN-001, type: GATES }
  - { target: PBK-PROC-TDD-001, type: PRECEDES }
---

# Playbook: Work-mode three-gate pipeline

- Phase 1 (plan). Enter `/plan`, write `plan.md` to the project root WHILE STILL IN /plan mode and BEFORE calling ExitPlanMode. The file must contain the four canonical sections: `## Files`, `## Analysis`, `## Rules Applied`, `## Capabilities`. Also write `capabilities.md` as the checklist surface. Exit /plan, present a summary in chat, then stop and wait for the user to type `approved`.
- Phase 2 (test skeletons). After approval, write all test skeleton files to disk. Present only `"Test skeletons written: ClassName (N tests), ClassName (N tests). Say approved to proceed."` Do not reproduce method names or descriptions - the user can read the files. Stop and wait for `approved`.
- Phase 3 (implementation). Only after the test-skeletons gate is approved may non-test files be written. Implement files in dependency order; update `capabilities.md` to check off completed items as `[x]`.
- Gate creation is automatic, not manual. When the user types `approved`, a hook creates the gate file under `.claude/gates/`. Never run commands to create gate files yourself; never `touch phase-a.approved`.
- Phase boundaries are mechanical. The phase-a gate denies every non-`plan.md` write before approval; the test-skeletons gate denies every non-test write before approval. A denial applies to ALL files, not just the one denied (see SKL-PROC-WRIT-FAILURE-001).
- The /plan UI message `User approved Claude's plan` is format-validation only, not code-write approval. The session state machine in `bin/lib/writ-session.py` waits for the explicit user `approved` in chat, which the hook converts into a gate file.
