---
playbook_id: PBK-PROC-ORCHESTRATOR-001
node_type: Playbook
domain: process
severity: high
scope: session
trigger: "When a Work-mode task is large enough to warrant per-phase sub-agent dispatch (typically >5 files) and the user has not requested single-session execution."
statement: "In Work mode with sub-agent dispatch, set the master's mode with --orchestrator (suppresses ~1400-token broad RAG injection per turn), then dispatch explore -> plan -> test-skeletons -> implement workers in the foreground. Master owns user approvals and gate creation; workers bypass mode/gate checks via is_subagent=true."
rationale: "Workers run on their own Writ sessions with their own RAG budget. Without --orchestrator the master accumulates ~3000+ tokens of duplicate rule injection per turn that it never needs. Foreground dispatch blocks the input prompt so the user cannot send mid-dispatch instructions that desync the pipeline."
tags: [process, work-mode, gates]
confidence: peer-reviewed
authority: human
last_validated: 2026-05-20
staleness_window: 180
evidence: "bin/lib/writ-session.py mode set work <id> --orchestrator sets is_orchestrator=true in the master cache. .claude/hooks/writ-rag-inject.sh checks IS_ORCHESTRATOR and emits a compact status line instead of the broad /query result."
always_on: false
source_attribution: writ-1.4.0-migration
source_commit: pending
phase_ids: [explore, plan, test, implement]
preconditions: [SKL-PROC-MODE-001, PBK-PROC-WORK-WORKFLOW-001]
dispatched_roles: [writ-explorer, writ-planner, writ-test-writer, writ-implementer]
edges:
  - { target: PBK-PROC-WORK-WORKFLOW-001, type: PRECEDES }
---

# Playbook: Orchestrator dispatch with named workers

- Set Work mode with the flag: `python3 $SKILL_DIR/bin/lib/writ-session.py mode set work $SESSION_ID --orchestrator`. The flag flips `is_orchestrator: true` in the session cache; `.claude/hooks/writ-rag-inject.sh` reads it and suppresses the broad `/query` injection on every UserPromptSubmit in the master session.
- Dispatch four workers in strict sequence: `writ-explorer` (gathers the codebase facts), `writ-planner` (writes plan.md + capabilities.md), `writ-test-writer` (lays down test skeletons), `writ-implementer` (writes production code and updates capabilities). Each worker gets its own Writ session and its own RAG budget.
- Spawn workers in the foreground (do not pass `run_in_background=true`). Foreground blocks the input prompt while the worker runs, which is the intended UX: the user cannot send mid-dispatch instructions that desync the pipeline.
- The master orchestrator owns all user approvals. After the planner returns, present the plan and wait for `approved` (the hook creates the gate). After the test-writer returns, present test class names and counts only and wait for the next `approved`. Workers never interact with the user.
- Workers bypass mode and gate checks. `.claude/hooks/writ-subagent-start.sh` sets `is_subagent: true` so workers can write freely without declaring a mode or tripping the phase-a / test-skeletons gates. Their PostToolUse RAG injection still fires.
- Skip the orchestrator pattern for small tasks (<5 files), Conversation / Debug / Review modes, and any session where the user explicitly requests single-session execution.
