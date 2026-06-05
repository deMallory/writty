---
technique_id: TEC-ANIM-STAGGER-001
node_type: Technique
domain: animation
severity: medium
scope: component
trigger: "When animating a set of elements with offset start times in GSAP."
statement: "Stagger object syntax: use the object form {amount, each, from, grid, axis} for fine control over how start-time offsets are distributed across targets. The 'from' property controls distribution origin: 'start', 'center', 'end', 'edges', 'random', or a numeric index."
rationale: "The simple stagger: 0.1 shorthand distributes evenly from the first element. The object syntax unlocks non-linear distributions (center-out, edges-in, random) and grid-aware patterns (grid: [rows, cols] with axis: 'x' or 'y'). These produce more natural motion for grids, lists, and UI element groups without requiring separate tween calls."
tags: [animation, distribution, gsap, stagger, technique, timing]
confidence: peer-reviewed
authority: ai-provisional
last_validated: 2026-06-05
staleness_window: 365
evidence: peer-reviewed
source_attribution: "gsap-skills:gsap-core"
source_commit: null
edges: []
---

# Technique: Stagger patterns

Simple form offsets each target by a fixed amount:

```javascript
gsap.to(".item", { y: -20, stagger: 0.1 });
```

Object form for advanced distribution:

```javascript
gsap.to(".item", {
  y: -20,
  stagger: {
    amount: 0.5,        // total stagger time spread across all targets
    from: "center",     // radiate from center outward
    grid: [4, 5],       // treat targets as a 4x5 grid
    axis: "x"           // stagger along x-axis only
  }
});
```

The `from` property accepts: "start" (default), "center", "end", "edges", "random", or a numeric index. Grid-aware stagger requires `grid: [rows, cols]` and optionally `axis`.
