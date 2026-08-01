---
technique_id: TEC-ANIM-DEFAULTS-001
node_type: Technique
domain: animation
severity: low
scope: task
trigger: "When multiple tweens across a project share the same duration, ease, or other common vars."
statement: "gsap.defaults() sets project-wide tween defaults. Call once at initialization. All subsequent tweens inherit these values unless explicitly overridden. Reduces repetition and ensures consistent motion feel across the application."
rationale: "Inconsistent duration and easing across an application produces a disjointed motion language. gsap.defaults() establishes a single source of truth for the base motion feel. Individual tweens can still override any default. This is the GSAP equivalent of design tokens for motion."
tags: [animation, consistency, defaults, gsap, motion-design, technique]
confidence: peer-reviewed
authority: ai-provisional
last_validated: 2026-06-05
staleness_window: 365
evidence: peer-reviewed
source_attribution: "gsap-skills:gsap-core"
source_commit: null
edges: []
---

# Technique: gsap.defaults for project-wide consistency

```javascript
gsap.defaults({ duration: 0.6, ease: "power2.out" });
```

Call once at app initialization. All gsap.to/from/fromTo calls inherit these values. Override per-tween as needed. Timeline defaults (tl.defaults()) scope to that timeline's children only, useful for section-specific motion.
