---
rule_id: EDIT-SPEC-SCALE-001
node_type: Rule
domain: editorial
severity: high
scope: layout
mandatory: false
trigger: |
  When displaying numerals, typographic characters, or letterforms as aesthetic objects in a ratio/specimen spread.
statement: |
  Numerals and characters become art objects when given sufficient surrounding margin. Large-scale display elements demand whitespace to function compositionally. Negative space alternating with dense type blocks creates rhythm analogous to musical phrasing (Ruder). Each unit of space relates proportionally to every other through the underlying scale.
violation: |
  ```css
  /* Display numeral crammed into body flow; no breathing room */
  .display-numeral {
    font-size: 4rem;
    margin: 0;
    /* Numeral reads as oversized body text, not as an aesthetic object */
  }
  ```
pass_example: |
  ```css
  /* Display numeral with generous margin; reads as typographic event */
  .display-numeral {
    font-size: 4rem;
    margin-top: calc(4 * var(--baseline));
    margin-bottom: calc(3 * var(--baseline));
    /* Surrounding space proportional to scale; numeral is a visual event */
  }
  ```
enforcement: |
  Code review. Check whether display-scale elements have margin proportional to their size and the underlying scale. Margin of zero or body-text-scale margin on display elements is a violation.
rationale: |
  Bodoni's Manuale Tipografico (1818) demonstrated that letterforms at display scale are aesthetic objects, not just enlarged text. The surrounding margin is what transforms scale into presence. Without it, the large type is just loud, not monumental.
tags: [rule, editorial, specimen, bodoni, ruder, display-type]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-01
staleness_window: 365
evidence: peer-reviewed
source_attribution: "editorial-claude-skills:spread-archetypes"
source_commit: null
edges:
  - { target: EDIT-GRID-SCALE-001, type: DEPENDS_ON }
  - { target: EDIT-GRID-PROPORTION-001, type: DEPENDS_ON }
---
