---
antipattern_id: ANT-EDIT-RESIDUAL-001
node_type: AntiPattern
domain: editorial
severity: high
scope: layout
trigger: "When a layout contains empty regions where no one can name what the whitespace is doing."
statement: "Residual whitespace: empty space that is not compositional breathing, semantic encoding, structural silence, or tension/direction. If the answer to 'what is this space doing?' is 'nothing' or 'balance,' the whitespace is residual and the layout is broken."
rationale: "Tschichold: 'White space is to be regarded as an active element, not a passive background.' Residual whitespace is the most common sign that the layout was assembled rather than composed. Every empty region must be load-bearing or it is waste."
tags: [anti-pattern, editorial, whitespace, composition, layout]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-01
staleness_window: 365
evidence: peer-reviewed
source_attribution: "editorial-claude-skills:spread-archetypes"
source_commit: null
counter_nodes:
  - EDIT-ARCH-WHITESPACE-001
named_in: "editorial-framework:whitespace-and-axis"
edges:
  - { target: EDIT-ARCH-WHITESPACE-001, type: COUNTERS }
---

# Anti-pattern: Residual whitespace

## Why this is broken

Whitespace has four jobs across the four archetypes: compositional breathing, semantic encoding, structural silence, and tension/direction. A region that does none of these is residual. Residual whitespace accumulates when elements are placed by default spacing rather than by compositional intent.

The stronger test: "What would happen if I filled this space?" If filling it wouldn't collapse the composition, the space is not structural. It is leftover.

## Counter

For every empty region, state its function. If no function can be named, the region is either: (a) waste to be reclaimed by reducing margins or redistributing elements, or (b) a counterweight that needs its paired heavy element strengthened so the balance relationship becomes legible.

## Diagnostic

Squint at the layout. Do the empty regions feel like they are holding something apart, or do they feel like nothing happened there? The former is active; the latter is residual.
