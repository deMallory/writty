---
rule_id: ANIM-GSAP-MATCHMEDIA-001
node_type: Rule
domain: animation
severity: high
scope: component
mandatory: false
trigger: |
  When animations must adapt to viewport size or respect the user's prefers-reduced-motion setting.
statement: |
  Use gsap.matchMedia() for responsive breakpoints and reduced-motion support. matchMedia runs setup code only when a media query matches; when it stops matching, all animations and ScrollTriggers created in that run are reverted automatically. For prefers-reduced-motion, set duration: 0 or skip the animation entirely. Do not nest gsap.context() inside matchMedia; matchMedia creates its own context internally.
violation: |
  ```javascript
  // No reduced-motion handling; animations run regardless of user preference
  gsap.to(".hero", { x: 200, rotation: 360, duration: 2 });
  ```
pass_example: |
  ```javascript
  const mm = gsap.matchMedia();
  mm.add(
    {
      isDesktop: "(min-width: 800px)",
      isMobile: "(max-width: 799px)",
      reduceMotion: "(prefers-reduced-motion: reduce)"
    },
    (context) => {
      const { isDesktop, reduceMotion } = context.conditions;
      gsap.to(".hero", {
        x: isDesktop ? 200 : 50,
        rotation: isDesktop ? 360 : 180,
        duration: reduceMotion ? 0 : 2
      });
    }
  );
  ```
enforcement: |
  Code review. Any GSAP animation visible to end users should handle prefers-reduced-motion via matchMedia or an equivalent mechanism. Flag animation code that lacks reduced-motion handling.
rationale: |
  Users with vestibular disorders experience nausea, dizziness, or disorientation from animated content. prefers-reduced-motion is a system-level accessibility preference that animations must respect. gsap.matchMedia() is the GSAP-native way to handle this: it groups animations by media query and automatically reverts them (kills tweens, restores inline styles) when the query stops matching, preventing stale animation state.
tags: [accessibility, animation, gsap, matchmedia, reduced-motion, responsive, rule]
confidence: peer-reviewed
authority: ai-provisional
last_validated: 2026-06-05
staleness_window: 365
evidence: peer-reviewed
source_attribution: "gsap-skills:gsap-core"
source_commit: null
edges: []
---

# Rule: matchMedia for responsive and reduced-motion

gsap.matchMedia() (GSAP 3.11+) binds animation setup to media queries. When a query stops matching, all animations created in that handler are reverted: tweens killed, inline styles restored. This is the correct mechanism for both responsive breakpoints and accessibility (prefers-reduced-motion).

Use mm.revert() on component unmount. Do not nest gsap.context() inside matchMedia.
