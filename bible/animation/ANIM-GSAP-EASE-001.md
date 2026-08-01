---
rule_id: ANIM-GSAP-EASE-001
node_type: Rule
domain: animation
severity: low
scope: component
mandatory: false
trigger: |
  When specifying easing for a GSAP tween.
statement: |
  Use documented built-in ease names only. Invalid or misspelled ease strings fail silently, falling back to the default ease (power1.out). Built-in eases: none, power1-4, back, bounce, circ, elastic, expo, sine, each with .in, .out, .inOut variants. Use CustomEase plugin for custom curves.
violation: |
  ```javascript
  // Misspelled ease: silently falls back to default
  gsap.to(".box", { x: 100, ease: "easeInOutQuad" });
  // CSS-style name: not recognized by GSAP
  gsap.to(".box", { x: 100, ease: "cubic-bezier(0.4, 0, 0.2, 1)" });
  ```
pass_example: |
  ```javascript
  // Correct built-in ease names
  gsap.to(".box", { x: 100, ease: "power2.inOut" });
  gsap.to(".box", { x: 100, ease: "back.out(1.7)" });
  gsap.to(".box", { x: 100, ease: "elastic.out(1, 0.3)" });
  ```
enforcement: |
  Code review. Verify ease values against the GSAP built-in list. Flag CSS-style easing names (easeInOut, cubic-bezier) or jQuery-style names (easeInOutQuad).
rationale: |
  GSAP's ease parser does not throw on unrecognized names; it silently defaults. This means a typo in an ease string produces a working but visually wrong animation. The developer sees smooth motion and assumes their ease is applied when it is actually the default. GSAP's ease namespace (power1-4, back, bounce, circ, elastic, expo, sine) does not match CSS (ease-in-out, cubic-bezier) or jQuery UI (easeInOutQuad) naming conventions.
tags: [animation, easing, gsap, rule, silent-failure]
confidence: peer-reviewed
authority: ai-provisional
last_validated: 2026-06-05
staleness_window: 365
evidence: peer-reviewed
source_attribution: "gsap-skills:gsap-core"
source_commit: null
edges: []
---

# Rule: Documented ease names only

GSAP ease strings are case-sensitive and namespace-specific. Invalid names produce no error; the tween runs with the default ease. Common mistakes: CSS-style names (ease-in-out), jQuery UI names (easeInOutQuad), and typos in the GSAP namespace.
