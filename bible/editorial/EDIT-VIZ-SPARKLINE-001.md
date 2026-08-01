---
rule_id: EDIT-VIZ-SPARKLINE-001
node_type: Rule
domain: editorial
severity: low
scope: component
mandatory: false
trigger: |
  When a dashboard, table, or prose passage needs to show trend, shape, or variability for many metrics without dedicating full chart space to each.
statement: |
  Use sparklines (word-sized, data-intense graphics) for inline trend display. Height approximately equal to the x-height of surrounding text (~14-20px). No axes, no labels, no decoration. Endpoints may be marked (start/end values, or min/max). Pair with the most recent numeric value. Stack in tables for vertical scanning.
violation: |
  ```html
  <!-- Full chart for a single metric trend; dominates the dashboard row -->
  <div class="chart-container" style="height: 200px; width: 400px;">
    <!-- Full axes, legend, gridlines for 12 data points -->
  </div>
  ```
pass_example: |
  ```html
  <!-- Sparkline inline with the metric; word-sized, no decoration -->
  <td>Revenue</td>
  <td><svg class="sparkline" height="16" width="80"><!-- 12 points --></svg></td>
  <td>$2.4M</td>
  <td class="delta">+12%</td>
  ```
enforcement: |
  Code review. When multiple metrics each have their own full-size chart, consider whether sparklines would provide the same trend information at a fraction of the space.
rationale: |
  Tufte's Beautiful Evidence introduced sparklines as the highest data-density format: thousands of data points per square inch at typographic resolution. They work because the reader needs shape and trend, not precise values. Pair with a single current number for precision. The combination (sparkline + number) gives both trend and value in the space of one table cell.
tags: [rule, editorial, tufte, sparkline, inline-graphic, data-density]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-01
staleness_window: 365
evidence: peer-reviewed
source_attribution: "editorial-claude-skills:tufte-viz"
source_commit: null
edges:
  - { target: EDIT-VIZ-INTEGRATE-001, type: DEPENDS_ON }
  - { target: EDIT-VIZ-INK-001, type: SUPPLEMENTS }
---
