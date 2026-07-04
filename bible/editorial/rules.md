<!-- RULE START: EDIT-ARCH-ASYMMETRY-001 -->
## Rule EDIT-ARCH-ASYMMETRY-001

**Domain**: editorial
**Severity**: High
**Scope**: Layout
**Mandatory**: false

### Trigger
When choosing the compositional balance of an editorial layout, or when a layout feels structurally correct but emotionally dead.

### Statement
Asymmetric balance is the default; symmetry requires justification. Symmetric composition is appropriate for explicitly ceremonial moments (title pages, frontispieces, colophons, monuments). For all other editorial content, asymmetric composition creates the tension that makes the eye move through the spread rather than terminate at its center. Centered composition with no asymmetric tension reads as timid regardless of archetype.

### Violation
```css
/* Everything centered; no tension, no declared posture */
.spread {
  text-align: center;
  display: flex;
  align-items: center;
  justify-content: center;
}
/* Diagnostic: shift everything 20% off-center. If the layout improves,
   the symmetry was inertia, not choice. */
```

### Pass
```css
/* Asymmetric arrangement on a strong grid */
.spread {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
}
.headline { grid-column: 1 / 8; }  /* Heavy element, left-biased */
.body     { grid-column: 4 / 10; } /* Offset, creating tension with headline */
/* Whitespace in columns 8-12 acts as counterweight to the headline mass */
```

### Enforcement
Code review. Check whether the layout is symmetric or asymmetric. If symmetric, verify that the symmetry is chosen (ceremonial intent stated) rather than inherited (default centering). If asymmetric, verify that tension exists (heavy element balanced by whitespace counterweight, not just unbalanced).

### Rationale
The Swiss inheritance (Muller-Brockmann, Hofmann, Ruder, Gerstner, Bill) established asymmetric balance as the default compositional posture. The shift from centered to asymmetric was philosophical: centered composition implies a single sacred axis; asymmetric composition implies a field of forces. Grid provides the law; asymmetry provides the life. Each without the other fails.

<!-- RULE END: EDIT-ARCH-ASYMMETRY-001 -->
---

<!-- RULE START: EDIT-ARCH-AXIS-001 -->
## Rule EDIT-ARCH-AXIS-001

**Domain**: editorial
**Severity**: High
**Scope**: Layout
**Mandatory**: false

### Trigger
When choosing or critiquing the compositional axis (static vs. dynamic) of an editorial layout.

### Statement
The axis posture of the spread must match the emotional posture of the content. Static axis (right angles, orthogonal grids) reads as trustworthy, formal, settled. Dynamic axis (diagonals, rotated blocks) reads as active, contested, provisional. A static argument in a dynamic spread reads as posturing; a dynamic argument in a static spread reads as suppressed. Lissitzky's principle of correspondence: "The design of the book-space must correspond to the tensions and pressures of content."

### Violation
```
Content: a formal financial report (settled, authoritative data).
Layout: diagonal text blocks, rotated elements, 45-degree angles.
Mismatch: dynamic axis on static content reads as posturing.
```

### Pass
```
Content: a manifesto on design reform (urgent, contested argument).
Layout: static base with selective diagonal disruption carrying
the most important content.
Match: hybrid axis with dynamic elements serving the content's energy.
```

### Enforcement
Code review. Identify the content's emotional posture (settled vs. contested, formal vs. urgent). Check whether the layout's axis posture matches.

### Rationale
Lissitzky's "Topography of Typography" (1923) established that compositional axis carries emotional and cognitive weight. The right angle has a static effect (rest); the diagonal has a dynamic effect (agitation). The mismatch between content energy and layout energy is what most "off" spreads actually fail at.

<!-- RULE END: EDIT-ARCH-AXIS-001 -->
---

<!-- RULE START: EDIT-ARCH-IDENTIFY-001 -->
## Rule EDIT-ARCH-IDENTIFY-001

**Domain**: editorial
**Severity**: Critical
**Scope**: Layout
**Mandatory**: true

### Trigger
When designing or critiquing any editorial spread, page, or layout.

### Statement
The spread's archetype must be identified: data spread (Isotype to Swiss to Tufte), ratio/specimen spread (Bodoni to Tschichold to Weingart to Bill), fragmented Merz spread (Schwitters to Dada to Lissitzky to Bauhaus), or multi-column prose spread (medieval canon to Tschichold to Muller-Brockmann to Bringhurst). Content type must match the archetype. Choosing the wrong archetype for the content is the most common failure.

### Violation
```
A long argumentative essay placed in a Merz spread (fragmented layout for
sustained prose -- unreadable). Or a data report placed in a prose grid
(quantitative content hidden in narrative form).
```

### Pass
```
Content: sustained argumentative essay with figure interruptions.
Archetype: multi-column prose spread.
Match: correct -- prose archetype serves sustained reading.

Content: manifesto fragment, sound-poem, declaration.
Archetype: fragmented Merz spread.
Match: correct -- Merz archetype serves poetic/declamatory content.
```

### Enforcement
Code review. Name the archetype; verify that the content's reading mode (scanning, contemplating, deciphering, sustained reading) matches the archetype's purpose.

### Rationale
The four archetypes descend from a small network of designers (Tschichold, Muller-Brockmann, Schwitters, Lissitzky, Bill, Ruder, Weingart, Tufte) whose overlapping careers established the grammar. Each answers "how should ink relate to paper?" differently. Choosing the wrong archetype for the content is more common than executing the chosen archetype poorly.

<!-- RULE END: EDIT-ARCH-IDENTIFY-001 -->
---

<!-- RULE START: EDIT-ARCH-INTEGRATE-001 -->
## Rule EDIT-ARCH-INTEGRATE-001

**Domain**: editorial
**Severity**: High
**Scope**: Layout
**Mandatory**: false

### Trigger
When placing text, numbers, and images in any editorial layout or data visualization.

### Statement
Words, numbers, and images must be integrated within their eye-frame, not segregated into zones. Labels sit on or near the data they describe. Figures appear near their first text reference. Legends placed far from the data they decode are a violation. Tufte's fourth principle of analytical design: "Completely integrate words, numbers, images, diagrams."

### Violation
```html
<!-- Chart in one zone, legend in another, explanation in a third -->
<div class="chart-zone">...</div>
<div class="legend-zone">...</div>
<div class="explanation-zone">...</div>
<!-- Reader's eye must jump between three zones to decode the display -->
```

### Pass
```html
<!-- Labels directly on the data; explanation integrated with the figure -->
<figure>
  <svg><!-- data points with direct labels, no separate legend --></svg>
  <figcaption>Explanation within the same eye-frame as the data.</figcaption>
</figure>
```

### Enforcement
Code review. Check whether labels, legends, and explanations are within the same visual frame as the data or content they describe.

### Rationale
Segregation forces the reader to hold information in working memory while their eye travels between zones. Integration lets the eye decode in place. This is both a Tufte principle (analytical design #4) and a Swiss inheritance (Muller-Brockmann's figure-text integration rule).

<!-- RULE END: EDIT-ARCH-INTEGRATE-001 -->
---

<!-- RULE START: EDIT-ARCH-MIX-001 -->
## Rule EDIT-ARCH-MIX-001

**Domain**: editorial
**Severity**: High
**Scope**: Layout
**Mandatory**: false

### Trigger
When a layout appears to use elements from more than one editorial archetype (data, specimen, Merz, prose).

### Statement
No covert archetype mixing. If a layout mixes archetypes, the dominant archetype must be identifiable and the secondary elements must support rather than undermine it. Unnameable archetype identity is a sign of confusion, not sophistication.

### Violation
```
A spread with Merz-style diagonal typography (fragmented archetype),
a data table (data archetype), and sustained body text in narrow columns
(prose archetype). No dominant archetype identifiable.
The spread reads as confused rather than hybrid.
```

### Pass
```
Dominant: multi-column prose spread.
Secondary: a single data figure (data archetype) placed at column top,
sized to integer column widths, following prose-spread figure placement
rules. The prose archetype dominates; the data element supports it.
```

### Enforcement
Code review. Name the archetype. If it cannot be named, the layout is confused. If mixed, verify the dominant archetype is clear and secondary elements follow the dominant archetype's rules.

### Rationale
The four archetypes are four distinct grammars, not four styles to mix freely. A spread that violates its own archetype reads as decorative chaos; a spread that violates the wrong archetype's rules reads as confused. Genuine hybrids are rare; confusion is common.

<!-- RULE END: EDIT-ARCH-MIX-001 -->
---

<!-- RULE START: EDIT-ARCH-RHYTHM-001 -->
## Rule EDIT-ARCH-RHYTHM-001

**Domain**: editorial
**Severity**: Medium
**Scope**: Layout
**Mandatory**: false

### Trigger
When evaluating whether a layout's reading pace matches its content type.

### Statement
Reading rhythm must match content. Poetry and manifesto content demands decelerated reading (vertical fragmentation, large-scale type, sparse elements). Sustained prose demands even rhythm (consistent line length, regular leading, predictable column structure). Data demands scanning rhythm (aligned comparisons, small multiples, dense but organized). Merz slows reading deliberately; prose sustains it; data enables it.

### Violation
```
Content: a 3000-word argumentative essay.
Layout: text broken into scattered fragments at varying angles,
large display type interrupting every paragraph.
Reading rhythm: decelerated (Merz pace) for sustained-reading content.
Mismatch: the reader cannot build momentum through the argument.
```

### Pass
```
Content: a 3000-word argumentative essay.
Layout: multi-column prose, baseline-locked, consistent line length,
figures at column tops, sidenotes in the margin.
Reading rhythm: sustained, even, predictable.
Match: prose rhythm for prose content.
```

### Enforcement
Code review. Identify the content's reading mode (scanning, contemplating, deciphering, sustained). Check whether the layout's pacing mechanisms match.

### Rationale
Each archetype carries an inherent reading rhythm. The rhythm is not stylistic; it is functional. A prose spread that decelerates the reader prevents comprehension of the argument. A Merz spread that allows smooth reading defeats its purpose of semantic deceleration.

<!-- RULE END: EDIT-ARCH-RHYTHM-001 -->
---

<!-- RULE START: EDIT-ARCH-TENSION-001 -->
## Rule EDIT-ARCH-TENSION-001

**Domain**: editorial
**Severity**: High
**Scope**: Layout
**Mandatory**: false

### Trigger
When a layout passes all structural checks (correct proportions, margins, scale, metrics, baseline) but still feels dead or inert.

### Statement
A layout must have both grid and asymmetric tension. Grid alone without asymmetry is correct but inert (reads as bureaucratic, machine-produced). Asymmetry alone without grid is alive but accidental (reads as one-off, ungeneralizable). Grid and asymmetry together produce layouts that are both lawful and alive.

### Violation
```
Layout passes all grid checks: correct margin canon, named scale,
baseline alignment, proper line length.
But: everything is centered. No element pulls against another.
No whitespace functions as counterweight.
The eye has nowhere to go because everything has already arrived.
Diagnosis: grid without life.
```

### Pass
```
Layout passes all grid checks AND:
- headline sits off-center against the field divisions
- a large empty region counterweights the text cluster
- the eye enters at the headline and traverses through the body
- whitespace is load-bearing (removing it would collapse the composition)
Diagnosis: lawful and alive.
```

### Enforcement
Code review. After verifying grid infrastructure, apply the five-point diagnostic: (1) symmetric or asymmetric? (2) if symmetric, chosen or inherited? (3) if asymmetric, is there tension? (4) whitespace as counterweight or residue? (5) clear entry point and path?

### Rationale
Muller-Brockmann's strongest work (Tonhalle Zurich posters, Neue Grafik covers) is grid-rigorous and visually asymmetric. The combination is the canonical demonstration: centered text blocks on a 12-field grid sit deliberately off-center against the field divisions, creating tension while obeying law.

<!-- RULE END: EDIT-ARCH-TENSION-001 -->
---

<!-- RULE START: EDIT-ARCH-WHITESPACE-001 -->
## Rule EDIT-ARCH-WHITESPACE-001

**Domain**: editorial
**Severity**: High
**Scope**: Layout
**Mandatory**: false

### Trigger
When reviewing whitespace in any editorial layout.

### Statement
Every empty region must have a named function: compositional breathing (preventing cognitive overload), semantic encoding (representing absence or zero), structural silence (rhythmic pauses between typographic events), or tension and direction (channeling the eye). Tschichold: "White space is to be regarded as an active element, not a passive background." If the answer to "what is this space doing?" is "nothing" or "balance" (which is just "nothing" with vocabulary), the layout is residual.

### Violation
```
Large empty region in the lower-right corner of the spread.
Q: What is this space doing?
A: "Balance" / "It looks better with some breathing room."
-- Residual. No identifiable function.
```

### Pass
```
Large empty region in the lower-right, counterweighting the heavy
display headline in the upper-left.
Q: What is this space doing?
A: Asymmetric counterweight. The emptiness balances the headline's
   visual mass. Removing it would collapse the composition's tension.
-- Active. Load-bearing.
```

### Enforcement
Code review. For every empty region, ask "what is it doing?" and "what would happen if I filled this space?" If filling it wouldn't collapse the composition, the space is residual.

### Rationale
Whitespace is never residual in strong layouts. Muller-Brockmann's whitespace is counterweight. Lissitzky's whitespace is tension and direction. Ruder's whitespace is structural silence. Different vocabularies for the same principle: emptiness must carry weight or it is waste.

<!-- RULE END: EDIT-ARCH-WHITESPACE-001 -->
---

<!-- RULE START: EDIT-DATA-LABEL-001 -->
## Rule EDIT-DATA-LABEL-001

**Domain**: editorial
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When designing proportional shapes (circles, bubbles, bars) in a data visualization.

### Statement
Every proportional shape must be directly labeled with its actual value. Relying on a legend placed away from the data forces the reader to hold values in working memory while their eye travels. Direct labels make the display self-decoding. For bubble charts specifically, limit to 5-7 categories maximum; beyond this, eye comparison breaks down.

### Violation
```
Bubble chart with 12 categories, no direct labels.
Reader must cross-reference each bubble to a legend in the corner.
Working memory overflows at ~4 items; the display is unreadable.
```

### Pass
```
Bubble chart with 5 categories, each bubble directly labeled
with its value and category name. No separate legend needed.
```

### Enforcement
Code review. Check whether proportional shapes carry direct value labels. Count categories in bubble/scatter charts; flag if > 7.

### Rationale
Neurath's Isotype rule extended: direct labeling removes the legend as a cognitive intermediary. Viewers underestimate area differences even when scaling is correct, so labels provide the ground truth the eye cannot supply. The 5-7 category limit reflects the empirical boundary of pre-attentive discrimination for area.

<!-- RULE END: EDIT-DATA-LABEL-001 -->
---

<!-- RULE START: EDIT-DATA-PALETTE-001 -->
## Rule EDIT-DATA-PALETTE-001

**Domain**: editorial
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When choosing colors for a data visualization.

### Statement
Color palette must match the data structure. Sequential data (ordered) uses a single-hue ramp (light to dark). Diverging data (meaningful midpoint) uses two hues meeting at neutral. Categorical data (unordered groups) uses distinct hues at similar luminance, maximum 5-8 categories. Use ColorBrewer or equivalent accessibility-tested palettes. Decorative color where categorical encoding is needed is a violation.

### Violation
```css
/* Rainbow palette on ordered sequential data */
.low    { fill: red; }
.medium { fill: green; }
.high   { fill: blue; }
/* Unordered hues on ordered data; no perceptual sequence */
```

### Pass
```css
/* Sequential single-hue ramp for ordered data */
.low    { fill: hsl(210, 60%, 90%); }
.medium { fill: hsl(210, 60%, 60%); }
.high   { fill: hsl(210, 60%, 30%); }
/* Lightness encodes magnitude; colorblind-safe */
```

### Enforcement
Code review. Identify whether the data is sequential, diverging, or categorical. Check whether the palette type matches.

### Rationale
Mismatched palettes mislead: rainbow colors on sequential data hide the ordering because human color perception does not arrange hues in a natural sequence. Sequential data needs sequential luminance. ColorBrewer palettes are empirically tested for perceptual uniformity and colorblind accessibility.

<!-- RULE END: EDIT-DATA-PALETTE-001 -->
---

<!-- RULE START: EDIT-DATA-REPEAT-001 -->
## Rule EDIT-DATA-REPEAT-001

**Domain**: editorial
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When designing a data visualization that represents quantities using pictograms, icons, or repeated shapes.

### Statement
Greater quantities are shown by greater number of same-size pictograms, never by enlarging a single pictogram (Neurath's cardinal rule). Variation in size creates ambiguity between height and area comparison; repeated icons can be counted directly. This is the Isotype principle.

### Violation
```html
<!-- One big icon for large value, one small for small value -->
<svg class="big-icon" width="80" height="80"><!-- 1000 units --></svg>
<svg class="small-icon" width="20" height="20"><!-- 250 units --></svg>
<!-- Is the big icon 4x or 16x the small one? Ambiguous. -->
```

### Pass
```html
<!-- Same-size icons repeated; countable at a glance -->
<div class="pictogram-row">
  <svg width="20" height="20" /><!-- x4 icons = 1000 units -->
  <svg width="20" height="20" />
  <svg width="20" height="20" />
  <svg width="20" height="20" />
</div>
<div class="pictogram-row">
  <svg width="20" height="20" /><!-- x1 icon = 250 units -->
</div>
```

### Enforcement
Code review. Check whether pictogram/icon displays use repetition (correct) or scaling (violation) to represent magnitude.

### Rationale
Otto Neurath's Isotype system (Vienna, 1925) established this as the foundational rule of pictorial statistics. Scaling introduces the same area-vs-diameter ambiguity as bubble charts. Repetition is unambiguous: the reader counts.

<!-- RULE END: EDIT-DATA-REPEAT-001 -->
---

<!-- RULE START: EDIT-GRID-BASELINE-001 -->
## Rule EDIT-GRID-BASELINE-001

**Domain**: editorial
**Severity**: High
**Scope**: Layout
**Mandatory**: false

### Trigger
When constructing or critiquing a multi-column editorial layout.

### Statement
All text must align to a single baseline grid across all columns. The baseline unit derives from body-text leading. All other vertical measurements (paragraph spacing, image heights, margin offsets) must be integer multiples of the baseline unit. Adjacent columns with independent vertical drift are a violation.

### Violation
```css
/* Each column drifts independently; no shared baseline */
.col-1 p { line-height: 1.5; margin-bottom: 1.2em; }
.col-2 p { line-height: 1.6; margin-bottom: 1em; }
/* Squint test: columns look like two different documents */
```

### Pass
```css
/* Shared baseline unit: 1.5rem (body line-height) */
:root { --baseline: 1.5rem; }
p { line-height: var(--baseline); margin-bottom: var(--baseline); }
h2 { line-height: calc(2 * var(--baseline)); margin-bottom: var(--baseline); }
/* All vertical rhythm is integer multiples of the baseline unit */
```

### Enforcement
Code review. Check that line-height and vertical spacing derive from a single baseline unit. Squint test: adjacent columns should show shared horizontal rhythm.

### Rationale
The baseline grid is the most powerful rhythm tool in editorial design. When it works, adjacent columns lock together and the spread reads as a unified surface. When it drifts, columns look like separate documents pasted side by side. Accidental drift is unforgivable and reads as sloppy regardless of how good the rest of the spread is.

<!-- RULE END: EDIT-GRID-BASELINE-001 -->
---

<!-- RULE START: EDIT-GRID-BASELINE-002 -->
## Rule EDIT-GRID-BASELINE-002

**Domain**: editorial
**Severity**: Medium
**Scope**: Layout
**Mandatory**: false

### Trigger
When an element in an editorial layout breaks the baseline grid (display type, large images, pull-quotes, figure spreads).

### Statement
Grid breakage must be intentional and announced. The broken element must be separated from body text by clear margin, framed by rules, or otherwise visually distinguished so the eye is told "this is a different rhythm zone." Accidental drift (text in column A one baseline ahead of text in column B) is a violation.

### Violation
```html
<!-- Image height doesn't fit baseline; subsequent text drifts silently -->
<img style="height: 237px" />
<p>Text continues here, now off-baseline with the adjacent column...</p>
```

### Pass
```html
<!-- Image height is integer multiple of baseline; or breakage is framed -->
<figure class="full-width" style="height: calc(10 * var(--baseline))">
  <img src="..." />
</figure>
<!-- Alternatively: framed with rules, visually separated as a different zone -->
```

### Enforcement
Code review. Where grid breakage exists, check whether it is visually announced or silently accumulated.

### Rationale
Display type, large images, and pull-quotes will sometimes not fit the baseline neatly. The distinction that matters is between announced breakage (the reader sees a deliberate rhythm shift) and accidental drift (adjacent columns slowly desynchronize). The first is design; the second is neglect.

<!-- RULE END: EDIT-GRID-BASELINE-002 -->
---

<!-- RULE START: EDIT-GRID-FIELD-001 -->
## Rule EDIT-GRID-FIELD-001

**Domain**: editorial
**Severity**: Medium
**Scope**: Layout
**Mandatory**: false

### Trigger
When choosing a modular grid for an editorial layout.

### Statement
Modular grid field count must be chosen for content complexity (Muller-Brockmann range: 8 to 32 fields). 8-12 fields for simple, decisive work; 16-20 for mixed editorial; 24-32 for complex multivariate content. Field count is not column count; column count is one decision made on top of the field grid.

### Violation
```css
/* Grid chosen by template default, not content complexity */
.layout { display: grid; grid-template-columns: repeat(3, 1fr); }
/* No stated field count; no relationship between grid and content needs */
```

### Pass
```css
/* 12-field grid for editorial default (permits 1, 2, 3, 4, 6 columns) */
.layout {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
}
/* Field count: 12. Content type: mixed editorial (prose + figures). */
/* Current use: 3-column layout (each column spans 4 fields). */
```

### Enforcement
Code review. Check whether the field count is stated and appropriate to the content complexity. Verify that column spans are integer divisions of the field count.

### Rationale
Muller-Brockmann's Grid Systems established the 8-32 field range. The field grid is the underlying division of the text area; column count is derived from it. A 12-field grid lets you run 3 columns on one page and 4 columns on the next, with everything still aligning. Choosing column count without a field grid produces accidental geometry that cannot accommodate variation.

<!-- RULE END: EDIT-GRID-FIELD-001 -->
---

<!-- RULE START: EDIT-GRID-GUTTER-001 -->
## Rule EDIT-GRID-GUTTER-001

**Domain**: editorial
**Severity**: Medium
**Scope**: Layout
**Mandatory**: false

### Trigger
When setting gutter width between columns in a multi-column editorial layout.

### Statement
Gutters must be approximately 2 ems wide, proportional to text size. The gutter must be wide enough to prevent the eye from jumping between columns on line-return. Too narrow causes eye-jumping; too wide causes columns to feel disconnected.

### Violation
```css
/* Gutter too narrow; eye jumps between columns */
.columns { column-gap: 0.5rem; font-size: 1rem; }
```

### Pass
```css
/* Gutter approximately 2 ems, proportional to text size */
.columns { column-gap: 2em; }
```

### Enforcement
Code review. Check column-gap or grid-gap against the body text size; ratio should be approximately 2:1 (gap to font-size in ems).

### Rationale
The gutter exists to separate columns enough that the eye returns to the correct column after each line. Too narrow and the saccade overshoots into the adjacent column. Too wide and the columns feel like independent documents rather than parts of a spread. Two ems is the standard derived from centuries of multi-column printing.

<!-- RULE END: EDIT-GRID-GUTTER-001 -->
---

<!-- RULE START: EDIT-GRID-LINE-001 -->
## Rule EDIT-GRID-LINE-001

**Domain**: editorial
**Severity**: Critical
**Scope**: Layout
**Mandatory**: true

### Trigger
When setting or reviewing line length (measure) for body text in any editorial layout.

### Statement
Body text must be 45-75 characters per line for single-column serif text (ideal: 66 characters including spaces). Multi-column work narrows to 40-50 characters per line. Lines exceeding 75 characters cause eye fatigue and lost line returns. Lines under 40 characters produce choppy rhythm.

### Violation
```css
/* max-width too wide; body text runs to ~110 characters per line */
.article-body { max-width: 60rem; font-size: 1rem; }
```

### Pass
```css
/* ~66 characters per line at 1rem body text */
.article-body { max-width: 40rem; font-size: 1rem; }
/* Measure: approximately 65 characters per line (single column, serif) */
```

### Enforcement
Code review. Measure characters per line at the primary breakpoint. Count actual characters in rendered text, not just the CSS value.

### Rationale
Bringhurst: 45-75 characters per line for single-column serif. Muller-Brockmann: approximately 7 words per line at 30-35 cm reading distance. These are the most empirically validated numbers in typography. Lines too long cause the eye to lose its place on the return sweep; lines too short break phrases and rhythm.

<!-- RULE END: EDIT-GRID-LINE-001 -->
---

<!-- RULE START: EDIT-GRID-LINE-002 -->
## Rule EDIT-GRID-LINE-002

**Domain**: editorial
**Severity**: High
**Scope**: Layout
**Mandatory**: false

### Trigger
When setting or reviewing line-height (leading) for body text in any editorial layout.

### Statement
Leading must be at least 120% of type size (10pt type requires 12pt leading as the classical minimum). Increase to 150% for lines approaching the upper character limit (70+). Leading below 110% causes lines to touch and produces eye fatigue.

### Violation
```css
/* Leading too tight: 100% of type size, lines touching */
.body-text { font-size: 16px; line-height: 1.0; }
```

### Pass
```css
/* Classical leading: 120% of type size (16px * 1.5 = 24px) */
.body-text { font-size: 16px; line-height: 1.5; }
```

### Enforcement
Code review. Check line-height against font-size; ratio must be >= 1.2.

### Rationale
The 10/12 combination (10pt text, 12pt leading) is the classical default with centuries of use. Leading exists to prevent adjacent lines from interfering with each other during the reading saccade. Below 120%, ascenders and descenders collide visually and the eye loses its tracking line.

<!-- RULE END: EDIT-GRID-LINE-002 -->
---

<!-- RULE START: EDIT-GRID-MARGIN-001 -->
## Rule EDIT-GRID-MARGIN-001

**Domain**: editorial
**Severity**: High
**Scope**: Layout
**Mandatory**: false

### Trigger
When constructing margins for an editorial layout, page, or content area.

### Statement
Margins must be constructed from a named canon (Van de Graaf 2:3:4:6, Tschichold medieval 1:1:2:3, or a stated alternative), not eyeballed. The canon must be stated. Equal margins on all sides is a violation for editorial layouts.

### Violation
```css
/* Equal margins; no canon, no proportion */
.content { margin: 2rem; }
```

### Pass
```css
/* Van de Graaf canon: inner:top:outer:bottom = 2:3:4:6 */
.content {
  margin-top: 3rem;    /* 3 units */
  margin-right: 4rem;  /* 4 units (outer) */
  margin-bottom: 6rem; /* 6 units */
  margin-left: 2rem;   /* 2 units (inner) */
}
/* Canon: Van de Graaf 2:3:4:6 on a 2:3 page proportion. */
```

### Enforcement
Code review. Trace margin values back to a named canon and verify the ratio holds.

### Rationale
The Van de Graaf canon produces margins by geometric construction (9x9 page grid), not intuition. Four hundred years of verified bookwork confirm: constructed margins produce pages that feel right because the proportions are mathematically coherent. Equal margins are the default of word processors, not of considered design.

<!-- RULE END: EDIT-GRID-MARGIN-001 -->
---

<!-- RULE START: EDIT-GRID-MARGIN-002 -->
## Rule EDIT-GRID-MARGIN-002

**Domain**: editorial
**Severity**: Critical
**Scope**: Layout
**Mandatory**: true

### Trigger
When reviewing or setting margins on any editorial layout, page, or content area.

### Statement
Bottom margin must be the largest margin. Top margin larger than bottom margin is a violation. This is universal across all canons.

### Violation
```css
/* Top margin exceeds bottom; page feels visually unstable */
.content {
  margin-top: 4rem;
  margin-bottom: 2rem;
}
```

### Pass
```css
/* Bottom largest (Van de Graaf: bottom = 6 units, top = 3 units) */
.content {
  margin-top: 3rem;
  margin-bottom: 6rem;
}
```

### Enforcement
Code review. Compare top and bottom margin values; bottom must be equal or larger.

### Rationale
We hold the book by the lower margin (Paul Renner). A page with top margin larger than bottom feels like the text is sliding off. This is the single most common margin failure and the easiest to detect.

<!-- RULE END: EDIT-GRID-MARGIN-002 -->
---

<!-- RULE START: EDIT-GRID-MARGIN-003 -->
## Rule EDIT-GRID-MARGIN-003

**Domain**: editorial
**Severity**: High
**Scope**: Layout
**Mandatory**: false

### Trigger
When reviewing or setting margins on any editorial layout with inner (gutter) and outer margins.

### Statement
Outer margin must exceed inner margin. Equal or reversed (inner > outer) produces claustrophobic gutter on spreads and denies the reader thumb room.

### Violation
```css
/* Inner margin equals outer; spread will feel cramped at the gutter */
.content {
  margin-left: 3rem;   /* inner */
  margin-right: 3rem;  /* outer */
}
```

### Pass
```css
/* Outer exceeds inner: Van de Graaf ratio 2:4 (inner:outer) */
.content {
  margin-left: 2rem;   /* inner */
  margin-right: 4rem;  /* outer */
}
```

### Enforcement
Code review. Compare inner and outer margin values on spread-aware layouts.

### Rationale
Outer margin provides thumb room and visual breathing. Inner margin exceeding outer produces claustrophobia at the gutter. Every classical canon respects this hierarchy.

<!-- RULE END: EDIT-GRID-MARGIN-003 -->
---

<!-- RULE START: EDIT-GRID-PROPORTION-001 -->
## Rule EDIT-GRID-PROPORTION-001

**Domain**: editorial
**Severity**: High
**Scope**: Layout
**Mandatory**: false

### Trigger
When setting up a new page, spread, or layout, or critiquing an existing one whose proportions feel arbitrary.

### Statement
Page proportion must be named as a ratio (2:3, golden 1:1.618, A-series 1:1.414, or custom with stated rationale). If the ratio cannot be stated, it was eyeballed. Eyeballed proportions are a violation.

### Violation
```css
/* No stated proportion; dimensions chosen by feel */
.page { width: 850px; height: 1200px; }
```

### Pass
```css
/* 2:3 proportion (Tschichold's classical preference) */
.page { width: 850px; height: 1275px; /* 850 * 1.5 = 1275 */ }
/* Ratio: 2:3. Sits in the Fibonacci sequence, approaches golden ratio. */
```

### Enforcement
Code review. Check whether the layout's width:height can be expressed as a named ratio.

### Rationale
The page proportion is the first design decision; everything else descends from it. Unnamed proportions produce accidental geometry that cannot be extended, defended, or repeated. Tschichold, Van de Graaf, and four centuries of bookwork confirm: proportion is the foundation, not a detail.

<!-- RULE END: EDIT-GRID-PROPORTION-001 -->
---

<!-- RULE START: EDIT-GRID-SCALE-001 -->
## Rule EDIT-GRID-SCALE-001

**Domain**: editorial
**Severity**: High
**Scope**: Layout
**Mandatory**: false

### Trigger
When setting type sizes for any editorial layout, page, or component.

### Statement
A typographic scale must be named: classical progression (6, 7, 8, 9, 10, 11, 12, 14, 16, 18, 21, 24, 36, 48, 60, 72), a modular scale ratio (minor second 1.067, major third 1.250, perfect fourth 1.333, golden ratio 1.618), or a stated alternative. Ad-hoc type sizing is a violation. Bringhurst's directive: "Don't compose without a scale."

### Violation
```css
/* Ad-hoc sizes with no scale relationship */
h1 { font-size: 32px; }
h2 { font-size: 22px; }
h3 { font-size: 17px; }
p  { font-size: 15px; }
/* 32/22 = 1.45, 22/17 = 1.29, 17/15 = 1.13 -- no consistent ratio */
```

### Pass
```css
/* Perfect fourth scale (1.333), base 16px */
/* 12 - 16 - 21 - 28 - 38 - 50 */
p  { font-size: 1rem; }      /* 16px base */
h3 { font-size: 1.333rem; }  /* 21px */
h2 { font-size: 1.777rem; }  /* 28px (1.333^2) */
h1 { font-size: 2.369rem; }  /* 38px (1.333^3) */
/* Scale: perfect fourth (1.333), base 16px */
```

### Enforcement
Code review. List all type sizes used; verify they can be expressed as values in one named scale.

### Rationale
The typographic scale has governed type sizing for 400+ years. Octaves double (6 to 12 to 24 to 48); intermediates follow the fifth root of 2. Ad-hoc sizing produces incoherent hierarchy. The scale is the type equivalent of the margin canon: structural, not decorative.

<!-- RULE END: EDIT-GRID-SCALE-001 -->
---

<!-- RULE START: EDIT-GRID-SCALE-002 -->
## Rule EDIT-GRID-SCALE-002

**Domain**: editorial
**Severity**: Medium
**Scope**: Layout
**Mandatory**: false

### Trigger
When auditing type sizes in an existing editorial layout where a scale has been declared.

### Statement
All type sizes in the layout must be derivable from the named scale. Any size that cannot be expressed as a value in the declared scale is a violation. Exception: caption sizing (2 points smaller than body, per Bringhurst convention) is permitted as a deliberate deviation.

### Violation
```css
/* Declared scale: perfect fourth (1.333), base 16px */
/* Expected: 12, 16, 21, 28, 38, 50 */
.callout { font-size: 19px; } /* Not on the scale */
.label   { font-size: 13px; } /* Not on the scale */
```

### Pass
```css
/* All sizes on the declared scale: perfect fourth (1.333), base 16px */
.callout { font-size: 1.333rem; } /* 21px -- on scale */
.label   { font-size: 0.75rem; }  /* 12px -- on scale */
```

### Enforcement
Code review. List every font-size declaration; check each against the named scale.

### Rationale
A scale that is present but inconsistently applied is worse than no scale at all. The inconsistent sizes create visual noise that undermines the hierarchy the scale was meant to establish.

<!-- RULE END: EDIT-GRID-SCALE-002 -->
---

<!-- RULE START: EDIT-MERZ-DIAGONAL-001 -->
## Rule EDIT-MERZ-DIAGONAL-001

**Domain**: editorial
**Severity**: Medium
**Scope**: Layout
**Mandatory**: false

### Trigger
When using diagonal elements (rotated text, angled rules, non-orthogonal alignment) in an editorial layout.

### Statement
Diagonals must do work. Lissitzky's static/dynamic axis theory: the right angle has a static effect (rest); the diagonal has a dynamic effect (agitation). Choose deliberately. Diagonals used for decoration rather than energy are a violation. If the diagonal could be removed without changing the meaning, remove it.

### Violation
```css
/* Decorative diagonal; adds no energy to content */
.section-divider {
  transform: rotate(5deg);
  /* Why 5 degrees? No structural reason. Just "looks modern." */
}
```

### Pass
```css
/* Diagonal carries the most important content; energy serves meaning */
.manifesto-claim {
  transform: rotate(15deg);
  /* The claim cuts across the static grid, demanding attention.
     The angle matches the content's urgency. */
}
```

### Enforcement
Code review. For every diagonal element, ask: "What work is this doing?" and "Could it be removed without losing meaning?" If removable, it is decorative.

### Rationale
Lissitzky's "Topography of Typography" (Merz No. 4, 1923) established that axis angle carries cognitive weight. Diagonals are expensive: they agitate the eye and demand attention. Spending that cost on decoration wastes it. Spending it on the most important content leverages it.

<!-- RULE END: EDIT-MERZ-DIAGONAL-001 -->
---

<!-- RULE START: EDIT-MERZ-FRAGMENT-001 -->
## Rule EDIT-MERZ-FRAGMENT-001

**Domain**: editorial
**Severity**: Medium
**Scope**: Layout
**Mandatory**: false

### Trigger
When breaking words or text into fragments, stacking letters vertically, or using extreme size contrast in a layout.

### Statement
Vertical fragmentation and extreme size contrast are semantic deceleration: they slow reading deliberately. This is appropriate when slowing serves the content (poetry, monuments, declarations, manifesto fragments). It is inappropriate when the content needs to be absorbed quickly. The BAUHAUS lettering down the Dessau facade is the canonical example: the building announces itself slowly, as a presence rather than a label.

### Violation
```
Navigation menu items stacked vertically letter-by-letter.
Content: utility links (Home, About, Contact).
Mismatch: semantic deceleration on content that needs fast scanning.
The reader must reassemble each word before navigating.
```

### Pass
```
Article title broken into stacked letters spanning the full height.
Content: a manifesto opening declaration.
Match: the deceleration forces the reader to encounter each letter
as architectural mass. The title announces itself as a presence.
```

### Enforcement
Code review. For fragmented or vertically stacked text, check whether the deceleration serves the content's intent. Utility content fragmented is always a violation.

### Rationale
Schwitters' Merz and Lissitzky's constructivism used fragmentation as a compositional tool with specific purpose: slowing the eye, creating architectural mass, treating type as pictorial element. When applied to content that needs speed (navigation, labels, instructions), the technique defeats its own purpose.

<!-- RULE END: EDIT-MERZ-FRAGMENT-001 -->
---

<!-- RULE START: EDIT-MERZ-GOVERN-001 -->
## Rule EDIT-MERZ-GOVERN-001

**Domain**: editorial
**Severity**: High
**Scope**: Layout
**Mandatory**: false

### Trigger
When designing or critiquing a fragmented/Merz-style layout where elements appear scattered, diagonal, or chaotic.

### Statement
The chaos must be governed. Schwitters' compositions respected letterpress constraints; Dada respected De Stijl balance. Genuinely arbitrary fragmentation reads as noise, not Merz. An underlying structure must be identifiable beneath the apparent chaos. If you cannot point to the governing structure, the layout is arbitrary, not expressive.

### Violation
```
Elements scattered across the page at random positions.
No detectable grid underneath. No structural logic.
Asked "what governs this?" Answer: "it felt right."
Result: noise, not Merz.
```

### Pass
```
Elements scattered across the page, but:
- Heavy rules create architectural beams structuring the chaos
- Positions align to an underlying 12-field grid at non-obvious intersections
- Diagonal energy follows Lissitzky's static/dynamic axis theory
Asked "what governs this?" Answer: "the 12-field grid, with diagonals
at the intersections of fields 3/7 and 5/9."
Result: governed chaos. Merz.
```

### Enforcement
Code review. For any fragmented layout, ask: "Can you point to the underlying structure?" If no one can, the fragmentation is arbitrary.

### Rationale
Schwitters' Merz magazine (1923-1932) and Lissitzky's constructivist typography both operated within strict material and geometric constraints. The apparent freedom was real but bounded. The distinction between governed chaos and arbitrary chaos is the distinction between Merz and mess.

<!-- RULE END: EDIT-MERZ-GOVERN-001 -->
---

<!-- RULE START: EDIT-PROSE-CAPTION-001 -->
## Rule EDIT-PROSE-CAPTION-001

**Domain**: editorial
**Severity**: Medium
**Scope**: Layout
**Mandatory**: false

### Trigger
When styling captions for figures or tables in an editorial layout.

### Statement
Captions must be visually subordinate to body text: typically 2 points smaller than body (Bringhurst convention), often in a contrasting face (sans-serif against serif body, or vice versa). Captions go below figures and above tables (tables read top-down; figures read body-first). Captions at the same size as body text collapse the visual hierarchy.

### Violation
```css
/* Caption same size and face as body text */
.body { font: 16px/1.5 Georgia; }
.caption { font: 16px/1.5 Georgia; }
/* No hierarchy between body and caption; reader can't distinguish */
```

### Pass
```css
/* Caption subordinate: smaller, contrasting face */
.body { font: 16px/1.5 Georgia; }
figcaption { font: 14px/1.4 'Inter', sans-serif; color: #555; }
/* 2px smaller, contrasting sans face, slightly muted */
```

### Enforcement
Code review. Compare caption font-size to body font-size (should be ~2pt smaller). Check whether faces contrast. Verify placement: below figures, above tables.

### Rationale
Bringhurst's Elements of Typographic Style establishes the convention: captions are a supporting voice, not the primary voice. The size reduction and face contrast signal to the reader that this is metadata about the figure, not part of the body argument. Same-size captions force the reader to parse context from content rather than seeing it structurally.

<!-- RULE END: EDIT-PROSE-CAPTION-001 -->
---

<!-- RULE START: EDIT-PROSE-FIGURE-001 -->
## Rule EDIT-PROSE-FIGURE-001

**Domain**: editorial
**Severity**: High
**Scope**: Layout
**Mandatory**: false

### Trigger
When placing figures (images, charts, diagrams) in a multi-column prose layout.

### Statement
Figures must be placed near their first text reference, sized to whole-number multiples of column widths, and positioned at column tops or bottoms only. Figures placed mid-column break reading flow. Figures sized arbitrarily (not aligned to column grid) make the composition feel accidental. Full-width figures create horizontal breaks; single-column figures sit within one text stream; margin figures minimize disruption.

### Violation
```css
/* Figure floated mid-column at arbitrary width */
.figure {
  float: left;
  width: 347px; /* arbitrary; not aligned to any column */
  margin: 1em;
}
/* Text wraps around figure mid-paragraph; reading flow broken */
```

### Pass
```css
/* Figure at column top, spanning 2 of 3 columns (integer column widths) */
.figure {
  grid-column: 1 / 3; /* spans 2 columns exactly */
  margin-bottom: var(--baseline);
}
/* Placed at column top via grid-row: 1; text flows below */
```

### Enforcement
Code review. Check figure widths against column widths (must be integer multiples). Check vertical position (column tops/bottoms, not mid-column). Check proximity to first text reference.

### Rationale
Cognitive science confirms spatial contiguity aids comprehension: figures near their text reference are processed together. Grid-aligned figure sizing is the structural defense against accidental composition. Mid-column placement forces the eye to navigate around the figure, breaking the reading saccade that sustained prose depends on.

<!-- RULE END: EDIT-PROSE-FIGURE-001 -->
---

<!-- RULE START: EDIT-PROSE-MARBER-001 -->
## Rule EDIT-PROSE-MARBER-001

**Domain**: editorial
**Severity**: Medium
**Scope**: Layout
**Mandatory**: false

### Trigger
When designing a layout system that must accommodate variation across many pages or issues of the same publication.

### Statement
The layout must pass the Marber test: could the spread accommodate variation across many pages of the same publication while remaining systematically consistent? Romek Marber's 1961 Penguin grid allocated over two-thirds of the cover to illustration with rigorous type placement, enabling systematic flexibility across hundreds of titles. A layout that works for one page but cannot accommodate variation is a one-off, not a system.

### Violation
```
Layout designed for a specific article with hard-coded positions.
A different article (longer title, more figures, no images)
would require redesigning the layout from scratch.
No system; only a one-off.
```

### Pass
```
Layout system with:
- Named grid fields that accommodate 1, 2, or 3 columns
- Figure placement rules that work regardless of figure count
- Type hierarchy that holds whether the title is 3 words or 15
- Consistent margins and baseline across all instances
The 50th article looks as considered as the first.
```

### Enforcement
Code review. Test the layout with different content: short title vs. long, many figures vs. none, text-heavy vs. image-heavy. If any variation requires ad-hoc overrides, the system is incomplete.

### Rationale
Marber's Penguin grid (1961) proved that systematic flexibility and visual quality are not in tension. The grid enables variation by constraining it to a set of lawful configurations. A layout without this property is a poster, not a system.

<!-- RULE END: EDIT-PROSE-MARBER-001 -->
---

<!-- RULE START: EDIT-SPEC-SCALE-001 -->
## Rule EDIT-SPEC-SCALE-001

**Domain**: editorial
**Severity**: High
**Scope**: Layout
**Mandatory**: false

### Trigger
When displaying numerals, typographic characters, or letterforms as aesthetic objects in a ratio/specimen spread.

### Statement
Numerals and characters become art objects when given sufficient surrounding margin. Large-scale display elements demand whitespace to function compositionally. Negative space alternating with dense type blocks creates rhythm analogous to musical phrasing (Ruder). Each unit of space relates proportionally to every other through the underlying scale.

### Violation
```css
/* Display numeral crammed into body flow; no breathing room */
.display-numeral {
  font-size: 4rem;
  margin: 0;
  /* Numeral reads as oversized body text, not as an aesthetic object */
}
```

### Pass
```css
/* Display numeral with generous margin; reads as typographic event */
.display-numeral {
  font-size: 4rem;
  margin-top: calc(4 * var(--baseline));
  margin-bottom: calc(3 * var(--baseline));
  /* Surrounding space proportional to scale; numeral is a visual event */
}
```

### Enforcement
Code review. Check whether display-scale elements have margin proportional to their size and the underlying scale. Margin of zero or body-text-scale margin on display elements is a violation.

### Rationale
Bodoni's Manuale Tipografico (1818) demonstrated that letterforms at display scale are aesthetic objects, not just enlarged text. The surrounding margin is what transforms scale into presence. Without it, the large type is just loud, not monumental.

<!-- RULE END: EDIT-SPEC-SCALE-001 -->
---

<!-- RULE START: EDIT-SPEC-WEINGART-001 -->
## Rule EDIT-SPEC-WEINGART-001

**Domain**: editorial
**Severity**: Medium
**Scope**: Layout
**Mandatory**: false

### Trigger
When applying expressive or experimental typographic moves (weight variation, spatial disruption, unconventional arrangement) in a specimen or editorial layout.

### Statement
Expressive typographic moves require Swiss-precision rigor underneath first. Weingart's permission: typographic elements may be treated as visual events (weight, direction, spatial energy independent of linguistic function), but only when the underlying structural rigor is present. Without the grid, the experiments look arbitrary. The structure must be visible even where the surface looks chaotic.

### Violation
```
Rotated text blocks, mixed weights, overlapping elements.
No visible underlying grid. No named scale.
Result: looks like chaos, not transcendence.
```

### Pass
```
Rotated text block at 15 degrees, breaking from a visible 12-field grid.
All type sizes on a named scale (perfect fourth).
Margins follow Van de Graaf canon.
The departure is legible as departure because the norm is established.
```

### Enforcement
Code review. When expressive moves are present, verify that the underlying grid, scale, and margin system are intact. If the base structure cannot be named, the expression is arbitrary.

### Rationale
Weingart's Basel experiments (1960s-70s) demonstrated that typographic autonomy is earned, not asserted. His work succeeded because the Swiss grid system was the departure point. Expressive moves without that foundation read as student work, not as mastery.

<!-- RULE END: EDIT-SPEC-WEINGART-001 -->
---

<!-- RULE START: EDIT-VIZ-COMPARE-001 -->
## Rule EDIT-VIZ-COMPARE-001

**Domain**: editorial
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When designing or reviewing any data visualization or analytical display.

### Statement
Every display must answer "compared to what?" (Tufte's first principle of analytical design). A visualization that shows data without a comparison framework is incomplete. Comparisons can be across time, categories, conditions, or against a baseline. Isolated data points without comparison context are a violation.

### Violation
```html
<!-- Single number, no comparison, no context -->
<div class="metric">Revenue: $2.4M</div>
```

### Pass
```html
<!-- Number with comparison: previous period, target, trend -->
<div class="metric">
  Revenue: $2.4M
  <span class="delta">+12% vs Q3</span>
  <span class="sparkline"><!-- inline trend --></span>
</div>
```

### Enforcement
Code review. For every data display, ask: "Compared to what?" If no comparison is visible, recommend adding one.

### Rationale
Tufte's first principle of analytical design: "Show comparisons, contrasts, differences." The fundamental analytical act is comparison. A single number without context is a decoration, not an analysis. Even a simple baseline (last period, target, average) transforms decoration into information.

<!-- RULE END: EDIT-VIZ-COMPARE-001 -->
---

<!-- RULE START: EDIT-VIZ-INK-001 -->
## Rule EDIT-VIZ-INK-001

**Domain**: editorial
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When designing or reviewing any data visualization, chart, or quantitative display.

### Statement
Maximize the data-ink ratio: the proportion of ink devoted to non-redundant display of data. Every non-data element (decoration, heavy grids, boxes, redundant labels, 3D effects) must justify itself or be erased. The eraser test: if you can remove an element without losing data information, remove it.

### Violation
```html
<!-- Heavy grid, decorative border, redundant legend, 3D shadow -->
<div class="chart" style="
  border: 2px solid #333;
  box-shadow: 4px 4px 8px rgba(0,0,0,0.3);
  background: repeating-linear-gradient(/* heavy grid pattern */);
">
  <!-- Bars with gradient fills, rounded corners, drop shadows -->
</div>
```

### Pass
```html
<!-- Minimal: data elements only, light reference lines, direct labels -->
<svg class="chart">
  <!-- Bars with flat fill, direct value labels, no legend needed -->
  <!-- Light gray reference lines, barely visible -->
  <!-- No border, no shadow, no gradient -->
</svg>
```

### Enforcement
Code review. For every visual element in the chart, ask: "Can I erase this without losing data information?" If yes, erase it.

### Rationale
Tufte's data-ink ratio is the single most actionable principle in data visualization. Every non-data element competes with the data for the viewer's attention. Maximizing data-ink means the viewer thinks about substance, not methodology or design.

<!-- RULE END: EDIT-VIZ-INK-001 -->
---

<!-- RULE START: EDIT-VIZ-INTEGRATE-001 -->
## Rule EDIT-VIZ-INTEGRATE-001

**Domain**: editorial
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When placing labels, legends, annotations, and explanatory text in any data visualization.

### Statement
Words, numbers, images, and diagrams must be completely integrated within the visualization, not segregated by mode. Labels sit on or near the data they describe. Legends placed far from the data they decode force the reader to hold information in working memory while their eye travels. Segregated zones (chart here, legend there, explanation elsewhere) are a violation.

### Violation
```
Chart in the upper half of the page.
Legend in a sidebar 400px away.
Explanation paragraph below the fold.
Reader must triangulate between three zones to decode any single data point.
```

### Pass
```
Direct labels on each data series (no legend needed).
Annotation callouts pointing to specific data points with explanatory text.
All interpretive material within the same eye-frame as the data.
```

### Enforcement
Code review. Check whether labels and annotations are within the same visual frame as the data they describe. Measure the eye-travel distance from any data point to its label.

### Rationale
Tufte's fourth principle of analytical design: "Completely integrate words, numbers, images, diagrams." Segregation is the most common failure in dashboard design. Every zone boundary is a working-memory tax on the reader.

<!-- RULE END: EDIT-VIZ-INTEGRATE-001 -->
---

<!-- RULE START: EDIT-VIZ-JUNK-001 -->
## Rule EDIT-VIZ-JUNK-001

**Domain**: editorial
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When reviewing any data visualization for decorative elements.

### Statement
Zero chartjunk. Chartjunk is the interior decoration of graphics that does not convey information. Three categories: unintentional optical art (moire vibration, busy cross-hatching), heavy grids (competing with data for visual dominance), and the Duck (graphics that draw attention to their own design). If the viewer notices the design before the data, there is chartjunk.

### Violation
```css
/* 3D bar chart with gradient fills, drop shadows, and heavy grid */
.bar { background: linear-gradient(to top, #2196F3, #64B5F6); }
.bar { box-shadow: 2px 2px 4px rgba(0,0,0,0.3); }
.grid-line { border: 1px solid #999; } /* Heavy grid lines */
```

### Pass
```css
/* Flat bars, minimal reference lines, direct labels */
.bar { background: #2196F3; }
.reference-line { border: 1px solid #eee; } /* Barely visible */
/* No shadows, no gradients, no 3D effects */
```

### Enforcement
Code review. Identify every decorative element (gradients, shadows, 3D effects, heavy borders, busy patterns). If the element does not carry data, it is chartjunk.

### Rationale
Tufte identifies chartjunk as the most pervasive failure in data visualization. The three categories (optical art, heavy grids, the Duck) cover most decorative failures. The viewer should think about substance, not methodology or design.

<!-- RULE END: EDIT-VIZ-JUNK-001 -->
---

<!-- RULE START: EDIT-VIZ-LAYER-001 -->
## Rule EDIT-VIZ-LAYER-001

**Domain**: editorial
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When a data visualization contains multiple overlapping elements or when primary data competes visually with secondary elements (grids, axes, annotations).

### Statement
Visually layer elements by importance: primary data in dark/saturated, secondary data in lighter values, reference elements (grids, axes) barely visible. The squint test: squint at the graphic; the most important data should remain visible while chartjunk and secondary elements disappear first. Grids should whisper, not shout.

### Violation
```css
/* Grid lines and data bars at similar visual weight */
.grid-line { stroke: #666; stroke-width: 1px; }
.data-bar  { fill: #888; }
/* Squint test: grid and data are equally visible. Grid competes. */
```

### Pass
```css
/* Primary data dominates; grid recedes */
.grid-line { stroke: #eee; stroke-width: 0.5px; }
.data-bar  { fill: #2196F3; }
/* Squint test: data bars are visible; grid lines vanish. */
```

### Enforcement
Code review. Apply the squint test: does the most important data dominate when the graphic is viewed at reduced attention? If grid, borders, or annotations compete, lighten them.

### Rationale
Tufte's layering and separation principle (from Envisioning Information): visually distinct elements coexist in the same space when separated by value, weight, or hue. The 1+1=3 effect (two heavy elements create a phantom third) is the mechanism: reducing weight on secondary elements eliminates the phantoms and lets the data speak.

<!-- RULE END: EDIT-VIZ-LAYER-001 -->
---

<!-- RULE START: EDIT-VIZ-LIE-001 -->
## Rule EDIT-VIZ-LIE-001

**Domain**: editorial
**Severity**: Critical
**Scope**: Component
**Mandatory**: true

### Trigger
When designing or reviewing any data visualization where visual size represents a quantity.

### Statement
Lie Factor must be approximately 1.0. Lie Factor = (size of effect shown in graphic) / (size of effect in data). A Lie Factor above 1.05 or below 0.95 is distortion. Proportional shapes (circles, bubbles) must be scaled by area, not diameter. Truncated axes that exaggerate change are a violation. 3D effects on 2D data are a violation.

### Violation
```javascript
// Bubble sized by diameter, not area -- quadratic exaggeration
const radius = value * 10; // 2x value = 2x radius = 4x area (Lie Factor = 2.0)
```

### Pass
```javascript
// Bubble sized by area -- proportional representation
const radius = Math.sqrt(value / Math.PI) * scale; // 2x value = 2x area (Lie Factor = 1.0)
```

### Enforcement
Code review. Check whether proportional shapes use area or diameter scaling. Verify axis baselines. Calculate Lie Factor for any visual encoding of magnitude.

### Rationale
Tufte's six principles of graphical integrity begin with: "Representation of numbers should be directly proportional to quantities represented." Diameter-scaling of circles is the most common violation because it produces quadratic exaggeration that looks subtle but distorts badly. A value twice as large appears four times as large when scaled by diameter.

<!-- RULE END: EDIT-VIZ-LIE-001 -->
---

<!-- RULE START: EDIT-VIZ-MULTIVAR-001 -->
## Rule EDIT-VIZ-MULTIVAR-001

**Domain**: editorial
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When designing a data visualization or analytical display that presents a phenomenon with multiple interacting variables.

### Statement
Show multivariate data, not just 1 or 2 variables (Tufte's third principle of analytical design). Real problems are multivariate. Reducing to a single variable hides interactions. The display should encode at least 3 dimensions where the data supports it: position, color, size, shape, time, or small-multiples indexing.

### Violation
```
Bar chart showing revenue by quarter.
One variable (revenue) against one index (time).
Hides: revenue by product line, by region, by customer segment.
The interactions are invisible.
```

### Pass
```
Small multiples of sparklines: revenue by quarter,
one panel per product line, color-coded by region.
Three variables visible simultaneously.
Reader can compare across lines, across regions, across time.
```

### Enforcement
Code review. Count the variables encoded in the display. If the underlying data has 3+ relevant dimensions and the chart shows only 1-2, recommend adding encoding channels or small multiples.

### Rationale
Tufte's third principle of analytical design: "Show multivariate data." Over-reduction is the most common analytical failure. A single-variable chart answers "what happened?" but not "why?" or "where?" Adding dimensions (via color, faceting, or small multiples) transforms description into analysis.

<!-- RULE END: EDIT-VIZ-MULTIVAR-001 -->
---

<!-- RULE START: EDIT-VIZ-SPARKLINE-001 -->
## Rule EDIT-VIZ-SPARKLINE-001

**Domain**: editorial
**Severity**: Low
**Scope**: Component
**Mandatory**: false

### Trigger
When a dashboard, table, or prose passage needs to show trend, shape, or variability for many metrics without dedicating full chart space to each.

### Statement
Use sparklines (word-sized, data-intense graphics) for inline trend display. Height approximately equal to the x-height of surrounding text (~14-20px). No axes, no labels, no decoration. Endpoints may be marked (start/end values, or min/max). Pair with the most recent numeric value. Stack in tables for vertical scanning.

### Violation
```html
<!-- Full chart for a single metric trend; dominates the dashboard row -->
<div class="chart-container" style="height: 200px; width: 400px;">
  <!-- Full axes, legend, gridlines for 12 data points -->
</div>
```

### Pass
```html
<!-- Sparkline inline with the metric; word-sized, no decoration -->
<td>Revenue</td>
<td><svg class="sparkline" height="16" width="80"><!-- 12 points --></svg></td>
<td>$2.4M</td>
<td class="delta">+12%</td>
```

### Enforcement
Code review. When multiple metrics each have their own full-size chart, consider whether sparklines would provide the same trend information at a fraction of the space.

### Rationale
Tufte's Beautiful Evidence introduced sparklines as the highest data-density format: thousands of data points per square inch at typographic resolution. They work because the reader needs shape and trend, not precise values. Pair with a single current number for precision. The combination (sparkline + number) gives both trend and value in the space of one table cell.

<!-- RULE END: EDIT-VIZ-SPARKLINE-001 -->
