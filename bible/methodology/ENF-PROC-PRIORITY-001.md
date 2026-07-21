---
rule_id: ENF-PROC-PRIORITY-001
domain: process
severity: high
scope: session
trigger: "When a surfaced Writ methodology rule appears to conflict with an explicit user or project instruction (CLAUDE.md, AGENTS.md, or a direct request), and you must decide which to follow."
statement: "Advisory rule: instruction priority is user/project instructions (CLAUDE.md, direct requests) > Writ methodology nodes > default model behavior. When a surfaced rule conflicts with an explicit user instruction, the user wins; follow the instruction and note the override. Methodology overrides only the default behavior, never an explicit human instruction."
violation: "A user's CLAUDE.md says 'no Co-Authored-By trailer'; a surfaced convention suggests adding one. Agent follows the methodology and adds the trailer, overriding the explicit user instruction."
pass_example: "Same conflict: agent follows CLAUDE.md (no trailer) and notes 'overriding the trailer convention per your CLAUDE.md.' The methodology yields to the explicit instruction."
enforcement: "Advisory only -- surfaced when a conflict is detected in context. No deny condition; no reliable lexical detector for 'is this a conflict?'. Friction-logged when an explicit user instruction is overridden by methodology."
rationale: "The user is in control. Methodology exists to override the model's default habits, not to override the human's explicit choices. Without a stated hierarchy, an agent can 'follow the rule' straight past what the user actually asked for."
mandatory: false
always_on: false
confidence: peer-reviewed
authority: human
last_validated: 2026-06-04
staleness_window: 365
evidence: peer-reviewed
mechanical_enforcement_path: null
rationalization_counters:
  - { thought: "The methodology rule is the standard, so it wins.", counter: "Methodology beats DEFAULT behavior, not an explicit user instruction. The user wins; note the override." }
  - { thought: "The user probably didn't mean to contradict the rule.", counter: "Do not assume. The explicit instruction is the signal; if it truly seems mistaken, ask -- do not silently override it." }
tags: [advisory, instruction-priority, precedence, user-control, process]
source_attribution: "writ-native"
source_commit: null
body: "Advisory (empty mechanical_enforcement_path). Org-level instructions, where present, sit above user instructions; this rule governs the user-vs-methodology-vs-default axis."
edges: []
category: CAT-PROC-001
---

# Rule: Instruction priority (user > methodology > default)

Advisory (no mechanical path). When a surfaced rule conflicts with an explicit user or project
instruction, the instruction takes precedence -- follow it and note that you are overriding the
convention. Methodology overrides the model's default behavior, never the human's explicit
choice. Taught by `SKL-PROC-METHODOLOGY-CHECK-001`.
