---
technique_id: TEC-ANIM-FUNCTIONVALS-001
node_type: Technique
domain: animation
severity: medium
scope: component
trigger: "When each target in a GSAP tween needs a different animation value based on its index, element, or context."
statement: "Function-based values: pass a function as any vars property value. The function receives (index, target, targetsArray) and is called once per target when the tween first renders. The return value becomes that target's animation value. Combine with stagger for offset timing."
rationale: "Hardcoding per-target values requires separate tween calls for each element. Function-based values let a single tween handle N targets with computed values, keeping the animation declarative. The function is called once at render time, not on every frame, so performance cost is negligible."
tags: [animation, dynamic, function, gsap, per-target, technique]
confidence: peer-reviewed
authority: ai-provisional
last_validated: 2026-06-05
staleness_window: 365
evidence: peer-reviewed
source_attribution: "gsap-skills:gsap-core"
source_commit: null
edges:
  - { target: ANIM-GSAP-TRANSFORM-001, type: DEMONSTRATES }
---

# Technique: Function-based values

Pass a function instead of a static value for any GSAP vars property:

```javascript
gsap.to(".item", {
  x: (i, target, targets) => i * 50,
  rotation: (i) => i % 2 === 0 ? 45 : -45,
  stagger: 0.1
});
```

The function is called once per target at first render. Arguments: index (0-based), the target element, and the full targets array. Works with any animatable property. Combine with stagger for distributed, dynamic animations from a single tween call.
