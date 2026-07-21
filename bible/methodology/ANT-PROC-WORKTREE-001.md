---
antipattern_id: ANT-PROC-WORKTREE-001
node_type: AntiPattern
domain: process
severity: medium
scope: task
trigger: "When setting up isolated feature work: reaching for `git worktree add` while a native worktree tool (EnterWorktree, a /worktree command, a --worktree flag) is available, or creating a worktree without first checking whether the current checkout is already a linked worktree."
statement: "Fighting the harness: running raw `git worktree add` when a native worktree tool exists, or creating a nested worktree because you skipped the detect-existing-isolation check. Native tools own placement, branch creation, and cleanup; raw git behind their back leaves phantom state the harness cannot see, and a nested worktree compounds it."
rationale: "The native tool and the harness share state that `git worktree add` does not update, so manual worktrees become orphans the harness cannot clean up. Skipping Step 0 creates a worktree inside a worktree, doubling the confusion. Both are avoided by detecting isolation first and preferring native tools."
tags: [anti-pattern, worktree, isolation, native-tools, harness, process]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-03
staleness_window: 365
evidence: peer-reviewed
source_attribution: "writ-native"
source_commit: null
counter_nodes: [SKL-PROC-WORKTREE-001]
named_in: "writ-methodology:using-git-worktrees"
edges:
  - { target: SKL-PROC-WORKTREE-001, type: COUNTERS }
  - { target: TEC-PROC-WORKTREE-001, type: RELATED_TO }
category: CAT-DISC-001
---

# Anti-pattern: Fighting the harness on worktrees

## The smell

- `git worktree add ...` typed directly while `EnterWorktree` (or an equivalent native tool) is
  right there.
- A new worktree created without running Step 0 -- so it lands nested inside the worktree you
  were already in.

## The counter

Detect existing isolation first (`TEC-PROC-WORKTREE-001` Step 0): if already in a linked
worktree, do not create another. Then prefer the native worktree tool; fall back to
`git worktree add` only when none exists. Native tools keep placement, branch, and cleanup in
sync with the harness; raw git does not.
