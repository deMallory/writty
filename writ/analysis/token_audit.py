"""P0: the FOOTPRINT observer (WRIT-TOKEN-BLUEPRINT.md).

Measures Writ's token FOOTPRINT per session, in COST units, from a Claude Code transcript jsonl.
This is the DENOMINATOR instrument: passive, exact on cost. It is SILENT on trajectory/efficacy
(the numerator) -- that is the separate P0.5 A/B harness. Do not ask it to rank an
efficacy-affecting change.

The MEASURED denominator needs no tokenizer: the transcript's per-turn usage fields are real token
counts from the API. Only the ATTRIBUTED numerator (Writ's share) is an estimate, and it is labeled
as such. A schema canary fails loud rather than emit a number on an unverified schema.
"""
from __future__ import annotations

import json

from writ.analysis.jsonl import read_jsonl

# input-equivalent weights relative to base input = 1.0 (verified Opus 4.x + Sonnet ratios).
COST_WEIGHTS = {
    "input": 1.0,
    "cache_read": 0.1,
    "cache_write_5m": 1.25,
    "cache_write_1h": 2.0,
    "output": 5.0,
}
# Base-input USD per MTok (output etc. derived via the weights above).
INPUT_USD_PER_MTOK = {
    "claude-opus-4-8": 5.0, "claude-opus-4-7": 5.0, "claude-opus-4-6": 5.0,
    "claude-sonnet-4-6": 3.0, "claude-haiku-4-5": 1.0, "claude-fable-5": 10.0,
}

_REQUIRED_USAGE = (
    "input_tokens", "output_tokens",
    "cache_read_input_tokens", "cache_creation_input_tokens",
)


class TokenAuditSchemaError(Exception):
    """The CC transcript usage schema did not match expectations. Raised by the canary so a
    drifted schema fails loud instead of silently corrupting the denominator."""


def assert_usage_schema(usages: list[dict]) -> None:
    """Fail loud if the reverse-engineered CC usage schema drifted. A wrong denominator silently
    corrupts every downstream gate, so refuse rather than guess."""
    if not usages:
        raise TokenAuditSchemaError(
            "no assistant-turn usage records found in transcript -- cannot establish a denominator"
        )
    for i, u in enumerate(usages):
        missing = [f for f in _REQUIRED_USAGE if f not in u]
        if missing:
            raise TokenAuditSchemaError(
                f"usage record {i} missing field(s) {missing}; the CC transcript schema may have "
                f"changed. Refusing to emit a scorecard on an unverified schema."
            )


def _split_cache_creation(usage: dict) -> tuple[int, int]:
    """(5m, 1h) cache-creation tokens. When CC provides the ephemeral split, use it; otherwise
    treat the whole cache_creation total as 5m -- the cheaper weight, conservative against
    overstating cost."""
    cc = usage.get("cache_creation")
    if isinstance(cc, dict):
        c5 = cc.get("ephemeral_5m_input_tokens", 0) or 0
        c1 = cc.get("ephemeral_1h_input_tokens", 0) or 0
        if c5 or c1:
            return c5, c1
    return (usage.get("cache_creation_input_tokens", 0) or 0), 0


def weighted_cost(usage: dict) -> float:
    """Input-equivalent cost of one turn, per COST_WEIGHTS."""
    c5, c1 = _split_cache_creation(usage)
    return (
        (usage.get("input_tokens", 0) or 0) * COST_WEIGHTS["input"]
        + (usage.get("cache_read_input_tokens", 0) or 0) * COST_WEIGHTS["cache_read"]
        + c5 * COST_WEIGHTS["cache_write_5m"]
        + c1 * COST_WEIGHTS["cache_write_1h"]
        + (usage.get("output_tokens", 0) or 0) * COST_WEIGHTS["output"]
    )


def parse_turns(transcript_path: str) -> list[dict]:
    """Per-assistant-turn usage dicts from a CC transcript jsonl (the four token fields + any
    cache_creation split + model). Non-assistant / usage-less lines are skipped."""
    turns: list[dict] = []
    for ev in read_jsonl(transcript_path, errors="ignore"):
        if ev.get("type") != "assistant":
            continue
        msg = ev.get("message") or {}
        usage = msg.get("usage")
        if not isinstance(usage, dict):
            continue
        u = dict(usage)
        u["_model"] = msg.get("model", "")
        turns.append(u)
    return turns


def _detect_cc_version(transcript_path: str) -> str:
    """First `version` field seen on any transcript line (the CC version this schema came from);
    'unknown' if absent. Pinned in the scorecard so a silent CC change is at least visible."""
    for ev in read_jsonl(transcript_path, errors="ignore"):
        v = ev.get("version")
        if v:
            return str(v)
    return "unknown"


def compounding_curve(turns: list[dict]) -> list[float]:
    """Cumulative cache_read cost per turn index -- the super-linear re-read the plan targets.
    A flat-then-steep curve is the compounding signature; a fix should bend it down."""
    out: list[float] = []
    run = 0.0
    for u in turns:
        run += (u.get("cache_read_input_tokens", 0) or 0) * COST_WEIGHTS["cache_read"]
        out.append(run)
    return out


def segment_lengths(turns: list[dict]) -> list[int]:
    """Compaction segments, by turn count. A compaction resets the cached prefix, so cache_read
    drops sharply on the post-compaction turn; a drop below half the prior turn's cache_read marks
    a boundary. The re-read tax accrues WITHIN a segment and resets at each boundary -- so reread
    must be summed per-segment, never as one whole-session triangular (the P0 attribution bug)."""
    reads = [u.get("cache_read_input_tokens", 0) or 0 for u in turns]
    if not reads:
        return []
    lengths: list[int] = []
    cur = 1
    for i in range(1, len(reads)):
        if reads[i] < reads[i - 1] * 0.5:  # sharp drop = compaction reset
            lengths.append(cur)
            cur = 1
        else:
            cur += 1
    lengths.append(cur)
    return lengths


def attribute_writ(friction_events: list[dict], n_turns: int | None = None,
                   segments: list[int] | None = None,
                   cache_read_cost_cap: float | None = None) -> dict:
    """Writ's injected share -- an ATTRIBUTED ESTIMATE, never ground truth (four injectors share a
    turn). Uses a real per-string count when an event carries 'tokens_real'; otherwise the logged
    `tokens`/`tokens_injected` (a bytes/4-class estimate) and basis='estimate'.

    injected_write_cost  = injected tokens cache-written once (5m weight).
    injected_reread_cost = an UPPER BOUND on Writ's slice of the re-read tax. Computed ONLY when
    compaction `segments` are supplied (the re-read needs turn structure): a PER-SEGMENT triangular
    (not whole-session -- that was the P0 bug that produced a reread larger than the whole bill),
    then HARD-CLAMPED to the measured cache_read cost, since Writ's re-read is physically a portion
    of the total re-read and can never exceed it. Without segments it is 0.0 (not estimable here).
    The precise version (per-turn count of duplicate Writ blocks still resident) is a documented
    TODO; this is a clamped upper bound, labeled as such."""
    inject = [e for e in friction_events
              if e.get("event") in ("rag_query", "always_on_inject")]
    basis = "real" if inject and all("tokens_real" in e for e in inject) else "estimate"
    total_tokens = 0
    for e in inject:
        if "tokens_real" in e:
            total_tokens += int(e.get("tokens_real") or 0)
        else:
            total_tokens += int(e.get("tokens_injected", e.get("tokens", 0)) or 0)
    write_cost = total_tokens * COST_WEIGHTS["cache_write_5m"]

    reread_cost = 0.0
    reread_basis = "not-estimated (no segment structure)"
    if segments and n_turns and n_turns > 0:
        per_turn = total_tokens / n_turns
        raw_tokens = sum(per_turn * (L * (L - 1) / 2) for L in segments)  # per-segment triangular
        reread_cost = raw_tokens * COST_WEIGHTS["cache_read"]
        reread_basis = "upper_bound_per_segment"
        if cache_read_cost_cap is not None and reread_cost > cache_read_cost_cap:
            reread_cost = cache_read_cost_cap  # numerator cannot exceed the measured denominator
            reread_basis = "upper_bound_clamped_to_measured"
    return {
        "injected_tokens": total_tokens,
        "injected_write_cost": write_cost,
        "injected_reread_cost": reread_cost,
        "reread_basis": reread_basis,
        "basis": basis,
    }


def attribute_prevented(friction_events: list[dict]) -> dict:
    """Sum read_blocked prevented-token FLOORS into a cost floor at the cache_read weight (0.1x,
    the smallest -- understates by construction). A SEPARATE block from attribute_writ: its basis is
    a shell bytes/4 estimate, not injection telemetry, and must stay labeled as a floor."""
    blocked = [e for e in friction_events if e.get("event") == "read_blocked"]
    tokens_floor = sum(int(e.get("prevented_tokens_floor", 0) or 0) for e in blocked)
    gross_bytes = sum(int(e.get("gross_bytes_upper_bound", 0) or 0) for e in blocked)
    return {
        "prevented_cost_floor": tokens_floor * COST_WEIGHTS["cache_read"],
        "prevented_tokens_floor": tokens_floor,
        "gross_blocked_bytes": gross_bytes,
        "blocked_count": len(blocked),
        "basis": "bytes/4_floor*cache_read",
    }


def _read_friction(friction_path: str | None) -> list[dict]:
    if not friction_path:
        return []
    try:
        return list(read_jsonl(friction_path, errors="ignore"))
    except OSError:
        return []


def _coverage(friction_events: list[dict]) -> dict:
    """Advisory coverage floor read. reach is the clean proxy; gate_stick is CONFOUNDED
    (learned-helplessness: 'not overridden' != 'gate was right') -- labeled, not trusted."""
    rag = sum(1 for e in friction_events if e.get("event") == "rag_query")
    denials = [e for e in friction_events if e.get("event") == "gate_denial"]
    stuck = sum(1 for e in denials if not e.get("overridden"))
    return {
        "reach_rag_query_events": rag,
        "gate_denials": len(denials),
        "gate_stick_count": stuck,
        "gate_stick_confounded": True,  # needs override-latency / audit before it is trustworthy
    }


def scorecard(transcript_path: str, friction_path: str | None, model: str) -> dict:
    """Per-session FOOTPRINT scorecard. Runs the schema canary FIRST -- refuses on drift."""
    turns = parse_turns(transcript_path)
    assert_usage_schema(turns)  # fail loud before computing anything

    read_cost = sum((u.get("cache_read_input_tokens", 0) or 0) * COST_WEIGHTS["cache_read"]
                    for u in turns)
    out_cost = sum((u.get("output_tokens", 0) or 0) * COST_WEIGHTS["output"] for u in turns)
    inp_cost = sum((u.get("input_tokens", 0) or 0) * COST_WEIGHTS["input"] for u in turns)
    write_cost = sum(weighted_cost(u) for u in turns) - read_cost - out_cost - inp_cost
    total = read_cost + out_cost + inp_cost + write_cost

    usd = INPUT_USD_PER_MTOK.get(model)
    friction = _read_friction(friction_path)
    attributed = attribute_writ(
        friction, n_turns=len(turns),
        segments=segment_lengths(turns), cache_read_cost_cap=read_cost,
    )
    prevented = attribute_prevented(friction)
    # net_cost: a floor-CREDITED estimate -- Writ's injected cost minus the (understated,
    # cache_read-weighted) prevented-read floor. Both terms are estimates, not ground truth.
    attributed["net_cost"] = (
        attributed["injected_write_cost"]
        + attributed["injected_reread_cost"]
        - prevented["prevented_cost_floor"]
    )
    return {
        "model": model,
        "cc_version": _detect_cc_version(transcript_path),
        "turns": len(turns),
        "measured": {
            "input_cost": inp_cost,
            "cache_read_cost": read_cost,
            "cache_write_cost": write_cost,
            "output_cost": out_cost,
            "total_cost": total,
            "total_usd": (total / 1_000_000 * usd) if usd else None,
        },
        "attributed": attributed,
        "prevented": prevented,
        "segments": segment_lengths(turns),
        "compounding_curve": compounding_curve(turns),
        "coverage": _coverage(friction),
    }


def render_json(card: dict) -> str:
    return json.dumps(card, indent=2)


def render_text(card: dict) -> str:
    m = card["measured"]
    a = card["attributed"]
    cv = card["compounding_curve"]
    lines = [
        f"=== Writ FOOTPRINT scorecard (denominator only; silent on efficacy) ===",
        f"model={card['model']}  cc_version={card['cc_version']}  turns={card['turns']}",
        f"-- MEASURED cost (input-equivalent tokens; ground truth from the API) --",
        f"  input        {m['input_cost']:>14,.0f}",
        f"  cache_read   {m['cache_read_cost']:>14,.0f}   <- the recurring/compounding tax",
        f"  cache_write  {m['cache_write_cost']:>14,.0f}",
        f"  output       {m['output_cost']:>14,.0f}   (5x, never cached)",
        f"  TOTAL        {m['total_cost']:>14,.0f}"
        + (f"   (~${m['total_usd']:,.2f})" if m["total_usd"] is not None else ""),
        f"-- ATTRIBUTED to Writ (ESTIMATE, basis={a['basis']}; not ground truth) --",
        f"  injected~{a['injected_tokens']:,} tok  write~{a['injected_write_cost']:,.0f}"
        f"  reread~{a['injected_reread_cost']:,.0f} ({a['reread_basis']})",
        f"  segments={len(card.get('segments') or [])} (compaction boundaries)",
        f"-- compounding curve (cumulative cache_read cost): "
        f"start={cv[0]:,.0f} end={cv[-1]:,.0f}" if cv else "-- compounding curve: (none)",
        f"-- coverage (advisory): reach_rag={card['coverage'].get('reach_rag_query_events')} "
        f"gate_stick={card['coverage'].get('gate_stick_count')} (CONFOUNDED)",
    ]
    p = card.get("prevented", {})
    lines.append("-- PREVENTED (floor; read_blocked events) --")
    lines.append(f"  prevented_cost_floor = {p.get('prevented_cost_floor', 0):,.0f}  (input-equiv, cache_read-weighted)")
    lines.append(f"  blocked_count        = {p.get('blocked_count', 0)}")
    lines.append(f"  gross_blocked_bytes  = {p.get('gross_blocked_bytes', 0):,}  (GROSS BYTES, not a token count)")
    return "\n".join(lines)
