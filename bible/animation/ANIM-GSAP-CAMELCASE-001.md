---
rule_id: ANIM-GSAP-CAMELCASE-001
node_type: Rule
domain: animation
severity: medium
scope: component
mandatory: false
trigger: |
  When writing property objects (vars) for gsap.to(), gsap.from(), gsap.fromTo(), or gsap.set().
statement: |
  Use camelCase for all CSS property names in GSAP vars objects. GSAP's CSSPlugin expects camelCase (backgroundColor, marginTop, fontSize), not CSS kebab-case (background-color, margin-top, font-size). Kebab-case keys are silently ignored, producing no animation.
violation: |
  ```javascript
  // Kebab-case: silently ignored, no animation occurs
  gsap.to(".box", { "background-color": "red", "font-size": "20px" });
  ```
pass_example: |
  ```javascript
  // camelCase: GSAP recognizes and animates these properties
  gsap.to(".box", { backgroundColor: "red", fontSize: "20px" });
  ```
enforcement: |
  Code review. Grep vars objects for quoted hyphenated property names. Linter rule if available.
rationale: |
  GSAP's CSSPlugin parses property names as JavaScript object keys mapped to the DOM style API, which uses camelCase (element.style.backgroundColor). Kebab-case keys do not match any recognized property and are dropped without warning, leaving the developer with a tween that appears to run but changes nothing.
tags: [animation, camelcase, css, gsap, property, rule]
confidence: peer-reviewed
authority: ai-provisional
last_validated: 2026-06-05
staleness_window: 365
evidence: peer-reviewed
source_attribution: "gsap-skills:gsap-core"
source_commit: null
edges: []
---

# Rule: camelCase property names in GSAP vars

GSAP's CSSPlugin maps property names to the DOM style API. The style API uses camelCase. Any kebab-case key is silently dropped. This is the most common beginner mistake with GSAP and produces animations that run to completion but visibly do nothing.
