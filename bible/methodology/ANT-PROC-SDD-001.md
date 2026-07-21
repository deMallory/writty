---
antipattern_id: ANT-PROC-SDD-001
node_type: AntiPattern
domain: process
severity: high
scope: task
trigger: "When the reviewer judges code-quality before confirming spec-compliance, or skips the spec-compliance pass entirely."
statement: "Wrong review order: running the code-quality pass before the spec-compliance pass wastes effort polishing code that implements the wrong spec."
rationale: "Spec-compliance is the coarser filter — it catches 'built the wrong thing.' Code-quality is the finer filter — it polishes 'built the right thing.' Inverting the order polishes wrongness."
tags: [anti-pattern, process, review-order, sdd, spec-first]
confidence: peer-reviewed
authority: human
last_validated: 2026-04-21
staleness_window: 365
evidence: peer-reviewed
source_attribution: "writ-native"
source_commit: null
counter_nodes: [PBK-PROC-SDD-001, ENF-PROC-SDD-001]
named_in: "writ-methodology:subagent-driven-development"
edges:
  - { target: ENF-PROC-SDD-001, type: COUNTERS }
  - { target: PBK-PROC-SDD-001, type: COUNTERS }
category: CAT-DISC-001
---

# Anti-pattern: Wrong review order in SDD

## Counter

Spec compliance first, always. If the spec pass fails: back to implementer. Only when the spec pass passes does the code-quality pass run. See `PBK-PROC-SDD-001`.
