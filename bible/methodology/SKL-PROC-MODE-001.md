---
skill_id: SKL-PROC-MODE-001
node_type: Skill
domain: process
severity: medium
scope: session
trigger: "When a new Claude Code session begins, before the first tool call that could write or modify files."
statement: "Before any code generation, set the session mode by running the 'mode set' command the RAG inject hook prints. Mode determines whether code generation is allowed (Work only) and which gates apply (phase-a + test-skeletons for Work; none for the other three)."
rationale: "Mode is the root of Writ's gate machine. Until it is set, the phase-a gate denies every Write/Edit (except plan.md). Setting the mode unblocks the correct workflow for the task at hand and tells later hooks which rules and gates to apply."
tags: [process, mode, workflow]
confidence: peer-reviewed
authority: human
last_validated: 2026-05-20
staleness_window: 180
evidence: "bin/lib/writ-session.py implements the mode state machine; .claude/hooks/writ-rag-inject.sh prints the exact mode-set command when no mode is detected."
always_on: false
source_attribution: writ-1.4.0-migration
source_commit: pending
edges: []
---

# Skill: Set the session mode before generating code

- Mode declaration is mechanical, not advisory. The RAG inject hook prints the exact `python3 $SESSION_HELPER mode set <mode> $SESSION_ID` invocation when `current_mode` is empty in the cache; copy it and run it before any tool call that writes.
- The four modes have non-overlapping intents. Conversation, Debug, and Review forbid code generation; Work is the only mode that engages the plan / test-skeletons / implementation gate sequence.
- The phase-a gate in `bin/lib/writ-session.py` denies every `Write`/`Edit` (except `plan.md`) while mode is unset, so skipping this step does not produce a silent regression - it produces an immediate denial with `[ENF-GATE-PLAN]`.
- Re-declare mode whenever the task changes shape. A Debug session that uncovers a fix should switch to Work before writing the patch; the rag-inject hook will surface the gate state for the new mode.
- If the Writ server is unreachable, hooks fall back gracefully but the mode reminder still prints on stderr; declare mode anyway so a later server recovery does not strand the session in an undeclared state.
