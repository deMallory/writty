---
antipattern_id: ANT-ANIM-LAYOUT-001
node_type: AntiPattern
domain: animation
severity: high
scope: component
trigger: "When a GSAP tween animates width, height, top, left, margin, or padding on a DOM element."
statement: "Layout property animation: animating layout-triggering CSS properties (width, height, top, left, margin, padding) forces the browser to recalculate geometry for the affected subtree on every frame. At 60fps this means 16ms per reflow budget, which layout recalculation routinely exceeds, producing visible jank."
rationale: "Browser rendering pipelines separate layout, paint, and compositing into distinct stages. Only transform and opacity skip the layout and paint stages entirely, running on the GPU compositor thread. Any other animated property forces at least a paint; layout properties force the most expensive path: layout, paint, and composite. GSAP provides transform aliases specifically to avoid this."
tags: [animation, anti-pattern, gsap, jank, layout, performance, reflow]
confidence: peer-reviewed
authority: ai-provisional
last_validated: 2026-06-05
staleness_window: 365
evidence: peer-reviewed
source_attribution: "gsap-skills:gsap-core"
source_commit: null
counter_nodes:
  - ANIM-GSAP-TRANSFORM-001
edges:
  - { target: ANIM-GSAP-TRANSFORM-001, type: COUNTERS }
---

# Anti-pattern: Layout property animation

## Why this is broken

Animating width, height, top, or left triggers browser reflow on every frame. The browser must recalculate the geometry of the element and potentially its siblings and ancestors. This is the single largest source of animation jank in web applications.

Symptoms:
- Dropped frames visible in DevTools Performance panel
- "Layout" bars exceeding the 16ms frame budget
- Janky motion on mid-range mobile devices even when desktop appears smooth

## Counter

Replace layout properties with GSAP transform aliases. x/y for position, scale for size changes, xPercent/yPercent for percentage-based movement. See ANIM-GSAP-TRANSFORM-001.
