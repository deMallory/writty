"""Friction-log reader + aggregator.

Reads the JSONL workflow-friction.log that Writ hooks write to, produces
human-readable summaries, and rotates the log when it grows too large.
Exposed via the `writ analyze-friction` CLI subcommand and the
`/dashboard` server endpoint.

Phase 4 added: FrictionEvent Pydantic model + parse_log + per-rule and
per-event aggregators.

Phase 5 adds:
  - log_friction_event(): Python writer honoring WRIT_FRICTION_LOG env var
  - resolve_log_path(): canonical lookup for the active log
  - Six analyzer functions for measurement / graduation / trim
  - Six typed result-row models
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict

__all__ = [
    "load_events", "summarize", "rotate_if_needed", "format_report",
    "FrictionEvent", "parse_log", "aggregate_by_rule", "aggregate_by_event",
    "log_friction_event", "resolve_log_path",
    # Phase 5 result models
    "RuleEffectivenessRow", "SkillUsageRow", "PlaybookComplianceRow",
    "GraduationCandidate", "TrimCandidate", "QualityJudgeOverride",
    # Phase 5 analyzers
    "analyze_rule_effectiveness", "analyze_skill_usage",
    "analyze_playbook_compliance", "analyze_graduation_candidates",
    "analyze_trim_candidates", "analyze_quality_judge_false_positives",
]


class FrictionEvent(BaseModel):
    """One JSONL row from workflow-friction.log.

    Extra fields (rule_id, gate, matched_prompt, etc.) are preserved via
    model_config.extra so callers can inspect without hard-coding every
    hook's emit schema.
    """

    model_config = ConfigDict(extra="allow")

    ts: str
    session: str
    event: str
    mode: str | None = None
    rule_id: str | None = None
    gate: str | None = None


# --- Log path resolution + writer -------------------------------------------


def resolve_log_path(explicit: Path | str | None = None) -> Path:
    """Return the canonical friction-log path.

    Resolution order:
      1. explicit argument (absolute or relative)
      2. WRIT_FRICTION_LOG env var
      3. ./workflow-friction.log

    Used by both the CLI (which passes --log) and the dashboard (which
    reads the env var). Single source of truth.
    """
    if explicit is not None:
        return Path(explicit)
    env = os.environ.get("WRIT_FRICTION_LOG")
    if env:
        return Path(env)
    return Path("workflow-friction.log")


def log_friction_event(
    session_id: str,
    mode: str | None,
    event: str,
    log_path: Path | str | None = None,
    **fields: Any,
) -> None:
    """Append one JSON event to the friction log. Fire-and-forget.

    Honors WRIT_FRICTION_LOG. Written from server-side endpoints that
    record metrics (quality_judgment, playbook_step_complete). Bash
    hooks have their own writer in bin/lib/common.sh.
    """
    path = resolve_log_path(log_path)
    entry: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "session": session_id,
        "mode": mode,
        "event": event,
    }
    entry.update({k: v for k, v in fields.items() if v is not None})
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        # Fire-and-forget: never break the server because the log is unwritable.
        pass


# --- Parsers -----------------------------------------------------------------


def parse_log(path: Path) -> list[FrictionEvent]:
    """Parse JSONL log into validated FrictionEvent models.

    Malformed lines are skipped. Missing file returns []. Use this when
    the caller wants typed access; use load_events for raw dicts.
    """
    if not path.exists():
        return []
    events: list[FrictionEvent] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            try:
                events.append(FrictionEvent.model_validate(row))
            except Exception:
                continue
    return events


def aggregate_by_rule(events: list[FrictionEvent]) -> dict[str, int]:
    """Count events per rule_id. Events without rule_id are ignored."""
    counts: Counter[str] = Counter()
    for e in events:
        if e.rule_id:
            counts[e.rule_id] += 1
    return dict(counts)


def aggregate_by_event(events: list[FrictionEvent]) -> dict[str, int]:
    """Count events per event-name."""
    counts: Counter[str] = Counter()
    for e in events:
        counts[e.event] += 1
    return dict(counts)


DEFAULT_ROTATION_THRESHOLD_BYTES = 5 * 1024 * 1024  # 5MB


def load_events(log_path: Path) -> list[dict[str, Any]]:
    """Parse JSONL log, skipping malformed lines. Returns list of event dicts."""
    events: list[dict[str, Any]] = []
    if not log_path.exists():
        return events
    with log_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except (json.JSONDecodeError, ValueError):
                continue
    return events


def _filter_since(events: list[dict], since_days: int | None) -> list[dict]:
    if since_days is None:
        return events
    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    filtered: list[dict] = []
    for e in events:
        ts = e.get("ts")
        if not ts:
            continue
        try:
            event_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        if event_time >= cutoff:
            filtered.append(e)
    return filtered


def _percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    sorted_values = sorted(values)
    idx = int(len(sorted_values) * pct / 100)
    idx = min(idx, len(sorted_values) - 1)
    return sorted_values[idx]


def summarize(
    events: list[dict[str, Any]],
    top: int = 10,
    since_days: int | None = None,
) -> dict[str, Any]:
    """Aggregate events into a summary dict."""
    events = _filter_since(events, since_days)

    event_counts: Counter[str] = Counter()
    hook_durations: dict[str, list[int]] = defaultdict(list)
    rule_hits: Counter[str] = Counter()
    pre_write_decisions: Counter[str] = Counter()
    subagent_completions: Counter[str] = Counter()
    session_denials: Counter[str] = Counter()
    write_failures = 0
    phase_transitions = 0
    approval_matches = 0

    for e in events:
        evt = e.get("event", "unknown")
        event_counts[evt] += 1

        if evt == "hook_execution":
            name = e.get("hook_name")
            dur = e.get("duration_ms")
            if name and isinstance(dur, (int, float)):
                hook_durations[name].append(int(dur))
        elif evt == "rag_query":
            for rid in e.get("rule_ids", []):
                rule_hits[rid] += 1

        single_rid = e.get("rule_id")
        if single_rid and evt != "rag_query":
            rule_hits[single_rid] += 1
        elif evt == "pre_write_decision":
            decision = e.get("decision", "unknown")
            pre_write_decisions[decision] += 1
        elif evt == "subagent_complete":
            agent_type = e.get("agent_type") or "general-purpose"
            subagent_completions[agent_type] += 1
        elif evt == "gate_denial":
            sess = e.get("session", "unknown")
            session_denials[sess] += 1
        elif evt == "write_failure":
            write_failures += 1
        elif evt == "phase_transition":
            phase_transitions += 1
        elif evt == "approval_pattern_match":
            approval_matches += 1

    hook_p95: dict[str, int] = {
        name: _percentile(durs, 95) for name, durs in hook_durations.items()
    }

    return {
        "total_events": len(events),
        "event_counts": dict(event_counts.most_common(top)),
        "hook_p95_ms": dict(sorted(hook_p95.items(), key=lambda kv: -kv[1])[:top]),
        "top_rules": dict(rule_hits.most_common(top)),
        "pre_write_decisions": dict(pre_write_decisions),
        "subagent_completions": dict(subagent_completions),
        "sessions_with_denials": dict(session_denials.most_common(top)),
        "write_failures": write_failures,
        "phase_transitions": phase_transitions,
        "approval_matches": approval_matches,
    }


def format_report(summary: dict[str, Any]) -> str:
    """Render the summary dict as a human-readable report."""
    lines: list[str] = []
    lines.append(f"Writ friction report ({summary['total_events']} events)")
    lines.append("=" * 60)
    lines.append("")

    if summary["event_counts"]:
        lines.append("Event breakdown:")
        for name, count in summary["event_counts"].items():
            lines.append(f"  {name:30s} {count:>6d}")
        lines.append("")

    if summary["hook_p95_ms"]:
        lines.append("Hook latency p95 (top slowest):")
        for name, ms in summary["hook_p95_ms"].items():
            lines.append(f"  {name:30s} {ms:>5d} ms")
        lines.append("")

    if summary["top_rules"]:
        lines.append("Top rules injected:")
        for rid, count in summary["top_rules"].items():
            lines.append(f"  {rid:20s} {count:>4d}x")
        lines.append("")

    if summary["pre_write_decisions"]:
        lines.append("Pre-write decisions:")
        for decision, count in summary["pre_write_decisions"].items():
            lines.append(f"  {decision:15s} {count:>4d}")
        lines.append("")

    if summary["subagent_completions"]:
        lines.append("Sub-agent completions:")
        for agent_type, count in summary["subagent_completions"].items():
            lines.append(f"  {agent_type:30s} {count:>3d}")
        lines.append("")

    lines.append("Gate activity:")
    lines.append(f"  approval_pattern_match {summary['approval_matches']:>5d}")
    lines.append(f"  phase_transitions      {summary['phase_transitions']:>5d}")
    lines.append(f"  write_failures         {summary['write_failures']:>5d}")
    if summary["sessions_with_denials"]:
        lines.append("  sessions with gate denials:")
        for sess, count in summary["sessions_with_denials"].items():
            lines.append(f"    {sess}  ({count})")

    return "\n".join(lines) + "\n"


def rotate_if_needed(
    log_path: Path,
    threshold_bytes: int = DEFAULT_ROTATION_THRESHOLD_BYTES,
) -> bool:
    """Rotate the log if it exceeds the size threshold."""
    if not log_path.exists():
        return False
    if log_path.stat().st_size < threshold_bytes:
        return False
    rotated = log_path.with_suffix(log_path.suffix + ".1")
    if rotated.exists():
        rotated.unlink()
    os.rename(str(log_path), str(rotated))
    log_path.touch()
    return True


# ============================================================================
# Phase 5: result models + analyzer functions
# ============================================================================


class RuleEffectivenessRow(BaseModel):
    rule_id: str
    activations: int
    stuck_denials: int
    denial_stick_rate: float
    rationalizations: int


class SkillUsageRow(BaseModel):
    skill_id: str
    loads: int
    completions: int
    completion_rate: float


class PlaybookComplianceRow(BaseModel):
    playbook_id: str
    runs: int
    compliant_runs: int
    common_skip_points: list[str]


class GraduationCandidate(BaseModel):
    rule_id: str
    days_stable: int
    current_tier: str
    recommended_tier: str
    denial_stick_rate: float


class TrimCandidate(BaseModel):
    entity_id: str
    entity_type: str  # "rule" or "skill"
    last_activation: str | None
    activations_in_window: int
    recommendation: str


class QualityJudgeOverride(BaseModel):
    rubric: str
    total_fails: int
    overrides: int
    override_rate: float


# --- Helpers shared across analyzers ----------------------------------------


def _parse_ts(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _within_window(
    events: Iterable[FrictionEvent], since_days: int
) -> list[FrictionEvent]:
    if since_days <= 0:
        return list(events)
    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    out: list[FrictionEvent] = []
    for e in events:
        t = _parse_ts(e.ts)
        if t is None:
            continue
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        if t >= cutoff:
            out.append(e)
    return out


def _session_grouped(
    events: Iterable[FrictionEvent],
) -> dict[str, list[FrictionEvent]]:
    grouped: dict[str, list[FrictionEvent]] = defaultdict(list)
    for e in events:
        grouped[e.session].append(e)
    for sid in grouped:
        grouped[sid].sort(key=lambda e: e.ts)
    return dict(grouped)


def _extract_rule_ids(payload: dict[str, Any]) -> list[str]:
    """Pull rule_ids out of a rag_query bundle, single rule_id, or empty."""
    rule_ids = payload.get("rule_ids")
    if isinstance(rule_ids, list):
        return [r for r in rule_ids if isinstance(r, str)]
    rid = payload.get("rule_id")
    return [rid] if isinstance(rid, str) else []


def _ev_field(ev: FrictionEvent, key: str) -> Any:
    """Read a field from a FrictionEvent (declared or extra)."""
    return ev.model_dump().get(key)


# --- Analyzer 1: rule effectiveness -----------------------------------------

_STUCK_WINDOW = timedelta(minutes=30)


def analyze_rule_effectiveness(
    events: list[FrictionEvent],
    since_days: int = 30,
    top: int = 50,
) -> list[RuleEffectivenessRow]:
    """Per rule: activations, stuck denials, denial-stick-rate, rationalizations.

    A gate_denial is "stuck" if no approval_pattern_match or
    phase_advance for the same rule appears in the same session within
    30 minutes after it.
    """
    events = _within_window(events, since_days)
    grouped = _session_grouped(events)

    activations: Counter[str] = Counter()
    stuck: Counter[str] = Counter()
    rationalizations: Counter[str] = Counter()

    for sid, ses_events in grouped.items():
        for i, e in enumerate(ses_events):
            payload = e.model_dump()
            if e.event == "rag_query":
                for rid in _extract_rule_ids(payload):
                    activations[rid] += 1
            elif e.event == "gate_denial" and e.rule_id:
                # Look ahead within session for an unsticking event.
                t0 = _parse_ts(e.ts)
                if t0 is None:
                    continue
                resolved = False
                for nxt in ses_events[i + 1:]:
                    t = _parse_ts(nxt.ts)
                    if t is None or (t - t0) > _STUCK_WINDOW:
                        break
                    if (
                        nxt.event in ("approval_pattern_match", "phase_advance")
                        and (nxt.rule_id == e.rule_id or _ev_field(nxt, "gate") == _ev_field(e, "gate"))
                    ):
                        resolved = True
                        break
                if not resolved:
                    stuck[e.rule_id] += 1
                # Single-rule denials count toward activations even without rag_query.
                activations[e.rule_id] += 0
            elif e.event == "repeated_denial" and e.rule_id:
                rationalizations[e.rule_id] += 1

    rows: list[RuleEffectivenessRow] = []
    all_rules = set(activations) | set(stuck) | set(rationalizations)
    for rid in all_rules:
        a = activations.get(rid, 0)
        s = stuck.get(rid, 0)
        rate = (s / a) if a > 0 else 0.0
        rows.append(RuleEffectivenessRow(
            rule_id=rid,
            activations=a,
            stuck_denials=s,
            denial_stick_rate=rate,
            rationalizations=rationalizations.get(rid, 0),
        ))
    rows.sort(key=lambda r: (-r.stuck_denials, -r.activations, r.rule_id))
    return rows[:top]


# --- Analyzer 2: skill usage -------------------------------------------------


def analyze_skill_usage(
    events: list[FrictionEvent],
    since_days: int = 60,
    top: int = 50,
) -> list[SkillUsageRow]:
    """Per skill: loads vs sessions where the relevant playbook completed.

    Skill load = rag_query event with skill_id or a SKL-* rule_id.
    Completion = same session also has a playbook_step_complete event
    where step_index + 1 == total_steps.
    """
    events = _within_window(events, since_days)
    grouped = _session_grouped(events)

    skill_sessions: dict[str, set[str]] = defaultdict(set)
    completed_sessions: set[str] = set()

    for sid, ses_events in grouped.items():
        for e in ses_events:
            payload = e.model_dump()
            if e.event == "rag_query":
                skill = payload.get("skill_id")
                if isinstance(skill, str):
                    skill_sessions[skill].add(sid)
                # Treat any SKL-* rule_id as a skill load.
                for rid in _extract_rule_ids(payload):
                    if rid.startswith("SKL-"):
                        skill_sessions[rid].add(sid)
            elif e.event == "playbook_step_complete":
                idx = payload.get("step_index")
                total = payload.get("total_steps")
                if isinstance(idx, int) and isinstance(total, int) and idx + 1 >= total:
                    completed_sessions.add(sid)

    rows: list[SkillUsageRow] = []
    for skill, sessions in skill_sessions.items():
        loads = len(sessions)
        completions = len(sessions & completed_sessions)
        rate = (completions / loads) if loads > 0 else 0.0
        rows.append(SkillUsageRow(
            skill_id=skill,
            loads=loads,
            completions=completions,
            completion_rate=rate,
        ))
    rows.sort(key=lambda r: (-r.loads, r.skill_id))
    return rows[:top]


# --- Analyzer 3: playbook compliance ----------------------------------------


def analyze_playbook_compliance(
    events: list[FrictionEvent],
    since_days: int = 30,
    top: int = 50,
) -> list[PlaybookComplianceRow]:
    """Per playbook: runs, compliant runs (in-order, no skipped indices),
    plus the most common skip-point step_ids across all non-compliant
    runs.
    """
    events = _within_window(events, since_days)
    grouped = _session_grouped(events)

    runs_by_pb: dict[str, list[list[FrictionEvent]]] = defaultdict(list)
    for sid, ses_events in grouped.items():
        # Group consecutive playbook_step_complete events by playbook_id.
        per_pb: dict[str, list[FrictionEvent]] = defaultdict(list)
        for e in ses_events:
            if e.event != "playbook_step_complete":
                continue
            pb = _ev_field(e, "playbook_id")
            if isinstance(pb, str):
                per_pb[pb].append(e)
        for pb, evs in per_pb.items():
            if evs:
                runs_by_pb[pb].append(evs)

    rows: list[PlaybookComplianceRow] = []
    for pb, runs in runs_by_pb.items():
        compliant = 0
        # A "skip point" is the step_id of an out-of-place observation in
        # a non-compliant run -- either a step that came before its
        # expected predecessor, or a step that appeared with a higher
        # index than the run's prefix supports.
        skip_points: Counter[str] = Counter()
        for run in runs:
            pairs: list[tuple[int, str]] = []
            for e in run:
                idx = _ev_field(e, "step_index")
                sid = _ev_field(e, "step_id")
                if isinstance(idx, int) and isinstance(sid, str):
                    pairs.append((idx, sid))
            if not pairs:
                continue
            indices = [p[0] for p in pairs]
            in_order = (
                bool(indices)
                and indices == list(range(indices[0], indices[0] + len(indices)))
            )
            total_known = _ev_field(run[-1], "total_steps")
            reached_end = (
                not isinstance(total_known, int)
                or max(indices) >= total_known - 1
            )
            if in_order and reached_end:
                compliant += 1
                continue
            # Non-compliant: surface the step_ids that broke the sequence.
            # Any step whose index doesn't equal its position in the run
            # was observed out of order.
            for position, (idx, sid) in enumerate(pairs):
                if idx != position:
                    skip_points[sid] += 1

        rows.append(PlaybookComplianceRow(
            playbook_id=pb,
            runs=len(runs),
            compliant_runs=compliant,
            common_skip_points=[sid for sid, _ in skip_points.most_common(5)],
        ))
    rows.sort(key=lambda r: (-r.runs, r.playbook_id))
    return rows[:top]


# --- Analyzer 4: graduation candidates --------------------------------------


def analyze_graduation_candidates(
    events: list[FrictionEvent],
    days_stable: int = 30,
    stick_rate_threshold: float = 0.85,
    max_rationalizations: int = 5,
    top: int = 50,
) -> list[GraduationCandidate]:
    """Rules with high stuck-denial rate and low rationalization count.

    days_stable is reported on the row for the human reviewer's context;
    selection itself runs on all events to capture cumulative stability.
    A rule qualifies if denial_stick_rate >= stick_rate_threshold and
    rationalizations < max_rationalizations.
    """
    rows = analyze_rule_effectiveness(events, since_days=0, top=10_000)
    candidates: list[GraduationCandidate] = []
    for r in rows:
        if r.activations < 5:
            continue
        if r.denial_stick_rate < stick_rate_threshold:
            continue
        if r.rationalizations >= max_rationalizations:
            continue
        candidates.append(GraduationCandidate(
            rule_id=r.rule_id,
            days_stable=days_stable,
            current_tier="probationary",
            recommended_tier="canonical",
            denial_stick_rate=r.denial_stick_rate,
        ))
    candidates.sort(key=lambda c: (-c.denial_stick_rate, c.rule_id))
    return candidates[:top]


# --- Analyzer 5: trim candidates --------------------------------------------


def analyze_trim_candidates(
    events: list[FrictionEvent],
    since_days: int = 90,
    rule_min_activations: int = 5,
    skill_min_loads: int = 2,
    top: int = 100,
) -> list[TrimCandidate]:
    """Rules with <N activations in window; skills with <M loads in window.

    Scans the FULL log to identify every rule / skill the system has
    ever seen, then counts activations within the window. Entities
    that fall below threshold (including those with zero recent
    activity) are flagged.
    """
    universe_rules: set[str] = set()
    universe_skills: set[str] = set()
    last_seen: dict[str, str] = {}
    for e in events:
        payload = e.model_dump()
        for rid in _extract_rule_ids(payload):
            if rid.startswith("SKL-"):
                universe_skills.add(rid)
            else:
                universe_rules.add(rid)
            last_seen[rid] = max(e.ts, last_seen.get(rid, ""))
        if e.rule_id:
            if e.rule_id.startswith("SKL-"):
                universe_skills.add(e.rule_id)
            else:
                universe_rules.add(e.rule_id)
            last_seen[e.rule_id] = max(e.ts, last_seen.get(e.rule_id, ""))
        skill = payload.get("skill_id")
        if isinstance(skill, str):
            universe_skills.add(skill)
            last_seen[skill] = max(e.ts, last_seen.get(skill, ""))

    events = _within_window(events, since_days)

    rule_acts: Counter[str] = Counter()
    rule_denials: Counter[str] = Counter()
    rule_last_seen: dict[str, str] = dict(last_seen)
    skill_loads: Counter[str] = Counter()
    skill_last_seen: dict[str, str] = dict(last_seen)

    for e in events:
        payload = e.model_dump()
        if e.event == "rag_query":
            for rid in _extract_rule_ids(payload):
                rule_acts[rid] += 1
                rule_last_seen[rid] = e.ts
                if rid.startswith("SKL-"):
                    skill_loads[rid] += 1
                    skill_last_seen[rid] = e.ts
            skill = payload.get("skill_id")
            if isinstance(skill, str):
                skill_loads[skill] += 1
                skill_last_seen[skill] = e.ts
        elif e.event == "gate_denial" and e.rule_id:
            rule_denials[e.rule_id] += 1
            rule_last_seen[e.rule_id] = e.ts

    candidates: list[TrimCandidate] = []
    for rid in universe_rules:
        if rule_acts[rid] < rule_min_activations and rule_denials[rid] == 0:
            candidates.append(TrimCandidate(
                entity_id=rid,
                entity_type="rule",
                last_activation=rule_last_seen.get(rid),
                activations_in_window=rule_acts[rid],
                recommendation="trim or consolidate",
            ))

    for skill in universe_skills:
        loads = skill_loads.get(skill, 0)
        if loads < skill_min_loads:
            candidates.append(TrimCandidate(
                entity_id=skill,
                entity_type="skill",
                last_activation=skill_last_seen.get(skill),
                activations_in_window=loads,
                recommendation="deprecate",
            ))

    candidates.sort(key=lambda c: (c.activations_in_window, c.entity_id))
    return candidates[:top]


# --- Analyzer 6: quality-judge false positives ------------------------------


def analyze_quality_judge_false_positives(
    events: list[FrictionEvent],
    since_days: int = 30,
    top: int = 50,
) -> list[QualityJudgeOverride]:
    """Per rubric: total fail judgments + override count + rate.

    Override = the user proceeded despite the judge saying fail.
    A high override rate suggests the rubric is too strict (false
    positive) and needs refinement.
    """
    events = _within_window(events, since_days)

    fails: Counter[str] = Counter()
    overrides: Counter[str] = Counter()

    for e in events:
        if e.event != "quality_judgment":
            continue
        payload = e.model_dump()
        if payload.get("decision") != "fail":
            continue
        rubric = payload.get("rubric", "unknown")
        if not isinstance(rubric, str):
            rubric = "unknown"
        fails[rubric] += 1
        if payload.get("override"):
            overrides[rubric] += 1

    rows: list[QualityJudgeOverride] = []
    for rubric, total in fails.items():
        ovr = overrides[rubric]
        rate = ovr / total if total > 0 else 0.0
        rows.append(QualityJudgeOverride(
            rubric=rubric,
            total_fails=total,
            overrides=ovr,
            override_rate=rate,
        ))
    rows.sort(key=lambda r: (-r.override_rate, -r.total_fails, r.rubric))
    return rows[:top]
