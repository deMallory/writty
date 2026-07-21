---
skill_id: SKL-PROC-INVESTIGATE-001
node_type: Skill
domain: process
severity: medium
scope: session
trigger: "When starting an investigation -- an audit, codebase exploration, web research, or debugging a failure -- or whenever the session mode is set to investigate."
statement: "Investigation is one engine, not four tools. Declare the source_type (code | web | runtime); it selects the lens and the enforcing gate. The source_type, not the mode, owns gate strictness."
rationale: "Audit, explore, research, and debug share one evidence-grounded loop; modeling them as one engine with a source_type switch keeps the gate and the lens consistent and prevents code-first investigation. The switch lives in code (writ-session.py _LENS_TABLE); this node is its retrievable description."
tags: [investigate, audit, explore, research, debug, source_type, lens, process, skill]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-02
staleness_window: 180
evidence: "bin/lib/writ-session.py _LENS_TABLE + cmd_lens map source_type -> lens -> gate; investigate mode in MODE_CONFIG selects the lens via --set-source-type."
always_on: false
source_attribution: "writ-native"
source_commit: null
edges:
  - { target: PBK-PROC-RESEARCH-001, type: RELATED_TO }
  - { target: PBK-PROC-DEBUG-001, type: RELATED_TO }
  - { target: PBK-PROC-AUDIT-FANOUT-001, type: RELATED_TO }
category: CAT-PROC-001
floor_modes: [debug, investigate]
trigger_keywords: ["investigation", "audit", "explore", "research", "debug"]
---

# Skill: The investigation engine (one engine, four lenses)

Set `source_type` to engage the lens; the lens carries its own enforcing gate:

| source_type | lens | enforcing gate | strictness |
|-------------|------|----------------|------------|
| `code` | audit / explore | synthesis-gate | advisory |
| `web` | research | triangulation-gate | hard (>=2 independent domains) |
| `runtime` | debug | root-cause | advisory |

- One loop: gather evidence, narrow, conclude. Cite evidence; do not assert beyond it.
- `code` (audit/explore): the at-scale execution fans out per PBK-PROC-AUDIT-FANOUT-001; the
  synthesis-gate judges coverage sufficiency, not correctness.
- `web` (research): PBK-PROC-RESEARCH-001 is the spine; triangulation is a HARD gate -- a claim
  needs >=2 independent domains before you rely on it.
- `runtime` (debug): PBK-PROC-DEBUG-001; record runtime evidence and narrow the locus BEFORE
  reading source (code is investigated last, not first).

Select the lens with `--set-source-type <code|web|runtime>`; debug mode defaults to runtime.
