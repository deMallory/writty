---
technique_id: TEC-PROC-RED-VERIFY-001
node_type: Technique
domain: process
severity: medium
scope: task
trigger: "When running a freshly written test for the first time (the RED step) and it does not fail cleanly -- it errors with ImportError, NameError, a typo, a missing fixture, or a collection error -- or you are about to call RED 'done' without reading the failure."
statement: "A test that errors has not achieved RED. RED means the test fails at the assertion, with the expected message, because the behavior is missing -- not because of a typo, import error, or missing fixture. Fix the error and re-run until it fails for the right reason; only then write code."
rationale: "Watching the test fail for the right reason is the only evidence the test exercises the intended behavior. An erroring test proves nothing -- the assertion never ran -- so implementing against it is implementing against an unverified test. ANT-PROC-TDD-001 covers the other failure: a test that passes immediately."
tags: [tdd, red, verify, assertion, error, test-first, process, technique]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-03
staleness_window: 365
evidence: peer-reviewed
source_attribution: "writ-native"
source_commit: null
edges:
  - { target: PBK-PROC-TDD-001, type: RELATED_TO }
  - { target: ANT-PROC-TDD-001, type: RELATED_TO }
category: CAT-PROC-001
trigger_keywords: ["RED", "assertion", "ImportError", "fails"]
---

# Technique: Verify RED for the right reason

Run the new test and read the output before writing any code. Confirm all three:

1. **It fails, not errors.** An `ImportError`, `NameError`, missing fixture, or collection error
   means the assertion never executed -- the harness is broken, not the behavior unverified.
   Fix the error and re-run until the test reaches its assertion.
2. **It fails at the assertion**, with the expected-vs-actual you predicted.
3. **It fails because the behavior is missing**, not because of a typo in the test.

If it passes on first run instead, you are testing existing or vacuous behavior: see
`ANT-PROC-TDD-001`. Either way, do not proceed to GREEN until you have watched it fail for the
right reason -- that failure is the evidence the test works.
