"""Phase 5 dashboard composer.

Renders the friction-log signal as server-rendered HTML. No JS
framework -- a single `<meta http-equiv="refresh">` tag handles
auto-refresh. All metrics come from the analyzer functions in
writ/analysis/friction.py (ARCH-SSOT-001 -- never recompute).

Public surface: render_dashboard() -> str (HTML).
"""
from __future__ import annotations

import html
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from writ.analysis.friction import (
    _SPLIT_STREAMS,
    FrictionEvent,
    aggregate_by_event,
    analyze_graduation_candidates,
    analyze_playbook_compliance,
    analyze_quality_judge_false_positives,
    analyze_rule_effectiveness,
    analyze_skill_usage,
    analyze_trim_candidates,
    parse_log,
)
from writ.analysis.pair_ledger import (
    ProjectCopies,
    RuleSource,
    memory_copies,
    rule_sources,
    stale_notes,
)
from writ.shared.logging import resolve_project, stream_path

REFRESH_SECONDS = 60
_EMPTY = '<p class="empty">no data</p>'


def _esc(value: Any) -> str:
    return html.escape(str(value))


def _table_html(headers: list[str], rows_html: list[str]) -> str:
    th = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body = "\n".join(rows_html)
    return (f'<div class="table-wrap"><table>\n<thead><tr>{th}</tr></thead>\n'
            f"<tbody>\n{body}\n</tbody>\n</table></div>")


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return _EMPTY
    return _table_html(headers, [
        "<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>" for row in rows
    ])


def _block(title: str, body: str) -> str:
    return f'<div class="block">\n<h3>{_esc(title)}</h3>\n{body}\n</div>'


def _band(title: str, note: str, blocks: list[str]) -> str:
    """One question per band: the rail names it, the track answers it."""
    return (f'<section class="band">\n<div class="rail"><h2>{_esc(title)}</h2>'
            f'<p>{_esc(note)}</p></div>\n<div class="track">\n{"".join(blocks)}\n</div>\n</section>')


def _figs(items: list[tuple[int, str]]) -> str:
    return '<div class="figs">' + "".join(
        f'<div class="fig"><b>{_esc(n)}</b><span>{_esc(label)}</span></div>' for n, label in items
    ) + "</div>"


def _sync_kind(sync: str) -> str:
    """`ok` when the file is safe outside this Mac, `check` otherwise (see RuleSource.sync)."""
    return "ok" if sync == "in git" or sync.endswith(", same") else "check"


def _sync_chip(sync: str) -> str:
    return f'<span class="chip {_sync_kind(sync)}">{_esc(sync)}</span>'


def _sources_table(sources: list[RuleSource]) -> str:
    if not sources:
        return _EMPTY
    rows = []
    for s in sources:
        gap = ' class="gap"' if _sync_kind(s.sync) == "check" else ""
        size = "-" if s.rules is None else f"{s.rules} rule{'' if s.rules == 1 else 's'}"
        rows.append(
            f'<tr{gap}><td>{_esc(s.label)}<span class="sub mono">{_esc(s.display_path)}</span></td>'
            f"<td>{size}</td><td>{_esc(s.changed or '-')}</td><td>{_sync_chip(s.sync)}</td></tr>"
        )
    return _table_html(["Source", "Size", "Changed", "Sync"], rows) + (
        '<p class="src">Size counts the list lines in each file. Changed is the last commit, '
        "or the file date where git does not track it.</p>"
    )


def _memory_meter(copies: list[ProjectCopies]) -> str:
    """One bar per project, all on one scale, so bar length is the number of notes."""
    if not copies:
        return _EMPTY
    scale = max(c.copied + c.outdated + c.missing for c in copies)
    rows = []
    for c in copies:
        total = c.copied + c.outdated + c.missing
        segments = "".join(
            f'<i class="{cls}" style="flex:{n}" title="{_esc(c.project)}: {n} {what}"></i>'
            for cls, n, what in (("c", c.copied, "copied"), ("o", c.outdated, "outdated"),
                                 ("m", c.missing, "with no copy"))
            if n
        )
        val = f"{c.copied + c.outdated} of {total}" + (f", {c.outdated} outdated" if c.outdated else "")
        rows.append(
            f'<div class="m-row"><span class="lab">{_esc(c.project)}</span>'
            f'<div class="m-bar" style="width:{total / scale * 100:.1f}%">{segments}</div>'
            f'<span class="val">{val}</span></div>'
        )
    legend = ('<div class="meter-legend" aria-hidden="true"><span><i class="sw copied"></i>Copied</span>'
              '<span><i class="sw outdated"></i>Copy outdated</span>'
              '<span><i class="sw missing"></i>No copy</span></div>')
    outdated = [f"{name} ({c.project})" for c in copies for name in c.outdated_names]
    note = f'<p class="note">Outdated copies: {_esc(", ".join(outdated))}.</p>' if outdated else ""
    return legend + '<div class="meter">' + "\n".join(rows) + "</div>" + note


# A9: parse_log is ~785ms (Pydantic-bound) and ran on EVERY GET /dashboard.
# Cache the parsed events keyed on each file's (path, mtime_ns, size) -- the logs
# are append-only, so that stamp is an exact change key; size catches two appends
# inside one mtime tick, and a rolled stream starts a new file with a new stamp.
# Idempotent under concurrent GETs (same key -> same events), so no lock is needed.
_EVENTS_CACHE: dict = {"key": None, "events": None}


def _log_files() -> tuple[str | None, list[Path]]:
    """The project and files the dashboard reads.

    WRIT_FRICTION_LOG, when set, collapses the logs into that one file (project None).
    Otherwise: the daemon project's split streams, the same ones `writ analyze-friction`
    reads. The old ./workflow-friction.log fallback stopped receiving rows at the split.
    """
    env = os.environ.get("WRIT_FRICTION_LOG")
    if env:
        return None, [Path(env)]
    project = resolve_project()
    return project, [stream_path(project, s) for s in _SPLIT_STREAMS]


def _stamp(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return st.st_mtime_ns, st.st_size


def _safe_load_events(project: str | None, files: list[Path]) -> list[FrictionEvent]:
    """Best-effort parse. Missing logs -> empty list. No exceptions escape."""
    key = tuple((str(f), _stamp(f)) for f in files)
    if _EVENTS_CACHE["key"] == key and _EVENTS_CACHE["events"] is not None:
        return _EVENTS_CACHE["events"]
    try:
        events = parse_log(project=project)
    except Exception:
        return []
    _EVENTS_CACHE["key"] = key
    _EVENTS_CACHE["events"] = events
    return events


def render_dashboard(memory_rows: list[dict[str, Any]] | None = None) -> str:
    """Compose the dashboard HTML. Always returns a complete page.

    `memory_rows` are the graph's Memory rows, read by the async route; None means
    the graph was not reachable, and the memory section says so.
    """
    # Resolved once per request: without WRIT_LOG_PROJECT, resolve_project() shells out to git.
    project, files = _log_files()
    events = _safe_load_events(project, files)

    # Live counts
    total_events = len(events)
    sessions = len({e.session for e in events})
    by_event = aggregate_by_event(events)

    counts_rows = [[k, v] for k, v in sorted(by_event.items(), key=lambda kv: -kv[1])][:10]
    live_counts = _figs([(total_events, "events"), (sessions, "sessions")]) + _table(
        ["Event", "Count"], counts_rows
    )

    # Rule effectiveness (top 10)
    rule_rows = analyze_rule_effectiveness(events, since_days=30, top=10)
    rule_table = _table(
        ["Rule", "Activations", "Stuck", "Stick rate", "Rationalizations"],
        [[r.rule_id, r.activations, r.stuck_denials,
          f"{r.denial_stick_rate:.2f}", r.rationalizations] for r in rule_rows],
    )

    # Skill usage (top 10)
    skill_rows = analyze_skill_usage(events, since_days=60, top=10)
    skill_table = _table(
        ["Skill", "Loads", "Completions", "Completion rate"],
        [[s.skill_id, s.loads, s.completions,
          f"{s.completion_rate:.2f}"] for s in skill_rows],
    )

    # Playbook compliance (top 10)
    pb_rows = analyze_playbook_compliance(events, since_days=30, top=10)
    pb_table = _table(
        ["Playbook", "Runs", "Compliant", "Skip points"],
        [[r.playbook_id, r.runs, r.compliant_runs,
          ", ".join(r.common_skip_points) or "-"] for r in pb_rows],
    )

    # Graduation candidates
    grad_rows = analyze_graduation_candidates(events, top=10)
    grad_table = _table(
        ["Rule", "Days stable", "Current", "Recommended", "Stick rate"],
        [[g.rule_id, g.days_stable, g.current_tier, g.recommended_tier,
          f"{g.denial_stick_rate:.2f}"] for g in grad_rows],
    )

    # Trim candidates
    trim_rows = analyze_trim_candidates(events, since_days=90, top=20)
    trim_table = _table(
        ["Entity", "Type", "Activations", "Last seen", "Recommendation"],
        [[t.entity_id, t.entity_type, t.activations_in_window,
          t.last_activation or "-", t.recommendation] for t in trim_rows],
    )

    # Quality-judge false positives
    qj_rows = analyze_quality_judge_false_positives(events, since_days=30, top=10)
    qj_table = _table(
        ["Rubric", "Fails", "Overrides", "Override rate"],
        [[q.rubric, q.total_fails, q.overrides,
          f"{q.override_rate:.2f}"] for q in qj_rows],
    )

    # Pair Ledger: the files Claude follows, and its memory against the graph copy
    copies = memory_copies(memory_rows)
    copies_body = '<p class="empty">graph not reachable</p>' if copies is None else _memory_meter(copies)
    stale_table = _table(
        ["Note", "Project", "Last change"],
        [[n.name, n.project, f"{n.changed}, {n.age_days} days"] for n in stale_notes()],
    )

    bands = [
        _band("What we follow", "The files Claude reads its rules from, and where each one is kept.", [
            _block("Rule sources", _sources_table(rule_sources())),
        ]),
        _band("What holds", "How Writ's rules fare in practice, from the friction log.", [
            _block("Live counts", live_counts),
            _block("Rule effectiveness (last 30 days)", rule_table),
            _block("Skill usage (last 60 days)", skill_table),
            _block("Playbook compliance (last 30 days)", pb_table),
            _block("Graduation candidates", grad_table),
            _block("Quality judge false positives (last 30 days)", qj_table),
        ]),
        _band("What's gone stale", "Copies that drifted, notes nobody has reread, rules that never fire.", [
            _block("Claude's memory, copied into Writ", copies_body),
            _block("Notes untouched for 90 days or more", stale_table),
            _block("Trim candidates (last 90 days)", trim_table),
        ]),
    ]

    rendered_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    log_label = str(files[0] if project is None else files[0].parent)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="{REFRESH_SECONDS}">
  <title>Pair Ledger</title>
  <style>{_CSS}</style>
</head>
<body>
<main class="page">
  <header class="mast">
    <p class="eyebrow">Rendered {_esc(rendered_at)} · log: {_esc(log_label)} · refreshes every {REFRESH_SECONDS}s</p>
    <h1>Pair Ledger</h1>
    <p class="lede">The rules you and Claude both work by. Where each one lives, whether it holds, and what has gone stale.</p>
  </header>
  {''.join(bands)}
</main>
</body>
</html>
"""


# The Pair Ledger sketch's tokens and layout, on system fonts: the page comes from a local
# daemon and reloads every REFRESH_SECONDS, so it fetches nothing from outside.
_CSS = """
:root {
  color-scheme: light;
  --bg: #f6f6f4; --surface: #ffffff; --ink: #17191e; --ink-2: #464b55; --muted: #767b85;
  --rule: #dddee1; --track: #e8e9ec; --accent: #1d44c4; --bar: #2b2f38;
  --good: #0ca30c; --warn: #fab219; --crit: #d03b3b;
  --display: "Avenir Next Condensed", "Arial Narrow", "Helvetica Neue", sans-serif;
  --body: system-ui, -apple-system, "Helvetica Neue", sans-serif;
  --mono: ui-monospace, "SF Mono", Menlo, monospace;
}
@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    --bg: #121317; --surface: #1a1b20; --ink: #eceef2; --ink-2: #b6bbc5; --muted: #8b919c;
    --rule: #2d3038; --track: #2a2d34; --accent: #93a8ff; --bar: #d9dce3;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 400 15px/1.55 var(--body); }
.page { max-width: 72rem; margin: 0 auto; padding-inline: clamp(16px, 4vw, 48px); padding-block: 40px 96px; }
code, .mono { font-family: var(--mono); font-size: 0.86em; }
p { margin: 0; }
a { color: var(--accent); }

.mast { display: grid; gap: 10px; padding-block: 8px 36px; }
.eyebrow { font: 500 12px/1.4 var(--mono); letter-spacing: 0.04em; color: var(--muted); text-transform: uppercase; overflow-wrap: anywhere; }
h1 { margin: 0; font: 800 clamp(44px, 8vw, 88px)/0.92 var(--display); font-stretch: 72%; letter-spacing: -0.01em; }
.lede { max-width: 58ch; font-size: 17px; color: var(--ink-2); }

.band { display: grid; grid-template-columns: minmax(0, 12rem) minmax(0, 1fr); gap: 16px 40px; padding-block: 28px 36px; border-top: 1px solid var(--rule); }
.rail h2 { margin: 0; font: 700 26px/1.02 var(--display); font-stretch: 78%; text-wrap: balance; }
.rail p { margin-top: 8px; font-size: 13px; color: var(--muted); }
.track { display: grid; gap: 28px; min-width: 0; }
h3 { margin: 0 0 10px; font: 600 12px/1.3 var(--mono); letter-spacing: 0.05em; text-transform: uppercase; color: var(--muted); }
.note { margin-top: 10px; font-size: 13.5px; color: var(--ink-2); max-width: 66ch; }
.src { margin-top: 10px; font-size: 12px; color: var(--muted); max-width: 70ch; }
.empty { color: var(--muted); font-style: italic; }

/* Status marks: shape and word, never colour alone. */
.chip { display: inline-flex; align-items: center; gap: 6px; font: 500 11.5px/1 var(--mono); letter-spacing: 0.03em; text-transform: uppercase; white-space: nowrap; }
.chip::before { content: ""; width: 9px; height: 9px; flex: none; background: var(--muted); }
.chip.ok::before { background: var(--good); border-radius: 50%; }
.chip.check::before { background: var(--warn); transform: rotate(45deg) scale(0.85); }

.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 14px; font-variant-numeric: tabular-nums; }
th { text-align: left; font: 500 11.5px/1.3 var(--mono); letter-spacing: 0.04em; text-transform: uppercase; color: var(--muted); padding: 0 12px 8px 0; border-bottom: 1px solid var(--ink); white-space: nowrap; }
td { padding: 9px 12px 9px 0; border-bottom: 1px solid var(--rule); vertical-align: baseline; overflow-wrap: anywhere; }
td .sub { display: block; font-size: 12.5px; color: var(--muted); }
tr.gap td:first-child { font-weight: 600; }

.figs { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 13rem), 1fr)); gap: 20px 32px; margin-bottom: 20px; }
.fig { display: grid; gap: 4px; align-content: start; }
.fig b { font: 700 40px/1 var(--display); font-stretch: 80%; font-variant-numeric: tabular-nums; }
.fig span { font-size: 13.5px; color: var(--ink-2); }

.meter-legend { display: flex; flex-wrap: wrap; gap: 6px 20px; font-size: 12.5px; color: var(--ink-2); margin-bottom: 12px; }
.meter-legend span { display: inline-flex; align-items: center; gap: 7px; }
.sw { width: 18px; height: 8px; display: inline-block; }
.sw.copied { background: var(--bar); }
.sw.outdated { background: var(--warn); }
.sw.missing { background: var(--track); box-shadow: inset 0 0 0 1px var(--rule); }
.meter { display: grid; gap: 9px; }
.m-row { display: grid; grid-template-columns: minmax(0, 8rem) minmax(0, 1fr) minmax(0, 11rem); gap: 12px; align-items: center; font-size: 13.5px; }
.m-row .lab { font-family: var(--mono); font-size: 12.5px; overflow-wrap: anywhere; }
.m-row .val { color: var(--ink-2); font-variant-numeric: tabular-nums; }
.m-bar { display: flex; gap: 2px; height: 10px; }
.m-bar i { display: block; height: 100%; }
.m-bar i.c { background: var(--bar); }
.m-bar i.o { background: var(--warn); }
.m-bar i.m { background: var(--track); box-shadow: inset 0 0 0 1px var(--rule); }
.m-bar i:last-child { border-radius: 0 4px 4px 0; }

@media (max-width: 760px) {
  .band { grid-template-columns: minmax(0, 1fr); gap: 16px; }
  .m-row { grid-template-columns: minmax(0, 6.5rem) minmax(0, 1fr); }
  .m-row .val { grid-column: 2; font-size: 12.5px; margin-top: -4px; }
}
"""
