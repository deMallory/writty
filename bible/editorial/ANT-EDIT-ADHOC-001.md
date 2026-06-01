---
antipattern_id: ANT-EDIT-ADHOC-001
node_type: AntiPattern
domain: editorial
severity: high
scope: layout
trigger: "When type sizes in a layout cannot be expressed as values in a single named scale."
statement: "Ad-hoc type sizing: type sizes chosen by feel or by framework default rather than from a named typographic scale. If listing all sizes used produces values like 12, 13.5, 15, 22, there is no scale, only intuition. Bringhurst's directive: 'Don't compose without a scale.'"
rationale: "The typographic scale has governed type sizing for 400+ years. Ad-hoc sizing produces incoherent hierarchy. The eye detects inconsistency in type size relationships even when it cannot name it. A scale that is present but inconsistently applied is worse than no scale at all because the inconsistent sizes create visual noise."
tags: [anti-pattern, editorial, typography, scale, hierarchy]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-01
staleness_window: 365
evidence: peer-reviewed
source_attribution: "editorial-claude-skills:editorial-grid"
source_commit: null
counter_nodes:
  - EDIT-GRID-SCALE-001
  - EDIT-GRID-SCALE-002
named_in: "editorial-framework:grid-construction"
edges:
  - { target: EDIT-GRID-SCALE-001, type: COUNTERS }
  - { target: EDIT-GRID-SCALE-002, type: COUNTERS }
---

# Anti-pattern: Ad-hoc type sizing

## Why this is broken

List all type sizes in the layout. If they cannot be expressed as values in a single scale (classical progression, modular ratio, or double-stranded), the hierarchy is accidental. Adjacent sizes that are too close blur the distinction; sizes too far apart create gaps in the hierarchy.

Common symptoms:
- Font sizes from framework defaults (14px, 16px, 20px, 24px, 30px) that happen to be close to a scale but don't follow one
- Incremental adjustments by "a couple pixels" that accumulate into incoherence
- Different developers adding sizes independently with no shared reference

## Counter

Choose a scale. Name it. Derive all sizes from it. The classical progression (6, 7, 8, 9, 10, 11, 12, 14, 16, 18, 21, 24, 36, 48, 60, 72) works for traditional editorial. A modular scale with a stated ratio (perfect fourth 1.333, golden 1.618) works for screen. Check existing design tokens before creating new ones.
