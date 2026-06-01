---
phase_id: PHA-EDIT-ELENCHUS-004
node_type: Phase
domain: editorial
scope: task
trigger: "Fourth phase of PBK-EDIT-ELENCHUS-001. Fires after the three sentences are clear."
statement: "Assign form. Each part of the argument binds to one form: question to architecture form, antinomy to tension form, development to prose form, synthesis to construction form. These are bridges into spread-archetypes and editorial-grid."
rationale: "The form-assignment is the bridge between philosophical method and design execution. Without it, the grid has no argument to hold. With it, each layout element has a named purpose derived from the argument's structure."
tags: [elenchus, form-assignment, architecture, tension, prose, construction, phase, editorial]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-01
staleness_window: 365
evidence: peer-reviewed
source_attribution: "editorial-claude-skills:elenchus"
source_commit: null
position: 4
name: "Assign form"
description: |
  Each argument part binds to one form:
  - Question -> Architecture form (single sentence at page scale, reader enclosed)
  - Antinomy -> Tension form (two clauses held apart, geometry refuses to close)
  - Development -> Prose form (multi-column body with sidenotes)
  - Synthesis -> Construction form (figure built on a visible grid)
  See TEC-EDIT-ARCHITECTURE-001, TEC-EDIT-TENSION-001, TEC-EDIT-PROSE-001, TEC-EDIT-CONSTRUCTION-001.
parent_playbook_id: PBK-EDIT-ELENCHUS-001
edges:
  - { target: TEC-EDIT-ARCHITECTURE-001, type: DISPATCHES }
  - { target: TEC-EDIT-TENSION-001, type: DISPATCHES }
  - { target: TEC-EDIT-PROSE-001, type: DISPATCHES }
  - { target: TEC-EDIT-CONSTRUCTION-001, type: DISPATCHES }
---

# Phase 4: Assign form

Non-retrievable structural node. Surfaces via CONTAINS edge from PBK-EDIT-ELENCHUS-001.

## Advance criterion

All four form-assignments stated: architecture, tension, prose, construction. Each bound to its argument part.
