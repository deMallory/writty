---
rule_id: EDIT-VIZ-LAYER-001
node_type: Rule
domain: editorial
severity: medium
scope: component
mandatory: false
trigger: |
  When a data visualization contains multiple overlapping elements or when primary data competes visually with secondary elements (grids, axes, annotations).
statement: |
  Visually layer elements by importance: primary data in dark/saturated, secondary data in lighter values, reference elements (grids, axes) barely visible. The squint test: squint at the graphic; the most important data should remain visible while chartjunk and secondary elements disappear first. Grids should whisper, not shout.
violation: |
  ```css
  /* Grid lines and data bars at similar visual weight */
  .grid-line { stroke: #666; stroke-width: 1px; }
  .data-bar  { fill: #888; }
  /* Squint test: grid and data are equally visible. Grid competes. */
  ```
pass_example: |
  ```css
  /* Primary data dominates; grid recedes */
  .grid-line { stroke: #eee; stroke-width: 0.5px; }
  .data-bar  { fill: #2196F3; }
  /* Squint test: data bars are visible; grid lines vanish. */
  ```
enforcement: |
  Code review. Apply the squint test: does the most important data dominate when the graphic is viewed at reduced attention? If grid, borders, or annotations compete, lighten them.
rationale: |
  Tufte's layering and separation principle (from Envisioning Information): visually distinct elements coexist in the same space when separated by value, weight, or hue. The 1+1=3 effect (two heavy elements create a phantom third) is the mechanism: reducing weight on secondary elements eliminates the phantoms and lets the data speak.
tags: [rule, editorial, tufte, layering, separation, visual-weight]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-01
staleness_window: 365
evidence: peer-reviewed
source_attribution: "editorial-claude-skills:tufte-viz"
source_commit: null
edges:
  - { target: EDIT-VIZ-INK-001, type: DEPENDS_ON }
  - { target: EDIT-VIZ-JUNK-001, type: SUPPLEMENTS }
---
