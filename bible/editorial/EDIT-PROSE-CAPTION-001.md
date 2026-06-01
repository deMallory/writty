---
rule_id: EDIT-PROSE-CAPTION-001
node_type: Rule
domain: editorial
severity: medium
scope: layout
mandatory: false
trigger: |
  When styling captions for figures or tables in an editorial layout.
statement: |
  Captions must be visually subordinate to body text: typically 2 points smaller than body (Bringhurst convention), often in a contrasting face (sans-serif against serif body, or vice versa). Captions go below figures and above tables (tables read top-down; figures read body-first). Captions at the same size as body text collapse the visual hierarchy.
violation: |
  ```css
  /* Caption same size and face as body text */
  .body { font: 16px/1.5 Georgia; }
  .caption { font: 16px/1.5 Georgia; }
  /* No hierarchy between body and caption; reader can't distinguish */
  ```
pass_example: |
  ```css
  /* Caption subordinate: smaller, contrasting face */
  .body { font: 16px/1.5 Georgia; }
  figcaption { font: 14px/1.4 'Inter', sans-serif; color: #555; }
  /* 2px smaller, contrasting sans face, slightly muted */
  ```
enforcement: |
  Code review. Compare caption font-size to body font-size (should be ~2pt smaller). Check whether faces contrast. Verify placement: below figures, above tables.
rationale: |
  Bringhurst's Elements of Typographic Style establishes the convention: captions are a supporting voice, not the primary voice. The size reduction and face contrast signal to the reader that this is metadata about the figure, not part of the body argument. Same-size captions force the reader to parse context from content rather than seeing it structurally.
tags: [rule, editorial, prose, caption, bringhurst, hierarchy]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-01
staleness_window: 365
evidence: peer-reviewed
source_attribution: "editorial-claude-skills:spread-archetypes"
source_commit: null
edges:
  - { target: EDIT-GRID-SCALE-001, type: DEPENDS_ON }
  - { target: EDIT-PROSE-FIGURE-001, type: SUPPLEMENTS }
---
