<!-- RULE START: ENF-COMMS-001 -->
## Rule ENF-COMMS-001

**Domain**: communication
**Severity**: High
**Scope**: Session
**Mandatory**: false

### Trigger
Any time the agent responds to code review, user correction, or technical evaluation input, and the response text contains a forbidden phrase from FRB-COMMS-001 or FRB-COMMS-002.

### Statement
Advisory rule: agent responses must not contain performative agreement or unverified success claims. Lexical match against FRB-COMMS forbidden_phrases surfaces violation to friction log.

### Violation
Agent responds 'You're absolutely right! Great point!' to reviewer feedback. Matches FRB-COMMS-001 forbidden_phrases. Friction-log records ENF-COMMS-001 violation.

### Pass
Agent responds 'Let me verify that claim against the codebase. Running the check... Output: <quote>. Based on that, your point holds.' No forbidden phrase. No violation.

### Enforcement
Advisory only — post-response pattern match. No pre-response deny (blocking every turn on forbidden-phrase detection would cause false positives). Violations collected for Phase 5 review.

### Rationale
Lexical phrase match has false-positive risk in legitimate contexts (e.g., paraphrase of reviewer's argument). Blocking would create friction; advisory+telemetry lets Phase 5 rubric-refine the blocklist.

<!-- RULE END: ENF-COMMS-001 -->
