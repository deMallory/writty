---
antipattern_id: ANT-PROC-TDD-006
node_type: AntiPattern
domain: process
severity: medium
scope: task
trigger: "In the GREEN phase of TDD: when adding configuration options, parameters, abstractions, or refactors that the current failing test does not require, or rationalizing 'might as well add it while I'm here.'"
statement: "GREEN over-engineering: writing more than the minimal code that makes the test pass -- speculative options, premature abstraction, or refactoring unrelated code during GREEN. The extra code has no failing test, so it is unverified behavior smuggled in under a passing one."
rationale: "GREEN's job is exactly enough code to turn the test green; every line beyond that is untested, unrequested, and harder to change later. Speculative generality (the options-bag, the extra hook) is the YAGNI failure the cycle exists to prevent. New behavior earns its own RED first."
tags: [anti-pattern, tdd, green, over-engineering, yagni, minimal, process]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-03
staleness_window: 365
evidence: peer-reviewed
source_attribution: "writ-native"
source_commit: null
counter_nodes: [PBK-PROC-TDD-001]
named_in: "writ-methodology:test-driven-development"
edges:
  - { target: PBK-PROC-TDD-001, type: COUNTERS }
category: CAT-DISC-001
---

# Anti-pattern: Over-engineering in GREEN

## The smell

The failing test needs a three-line function; the commit adds an options object, a strategy
hook, and a "while I'm here" refactor of the neighboring module. None of it is demanded by a
failing test.

## The rationalizations

- "Might as well add the options now, I'll need them later."
- "It's cleaner to abstract this up front."
- "I'm already in this file, I'll tidy it too."

## The counter

In GREEN, write the minimal code that makes the current test pass -- no more, no less. Defer
every extra capability to its own RED: if you want the option, write the failing test for it
first. Refactor only after green, and only with the tests still passing.
