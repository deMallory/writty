---
playbook_id: PBK-PROC-DIAGNOSE-FAILING-TEST-001
node_type: Playbook
domain: process
severity: high
scope: task
trigger: "When a deterministic unit or integration test fails (assertion, error, or wrong value) and reproduces on every run."
statement: "A reproducible failing test already discharges evidence, narrowing, and reproduction in one artifact. Read expected-vs-actual, follow the code path, form one hypothesis from the discrepancy, and falsify before fixing."
rationale: "The failing test is the strongest, cheapest diagnostic artifact there is; the common waste is re-gathering evidence it already provides, or manufacturing a contrived second source to satisfy a triangulation reflex."
tags: [debugging, testing, failing-test, assertion, diagnose, playbook, process]
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
trigger_keywords: ["failing test", "assertion", "reproducible", "falsify"]
---

# Playbook: Diagnose a failing test

## When this applies

A deterministic unit or integration test that fails and reproduces on every run.
For intermittent/flaky failures use PBK-PROC-DIAGNOSE-HEISENBUG-001 instead.

## Ordering (one artifact discharges three gates)

A reproducible failing test already gives you Evidence, Narrowing, **and**
Reproduction at once -- do not re-gather them.

1. **Read the assertion: expected vs actual.** The exact wrong value is the sharpest
   possible evidence. Name the precise discrepancy.
2. **Follow the code path the test exercises.** From the test's inputs, trace to
   where the actual value is produced.
3. **Form one hypothesis from the discrepancy.** The gap between expected and actual
   usually names the defect directly: off-by-one, wrong branch, stale state, wrong
   boundary.
4. **Falsify before fixing (mandatory).** Predict the value if the hypothesis holds;
   add a focused assertion or log at the suspect line and run the test to confirm.
   Then make the minimal fix and watch the test pass.

## Do not manufacture a second source

Triangulation's "two independent sources" is already satisfied here by the test plus
the code path. Do not invent a contrived second confirmation -- a failing assertion
with the exact wrong value is single-source conclusive.

## Red flags

- "Edit the test until it passes." Unless the test encodes a wrong expectation, fix the code, not the test.
- "Add a sleep or retry to stabilize it." That signals a heisenbug; switch playbooks.
- Rewriting large sections before confirming which line produces the wrong value.
