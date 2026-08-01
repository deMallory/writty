---
antipattern_id: ANT-EDIT-DIAMETER-001
node_type: AntiPattern
domain: editorial
severity: critical
scope: component
trigger: "When proportional shapes (circles, bubbles, squares) in a data visualization are scaled by diameter or radius rather than by area."
statement: "Diameter scaling: sizing proportional shapes by linear dimension rather than area. A value 2x larger drawn with 2x the radius produces 4x the area, creating quadratic exaggeration. Lie Factor = 2.0 (severe distortion). Viewers already underestimate area differences; diameter scaling compounds the error."
rationale: "Tufte's first principle of graphical integrity: representation of numbers should be directly proportional to quantities represented. Diameter scaling is the most common Lie Factor violation because it looks subtle (the circle is 'only twice as big') while distorting badly (the visual area is four times as large)."
tags: [anti-pattern, editorial, visualization, tufte, lie-factor, distortion]
confidence: battle-tested
authority: human
last_validated: 2026-06-01
staleness_window: 365
evidence: peer-reviewed
source_attribution: "editorial-claude-skills:tufte-viz"
source_commit: null
counter_nodes:
  - EDIT-VIZ-LIE-001
named_in: "editorial-framework:tufte-principles"
edges:
  - { target: EDIT-VIZ-LIE-001, type: COUNTERS }
---

# Anti-pattern: Diameter scaling

## Why this is broken

Area scales with the square of the radius. Doubling the radius quadruples the area. The visual system reads area, not diameter, so:

- A value 2x larger appears 4x larger (Lie Factor = 2.0)
- A value 3x larger appears 9x larger (Lie Factor = 3.0)
- A value 10x larger appears 100x larger (Lie Factor = 10.0)

The distortion is nonlinear and accelerates with magnitude.

## Counter

Scale by area: `radius = sqrt(value / PI) * scale_factor`. This ensures that a value 2x larger produces a circle with 2x the area (Lie Factor = 1.0). Every proportional shape must be directly labeled with its actual value because viewers underestimate area differences even when scaling is correct.

## Detection

Look for: `r = value * k` or `width = value * k` in chart code. Correct code uses `r = sqrt(value) * k` or equivalent.
