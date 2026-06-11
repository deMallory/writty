---
rule_id: ANIM-GSAP-SVGORIGIN-001
node_type: Rule
domain: animation
severity: medium
scope: component
mandatory: false
trigger: |
  When setting transform origin on SVG elements animated with GSAP.
statement: |
  Use either svgOrigin or transformOrigin on an SVG element, never both. Only one applies; the other is silently ignored. svgOrigin uses the SVG's global coordinate space (e.g., "250 100") and is useful when multiple elements should rotate around a common point. transformOrigin is element-local. svgOrigin does not accept percentage values.
violation: |
  ```javascript
  // Both set: transformOrigin takes precedence; svgOrigin is ignored
  gsap.to(svgEl, { rotation: 90, svgOrigin: "100 100", transformOrigin: "50% 50%" });
  ```
pass_example: |
  ```javascript
  // svgOrigin only: global coordinate, shared pivot point
  gsap.to(svgEl, { rotation: 90, svgOrigin: "100 100" });

  // OR transformOrigin only: element-local pivot
  gsap.to(svgEl, { rotation: 90, transformOrigin: "center center" });
  ```
enforcement: |
  Code review. Flag GSAP tween vars that contain both svgOrigin and transformOrigin on an SVG target.
rationale: |
  SVG coordinate systems differ from HTML. transformOrigin operates in the element's local coordinate space; svgOrigin operates in the SVG viewBox's global coordinate space. If both are specified, transformOrigin takes precedence and svgOrigin is ignored, which can hide the intended pivot.
tags: [animation, gsap, rule, svg, svgorigin, transform-origin]
confidence: peer-reviewed
authority: ai-provisional
last_validated: 2026-06-05
staleness_window: 365
evidence: peer-reviewed
source_attribution: "gsap-skills:gsap-core"
source_commit: null
edges: []
---

# Rule: svgOrigin or transformOrigin, not both

SVG transform origins in GSAP: svgOrigin uses global SVG coordinates (useful for shared pivot points across elements), transformOrigin uses element-local coordinates. Setting both silently drops one.
