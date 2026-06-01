---
rule_id: EDIT-DATA-LABEL-001
node_type: Rule
domain: editorial
severity: high
scope: component
mandatory: false
trigger: |
  When designing proportional shapes (circles, bubbles, bars) in a data visualization.
statement: |
  Every proportional shape must be directly labeled with its actual value. Relying on a legend placed away from the data forces the reader to hold values in working memory while their eye travels. Direct labels make the display self-decoding. For bubble charts specifically, limit to 5-7 categories maximum; beyond this, eye comparison breaks down.
violation: |
  ```
  Bubble chart with 12 categories, no direct labels.
  Reader must cross-reference each bubble to a legend in the corner.
  Working memory overflows at ~4 items; the display is unreadable.
  ```
pass_example: |
  ```
  Bubble chart with 5 categories, each bubble directly labeled
  with its value and category name. No separate legend needed.
  ```
enforcement: |
  Code review. Check whether proportional shapes carry direct value labels. Count categories in bubble/scatter charts; flag if > 7.
rationale: |
  Neurath's Isotype rule extended: direct labeling removes the legend as a cognitive intermediary. Viewers underestimate area differences even when scaling is correct, so labels provide the ground truth the eye cannot supply. The 5-7 category limit reflects the empirical boundary of pre-attentive discrimination for area.
tags: [rule, editorial, data-spread, labeling, neurath, direct-label]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-01
staleness_window: 365
evidence: peer-reviewed
source_attribution: "editorial-claude-skills:spread-archetypes"
source_commit: null
edges:
  - { target: EDIT-VIZ-INTEGRATE-001, type: DEPENDS_ON }
  - { target: EDIT-DATA-REPEAT-001, type: SUPPLEMENTS }
---
