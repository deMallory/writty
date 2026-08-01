---
rule_id: ANIM-GSAP-IMMEDIATERENDER-001
node_type: Rule
domain: animation
severity: high
scope: component
mandatory: false
trigger: |
  When multiple from() or fromTo() tweens target the same property of the same element.
statement: |
  Set immediateRender: false on the later tweens. By default, from() and fromTo() apply their start state the instant the tween is created (immediateRender: true). When a second tween targets the same property, its immediate render overwrites the first tween's end state before the first tween runs, making the first animation invisible.
violation: |
  ```javascript
  // Both tweens immediateRender: true (default for from/fromTo)
  // Second tween's start state overwrites first tween's end state
  gsap.from(".box", { x: -100, duration: 1 });
  gsap.from(".box", { x: 200, duration: 1, delay: 1 });
  // The first animation appears to do nothing
  ```
pass_example: |
  ```javascript
  gsap.from(".box", { x: -100, duration: 1 });
  gsap.from(".box", { x: 200, duration: 1, delay: 1, immediateRender: false });
  // Both animations visible; second waits for its delay
  ```
enforcement: |
  Code review. When multiple from() or fromTo() calls target the same element and property, verify that all but the first set immediateRender: false.
rationale: |
  GSAP's immediateRender default exists to prevent flash of unstyled content: the start state is applied before the browser's next paint. This is correct for a single tween but creates a conflict when multiple tweens write to the same property at creation time. The second write wins, and the first tween's from-state is lost. This is the most common source of "my first animation isn't working" bugs in GSAP.
tags: [animation, from, fromto, gsap, immediaterender, rule, stacking]
confidence: peer-reviewed
authority: ai-provisional
last_validated: 2026-06-05
staleness_window: 365
evidence: peer-reviewed
source_attribution: "gsap-skills:gsap-core"
source_commit: null
edges: []
---

# Rule: immediateRender: false on stacked from/fromTo

The default immediateRender: true is correct for a single from() tween. It becomes a bug when two or more from/fromTo tweens write to the same property of the same element: the last one created wins and silently erases the first tween's animation range.
