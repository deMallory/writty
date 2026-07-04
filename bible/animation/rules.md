<!-- RULE START: ANIM-GSAP-AUTOALPHA-001 -->
## Rule ANIM-GSAP-AUTOALPHA-001

**Domain**: animation
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When fading elements in or out with GSAP.

### Statement
Use autoAlpha instead of opacity for fade animations. When autoAlpha reaches 0, GSAP sets visibility: hidden, removing the element from hit testing and improving rendering. When non-zero, visibility is set to inherit. Animating opacity alone leaves an invisible element that still captures pointer events and occupies the accessibility tree.

### Violation
```javascript
// opacity alone: element invisible but still captures clicks
gsap.to(".overlay", { opacity: 0, duration: 0.5 });
```

### Pass
```javascript
// autoAlpha: invisible AND non-interactive at 0
gsap.to(".overlay", { autoAlpha: 0, duration: 0.5 });
```

### Enforcement
Code review. Flag gsap.to/from calls using opacity for fade-out (to 0) where autoAlpha is not used instead.

### Rationale
An element with opacity: 0 remains in the document flow, captures click and hover events, and is announced by screen readers. This creates invisible click targets that block interaction with elements underneath. autoAlpha is GSAP's solution: it animates opacity and toggles visibility automatically at the zero boundary.

<!-- RULE END: ANIM-GSAP-AUTOALPHA-001 -->
---

<!-- RULE START: ANIM-GSAP-CAMELCASE-001 -->
## Rule ANIM-GSAP-CAMELCASE-001

**Domain**: animation
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When writing property objects (vars) for gsap.to(), gsap.from(), gsap.fromTo(), or gsap.set().

### Statement
Use camelCase for all CSS property names in GSAP vars objects. GSAP's CSSPlugin expects camelCase (backgroundColor, marginTop, fontSize), not CSS kebab-case (background-color, margin-top, font-size). Kebab-case keys are silently ignored, producing no animation.

### Violation
```javascript
// Kebab-case: silently ignored, no animation occurs
gsap.to(".box", { "background-color": "red", "font-size": "20px" });
```

### Pass
```javascript
// camelCase: GSAP recognizes and animates these properties
gsap.to(".box", { backgroundColor: "red", fontSize: "20px" });
```

### Enforcement
Code review. Grep vars objects for quoted hyphenated property names. Linter rule if available.

### Rationale
GSAP's CSSPlugin parses property names as JavaScript object keys mapped to the DOM style API, which uses camelCase (element.style.backgroundColor). Kebab-case keys do not match any recognized property and are dropped without warning, leaving the developer with a tween that appears to run but changes nothing.

<!-- RULE END: ANIM-GSAP-CAMELCASE-001 -->
---

<!-- RULE START: ANIM-GSAP-EASE-001 -->
## Rule ANIM-GSAP-EASE-001

**Domain**: animation
**Severity**: Low
**Scope**: Component
**Mandatory**: false

### Trigger
When specifying easing for a GSAP tween.

### Statement
Use documented built-in ease names only. Invalid or misspelled ease strings fail silently, falling back to the default ease (power1.out). Built-in eases: none, power1-4, back, bounce, circ, elastic, expo, sine, each with .in, .out, .inOut variants. Use CustomEase plugin for custom curves.

### Violation
```javascript
// Misspelled ease: silently falls back to default
gsap.to(".box", { x: 100, ease: "easeInOutQuad" });
// CSS-style name: not recognized by GSAP
gsap.to(".box", { x: 100, ease: "cubic-bezier(0.4, 0, 0.2, 1)" });
```

### Pass
```javascript
// Correct built-in ease names
gsap.to(".box", { x: 100, ease: "power2.inOut" });
gsap.to(".box", { x: 100, ease: "back.out(1.7)" });
gsap.to(".box", { x: 100, ease: "elastic.out(1, 0.3)" });
```

### Enforcement
Code review. Verify ease values against the GSAP built-in list. Flag CSS-style easing names (easeInOut, cubic-bezier) or jQuery-style names (easeInOutQuad).

### Rationale
GSAP's ease parser does not throw on unrecognized names; it silently defaults. This means a typo in an ease string produces a working but visually wrong animation. The developer sees smooth motion and assumes their ease is applied when it is actually the default. GSAP's ease namespace (power1-4, back, bounce, circ, elastic, expo, sine) does not match CSS (ease-in-out, cubic-bezier) or jQuery UI (easeInOutQuad) naming conventions.

<!-- RULE END: ANIM-GSAP-EASE-001 -->
---

<!-- RULE START: ANIM-GSAP-IMMEDIATERENDER-001 -->
## Rule ANIM-GSAP-IMMEDIATERENDER-001

**Domain**: animation
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When multiple from() or fromTo() tweens target the same property of the same element.

### Statement
Set immediateRender: false on the later tweens. By default, from() and fromTo() apply their start state the instant the tween is created (immediateRender: true). When a second tween targets the same property, its immediate render overwrites the first tween's end state before the first tween runs, making the first animation invisible.

### Violation
```javascript
// Both tweens immediateRender: true (default for from/fromTo)
// Second tween's start state overwrites first tween's end state
gsap.from(".box", { x: -100, duration: 1 });
gsap.from(".box", { x: 200, duration: 1, delay: 1 });
// The first animation appears to do nothing
```

### Pass
```javascript
gsap.from(".box", { x: -100, duration: 1 });
gsap.from(".box", { x: 200, duration: 1, delay: 1, immediateRender: false });
// Both animations visible; second waits for its delay
```

### Enforcement
Code review. When multiple from() or fromTo() calls target the same element and property, verify that all but the first set immediateRender: false.

### Rationale
GSAP's immediateRender default exists to prevent flash of unstyled content: the start state is applied before the browser's next paint. This is correct for a single tween but creates a conflict when multiple tweens write to the same property at creation time. The second write wins, and the first tween's from-state is lost. This is the most common source of "my first animation isn't working" bugs in GSAP.

<!-- RULE END: ANIM-GSAP-IMMEDIATERENDER-001 -->
---

<!-- RULE START: ANIM-GSAP-MATCHMEDIA-001 -->
## Rule ANIM-GSAP-MATCHMEDIA-001

**Domain**: animation
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When animations must adapt to viewport size or respect the user's prefers-reduced-motion setting.

### Statement
Use gsap.matchMedia() for responsive breakpoints and reduced-motion support. matchMedia runs setup code only when a media query matches; when it stops matching, all animations and ScrollTriggers created in that run are reverted automatically. For prefers-reduced-motion, set duration: 0 or skip the animation entirely. Do not nest gsap.context() inside matchMedia; matchMedia creates its own context internally.

### Violation
```javascript
// No reduced-motion handling; animations run regardless of user preference
gsap.to(".hero", { x: 200, rotation: 360, duration: 2 });
```

### Pass
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

### Enforcement
Code review. Any GSAP animation visible to end users should handle prefers-reduced-motion via matchMedia or an equivalent mechanism. Flag animation code that lacks reduced-motion handling.

### Rationale
Users with vestibular disorders experience nausea, dizziness, or disorientation from animated content. prefers-reduced-motion is a system-level accessibility preference that animations must respect. gsap.matchMedia() is the GSAP-native way to handle this: it groups animations by media query and automatically reverts them (kills tweens, restores inline styles) when the query stops matching, preventing stale animation state.

<!-- RULE END: ANIM-GSAP-MATCHMEDIA-001 -->
---

<!-- RULE START: ANIM-GSAP-RETURNVAL-001 -->
## Rule ANIM-GSAP-RETURNVAL-001

**Domain**: animation
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When a tween or timeline needs runtime control: pause, play, reverse, seek, kill, or progress inspection.

### Statement
Store the return value of gsap.to(), gsap.from(), gsap.fromTo(), or gsap.timeline() in a variable. All tween methods return a Tween instance; timeline() returns a Timeline. Without the reference, the animation cannot be controlled after creation.

### Violation
```javascript
// Fire-and-forget: no way to pause or reverse
gsap.to(".box", { x: 100, duration: 2 });
// Later: how to pause? No reference exists.
```

### Pass
```javascript
const tween = gsap.to(".box", { x: 100, duration: 2 });
// Later:
tween.pause();
tween.reverse();
tween.progress(0.5);
tween.kill();
```

### Enforcement
Code review. If any tween is later referenced for control (pause, play, reverse, kill, progress, time, totalTime), verify the return value was stored.

### Rationale
GSAP tweens are objects with a full playback API (pause, play, reverse, seek, kill, progress, time, totalTime). Discarding the return value is correct for fire-and-forget animations but is a bug when control is needed later. In frameworks like React, the reference is typically stored in a useRef to survive re-renders.

<!-- RULE END: ANIM-GSAP-RETURNVAL-001 -->
---

<!-- RULE START: ANIM-GSAP-SVGORIGIN-001 -->
## Rule ANIM-GSAP-SVGORIGIN-001

**Domain**: animation
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When setting transform origin on SVG elements animated with GSAP.

### Statement
Use either svgOrigin or transformOrigin on an SVG element, never both. Only one applies; the other is silently ignored. svgOrigin uses the SVG's global coordinate space (e.g., "250 100") and is useful when multiple elements should rotate around a common point. transformOrigin is element-local. svgOrigin does not accept percentage values.

### Violation
```javascript
// Both set: transformOrigin takes precedence; svgOrigin is ignored
gsap.to(svgEl, { rotation: 90, svgOrigin: "100 100", transformOrigin: "50% 50%" });
```

### Pass
```javascript
// svgOrigin only: global coordinate, shared pivot point
gsap.to(svgEl, { rotation: 90, svgOrigin: "100 100" });

// OR transformOrigin only: element-local pivot
gsap.to(svgEl, { rotation: 90, transformOrigin: "center center" });
```

### Enforcement
Code review. Flag GSAP tween vars that contain both svgOrigin and transformOrigin on an SVG target.

### Rationale
SVG coordinate systems differ from HTML. transformOrigin operates in the element's local coordinate space; svgOrigin operates in the SVG viewBox's global coordinate space. If both are specified, transformOrigin takes precedence and svgOrigin is ignored, which can hide the intended pivot.

<!-- RULE END: ANIM-GSAP-SVGORIGIN-001 -->
---

<!-- RULE START: ANIM-GSAP-TIMELINE-001 -->
## Rule ANIM-GSAP-TIMELINE-001

**Domain**: animation
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When sequencing multiple animations on one or more targets.

### Statement
Use gsap.timeline() for sequencing. Do not chain independent tweens using calculated delay offsets. Timelines compose, can be controlled as a unit (pause, reverse, seek), and automatically adjust when any child's duration changes. Delay-chained tweens require manual arithmetic that breaks silently.

### Violation
```javascript
// Delay chaining: fragile; changing box1 duration breaks box2 timing
gsap.to(".box1", { x: 100, duration: 0.5 });
gsap.to(".box2", { y: 50, duration: 0.3, delay: 0.5 });
gsap.to(".box3", { scale: 1.5, duration: 0.4, delay: 0.8 });
```

### Pass
```javascript
// Timeline: self-adjusting, controllable as a unit
const tl = gsap.timeline();
tl.to(".box1", { x: 100, duration: 0.5 })
  .to(".box2", { y: 50, duration: 0.3 })
  .to(".box3", { scale: 1.5, duration: 0.4 });
```

### Enforcement
Code review. Flag sequences of gsap.to/from calls with incrementing delay values that could be replaced by a timeline.

### Rationale
Delay-based sequencing embeds timing assumptions as magic numbers. When any tween's duration changes, all subsequent delays must be recalculated manually. Timelines handle this automatically: each child starts after the previous one ends (or at a relative position). Timelines also expose a single control surface (pause, reverse, seek the entire sequence) that delay chains cannot provide.

<!-- RULE END: ANIM-GSAP-TIMELINE-001 -->
---

<!-- RULE START: ANIM-GSAP-TRANSFORM-001 -->
## Rule ANIM-GSAP-TRANSFORM-001

**Domain**: animation
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When animating element position, size, or rotation with GSAP.

### Statement
Use GSAP's transform aliases (x, y, z, scale, scaleX, scaleY, rotation, rotationX, rotationY, xPercent, yPercent) instead of layout properties (width, height, top, left, margin, padding). Transform aliases use the GPU-composited transform pipeline; layout properties trigger browser reflow on every frame.

### Violation
```javascript
// Layout properties: triggers reflow, janky on every frame
gsap.to(".box", { width: 200, height: 200, top: 100, left: 50 });
```

### Pass
```javascript
// Transform aliases: GPU-composited, smooth
gsap.to(".box", { x: 50, y: 100, scale: 1.5 });
```

### Enforcement
Code review. Flag gsap.to/from/fromTo calls that animate width, height, top, left, margin, or padding when a transform alias achieves the same visual result.

### Rationale
Browser rendering separates layout (reflow) from compositing (GPU). Animating layout properties forces the browser to recalculate geometry for potentially the entire document on every frame. Transform and opacity are the only properties that skip layout and paint, running entirely on the compositor thread. GSAP's transform aliases (x, y, scale, rotation) map directly to CSS transforms and apply in a consistent, cross-browser order: translation, scale, rotationX/Y, skew, rotation.

<!-- RULE END: ANIM-GSAP-TRANSFORM-001 -->
