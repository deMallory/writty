---
rule_id: EDIT-SPEC-WEINGART-001
node_type: Rule
domain: editorial
severity: medium
scope: layout
mandatory: false
trigger: |
  When applying expressive or experimental typographic moves (weight variation, spatial disruption, unconventional arrangement) in a specimen or editorial layout.
statement: |
  Expressive typographic moves require Swiss-precision rigor underneath first. Weingart's permission: typographic elements may be treated as visual events (weight, direction, spatial energy independent of linguistic function), but only when the underlying structural rigor is present. Without the grid, the experiments look arbitrary. The structure must be visible even where the surface looks chaotic.
violation: |
  ```
  Rotated text blocks, mixed weights, overlapping elements.
  No visible underlying grid. No named scale.
  Result: looks like chaos, not transcendence.
  ```
pass_example: |
  ```
  Rotated text block at 15 degrees, breaking from a visible 12-field grid.
  All type sizes on a named scale (perfect fourth).
  Margins follow Van de Graaf canon.
  The departure is legible as departure because the norm is established.
  ```
enforcement: |
  Code review. When expressive moves are present, verify that the underlying grid, scale, and margin system are intact. If the base structure cannot be named, the expression is arbitrary.
rationale: |
  Weingart's Basel experiments (1960s-70s) demonstrated that typographic autonomy is earned, not asserted. His work succeeded because the Swiss grid system was the departure point. Expressive moves without that foundation read as student work, not as mastery.
tags: [rule, editorial, specimen, weingart, expression, rigor]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-01
staleness_window: 365
evidence: peer-reviewed
source_attribution: "editorial-claude-skills:spread-archetypes"
source_commit: null
edges:
  - { target: EDIT-GRID-BASELINE-001, type: DEPENDS_ON }
  - { target: EDIT-GRID-SCALE-001, type: DEPENDS_ON }
---
