---
rule_id: ANIM-GSAP-TRANSFORM-001
node_type: Rule
domain: animation
severity: high
scope: component
mandatory: false
trigger: |
  When animating element position, size, or rotation with GSAP.
statement: |
  Use GSAP's transform aliases (x, y, z, scale, scaleX, scaleY, rotation, rotationX, rotationY, xPercent, yPercent) instead of layout properties (width, height, top, left, margin, padding). Transform aliases use the GPU-composited transform pipeline; layout properties trigger browser reflow on every frame.
violation: |
  ```javascript
  // Layout properties: triggers reflow, janky on every frame
  gsap.to(".box", { width: 200, height: 200, top: 100, left: 50 });
  ```
pass_example: |
  ```javascript
  // Transform aliases: GPU-composited, smooth
  gsap.to(".box", { x: 50, y: 100, scale: 1.5 });
  ```
enforcement: |
  Code review. Flag gsap.to/from/fromTo calls that animate width, height, top, left, margin, or padding when a transform alias achieves the same visual result.
rationale: |
  Browser rendering separates layout (reflow) from compositing (GPU). Animating layout properties forces the browser to recalculate geometry for potentially the entire document on every frame. Transform and opacity are the only properties that skip layout and paint, running entirely on the compositor thread. GSAP's transform aliases (x, y, scale, rotation) map directly to CSS transforms and apply in a consistent, cross-browser order: translation, scale, rotationX/Y, skew, rotation.
tags: [animation, gpu, gsap, layout, performance, reflow, rule, transform]
confidence: peer-reviewed
authority: ai-provisional
last_validated: 2026-06-05
staleness_window: 365
evidence: peer-reviewed
source_attribution: "gsap-skills:gsap-core"
source_commit: null
edges: []
---

# Rule: Transform aliases over layout properties

GSAP provides shorthand aliases (x, y, scale, rotation, xPercent, yPercent) that compile to CSS transforms. These run on the GPU compositor thread. Layout properties (width, height, top, left) trigger a full layout-paint-composite cycle on every frame, visible as jank at 60fps.

Prefer autoAlpha over opacity for the same reason: autoAlpha additionally sets visibility:hidden at 0, removing the element from hit testing.
