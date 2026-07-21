---
technique_id: TEC-PROC-FILE-STRUCTURE-001
node_type: Technique
domain: process
severity: medium
scope: task
trigger: "When planning a change and deciding which files to create or modify -- whether to split a unit into multiple files, put it in one, or organize by feature vs by technical layer -- before locking the decomposition into tasks."
statement: "Before decomposing a plan into tasks, design the file structure: one clear responsibility per file, kept small enough to hold in context; split by responsibility, not by technical layer (files that change together live together). In an existing codebase, follow its established patterns -- do not unilaterally restructure; only split a file you are already modifying when it has grown unwieldy."
rationale: "Decomposition decisions are locked in at plan time; an honest file structure makes every later task self-contained, and edits are more reliable on focused files you can reason about whole. Organizing by technical layer scatters one change across many files; organizing by responsibility keeps it local."
tags: [planning, file-structure, decomposition, responsibility, coupling, process, technique]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-03
staleness_window: 365
evidence: peer-reviewed
source_attribution: "writ-native"
source_commit: null
edges:
  - { target: PBK-PROC-PLAN-001, type: RELATED_TO }
  - { target: SKL-PROC-TDD-DESIGN-FEEDBACK-001, type: RELATED_TO }
category: CAT-PROC-001
trigger_keywords: ["file structure", "decomposition", "responsibility"]
---

# Technique: Design the file structure before decomposing

Map which files a change touches, then shape them deliberately:

- **One responsibility per file.** A file should have a single clear job and a well-defined
  interface. You reason best about code you can hold in context at once, and edits are more
  reliable on focused files -- prefer several small files over one that does too much.
- **Split by responsibility, not by technical layer.** Files that change together should live
  together. Layer-based splits (all "controllers" here, all "models" there) scatter one logical
  change across the tree; responsibility-based splits keep it local.
- **In an existing codebase, follow the established patterns.** Do not unilaterally restructure.
  If a file you are already modifying has grown unwieldy, a split is reasonable -- put it in the
  plan as its own task rather than improvising mid-implementation.

If a unit is hard to give one responsibility, the test will fight you too: see
`SKL-PROC-TDD-DESIGN-FEEDBACK-001`. The structure you choose here informs the task breakdown in
`PBK-PROC-PLAN-001`.
