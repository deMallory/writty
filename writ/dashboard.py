"""Phase 5 dashboard composer.

Renders the friction-log signal as server-rendered HTML. No JS
framework -- a single `<meta http-equiv="refresh">` tag handles
auto-refresh. All metrics come from the analyzer functions in
writ/analysis/friction.py (ARCH-SSOT-001 -- never recompute).

Public surface: render_dashboard() -> str (HTML).
"""
from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any

from writ.analysis.friction import (
    FrictionEvent,
    aggregate_by_event,
    analyze_graduation_candidates,
    analyze_playbook_compliance,
    analyze_quality_judge_false_positives,
    analyze_rule_effectiveness,
    analyze_skill_usage,
    analyze_trim_candidates,
    parse_log,
    resolve_log_path,
)

REFRESH_SECONDS = 60


def _esc(value: Any) -> str:
    return html.escape(str(value))


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return '<p class="empty">no data</p>'
    th = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body = "\n".join(
        "<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>"
        for row in rows
    )
    return f"<table>\n<thead><tr>{th}</tr></thead>\n<tbody>\n{body}\n</tbody>\n</table>"


def _section(title: str, body: str) -> str:
    return f'<section>\n<h2>{_esc(title)}</h2>\n{body}\n</section>'


def _safe_load_events() -> list[FrictionEvent]:
    """Best-effort parse. Missing log -> empty list. No exceptions escape."""
    try:
        path = resolve_log_path()
        return parse_log(path)
    except Exception:
        return []


def render_dashboard() -> str:
    """Compose the dashboard HTML. Always returns a complete page."""
    events = _safe_load_events()

    # Live counts
    total_events = len(events)
    sessions = len({e.session for e in events})
    by_event = aggregate_by_event(events)

    counts_rows = [[k, v] for k, v in sorted(by_event.items(), key=lambda kv: -kv[1])][:10]
    live_counts = _table(["event", "count"], counts_rows)

    # Rule effectiveness (top 10)
    rule_rows = analyze_rule_effectiveness(events, since_days=30, top=10)
    rule_table = _table(
        ["rule_id", "activations", "stuck", "stick_rate", "rationalizations"],
        [[r.rule_id, r.activations, r.stuck_denials,
          f"{r.denial_stick_rate:.2f}", r.rationalizations] for r in rule_rows],
    )

    # Skill usage (top 10)
    skill_rows = analyze_skill_usage(events, since_days=60, top=10)
    skill_table = _table(
        ["skill_id", "loads", "completions", "completion_rate"],
        [[s.skill_id, s.loads, s.completions,
          f"{s.completion_rate:.2f}"] for s in skill_rows],
    )

    # Playbook compliance (top 10)
    pb_rows = analyze_playbook_compliance(events, since_days=30, top=10)
    pb_table = _table(
        ["playbook_id", "runs", "compliant", "skip_points"],
        [[r.playbook_id, r.runs, r.compliant_runs,
          ", ".join(r.common_skip_points) or "-"] for r in pb_rows],
    )

    # Graduation candidates
    grad_rows = analyze_graduation_candidates(events, top=10)
    grad_table = _table(
        ["rule_id", "days_stable", "current", "recommended", "stick_rate"],
        [[g.rule_id, g.days_stable, g.current_tier, g.recommended_tier,
          f"{g.denial_stick_rate:.2f}"] for g in grad_rows],
    )

    # Trim candidates
    trim_rows = analyze_trim_candidates(events, since_days=90, top=20)
    trim_table = _table(
        ["entity", "type", "activations", "last_seen", "recommendation"],
        [[t.entity_id, t.entity_type, t.activations_in_window,
          t.last_activation or "-", t.recommendation] for t in trim_rows],
    )

    # Quality-judge false positives
    qj_rows = analyze_quality_judge_false_positives(events, since_days=30, top=10)
    qj_table = _table(
        ["rubric", "fails", "overrides", "override_rate"],
        [[q.rubric, q.total_fails, q.overrides,
          f"{q.override_rate:.2f}"] for q in qj_rows],
    )

    sections = [
        _section("Live counts", _table(
            ["metric", "value"],
            [["total events", total_events], ["distinct sessions", sessions]]
        ) + live_counts),
        _section("Rule effectiveness (last 30 days)", rule_table),
        _section("Skill usage (last 60 days)", skill_table),
        _section("Playbook compliance (last 30 days)", pb_table),
        _section("Graduation candidates", grad_table),
        _section("Trim candidates (last 90 days)", trim_table),
        _section("Quality judge false positives (last 30 days)", qj_table),
    ]

    rendered_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    log_path = resolve_log_path()

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="{REFRESH_SECONDS}">
  <title>Writ -- friction dashboard</title>
  <style>
    body {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; max-width: 1100px;
            margin: 1.5em auto; padding: 0 1em; color: #222; }}
    h1 {{ margin-bottom: 0.2em; }}
    h2 {{ margin-top: 1.6em; border-bottom: 1px solid #ccc; padding-bottom: 0.2em; }}
    section {{ margin-bottom: 1.5em; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 0.9em; }}
    th, td {{ text-align: left; padding: 0.3em 0.6em; border-bottom: 1px solid #eee; }}
    th {{ background: #f6f6f6; }}
    .meta {{ color: #666; font-size: 0.85em; }}
    .empty {{ color: #888; font-style: italic; }}
  </style>
</head>
<body>
  <h1>Writ friction dashboard</h1>
  <p class="meta">
    rendered at {_esc(rendered_at)} -- log: {_esc(str(log_path))} -- auto-refresh every {REFRESH_SECONDS}s
  </p>
  {''.join(sections)}
</body>
</html>
"""
