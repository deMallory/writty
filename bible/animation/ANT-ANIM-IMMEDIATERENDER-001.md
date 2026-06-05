---
antipattern_id: ANT-ANIM-IMMEDIATERENDER-001
node_type: AntiPattern
domain: animation
severity: high
scope: component
trigger: "When a second from() or fromTo() tween on the same property of the same element renders its start state before the first tween runs."
statement: "Stacked immediateRender conflict: the default immediateRender: true on from() and fromTo() tweens causes each tween to apply its start state at creation time. When two tweens target the same property, the second creation overwrites the first tween's end state, making the first animation invisible or producing unexpected start positions."
rationale: "immediateRender: true exists to prevent flash of unstyled content by applying the from-state before the browser's next paint. This is correct for a single tween but creates a race at creation time when multiple tweens write to the same property. The last tween created wins, and the property value the first tween expected to animate toward is gone. This is GSAP's most common 'my animation isn't working' bug."
tags: [animation, anti-pattern, from, fromto, gsap, immediaterender, stacking]
confidence: peer-reviewed
authority: ai-provisional
last_validated: 2026-06-05
staleness_window: 365
evidence: peer-reviewed
source_attribution: "gsap-skills:gsap-core"
source_commit: null
counter_nodes:
  - ANIM-GSAP-IMMEDIATERENDER-001
edges:
  - { target: ANIM-GSAP-IMMEDIATERENDER-001, type: COUNTERS }
---

# Anti-pattern: Stacked immediateRender conflict

## Why this is broken

from() and fromTo() default to immediateRender: true. This is intentional: the start state should be visible before the tween plays so the user does not see a flash of the end state. But when two tweens target the same property, the second tween's immediate render overwrites the value the first tween was going to animate toward.

The result: the first tween appears to do nothing, or animates to an unexpected value.

## Counter

Set immediateRender: false on all but the first tween targeting a given property. See ANIM-GSAP-IMMEDIATERENDER-001.
