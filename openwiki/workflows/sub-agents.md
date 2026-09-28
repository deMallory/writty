---
type: Guide
title: "Sub-agents"
description: The agents Writty ships, how a generic dispatch becomes a Writty role, what workers skip and inherit, and how a review verdict can hold a commit.
---

# Sub-agents

Writty ships seven Claude Code agents in `agents/`. Five are the roles of the gated workflow. Two are an older split of the reviewer, kept because a hook still orders them. On a plugin install, Claude Code prefixes each name with the plugin name: dispatch `writ:writ-explorer`, not the bare name.

| Agent | Role | Tools | Use it for |
|---|---|---|---|
| `writ-explorer` | Explorer | Read, Glob, Grep, Bash | read-only investigation before planning, or runtime evidence for a failure |
| `writ-planner` | Planner | Read, Glob, Grep, Write, Edit | writing `plan.md` and `capabilities.md` |
| `writ-test-writer` | Test writer | Read, Glob, Grep, Write, Edit, Bash | test skeletons, after the plan is approved |
| `writ-implementer` | Implementer | Read, Glob, Grep, Write, Edit, Bash | the code, after the tests are approved |
| `writ-reviewer` | Reviewer | Read, Glob, Grep, Bash | a diff review in two passes, spec first, then quality |
| `writ-spec-reviewer` | older split | Read, Glob, Grep, Bash | spec compliance only |
| `writ-code-quality-reviewer` | older split | Read, Glob, Grep, Bash | code quality only, after the spec review |

The five roles are also nodes in the rule graph (`ROL-*` in `writ-corpus.cypher`). `writ role-prompt <role>` prints a role's prompt from the graph.

## Dispatch discipline

In `work`, `investigate`, or with no mode set, `hooks/scripts/writ-dispatch-discipline.sh` checks every dispatch. A generic one (`general-purpose`, `Explore`, `Plan`, `claude`, or no type) is rewritten to the matching Writty role when the prompt says clearly what the job is: explore, write tests, review, plan, implement. When it cannot tell, it refuses and asks. To keep a generic agent on purpose, put `[general-purpose]` or `[writ:dispatch-ok]` in the prompt.

## What workers skip and inherit

- **Write gates.** Workers skip them. The session that dispatched them already passed your approvals, and each role's tools bound what it can do: the explorer and the reviewers have no Write or Edit tool.
- **Secret files.** Still refused. The secret-read guard applies to workers too.
- **Mode.** A worker inherits the parent's mode, phase and approvals, read from the parent's session file.
- **Rule usage.** The rules each worker looked up for each file join the commit's record in decision memory, so the record covers the whole fan-out.
- **Orchestrator flag.** `mode set work --orchestrator` stops the broad rule injection in the dispatching session, which saves tokens when that session only coordinates. The flag is manual.

## Review order and the commit hold

- In `work`, dispatching `writ-code-quality-reviewer` before the spec review of the same task has finished is refused (`ENF-PROC-SDD-001`, from `hooks/scripts/writ-sdd-review-order.sh`).
- When `writ-reviewer` stops, `hooks/scripts/writ-subagent-stop.sh` records its verdict from the reviewer's own last message, so the author of the code never carries it.
- While CRITICAL findings stand, `git commit` asks you to confirm. It asks rather than refuses, because any override the agent could set would reopen the hole. A verdict that cannot be parsed counts as blocking.
- To clear the hold, fix the findings and run the reviewer again. Writing the verdict record by hand is refused.

## Where to read more

- `HANDBOOK.md` section 8: roles and orchestration.
- `docs/reference/session-and-gates.md` section 7: the sub-agent lifecycle.
