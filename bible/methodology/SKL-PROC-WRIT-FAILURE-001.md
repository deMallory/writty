---
skill_id: SKL-PROC-WRIT-FAILURE-001
node_type: Skill
domain: process
severity: high
scope: session
trigger: "When a Writ gate denies a write, when the /plan UI announces user approval, or when test skeletons have just been written to disk."
statement: "Handle Writ workflow edge cases as follows. Gate denials with [ENF-GATE-PLAN] or [ENF-GATE-TEST] apply to ALL files, not just the denied one: STOP, do not retry. The /plan UI 'User approved Claude's plan' is format-validation only, not code-write approval; still wait for the user to type 'approved' in chat. Write plan.md to the project root WHILE STILL IN /plan mode, BEFORE calling ExitPlanMode. After test skeletons, present only: 'Test skeletons written: ClassName (N tests). Say approved to proceed.' -- never reproduce method names."
rationale: "These are the failure modes that look like normal progress from the agent's perspective. Each one trips up the gate machine in a different way; naming them lets retrieval surface the right correction at the right trigger."
tags: [process, gates, failure-modes]
confidence: peer-reviewed
authority: human
last_validated: 2026-05-20
staleness_window: 180
evidence: "bin/lib/writ-session.py enforces the gate state machine. .claude/hooks/writ-pre-write-dispatch.sh emits [ENF-GATE-PLAN] and [ENF-GATE-TEST] denials. The /plan UI message is platform-side and does not interact with the gate files under .claude/gates/."
always_on: false
source_attribution: writ-1.4.0-migration
source_commit: pending
edges:
  - { target: PBK-PROC-WORK-WORKFLOW-001, type: TEACHES }
---

# Skill: Writ workflow edge cases

- Gate denials are global, not per-file. A `[ENF-GATE-PLAN]` or `[ENF-GATE-TEST]` denial means every subsequent write is denied until the right gate is approved. Stop, read the denial message, follow its instructions. Do not retry the same write or batch writes hoping one slips through.
- The /plan UI string `User approved Claude's plan` is format validation, not code-write approval. The platform shows it when `/plan` exits with a valid plan structure; the Writ gate file is only created when the user types `approved` in chat. Always wait for the chat-side approval before writing non-`plan.md` files.
- Write `plan.md` to the project root WHILE STILL IN /plan mode and BEFORE calling ExitPlanMode. The ExitPlanMode hook validates the file on exit; if it is missing, the gate cannot open. The /plan mode also keeps its own internal copy - the double-write is expected.
- After writing test skeleton files, present only this sentence: `"Test skeletons written: ClassName (N tests), ClassName (N tests). Say approved to proceed."` Do not reproduce method names, do not list test descriptions, do not paste file contents. The user can read the files; the presentation is a confirmation, not a recap.
- Phase boundaries are absolute. Never write non-test files before the test-skeletons gate is approved. Never batch writes across phase boundaries (plan -> test -> implementation): each phase ends with a wait state, not a continuation.
