---
rule_id: ANIM-GSAP-TIMELINE-001
node_type: Rule
domain: animation
severity: high
scope: component
mandatory: false
trigger: |
  When sequencing multiple animations on one or more targets.
statement: |
  Use gsap.timeline() for sequencing. Do not chain independent tweens using calculated delay offsets. Timelines compose, can be controlled as a unit (pause, reverse, seek), and automatically adjust when any child's duration changes. Delay-chained tweens require manual arithmetic that breaks silently.
violation: |
  ```javascript
  // Delay chaining: fragile; changing box1 duration breaks box2 timing
  gsap.to(".box1", { x: 100, duration: 0.5 });
  gsap.to(".box2", { y: 50, duration: 0.3, delay: 0.5 });
  gsap.to(".box3", { scale: 1.5, duration: 0.4, delay: 0.8 });
  ```
pass_example: |
  ```javascript
  // Timeline: self-adjusting, controllable as a unit
  const tl = gsap.timeline();
  tl.to(".box1", { x: 100, duration: 0.5 })
    .to(".box2", { y: 50, duration: 0.3 })
    .to(".box3", { scale: 1.5, duration: 0.4 });
  ```
enforcement: |
  Code review. Flag sequences of gsap.to/from calls with incrementing delay values that could be replaced by a timeline.
rationale: |
  Delay-based sequencing embeds timing assumptions as magic numbers. When any tween's duration changes, all subsequent delays must be recalculated manually. Timelines handle this automatically: each child starts after the previous one ends (or at a relative position). Timelines also expose a single control surface (pause, reverse, seek the entire sequence) that delay chains cannot provide.
tags: [animation, delay, gsap, rule, sequencing, timeline]
confidence: peer-reviewed
authority: ai-provisional
last_validated: 2026-06-05
staleness_window: 365
evidence: peer-reviewed
source_attribution: "gsap-skills:gsap-core"
source_commit: null
edges: []
---

# Rule: Timelines for sequencing

gsap.timeline() is GSAP's composition primitive. Children play in sequence by default, with position parameters for overlap or offset. The timeline itself is a controllable unit: pause, reverse, seek, and progress apply to the entire sequence.
