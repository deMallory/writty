---
rationalization_id: RAT-PROC-SKILLCHECK-001
node_type: Rationalization
domain: process
scope: task
trigger: "When the agent has a surfaced rule in context but is about to act without addressing it, telling itself the task is too small, too obvious, or too urgent to bother."
statement: "'This task is too simple to need the surfaced rule, I'll just do it quickly.' The counter: a surfaced rule was retrieved because it is relevant; simple tasks become complex, and 'I already know this' is not the same as applying it."
rationale: "The most common way a surfaced rule gets ignored in Writ is not disagreement but dismissal -- the task feels too small to warrant the rule. Naming the bypass thought lets the agent catch itself."
tags: [rationalization, methodology, skill-check, discipline, process]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-04
staleness_window: 365
evidence: peer-reviewed
source_attribution: "writ-native"
source_commit: null
thought: "This is just a simple task / I'll do it quickly / the rule is overkill / I already know this."
counter: "A surfaced rule was retrieved because it is relevant; apply it or state an explicit reason to override. Simple tasks become complex, and knowing the concept is not applying the rule."
attached_to: SKL-PROC-METHODOLOGY-CHECK-001
edges:
  - { target: SKL-PROC-METHODOLOGY-CHECK-001, type: ATTACHED_TO }
  - { target: SKL-PROC-METHODOLOGY-CHECK-001, type: COUNTERS }
category: CAT-DISC-001
---

# Rationalization: The task is too simple to need the rule

Non-retrievable. Surfaces via bundle expansion when `SKL-PROC-METHODOLOGY-CHECK-001` is
retrieved. The bypass is dismissal ("too simple", "too quick", "overkill", "I already know
this"), not disagreement -- and dismissal is how a relevant rule gets silently skipped.
