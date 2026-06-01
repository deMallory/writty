---
antipattern_id: ANT-EDIT-PHANTOM-001
node_type: AntiPattern
domain: editorial
severity: medium
scope: layout
trigger: "When heavy adjacent visual elements (thick rules, dark borders, dense columns) create unintended phantom visual elements in the space between them."
statement: "1+1=3 effect (Tufte): two adjacent visual elements generate a third, unintended visual element in the space between them. Heavy adjacent rules create phantom rules. Closely spaced columns of dark text create a phantom vertical band in the gutter. Every additional heavy element multiplies the phantom-element problem nonlinearly."
rationale: "Tufte identified the 1+1=3 effect as the reason minimal designs feel cleaner: fewer heavy elements means fewer phantom artifacts. The problem compounds nonlinearly because each new heavy element creates phantom relationships with every existing heavy element."
tags: [anti-pattern, editorial, tufte, phantom, visual-noise, gutter]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-01
staleness_window: 365
evidence: peer-reviewed
source_attribution: "editorial-claude-skills:spread-archetypes"
source_commit: null
counter_nodes:
  - EDIT-VIZ-INK-001
  - EDIT-ARCH-WHITESPACE-001
named_in: "editorial-framework:whitespace-and-axis"
edges:
  - { target: EDIT-VIZ-INK-001, type: COUNTERS }
  - { target: EDIT-ARCH-WHITESPACE-001, type: COUNTERS }
---

# Anti-pattern: 1+1=3 phantom elements

## Why this is broken

The eye groups adjacent heavy elements and perceives the gap between them as a third element. Examples:

- Two thick horizontal rules with a narrow gap: the gap reads as a white rule
- Two dark text columns with a narrow gutter: the gutter reads as a white stripe
- A grid of bordered cells: the borders create a secondary grid of phantom lines in the space between cells

Each new heavy element creates phantom relationships with every existing one. Three heavy rules create three phantom rules. Four create six. The visual noise scales quadratically.

## Counter

Lighten one element in every heavy-adjacent pair. Use hierarchy by weight (primary in dark/saturated, secondary in light gray) rather than multiple heavy elements competing at the same weight. Minimize non-data elements specifically to keep negative space calm and functional.

## Diagnostic

Squint at the layout. Do you see shapes or bands that are not in the markup? Those are phantoms. The cure is always to reduce the weight of adjacent heavy elements, not to add more spacing between them.
