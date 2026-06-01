---
rule_id: EDIT-PROSE-MARBER-001
node_type: Rule
domain: editorial
severity: medium
scope: layout
mandatory: false
trigger: |
  When designing a layout system that must accommodate variation across many pages or issues of the same publication.
statement: |
  The layout must pass the Marber test: could the spread accommodate variation across many pages of the same publication while remaining systematically consistent? Romek Marber's 1961 Penguin grid allocated over two-thirds of the cover to illustration with rigorous type placement, enabling systematic flexibility across hundreds of titles. A layout that works for one page but cannot accommodate variation is a one-off, not a system.
violation: |
  ```
  Layout designed for a specific article with hard-coded positions.
  A different article (longer title, more figures, no images)
  would require redesigning the layout from scratch.
  No system; only a one-off.
  ```
pass_example: |
  ```
  Layout system with:
  - Named grid fields that accommodate 1, 2, or 3 columns
  - Figure placement rules that work regardless of figure count
  - Type hierarchy that holds whether the title is 3 words or 15
  - Consistent margins and baseline across all instances
  The 50th article looks as considered as the first.
  ```
enforcement: |
  Code review. Test the layout with different content: short title vs. long, many figures vs. none, text-heavy vs. image-heavy. If any variation requires ad-hoc overrides, the system is incomplete.
rationale: |
  Marber's Penguin grid (1961) proved that systematic flexibility and visual quality are not in tension. The grid enables variation by constraining it to a set of lawful configurations. A layout without this property is a poster, not a system.
tags: [rule, editorial, prose, marber, systematic, flexibility]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-01
staleness_window: 365
evidence: peer-reviewed
source_attribution: "editorial-claude-skills:spread-archetypes"
source_commit: null
edges:
  - { target: EDIT-GRID-FIELD-001, type: DEPENDS_ON }
  - { target: EDIT-GRID-PROPORTION-001, type: SUPPLEMENTS }
---
