---
antipattern_id: ANT-ANIM-DELAYCHAINING-001
node_type: AntiPattern
domain: animation
severity: medium
scope: component
trigger: "When multiple independent gsap.to/from calls are sequenced using calculated delay offsets instead of a timeline."
statement: "Delay chaining: sequencing animations by manually computing delay values (delay: 0.5, delay: 0.8, delay: 1.2) embeds timing as magic numbers. When any tween's duration changes, all downstream delays must be recalculated. The chain cannot be paused, reversed, or seeked as a unit."
rationale: "Delay-based sequencing is the procedural approach to a problem GSAP solved declaratively with timelines. A timeline automatically places each child after the previous one ends, adjusts when durations change, and exposes a single control surface for the entire sequence. Delay chains replicate this behavior with manual arithmetic that is fragile, uncontrollable, and invisible to debugging tools."
tags: [animation, anti-pattern, delay, gsap, sequencing, timeline]
confidence: peer-reviewed
authority: ai-provisional
last_validated: 2026-06-05
staleness_window: 365
evidence: peer-reviewed
source_attribution: "gsap-skills:gsap-core"
source_commit: null
counter_nodes:
  - ANIM-GSAP-TIMELINE-001
edges:
  - { target: ANIM-GSAP-TIMELINE-001, type: COUNTERS }
---

# Anti-pattern: Delay chaining

## Why this is broken

Delay chaining produces correct timing exactly once. Any change to a tween's duration requires recalculating every downstream delay. The chain cannot be paused or reversed as a unit. GSAP's DevTools plugin cannot visualize the sequence because the tweens are unrelated.

Symptoms:
- Cascading timing bugs when any duration changes
- Inability to pause/reverse the sequence
- Magic numbers in delay fields with no explanation

## Counter

Replace with gsap.timeline(). Children play in sequence by default. Position parameters (">", "<", "+=0.2") handle overlap. See ANIM-GSAP-TIMELINE-001.
