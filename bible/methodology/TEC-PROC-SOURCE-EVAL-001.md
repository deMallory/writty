---
technique_id: TEC-PROC-SOURCE-EVAL-001
node_type: Technique
domain: process
severity: medium
scope: task
trigger: "During investigation Phase 2-4 (gather, narrow, verify), when deciding whether a single source is trustworthy enough to cite for a claim."
statement: "Judge a source before you cite it on four axes: authority (primary vs secondary vs tertiary), independence (does it merely echo another source?), recency (is it current for a time-sensitive claim?), and directness (does it actually state the claim, or is it being stretched?). A source that fails authority or directness is a lead to chase, not a citation to record."
rationale: "Most bad findings are not fabricated; they are a real but weak source over-trusted. Evaluating the source explicitly, before it enters the citation ledger, catches the echo chamber (many sources, one origin) and the stale-but-confident source that corroboration counts alone would miss."
tags: [source-evaluation, authority, corroboration, staleness, investigation, technique, process]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-01
staleness_window: 365
evidence: peer-reviewed
source_attribution: "writ-native"
source_commit: null
edges:
  - { target: PBK-PROC-RESEARCH-001, type: DEMONSTRATES }
category: CAT-PROC-001
floor_modes: [investigate]
trigger_keywords: ["source", "authority", "recency", "independence", "cite"]
---

# Technique: Single-source credibility evaluation

## Procedure

1. **Authority.** Is this the primary source (the spec, the code, the dataset,
   the original announcement) or a description of it? Climb toward the primary.
2. **Independence.** Does this source derive from another already in your set?
   Two articles citing the same press release are one source, not two.
3. **Recency.** For a time-sensitive claim, is the source current? Note its date
   or version; treat fast-moving domains as stale by default.
4. **Directness.** Does the source actually state the claim, or is the claim a
   stretch of what it says? Quote the supporting span.

## Decision

- Passes authority + directness, with a recorded date -> cite it (record the
  `ref` and the supporting excerpt in the citation ledger).
- Fails authority or directness -> it is a lead. Chase it to a stronger source
  before recording a finding.

## Red flags

- Counting echoes as corroboration (N sources, one origin).
- Citing a summary when the primary source is one click away.
- A confident source with no date on a claim that changes monthly.
