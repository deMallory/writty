---
rule_id: EDIT-MERZ-DIAGONAL-001
node_type: Rule
domain: editorial
severity: medium
scope: layout
mandatory: false
trigger: |
  When using diagonal elements (rotated text, angled rules, non-orthogonal alignment) in an editorial layout.
statement: |
  Diagonals must do work. Lissitzky's static/dynamic axis theory: the right angle has a static effect (rest); the diagonal has a dynamic effect (agitation). Choose deliberately. Diagonals used for decoration rather than energy are a violation. If the diagonal could be removed without changing the meaning, remove it.
violation: |
  ```css
  /* Decorative diagonal; adds no energy to content */
  .section-divider {
    transform: rotate(5deg);
    /* Why 5 degrees? No structural reason. Just "looks modern." */
  }
  ```
pass_example: |
  ```css
  /* Diagonal carries the most important content; energy serves meaning */
  .manifesto-claim {
    transform: rotate(15deg);
    /* The claim cuts across the static grid, demanding attention.
       The angle matches the content's urgency. */
  }
  ```
enforcement: |
  Code review. For every diagonal element, ask: "What work is this doing?" and "Could it be removed without losing meaning?" If removable, it is decorative.
rationale: |
  Lissitzky's "Topography of Typography" (Merz No. 4, 1923) established that axis angle carries cognitive weight. Diagonals are expensive: they agitate the eye and demand attention. Spending that cost on decoration wastes it. Spending it on the most important content leverages it.
tags: [rule, editorial, merz, lissitzky, diagonal, axis]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-01
staleness_window: 365
evidence: peer-reviewed
source_attribution: "editorial-claude-skills:spread-archetypes"
source_commit: null
edges:
  - { target: EDIT-ARCH-AXIS-001, type: DEPENDS_ON }
  - { target: EDIT-MERZ-GOVERN-001, type: SUPPLEMENTS }
---
