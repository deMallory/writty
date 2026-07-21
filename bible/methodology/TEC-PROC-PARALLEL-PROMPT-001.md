---
technique_id: TEC-PROC-PARALLEL-PROMPT-001
node_type: Technique
domain: process
severity: medium
scope: task
trigger: "When dispatching a subagent (parallel or single) and writing its prompt -- deciding what context to give it, how to scope it, and what to ask it to return."
statement: "A dispatched agent never inherits your session history; you CONSTRUCT exactly the context it needs, which also preserves your own context window. Give it: a focused scope (one problem domain), self-contained context (symptoms, error text, relevant files), a hypothesis if you have one, ordered steps, hard constraints (what NOT to touch), and an explicit return shape. Vague scope or output wastes the dispatch."
rationale: "SKL-PROC-PARALLEL-001 decides WHEN to dispatch; this is HOW to write the prompt. The two failure modes are leakage (dumping session history, which pollutes the agent's focus and burns your window) and vagueness (no scope, no constraints, no return shape), which produce lost or unusable work."
tags: [parallel, dispatch, subagent, context-isolation, prompt, process, technique]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-04
staleness_window: 365
evidence: peer-reviewed
source_attribution: "writ-native"
source_commit: null
edges:
  - { target: SKL-PROC-PARALLEL-001, type: RELATED_TO }
category: CAT-PROC-DISPATCH-001
trigger_keywords: ["dispatch prompt", "subagent", "context", "isolation"]
---

# Technique: Construct a dispatch prompt

**Context isolation first.** The agent does not see your conversation. Construct exactly what it
needs -- never paste your session history. This keeps the agent focused and preserves your own
context window for coordination.

A good dispatch prompt has six parts:

1. **Scope** -- one problem domain, named precisely ("fix the 3 failures in `agent-abort.test.ts`",
   not "fix the tests").
2. **Context** -- self-contained: the error text, failing test names, the files involved. The
   agent cannot ask you mid-run.
3. **Hypothesis** -- your best guess at the cause, if you have one ("likely a timing/race issue").
4. **Ordered steps** -- read, identify root cause, fix; not a vague "make it work".
5. **Hard constraints** -- what NOT to do ("do NOT just increase timeouts", "tests only, no
   production code").
6. **Return shape** -- the exact structure to report back (a summary of root cause + changes, a
   JSON shape, or file paths). Vague output is unusable.

When to dispatch at all -- and independence -- is `SKL-PROC-PARALLEL-001`.
