---
rule_id: EDIT-VIZ-MULTIVAR-001
node_type: Rule
domain: editorial
severity: medium
scope: component
mandatory: false
trigger: |
  When designing a data visualization or analytical display that presents a phenomenon with multiple interacting variables.
statement: |
  Show multivariate data, not just 1 or 2 variables (Tufte's third principle of analytical design). Real problems are multivariate. Reducing to a single variable hides interactions. The display should encode at least 3 dimensions where the data supports it: position, color, size, shape, time, or small-multiples indexing.
violation: |
  ```
  Bar chart showing revenue by quarter.
  One variable (revenue) against one index (time).
  Hides: revenue by product line, by region, by customer segment.
  The interactions are invisible.
  ```
pass_example: |
  ```
  Small multiples of sparklines: revenue by quarter,
  one panel per product line, color-coded by region.
  Three variables visible simultaneously.
  Reader can compare across lines, across regions, across time.
  ```
enforcement: |
  Code review. Count the variables encoded in the display. If the underlying data has 3+ relevant dimensions and the chart shows only 1-2, recommend adding encoding channels or small multiples.
rationale: |
  Tufte's third principle of analytical design: "Show multivariate data." Over-reduction is the most common analytical failure. A single-variable chart answers "what happened?" but not "why?" or "where?" Adding dimensions (via color, faceting, or small multiples) transforms description into analysis.
tags: [rule, editorial, tufte, multivariate, analytical-design]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-01
staleness_window: 365
evidence: peer-reviewed
source_attribution: "editorial-claude-skills:tufte-viz"
source_commit: null
edges:
  - { target: EDIT-VIZ-COMPARE-001, type: DEPENDS_ON }
  - { target: EDIT-VIZ-INK-001, type: SUPPLEMENTS }
---
