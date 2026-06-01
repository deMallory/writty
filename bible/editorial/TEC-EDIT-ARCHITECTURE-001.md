---
technique_id: TEC-EDIT-ARCHITECTURE-001
node_type: Technique
domain: editorial
severity: medium
scope: layout
trigger: "When the elenchus question or answer needs a layout form. The architecture form renders a single sentence at page scale so the reader is enclosed by it."
statement: "Architecture form: single sentence at page scale. The reader does not approach the question; the reader is enclosed by it. Very little else on the page. The case number, perhaps, and the date, in the smallest possible apparatus. Everything else is the sentence and the room around it. Hofmann Berlin, Nureyev tower, Giselle column."
rationale: "The question wants to be encountered, not read. The architecture form fills the page the way the wound fills the day it announces itself. This is what the homepage becomes also: the central question of the site, rendered at the same scale."
tags: [technique, editorial, elenchus, architecture, monumental, page-scale]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-01
staleness_window: 365
evidence: peer-reviewed
source_attribution: "editorial-claude-skills:elenchus"
source_commit: null
edges:
  - { target: PBK-EDIT-ELENCHUS-001, type: DEMONSTRATES }
  - { target: EDIT-ARCH-IDENTIFY-001, type: DEMONSTRATES }
  - { target: EDIT-GRID-PROPORTION-001, type: DEPENDS_ON }
---

# Technique: Architecture form

Binds to: question and answer (elenchus moves 1 and 3).
Archetype bridge: ratio/specimen (typographic object at monumental scale).

Grid logic: a strong page proportion (2:3 or golden), Van de Graaf margins, with the sentence violating the text block at scale. The sentence is the only content. The room around it is active whitespace.

The article ends with the answer alone on the page, at the same scale as the question. The room that was filled by the question at the start is now filled by the answer at the end.
