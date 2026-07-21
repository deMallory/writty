---
skill_id: SKL-PROC-TDD-DESIGN-FEEDBACK-001
node_type: Skill
domain: process
severity: medium
scope: task
trigger: "When a test is hard to write -- you need to mock everything, wire up many dependencies, reach into internals or add a test-only getter, or you cannot tell what to assert -- before blaming the test framework or weakening the test."
statement: "Difficulty writing the test is design feedback, not a testing nuisance. Need to mock everything = too many collaborators; heavy setup = tight coupling; can't tell what to assert = no single responsibility; need test-only access = missing public interface. Fix the design the test points at, not the test."
rationale: "The RED phase is a design probe, not just regression coverage. A test that is painful to write is reporting a real defect in the code's shape; silencing the pain with mocks or internal hooks hides the design problem instead of fixing it. This is the cheapest design review available."
tags: [tdd, design, test-first, coupling, mocking, design-feedback, process, skill]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-03
staleness_window: 365
evidence: peer-reviewed
always_on: false
source_attribution: "writ-native"
source_commit: null
edges:
  - { target: PBK-PROC-TDD-001, type: RELATED_TO }
  - { target: ANT-PROC-TDD-002, type: RELATED_TO }
  - { target: ANT-PROC-TDD-003, type: RELATED_TO }
category: CAT-PROC-001
trigger_keywords: ["design feedback", "hard to write", "mocking"]
---

# Skill: The test is giving you design feedback

When the RED step fights you, read the resistance as a signal about the design, not the test:

| The test is hard because... | The design is telling you... |
|---|---|
| you must mock everything to isolate it | too many collaborators -- split the responsibilities |
| setup needs many dependencies | tight coupling -- inject or narrow the dependency surface |
| you cannot tell what to assert | the unit has no single, clear responsibility |
| you must reach internals or add a test-only getter | the public interface is missing something its real callers also need |

The fix is the design, not the test. Make the collaborator injectable, split the unit, or expose
the behavior real users need -- then the test becomes easy and the code becomes better.

A test you can only pass by mocking the subject (`ANT-PROC-TDD-002`) or by reaching internals
(`ANT-PROC-TDD-003`) is this same signal in its acute form. "Hard to test" is never a reason to
skip or weaken the test; it means hard to use.
