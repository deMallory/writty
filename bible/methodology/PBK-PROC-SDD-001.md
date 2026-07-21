---
playbook_id: PBK-PROC-SDD-001
node_type: Playbook
domain: process
severity: high
scope: task
trigger: "When executing an approved plan with subagents: dispatch implementer per task, then the reviewer (spec-compliance pass, then code-quality pass), all in the same session."
statement: "Fresh subagent per task. The reviewer runs two ordered passes: spec compliance FIRST, then code quality. Ignore implementer success reports, verify independently."
rationale: "Fresh subagents avoid context pollution from the implementer's framing. The two-pass order (spec first) catches wrong-thing-built before polishing wrong thing. Independent verification prevents subagent rubber-stamping."
tags: [dispatch, playbook, process, subagents, two-pass-review]
confidence: peer-reviewed
authority: human
last_validated: 2026-04-21
staleness_window: 365
evidence: peer-reviewed
source_attribution: "writ-native"
source_commit: null
phase_ids: []
preconditions: [SKL-PROC-PLAN-001]
dispatched_roles:
  - ROL-IMPLEMENTER-001
  - ROL-REVIEWER-001
edges:
  - { target: ENF-PROC-SDD-001, type: TEACHES }
  - { target: ROL-REVIEWER-001, type: DISPATCHES }
  - { target: ROL-IMPLEMENTER-001, type: DISPATCHES }
  - { target: SKL-PROC-EXEC-001, type: TEACHES }
category: CAT-PROC-DISPATCH-001
trigger_keywords: ["dispatch", "subagent", "spec-compliance", "code-quality"]
---

# Playbook: Subagent-driven development

## Per task

1. Fresh implementer subagent with full task context (plan excerpt + related files).
2. Fresh reviewer subagent: spec-compliance pass first; if it passes, the code-quality pass. If spec fails, back to implementer with the diff.
3. Implementer fixes code-quality issues if any. Re-review.
4. Mark task complete — and verify with `SKL-PROC-VERIFY-001` before believing the implementer.

## Implementer status (controller handling)

The implementer (`ROL-IMPLEMENTER-001`) ends every dispatch with one status. Handle it,
do not rubber-stamp it:

- **DONE** -> proceed to review (spec-compliance pass, then code-quality pass). Verify independently anyway.
- **DONE_WITH_CONCERNS** -> resolve the concerns first: correctness and scope concerns block
  review; a noted file-growth concern feeds the code-quality pass. Do not advance the task
  until each concern is closed or consciously accepted.
- **NEEDS_CONTEXT** -> supply the missing context, then re-dispatch a fresh implementer. The
  gap was yours, not the model's.
- **BLOCKED** -> branch on the reason: missing context -> add it and re-dispatch; reasoning
  dead end -> re-dispatch with a more capable model; task too large -> split it and dispatch
  the pieces; plan is wrong -> return to planning, do not patch around it.

Never re-dispatch the same model on the same task unchanged -- change the context, the model,
or the task size, or you will get the same result. Run tasks continuously: do not pause for
confirmation between independent tasks; only the workflow's own gates stop you.

## Anti-patterns

- Wrong review order (code-quality before spec): see `ANT-PROC-SDD-001`.
- Self-review by implementer: forbidden.
- Parallel implementer dispatch: forbidden (conflicts).
- Re-dispatching a BLOCKED task unchanged: forbidden (same input, same failure).
