---
skill_id: SKL-PROC-DISPATCH-001
node_type: Skill
domain: process
severity: high
scope: session
trigger: "When dispatching a sub-agent (the Task tool) for any Writ-governed task -- explore, plan, write tests, implement, or review -- regardless of whether the full orchestrator pipeline is running."
statement: "Dispatch the named Writ role that matches the job, never the built-in `Explore` or `general-purpose` agent. Generic agents are the exception (a task with no matching role), not the default: they run without the role prompt and outside Writ's session/gate governance."
rationale: "The default failure mode is reaching for Claude's built-in `Explore`/`general-purpose` agents because they are top-of-mind, which silently routes governed work around the role prompts and the Writ session that carries mode/gates/RAG. Naming the job->role mapping and the 'generic = exception' rule makes the right dispatch the obvious one."
tags: [agents, dispatch, subagents, roles, process, work-mode]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-10
staleness_window: 365
evidence: "The 5 roles exist as valid CC subagents (.claude/agents/writ-*.md) and as ROL-*-001 nodes. .claude/hooks/writ-dispatch-discipline.sh enforces this at the Task PreToolUse boundary in work mode (denies a generic dispatch and names the matching role)."
always_on: false
source_attribution: "writ-native"
source_commit: null
edges:
  - { target: PBK-PROC-ORCHESTRATOR-001, type: RELATED_TO }
  - { target: SKL-PROC-PARALLEL-001, type: RELATED_TO }
  - { target: ROL-EXPLORER-001, type: RELATED_TO }
  - { target: ROL-PLANNER-001, type: RELATED_TO }
  - { target: ROL-TEST-WRITER-001, type: RELATED_TO }
  - { target: ROL-IMPLEMENTER-001, type: RELATED_TO }
  - { target: ROL-REVIEWER-001, type: RELATED_TO }
category: CAT-PROC-DISPATCH-001
action_triggers: ["dispatch"]
trigger_keywords: ["dispatch", "sub-agent", "Task tool", "agent"]
---

# Skill: Dispatch the named Writ role, not a generic agent

When you reach for the Task tool, the built-in `Explore` and `general-purpose` agents are
top-of-mind, so they are the easy choice. They are the wrong choice for Writ-governed work:
they carry no role prompt and run outside the Writ session that holds mode, gates, and RAG
budget. Pick the named role whose job matches the task.

## Job -> role mapping

| The task is to...                                   | Dispatch this role            |
|-----------------------------------------------------|-------------------------------|
| Explore / understand / investigate the codebase     | `writ-explorer` (read-only)   |
| Turn an approved design into an implementation plan  | `writ-planner`                |
| Write test skeletons / failing tests                | `writ-test-writer`            |
| Implement code from an approved plan                | `writ-implementer`            |
| Review a diff (spec-compliance, then code quality)  | `writ-reviewer`               |

`writ-explorer` is a governed, read-only drop-in for the built-in `Explore`: same fan-out
search capability, but inside a Writ session.

## Generic is the exception, not the default

Use `general-purpose` only when the task genuinely has no matching role. That is rare. When
it is real, make it explicit so the dispatch boundary lets it through: add `[general-purpose]`
to the Task prompt. A generic dispatch with no marker, in work mode, is a discipline slip --
the dispatch-discipline hook will deny it and name the role that fits.

## Red flag thoughts (indicators of violation)

- "I'll just use Explore to look around first." -> use `writ-explorer`.
- "general-purpose can handle this implementation." -> use `writ-implementer`.
- "It's a quick lookup, the generic agent is fine." -> if it touches governed code, a role fits.

## Relationship to the orchestrator playbook

`PBK-PROC-ORCHESTRATOR-001` sequences these roles for a full >5-file Work task
(explore -> plan -> test -> implement). This skill is the narrower, always-applicable rule:
even a single one-off dispatch, outside any pipeline, goes to the matching named role.
