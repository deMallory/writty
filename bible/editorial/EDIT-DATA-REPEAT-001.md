---
rule_id: EDIT-DATA-REPEAT-001
node_type: Rule
domain: editorial
severity: high
scope: component
mandatory: false
trigger: |
  When designing a data visualization that represents quantities using pictograms, icons, or repeated shapes.
statement: |
  Greater quantities are shown by greater number of same-size pictograms, never by enlarging a single pictogram (Neurath's cardinal rule). Variation in size creates ambiguity between height and area comparison; repeated icons can be counted directly. This is the Isotype principle.
violation: |
  ```html
  <!-- One big icon for large value, one small for small value -->
  <svg class="big-icon" width="80" height="80"><!-- 1000 units --></svg>
  <svg class="small-icon" width="20" height="20"><!-- 250 units --></svg>
  <!-- Is the big icon 4x or 16x the small one? Ambiguous. -->
  ```
pass_example: |
  ```html
  <!-- Same-size icons repeated; countable at a glance -->
  <div class="pictogram-row">
    <svg width="20" height="20" /><!-- x4 icons = 1000 units -->
    <svg width="20" height="20" />
    <svg width="20" height="20" />
    <svg width="20" height="20" />
  </div>
  <div class="pictogram-row">
    <svg width="20" height="20" /><!-- x1 icon = 250 units -->
  </div>
  ```
enforcement: |
  Code review. Check whether pictogram/icon displays use repetition (correct) or scaling (violation) to represent magnitude.
rationale: |
  Otto Neurath's Isotype system (Vienna, 1925) established this as the foundational rule of pictorial statistics. Scaling introduces the same area-vs-diameter ambiguity as bubble charts. Repetition is unambiguous: the reader counts.
tags: [rule, editorial, data-spread, neurath, isotype, pictogram]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-01
staleness_window: 365
evidence: peer-reviewed
source_attribution: "editorial-claude-skills:spread-archetypes"
source_commit: null
edges:
  - { target: EDIT-VIZ-LIE-001, type: DEPENDS_ON }
  - { target: EDIT-VIZ-INK-001, type: SUPPLEMENTS }
---
