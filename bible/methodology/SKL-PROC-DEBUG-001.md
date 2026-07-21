---
skill_id: SKL-PROC-DEBUG-001
node_type: Skill
domain: process
severity: high
scope: task
category: CAT-PROC-001
trigger_keywords: ["bug", "runtime", "root-cause", "evidence", "debugging"]
trigger: "When a bug is reported, a test fails unexpectedly, an error is observed at runtime, or a fix attempt has already failed and the agent is reaching for another guess."
statement: "Hold the runtime-debug lens: gather evidence before forming a fix, trace backward from the failure to the exact diverging boundary, and cite root-cause evidence in the same response as any proposed fix. After three failed fixes, stop patching and question the architecture."
rationale: "Symptom-patching is the canonical debug-mode failure: the agent guesses, the guess masks the symptom, and the real cause survives. Naming the discipline as a runtime lens (the Skill sibling of the PBK-PROC-DEBUG-001 playbook and the ENF-PROC-DEBUG-001 advisory rule) lets retrieval surface the evidence-first reminder at the moment a fix is being proposed."
tags: [debugging, evidence-first, process, root-cause, runtime]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-12
staleness_window: 365
evidence: peer-reviewed
always_on: false
source_attribution: "writ-native"
source_commit: null
edges:
  - { target: PBK-PROC-DEBUG-001, type: TEACHES }
  - { target: ENF-PROC-DEBUG-001, type: TEACHES }
  - { target: TEC-PROC-ROOTCAUSE-001, type: DEMONSTRATES }
  - { target: TEC-PROC-HYPOTHESIS-001, type: DEMONSTRATES }
---

# Skill: Runtime debugging lens

Natural language: when something is broken at runtime, do not reach for a fix. Reach for evidence first. This skill is the runtime sibling of the systematic-debugging playbook (`PBK-PROC-DEBUG-001`) and the advisory evidence-cite rule (`ENF-PROC-DEBUG-001`).

## When this applies

A bug is reported. A test fails unexpectedly. An error or wrong value is observed at runtime. A fix attempt has already failed and you are about to guess again. The skill applies the moment a fix is being *proposed*, not only when one is being written.

## The lens

1. **Evidence before fix.** Read the failure: the exception, the traceback, the wrong value, the reproducer. State what the evidence shows before naming a cause.
2. **Trace backward.** From the failure point, walk up the call stack one boundary at a time. Find the exact boundary where expected and actual diverge. That boundary is the locus, not the symptom site.
3. **Cite in the same response.** Any proposed fix carries its root-cause evidence in the same message. "Fix X" without "because the evidence shows Y" is a guess.

## Red flag thoughts (indicators of violation)

- "Let me just try changing X and see."
- "Quick fix for now, investigate later."
- "It's probably this."
- "Emergency, skip the process."

## The 3-fix rule

Three failed fix attempts means the problem is architectural, not tactical. Stop patching. Re-examine the design before attempting fix number four.
