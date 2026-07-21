---
technique_id: TEC-PROC-VERIFY-EVIDENCE-MAP-001
node_type: Technique
domain: process
severity: high
scope: task
trigger: "When about to claim a status -- tests pass, build succeeds, bug fixed, regression test works, an agent completed, requirements met -- and you need to know exactly which evidence proves THAT claim, and which weaker signal does not."
statement: "Each claim type has one piece of evidence that proves it; a related-but-weaker signal does not substitute. Map the claim to its proof before asserting: tests pass -> test output with 0 failures; build succeeds -> build exit 0; bug fixed -> the original symptom now passes; regression test works -> a red-green cycle; agent completed -> the VCS diff; requirements met -> a line-by-line checklist."
rationale: "The verify gate (SKL-PROC-VERIFY-001) says 'evidence before claims'; the recurring failure is accepting the WRONG evidence -- a passing linter for a build, an agent's success report for an actual diff, one green run for a regression test. Naming the required proof per claim closes that gap."
tags: [verification, evidence, claims, partial-verification, process, technique]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-04
staleness_window: 365
evidence: peer-reviewed
source_attribution: "writ-native"
source_commit: null
edges:
  - { target: SKL-PROC-VERIFY-001, type: RELATED_TO }
category: CAT-PROC-001
trigger_keywords: ["evidence", "tests pass", "build succeeds", "claim"]
---

# Technique: Map each claim to the evidence that proves it

Before asserting a status, match the claim to its required proof. The middle column is the only
thing that earns the claim; the right column is the substitute that does not.

| Claim | Required evidence | NOT sufficient |
|-------|-------------------|----------------|
| Tests pass | test command output, 0 failures | "should pass", a previous run |
| Build succeeds | build command, exit 0 | linter clean (linter != compiler) |
| Bug fixed | the original symptom now passes | "code changed, assume fixed" |
| Regression test works | a red-green cycle (revert fix -> it fails) | passes once |
| Agent completed | the VCS diff shows the changes | the agent's success report |
| Requirements met | line-by-line checklist vs the spec | "tests pass, so it's done" |

Partial verification proves nothing for the unchecked part. If you cannot produce the required
evidence, state the actual status, not the hoped-for one (`SKL-PROC-VERIFY-001`).
