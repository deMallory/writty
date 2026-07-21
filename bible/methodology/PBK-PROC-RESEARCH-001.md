---
playbook_id: PBK-PROC-RESEARCH-001
node_type: Playbook
domain: process
severity: high
scope: task
trigger: "When gathering information to answer a question or ground a decision -- researching a topic online, auditing a codebase, or exploring an unfamiliar system. The unified investigation spine; debug is its runtime-source sibling."
statement: "Five phases: scope the question, gather from sources, narrow to what matters, verify each claim against its source, synthesize. Standards bind the gathering: prefer primary/authoritative sources, corroborate decision-driving claims across >=2 independent sources, cite every external claim, and record staleness. A claim with no source you can point to is not a finding."
rationale: "Audit, explore, and research are one process over different source types; the difference is the source, not the method. Front-loading the source standards before gathering is what separates investigation from collecting plausible text. Verifying each claim against its captured source is the floor that makes a synthesis trustworthy."
tags: [research, audit, explore, investigation, source-standards, playbook, process]
confidence: battle-tested
authority: human
last_validated: 2026-06-01
staleness_window: 365
evidence: peer-reviewed
source_attribution: "writ-native"
source_commit: null
phase_ids: []
preconditions: []
dispatched_roles: []
edges:
  - { target: PBK-PROC-AUDIT-FANOUT-001, type: INVOKES }
  - { target: PBK-PROC-DEBUG-001, type: INVOKES }
  - { target: TEC-PROC-SOURCE-EVAL-001, type: INVOKES }
category: CAT-PROC-001
floor_modes: [investigate]
trigger_keywords: ["research", "audit", "explore", "corroborate"]
---

# Playbook: Standards-grounded investigation

Audit, explore, and research are the same engine over different source types
(code, runtime, the web). Apply the standards BEFORE you gather, not after.

## Five phases

1. **Scope** — state the question and what would answer it. Define the boundary
   (which files, which systems, which claims need sources).
2. **Gather** — collect from sources within scope. Capture each source as you go
   (the citation ledger), never from memory.
3. **Narrow** — discard what is out of scope or redundant. Keep the candidate
   findings that actually bear on the question.
4. **Verify** — for each candidate finding, point at the source. A claim you
   cannot trace back to a captured source is dropped, not softened.
5. **Synthesize** — assemble the verified findings into an answer, carrying the
   citations forward.

## Source standards (bind phase 2-4)

- **Authority** — rest a claim on the most authoritative source reachable, not
  the first hit. Primary over secondary over tertiary.
- **Corroboration** — a factual claim that drives a decision is confirmed by
  two or more INDEPENDENT sources. One source is a lead, not a fact.
- **Citation** — every external claim carries a citation (a `ref` recorded in
  the session citation ledger). No claim without a citation.
- **Staleness** — time-sensitive facts record the retrieval date or version.
  Fast-moving domains are stale by default; re-verify before relying.

## The four lenses (one engine, by source_type)

One process, selected by `source_type` (run `writ-session.py lens <sid>` to see the active
one and the gate that enforces it):

- **code -> audit** (find issues) and **explore** (understand unfamiliar code): freeze the
  scope, examine files as citations, check the coverage map, pass the synthesis gate (advisory).
- **web -> research**: capture url citations; pass the hard triangulation gate (>=2 independent
  domains).
- **runtime -> debug** (PBK-PROC-DEBUG-001): capture command citations; establish a root cause
  before editing source (advisory).

Audit and explore share `source_type=code` and differ only in goal, not mechanism. Debug is the
runtime lens of this same engine, not a separate process.

## The honest ceiling

A citation proves the source was **captured**, never that the claim is **true**.
Presence is the floor, not truth. Triangulation across independent sources raises
confidence; it does not certify correctness. Truth stays human-adjudicated.

## Red flags

- "I recall that X is true." (No captured source -- not a finding.)
- "A blog post says X, ship it." (Single, non-authoritative, uncorroborated.)
- "This was true last year." (Staleness ignored on a fast-moving topic.)
