---
rule_id: ENF-PROC-VERIFY-001
domain: process
severity: critical
scope: session
trigger: "When the agent attempts to mark a TodoWrite item complete, or when the session's Stop hook fires and completion claims exist without verification evidence."
statement: "Completion claims require fresh verification evidence in the same message. TodoWrite completion denied without verification_evidence set in session state."
violation: "Agent marks todo 'implement fetch()' as completed in TodoWrite without running pytest in the current message. Gate denies. Friction log records 'gate_denied: ENF-PROC-VERIFY-001'."
pass_example: "Agent runs pytest tests/test_api.py, output shows '1 passed', quotes the output, then TodoWrite marks todo completed with verification_evidence='pytest tests/test_api.py: 1 passed'."
enforcement: "writ-verify-before-claim.sh on Stop (work mode): surfaces (stderr, exit 1; loop-safe, never additionalContext on Stop) any artifact whose Gate 5 quality self-review scored < 3 and was not overridden. The PreToolUse TodoWrite gate was removed (#1) -- TodoWrite does not exist in CC 2.1.183 and TaskUpdate fires no hook. The 'tests must pass' half of verification is enforced by writ-run-pending-tests (ENF-TEST-001); unverified-claim phrasing by FRB-COMMS-002. NOTE: statement/violation/pass_example still reference TodoWrite -- flagged for human re-authoring."
rationale: "Completion claims without evidence erode user trust. Mechanical enforcement prevents the confidence-as-evidence failure mode."
mandatory: true
always_on: true
confidence: battle-tested
authority: human
last_validated: 2026-04-21
staleness_window: 365
evidence: peer-reviewed
mechanical_enforcement_path: "hooks/scripts/writ-verify-before-claim.sh"
rationalization_counters:
  - { thought: "I ran it earlier in the session, still counts.", counter: "Stale evidence. Code may have changed since. Run fresh." }
  - { thought: "Linter passed, that's enough.", counter: "Partial verification. Linter does not run the code." }
  - { thought: "Subagent said it's done.", counter: "See ANT-PROC-VERIFY-001. Subagent confidence is not evidence." }
red_flag_thoughts:
  - "Should be fine"
  - "Probably works"
  - "Looks right"
tags: [always-on, completion, enforcement, process, verification]
source_attribution: "writ-native"
source_commit: null
body: "Always-on rule — injected in universal bundle per plan Section 3.4."
edges:
  - { target: SKL-PROC-VERIFY-001, type: GATES }
category: CAT-PROC-001
---

# Rule: Verify before claiming complete

Mechanical via `writ-verify-before-claim.sh`. Always-on.
