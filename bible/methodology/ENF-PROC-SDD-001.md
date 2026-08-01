---
rule_id: ENF-PROC-SDD-001
domain: process
severity: high
scope: task
trigger: "When the reviewer evaluates a diff and would judge code-quality before confirming spec-compliance."
statement: "Within a single review, the spec-compliance pass must complete (and pass) before the code-quality pass. Spec-first catches wrong-thing-built before effort is spent polishing it."
violation: "The reviewer reports code-quality findings without first confirming the diff implements the spec."
pass_example: "The reviewer runs Pass 1 (spec compliance); only after it passes does it run Pass 2 (code quality)."
enforcement: "Agent-prompt discipline in writ-reviewer (two ordered passes). No mechanical gate."
rationale: "Spec-first catches wrong-thing-built. Polishing wrong code is wasted work."
mandatory: false
always_on: false
confidence: peer-reviewed
authority: human
last_validated: 2026-04-21
staleness_window: 365
evidence: peer-reviewed
rationalization_counters:
  - { thought: "Code-quality review is fast, let me start in parallel.", counter: "Parallel + out-of-order = polishing unknown correctness. Sequential, spec first." }
  - { thought: "Self-review by implementer is enough.", counter: "Implementer bias. Fresh reviewer is the whole point of SDD." }
red_flag_thoughts:
  - "Save time by parallel reviews"
  - "Skip spec review, it looks right"
tags: [enforcement, process, review-order, sdd]
source_attribution: "writ-native"
source_commit: null
body: ""
edges:
  - { target: PBK-PROC-SDD-001, type: GATES }
category: CAT-PROC-001
---

# Rule: Spec-compliance pass before code-quality pass

Advisory. Enforced by agent-prompt discipline in `writ-reviewer` (ROL-REVIEWER-001): the
reviewer runs Pass 1 (spec compliance) and only proceeds to Pass 2 (code quality) if it passes.
No mechanical gate.
