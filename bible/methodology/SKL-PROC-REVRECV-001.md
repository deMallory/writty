---
skill_id: SKL-PROC-REVRECV-001
node_type: Skill
domain: communication
severity: high
scope: task
trigger: "When the agent receives code review feedback, a user correction, or external reviewer output and must respond."
statement: "Evaluate feedback technically before implementing. Verify against the codebase. Ask clarification on unclear items. Never respond with performative agreement."
rationale: "Performative agreement collapses the boundary between 'I heard you' and 'I agree.' Without technical verification, the agent implements things that may be wrong, making the review a liability rather than a check."
tags: [communication, external-review, process, technical-rigor, verification]
confidence: peer-reviewed
authority: human
last_validated: 2026-04-21
staleness_window: 365
evidence: peer-reviewed
source_attribution: "writ-native"
source_commit: null
edges:
  - { target: ENF-COMMS-001, type: TEACHES }
category: CAT-COMM-001
floor_modes: [review]
action_triggers: ["review-feedback"]
---

# Skill: Receive code review

Receiving review is technical evaluation, not compliance.

## Never-phrases

See `FRB-COMMS-001`. Gratitude, agreement, or implementation-intent BEFORE verification are all forbidden. State the fix or push back; do not perform agreement.

## The workflow

1. Read each item fully before reacting.
2. For each: restate the requirement, then verify against THIS codebase. Is the reviewer correct here? Is there something they missed?
3. If anything is unclear, STOP: clarify ALL items before implementing ANY. Items are often related, and a partial understanding ships the wrong change.
4. If you disagree, push back with technical reasoning, not defensiveness.
5. Only then implement, one item at a time, testing each.

## External reviewers: suggestions to evaluate, not orders

Before implementing an external suggestion, vet it: correct for THIS codebase? breaks existing behavior? is there a reason for the current implementation? does the reviewer have full context? If you cannot verify it, say so and ask. If it conflicts with a prior decision by your human partner, raise that first.

## YAGNI check

When a reviewer says "implement this properly," grep the codebase for actual usage first. If it is unused, propose removing it (YAGNI) rather than building it out. If it is used, implement it properly.

## Anti-pattern

Batch implementation of all review items without testing each. If any is wrong, all become suspect.
