# Exemplars

Gold-standard nodes from the editorial corpus. Match this level of quality, specificity, and tone.

---

## Rule: EDIT-DATA-LABEL-001

```yaml
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
```

Note: Rule nodes have no type prefix (uses domain prefix). Requires `violation`, `pass_example`, `enforcement`.

---

## AntiPattern: ANT-EDIT-ADHOC-001

```yaml
---
antipattern_id: ANT-EDIT-ADHOC-001
node_type: AntiPattern
domain: editorial
severity: high
scope: layout
trigger: "When type sizes in a layout cannot be expressed as values in a single named scale."
statement: "Ad-hoc type sizing: type sizes chosen by feel or by framework default rather than from a named typographic scale. If listing all sizes used produces values like 12, 13.5, 15, 22, there is no scale, only intuition. Bringhurst's directive: 'Don't compose without a scale.'"
rationale: "The typographic scale has governed type sizing for 400+ years. Ad-hoc sizing produces incoherent hierarchy. The eye detects inconsistency in type size relationships even when it cannot name it. A scale that is present but inconsistently applied is worse than no scale at all because the inconsistent sizes create visual noise."
tags: [anti-pattern, editorial, typography, scale, hierarchy]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-01
staleness_window: 365
evidence: peer-reviewed
source_attribution: "editorial-claude-skills:editorial-grid"
source_commit: null
counter_nodes:
  - EDIT-GRID-SCALE-001
  - EDIT-GRID-SCALE-002
named_in: "editorial-framework:grid-construction"
edges:
  - { target: EDIT-GRID-SCALE-001, type: COUNTERS }
  - { target: EDIT-GRID-SCALE-002, type: COUNTERS }
---

# Anti-pattern: Ad-hoc type sizing

## Why this is broken

List all type sizes in the layout. If they cannot be expressed as values in a single scale (classical progression, modular ratio, or double-stranded), the hierarchy is accidental. Adjacent sizes that are too close blur the distinction; sizes too far apart create gaps in the hierarchy.

## Counter

Choose a scale. Name it. Derive all sizes from it.
```

Note: AntiPattern requires `counter_nodes`. COUNTERS edges point to what fixes it. Body has "Why this is broken" and "Counter" sections.

---

## Playbook: PBK-EDIT-ELENCHUS-001

```yaml
---
playbook_id: PBK-EDIT-ELENCHUS-001
node_type: Playbook
domain: editorial
severity: high
scope: task
trigger: "When starting an article, essay, spread, or page-scale visual artifact intended to argue rather than display. When stuck in pre-design circling and unable to commit to a grid, scale, or composition because the argument underneath has not been named."
statement: "Five-phase pre-design method: find the question, find the antinomy, find the answer, assign form, refuse to design until moves 1-4 are done. The elenchus names the argument before the grid can hold it. Without a named argument, the grid passes through the content like mist."
rationale: "Socratic elenchus (cross-examination, refutation) destroys unearned answers and leaves the more honest position of not-knowing-yet. The method is maieutic: it midwifes a thought already present. Most pre-design circling is caused by attempting to design content whose argument has not yet been stated."
tags: [elenchus, editorial, philosophy, pre-design, socratic, argument, playbook]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-01
staleness_window: 365
evidence: peer-reviewed
source_attribution: "editorial-claude-skills:elenchus"
source_commit: null
phase_ids:
  - PHA-EDIT-ELENCHUS-001
  - PHA-EDIT-ELENCHUS-002
  - PHA-EDIT-ELENCHUS-003
  - PHA-EDIT-ELENCHUS-004
  - PHA-EDIT-ELENCHUS-005
preconditions:
  - "Content argues rather than displays (essays, investigations, manifestos, philosophical writing)"
dispatched_roles: []
edges:
  - { target: PHA-EDIT-ELENCHUS-001, type: CONTAINS }
  - { target: PHA-EDIT-ELENCHUS-002, type: CONTAINS }
  - { target: PHA-EDIT-ELENCHUS-003, type: CONTAINS }
  - { target: PHA-EDIT-ELENCHUS-004, type: CONTAINS }
  - { target: PHA-EDIT-ELENCHUS-005, type: CONTAINS }
  - { target: TEC-EDIT-ARCHITECTURE-001, type: DISPATCHES }
  - { target: TEC-EDIT-TENSION-001, type: DISPATCHES }
  - { target: TEC-EDIT-PROSE-001, type: DISPATCHES }
  - { target: TEC-EDIT-CONSTRUCTION-001, type: DISPATCHES }
  - { target: EDIT-ARCH-IDENTIFY-001, type: TEACHES }
  - { target: EDIT-GRID-PROPORTION-001, type: PRECEDES }
---

# Playbook: Elenchus (pre-design method)

## Phase references

1. `PHA-EDIT-ELENCHUS-001` -- Find the question
2. `PHA-EDIT-ELENCHUS-002` -- Find the antinomy
3. `PHA-EDIT-ELENCHUS-003` -- Find the answer
4. `PHA-EDIT-ELENCHUS-004` -- Assign form
5. `PHA-EDIT-ELENCHUS-005` -- Refuse to design

## Output

When complete, you have:
- Three sentences: question (interrogative), antinomy (two clauses), answer (declarative)
- Four form-assignments: architecture, tension, prose, construction
```

Note: Playbook requires `phase_ids`, `preconditions`. CONTAINS edges for every phase. DISPATCHES for techniques used. Body lists phases and output.

---

## Phase: PHA-EDIT-ELENCHUS-001

```yaml
---
phase_id: PHA-EDIT-ELENCHUS-001
node_type: Phase
domain: editorial
scope: task
trigger: "First phase of PBK-EDIT-ELENCHUS-001. Fires when elenchus begins."
statement: "Find the question. One sentence. Interrogative. Specific enough that it can be wrong. The question commits to an answer; a topic does not."
rationale: "You cannot draw a grid for a wander. You can draw a grid for a question. The distinction between question and topic is the distinction between an article with edges and one without."
tags: [elenchus, question, phase, editorial]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-01
staleness_window: 365
evidence: peer-reviewed
source_attribution: "editorial-claude-skills:elenchus"
source_commit: null
position: 1
name: "Find the question"
description: |
  One sentence. Interrogative. Specific enough that it can be wrong.
  "Why does Orpheus look back when he was told not to?" is a question.
  "Orpheus and the nature of love" is a topic.
  The question commits you to an answer; the topic does not.
parent_playbook_id: PBK-EDIT-ELENCHUS-001
edges: []
---

# Phase 1: Find the question

Non-retrievable structural node. Surfaces via CONTAINS edge from PBK-EDIT-ELENCHUS-001.

## Advance criterion

One interrogative sentence stated. The sentence is specific enough that it can be wrong.
```

Note: Phase is non-retrievable. Severity is optional. Requires `position`, `name`, `description`, `parent_playbook_id`. Body is brief with advance criterion.

---

## Technique: TEC-EDIT-ARCHITECTURE-001

```yaml
---
technique_id: TEC-EDIT-ARCHITECTURE-001
node_type: Technique
domain: editorial
severity: medium
scope: layout
trigger: "When the elenchus question or answer needs a layout form. The architecture form renders a single sentence at page scale so the reader is enclosed by it."
statement: "Architecture form: single sentence at page scale. The reader does not approach the question; the reader is enclosed by it. Very little else on the page. The case number, perhaps, and the date, in the smallest possible apparatus. Everything else is the sentence and the room around it."
rationale: "The question wants to be encountered, not read. The architecture form fills the page the way the wound fills the day it announces itself."
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
```

Note: Technique has no extra required fields beyond base. DEMONSTRATES edges to what it shows. DEPENDS_ON for prerequisites.
