---
rule_id: ANIM-GSAP-RETURNVAL-001
node_type: Rule
domain: animation
severity: medium
scope: component
mandatory: false
trigger: |
  When a tween or timeline needs runtime control: pause, play, reverse, seek, kill, or progress inspection.
statement: |
  Store the return value of gsap.to(), gsap.from(), gsap.fromTo(), or gsap.timeline() in a variable. All tween methods return a Tween instance; timeline() returns a Timeline. Without the reference, the animation cannot be controlled after creation.
violation: |
  ```javascript
  // Fire-and-forget: no way to pause or reverse
  gsap.to(".box", { x: 100, duration: 2 });
  // Later: how to pause? No reference exists.
  ```
pass_example: |
  ```javascript
  const tween = gsap.to(".box", { x: 100, duration: 2 });
  // Later:
  tween.pause();
  tween.reverse();
  tween.progress(0.5);
  tween.kill();
  ```
enforcement: |
  Code review. If any tween is later referenced for control (pause, play, reverse, kill, progress, time, totalTime), verify the return value was stored.
rationale: |
  GSAP tweens are objects with a full playback API (pause, play, reverse, seek, kill, progress, time, totalTime). Discarding the return value is correct for fire-and-forget animations but is a bug when control is needed later. In frameworks like React, the reference is typically stored in a useRef to survive re-renders.
tags: [animation, control, gsap, playback, reference, rule, tween]
confidence: peer-reviewed
authority: ai-provisional
last_validated: 2026-06-05
staleness_window: 365
evidence: peer-reviewed
source_attribution: "gsap-skills:gsap-core"
source_commit: null
edges: []
---

# Rule: Store tween return values for control

gsap.to/from/fromTo return a Tween instance. gsap.timeline() returns a Timeline. Both expose pause(), play(), reverse(), kill(), progress(), time(), and totalTime(). Discarding the reference makes the animation uncontrollable.
