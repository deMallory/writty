---
rule_id: EDIT-MERZ-FRAGMENT-001
node_type: Rule
domain: editorial
severity: medium
scope: layout
mandatory: false
trigger: |
  When breaking words or text into fragments, stacking letters vertically, or using extreme size contrast in a layout.
statement: |
  Vertical fragmentation and extreme size contrast are semantic deceleration: they slow reading deliberately. This is appropriate when slowing serves the content (poetry, monuments, declarations, manifesto fragments). It is inappropriate when the content needs to be absorbed quickly. The BAUHAUS lettering down the Dessau facade is the canonical example: the building announces itself slowly, as a presence rather than a label.
violation: |
  ```
  Navigation menu items stacked vertically letter-by-letter.
  Content: utility links (Home, About, Contact).
  Mismatch: semantic deceleration on content that needs fast scanning.
  The reader must reassemble each word before navigating.
  ```
pass_example: |
  ```
  Article title broken into stacked letters spanning the full height.
  Content: a manifesto opening declaration.
  Match: the deceleration forces the reader to encounter each letter
  as architectural mass. The title announces itself as a presence.
  ```
enforcement: |
  Code review. For fragmented or vertically stacked text, check whether the deceleration serves the content's intent. Utility content fragmented is always a violation.
rationale: |
  Schwitters' Merz and Lissitzky's constructivism used fragmentation as a compositional tool with specific purpose: slowing the eye, creating architectural mass, treating type as pictorial element. When applied to content that needs speed (navigation, labels, instructions), the technique defeats its own purpose.
tags: [rule, editorial, merz, schwitters, fragmentation, deceleration]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-01
staleness_window: 365
evidence: peer-reviewed
source_attribution: "editorial-claude-skills:spread-archetypes"
source_commit: null
edges:
  - { target: EDIT-ARCH-RHYTHM-001, type: DEPENDS_ON }
  - { target: EDIT-MERZ-GOVERN-001, type: SUPPLEMENTS }
---
