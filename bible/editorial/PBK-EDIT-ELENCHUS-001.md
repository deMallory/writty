---
playbook_id: PBK-EDIT-ELENCHUS-001
node_type: Playbook
domain: editorial
severity: high
scope: task
trigger: "When starting an article, essay, spread, or page-scale visual artifact intended to argue rather than display. When stuck in pre-design circling and unable to commit to a grid, scale, or composition because the argument underneath has not been named."
statement: "Five-phase pre-design method: find the question, find the antinomy, find the answer, assign form, refuse to design until moves 1-4 are done. The elenchus names the argument before the grid can hold it. Without a named argument, the grid passes through the content like mist."
rationale: "Socratic elenchus (cross-examination, refutation) destroys unearned answers and leaves the more honest position of not-knowing-yet. The method is maieutic: it midwifes a thought already present. Most pre-design circling is caused by attempting to design content whose argument has not yet been stated. The three sentences (question, antinomy, answer) are the exit from the abyssal nest."
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

Every article begins as a wound. Not a topic. A wound: a place where the world refuses to make sense, where two things that should be true cannot both be true. The article is the examination of the wound. The first work, before any layout, is naming the wound as a question.

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

These hand off to the grid and archetype skills for structural execution.

## When not to invoke

Do not invoke for content that displays: documentation, indexes, lists, navigation, utility surfaces, data dashboards, transactional flows. Those go straight to grid construction and archetype selection without elenchus.

## The refusal

If the three sentences will not clarify, if the question keeps revising itself, if the antinomy will not name itself, do not proceed to design. The article is not ready. This is not failure; it is fidelity.
