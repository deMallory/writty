---
rule_id: ANIM-GSAP-AUTOALPHA-001
node_type: Rule
domain: animation
severity: medium
scope: component
mandatory: false
trigger: |
  When fading elements in or out with GSAP.
statement: |
  Use autoAlpha instead of opacity for fade animations. When autoAlpha reaches 0, GSAP sets visibility: hidden, removing the element from hit testing and improving rendering. When non-zero, visibility is set to inherit. Animating opacity alone leaves an invisible element that still captures pointer events and occupies the accessibility tree.
violation: |
  ```javascript
  // opacity alone: element invisible but still captures clicks
  gsap.to(".overlay", { opacity: 0, duration: 0.5 });
  ```
pass_example: |
  ```javascript
  // autoAlpha: invisible AND non-interactive at 0
  gsap.to(".overlay", { autoAlpha: 0, duration: 0.5 });
  ```
enforcement: |
  Code review. Flag gsap.to/from calls using opacity for fade-out (to 0) where autoAlpha is not used instead.
rationale: |
  An element with opacity: 0 remains in the document flow, captures click and hover events, and is announced by screen readers. This creates invisible click targets that block interaction with elements underneath. autoAlpha is GSAP's solution: it animates opacity and toggles visibility automatically at the zero boundary.
tags: [accessibility, animation, autoalpha, fade, gsap, opacity, rule, visibility]
confidence: peer-reviewed
authority: ai-provisional
last_validated: 2026-06-05
staleness_window: 365
evidence: peer-reviewed
source_attribution: "gsap-skills:gsap-core"
source_commit: null
edges:
  - { target: ANIM-GSAP-TRANSFORM-001, type: DEPENDS_ON }
---

# Rule: autoAlpha for fade animations

autoAlpha combines opacity animation with automatic visibility toggling. At 0 the element is fully hidden (visibility: hidden); at any non-zero value, visibility is inherit. This prevents invisible elements from blocking clicks or appearing in the accessibility tree.
