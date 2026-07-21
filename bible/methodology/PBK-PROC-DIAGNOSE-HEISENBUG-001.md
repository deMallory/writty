---
playbook_id: PBK-PROC-DIAGNOSE-HEISENBUG-001
node_type: Playbook
domain: process
severity: high
scope: task
trigger: "When a failure does not reproduce reliably: races, time- or load-dependent bugs, order-dependent state pollution, or production-data-shape-dependent failures."
statement: "Reproduction is probabilistic, not binary. Never treat a single non-reproduction as falsification; establish a failure rate, gather timing/ordering evidence, hunt shared mutable state, amplify the rate, and falsify against the rate."
rationale: "Nondeterministic failures are the class where confident-wrong diagnosis is most dangerous, because one clean run feels like proof. Working from a failure RATE rather than a single run is what separates a diagnosis from a coincidence."
tags: [debugging, heisenbug, concurrency, race-condition, nondeterminism, diagnose, playbook, process]
confidence: peer-reviewed
authority: human
last_validated: 2026-05-29
staleness_window: 365
evidence: peer-reviewed
source_attribution: "writ-native"
source_commit: null
phase_ids: []
preconditions: []
dispatched_roles: []
edges: []
category: CAT-PROC-001
trigger_keywords: ["heisenbug", "intermittent", "race"]
---

# Playbook: Diagnose a heisenbug (intermittent / nondeterministic failure)

## When this applies

A failure that does not reproduce reliably: races, time- or load-dependent bugs,
order-dependent test pollution, and failures that depend on a production data shape.
This is the class where confident-wrong diagnosis is most dangerous.

## Ordering (reproduction is probabilistic, not binary)

1. **Do not treat a single non-reproduction as falsification.** One clean run proves
   nothing. Establish a failure RATE first: run N times and record successes and
   failures.
2. **Gather statistical and timing evidence.** Capture timestamps, thread/coroutine
   identifiers, ordering, and inputs across many runs. Compare failing runs to
   passing runs -- what differs?
3. **Hunt shared mutable state and ordering assumptions.** Most heisenbugs are
   concurrent access to shared state, an unsynchronized initialization, a missing
   await, a global/singleton, or a test leaking state into the next.
4. **Amplify the failure rate deliberately.** Add load, parallelism, or delays at the
   suspect window so the bug becomes near-deterministic -- then it is debuggable.
5. **Falsify against the rate, not a single run (mandatory).** "If the cause is the
   unsynchronized cache write, forcing two concurrent writers should push the failure
   rate toward 100%." Confirm the rate moves as predicted before fixing.

## Red flags

- "It passed when I reran it, so it is fixed." A passing run is not a fix; the rate is.
- "Add a retry or a sleep and move on." That hides the race; the next change reopens it.
- Claiming a root cause from a single observation of a nondeterministic failure.
