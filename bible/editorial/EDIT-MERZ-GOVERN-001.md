---
rule_id: EDIT-MERZ-GOVERN-001
node_type: Rule
domain: editorial
severity: high
scope: layout
mandatory: false
trigger: |
  When designing or critiquing a fragmented/Merz-style layout where elements appear scattered, diagonal, or chaotic.
statement: |
  The chaos must be governed. Schwitters' compositions respected letterpress constraints; Dada respected De Stijl balance. Genuinely arbitrary fragmentation reads as noise, not Merz. An underlying structure must be identifiable beneath the apparent chaos. If you cannot point to the governing structure, the layout is arbitrary, not expressive.
violation: |
  ```
  Elements scattered across the page at random positions.
  No detectable grid underneath. No structural logic.
  Asked "what governs this?" Answer: "it felt right."
  Result: noise, not Merz.
  ```
pass_example: |
  ```
  Elements scattered across the page, but:
  - Heavy rules create architectural beams structuring the chaos
  - Positions align to an underlying 12-field grid at non-obvious intersections
  - Diagonal energy follows Lissitzky's static/dynamic axis theory
  Asked "what governs this?" Answer: "the 12-field grid, with diagonals
  at the intersections of fields 3/7 and 5/9."
  Result: governed chaos. Merz.
  ```
enforcement: |
  Code review. For any fragmented layout, ask: "Can you point to the underlying structure?" If no one can, the fragmentation is arbitrary.
rationale: |
  Schwitters' Merz magazine (1923-1932) and Lissitzky's constructivist typography both operated within strict material and geometric constraints. The apparent freedom was real but bounded. The distinction between governed chaos and arbitrary chaos is the distinction between Merz and mess.
tags: [rule, editorial, merz, schwitters, governed-chaos, structure]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-01
staleness_window: 365
evidence: peer-reviewed
source_attribution: "editorial-claude-skills:spread-archetypes"
source_commit: null
edges:
  - { target: EDIT-GRID-FIELD-001, type: DEPENDS_ON }
  - { target: EDIT-ARCH-TENSION-001, type: SUPPLEMENTS }
---
