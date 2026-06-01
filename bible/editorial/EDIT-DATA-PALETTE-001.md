---
rule_id: EDIT-DATA-PALETTE-001
node_type: Rule
domain: editorial
severity: high
scope: component
mandatory: false
trigger: |
  When choosing colors for a data visualization.
statement: |
  Color palette must match the data structure. Sequential data (ordered) uses a single-hue ramp (light to dark). Diverging data (meaningful midpoint) uses two hues meeting at neutral. Categorical data (unordered groups) uses distinct hues at similar luminance, maximum 5-8 categories. Use ColorBrewer or equivalent accessibility-tested palettes. Decorative color where categorical encoding is needed is a violation.
violation: |
  ```css
  /* Rainbow palette on ordered sequential data */
  .low    { fill: red; }
  .medium { fill: green; }
  .high   { fill: blue; }
  /* Unordered hues on ordered data; no perceptual sequence */
  ```
pass_example: |
  ```css
  /* Sequential single-hue ramp for ordered data */
  .low    { fill: hsl(210, 60%, 90%); }
  .medium { fill: hsl(210, 60%, 60%); }
  .high   { fill: hsl(210, 60%, 30%); }
  /* Lightness encodes magnitude; colorblind-safe */
  ```
enforcement: |
  Code review. Identify whether the data is sequential, diverging, or categorical. Check whether the palette type matches.
rationale: |
  Mismatched palettes mislead: rainbow colors on sequential data hide the ordering because human color perception does not arrange hues in a natural sequence. Sequential data needs sequential luminance. ColorBrewer palettes are empirically tested for perceptual uniformity and colorblind accessibility.
tags: [rule, editorial, data-spread, color, palette, accessibility]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-01
staleness_window: 365
evidence: peer-reviewed
source_attribution: "editorial-claude-skills:spread-archetypes"
source_commit: null
edges:
  - { target: EDIT-VIZ-INK-001, type: DEPENDS_ON }
  - { target: EDIT-VIZ-COMPARE-001, type: SUPPLEMENTS }
---
