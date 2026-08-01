---
technique_id: TEC-EDIT-PROSE-001
node_type: Technique
domain: editorial
severity: medium
scope: layout
trigger: "When the elenchus development section needs a layout form. The prose form renders multi-column body text with sidenotes for the long middle of the argument."
statement: "Prose form: multi-column, baseline-locked, sidenotes in the margin like a critical edition. The calm middle is not the default; it is the reward for striking the reader with the question and holding them in the contradiction first. Sidenotes in a contrasting face because the form of philosophical writing is conversation with the text."
rationale: "The sidenote is not a footnote moved sideways; it is an acknowledgment that the text is already in dialogue with itself. Rashi reads Talmud in the margin. Heidegger's editions have marginalia that argue with the translation. The margin is where the dialogue becomes visible."
tags: [technique, editorial, elenchus, prose, sidenotes, baseline, multi-column]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-01
staleness_window: 365
evidence: peer-reviewed
source_attribution: "editorial-claude-skills:elenchus"
source_commit: null
edges:
  - { target: PBK-EDIT-ELENCHUS-001, type: DEMONSTRATES }
  - { target: EDIT-GRID-LINE-001, type: DEPENDS_ON }
  - { target: EDIT-GRID-BASELINE-001, type: DEPENDS_ON }
---

# Technique: Prose form

Binds to: development (elenchus move 3, the long middle).
Archetype bridge: multi-column prose (baseline-locked, marginal voice).

Sidenotes specifically in a contrasting face (monospace against grotesk works) so the reader sees at a glance: this is the voice arguing with the voice. Set sidenotes to run alongside the body text they annotate, not stacked at the end.

The reader who has been struck by the question and held in the contradiction is now ready to be patient. You have earned their patience by not being patient first.
