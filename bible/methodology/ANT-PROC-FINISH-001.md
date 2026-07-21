---
antipattern_id: ANT-PROC-FINISH-001
node_type: AntiPattern
domain: process
severity: medium
scope: task
trigger: "When wrapping up a completed branch: improvising a custom merge/cleanup flow, offering options beyond the fixed four, deleting a branch before removing its worktree, removing a worktree the workflow did not create, or skipping post-merge test re-verification."
statement: "Finish-time improvisation is an anti-pattern. Present exactly the four fixed options (merge+cleanup, push+PR, keep, discard); never invent a fifth path. Order cleanup merge -> remove worktree -> delete branch (never delete a branch whose worktree still exists). Only remove worktrees this workflow created. Re-run tests on the merged result before declaring done."
rationale: "A fixed option set and a fixed cleanup order eliminate novel-path improvisation when attention is lowest (work feels done). Wrong cleanup order orphans worktrees or loses commits; removing un-owned worktrees destroys others' state; skipping post-merge verification ships an unverified merge."
tags: [anti-pattern, branch, cleanup, finish, merge, process, worktree]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-02
staleness_window: 365
evidence: peer-reviewed
source_attribution: "writ-native"
source_commit: null
counter_nodes: [PBK-PROC-FINISH-001]
named_in: "writ-methodology:finishing-a-development-branch"
edges:
  - { target: PBK-PROC-FINISH-001, type: COUNTERS }
category: CAT-DISC-001
---

# Anti-pattern: Finish-time improvisation

Non-retrievable companion to PBK-PROC-FINISH-001. Captures the finish-time mistakes the
playbook's fixed four-option flow and ordered cleanup exist to prevent.
