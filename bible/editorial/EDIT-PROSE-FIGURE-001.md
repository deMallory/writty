---
rule_id: EDIT-PROSE-FIGURE-001
node_type: Rule
domain: editorial
severity: high
scope: layout
mandatory: false
trigger: |
  When placing figures (images, charts, diagrams) in a multi-column prose layout.
statement: |
  Figures must be placed near their first text reference, sized to whole-number multiples of column widths, and positioned at column tops or bottoms only. Figures placed mid-column break reading flow. Figures sized arbitrarily (not aligned to column grid) make the composition feel accidental. Full-width figures create horizontal breaks; single-column figures sit within one text stream; margin figures minimize disruption.
violation: |
  ```css
  /* Figure floated mid-column at arbitrary width */
  .figure {
    float: left;
    width: 347px; /* arbitrary; not aligned to any column */
    margin: 1em;
  }
  /* Text wraps around figure mid-paragraph; reading flow broken */
  ```
pass_example: |
  ```css
  /* Figure at column top, spanning 2 of 3 columns (integer column widths) */
  .figure {
    grid-column: 1 / 3; /* spans 2 columns exactly */
    margin-bottom: var(--baseline);
  }
  /* Placed at column top via grid-row: 1; text flows below */
  ```
enforcement: |
  Code review. Check figure widths against column widths (must be integer multiples). Check vertical position (column tops/bottoms, not mid-column). Check proximity to first text reference.
rationale: |
  Cognitive science confirms spatial contiguity aids comprehension: figures near their text reference are processed together. Grid-aligned figure sizing is the structural defense against accidental composition. Mid-column placement forces the eye to navigate around the figure, breaking the reading saccade that sustained prose depends on.
tags: [rule, editorial, prose, figure-placement, column-grid]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-01
staleness_window: 365
evidence: peer-reviewed
source_attribution: "editorial-claude-skills:spread-archetypes"
source_commit: null
edges:
  - { target: EDIT-GRID-FIELD-001, type: DEPENDS_ON }
  - { target: EDIT-ARCH-INTEGRATE-001, type: SUPPLEMENTS }
---
