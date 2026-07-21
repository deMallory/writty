---
skill_id: SKL-PROC-METHODOLOGY-CHECK-001
node_type: Skill
domain: process
severity: high
scope: session
trigger: "When Writ has surfaced methodology in your context (the --- WRIT RULES --- block, an injected rule, a retrieved Skill/Playbook/AntiPattern) and you are about to act -- especially if the task feels too simple to need it, or you are tempted to skip it to move faster."
statement: "Writ surfaces the relevant methodology for you automatically (the rag-inject hook); your job is to APPLY it. A surfaced rule is mandatory to address, not advisory mood music: comply, or state an explicit reason to override it. The failure mode in Writ is ignoring a retrieved rule, not failing to find one."
rationale: "Other skill systems fail at INVOCATION (forgetting to load the skill); Writ already retrieves automatically, so its failure mode is APPLICATION -- reading the injected rule and acting as if it were optional. Naming that as a discipline closes the gap retrieval alone cannot."
tags: [methodology, apply, surfaced-rules, discipline, rag-inject, process, skill]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-04
staleness_window: 365
evidence: peer-reviewed
always_on: false
source_attribution: "writ-native"
source_commit: null
edges:
  - { target: SKL-PROC-MODE-001, type: RELATED_TO }
  - { target: ENF-PROC-PRIORITY-001, type: TEACHES }
category: CAT-PROC-001
floor_modes: [conversation]
trigger_keywords: ["methodology", "retrieved rule", "override"]
---

# Skill: Apply the methodology Writ surfaces

Writ does the retrieval for you. The rule that lands in your context this turn was selected
because it is relevant -- treat it as a checklist item, not background noise.

- **A surfaced rule is not optional.** Read it. Either comply, or state an explicit, specific
  reason to override it this once. Silent skipping is the failure mode.
- **Apply before acting, not after.** The rule tells you HOW to do the task; do not finish the
  task your way and reconcile later.
- **Conflicts resolve by priority, not by convenience.** When a surfaced rule appears to clash
  with an explicit user or project instruction, `ENF-PROC-PRIORITY-001` governs: the user wins,
  and you note the override.
- **Set the mode first.** Mode (`SKL-PROC-MODE-001`) decides which gates and rules even apply;
  an unset mode means you are not yet seeing the right methodology.

"This task is too simple to need the rule" is a rationalization, not a judgment -- see the
companion `RAT-PROC-SKILLCHECK-001`.
