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
import os
import re
from pathlib import Path

from writ.analysis import token_tree
from writ.analysis.jsonl import read_jsonl

# input-equivalent weights relative to base input = 1.0 (verified Opus 4.x + Sonnet ratios).
COST_WEIGHTS = {
    "input": 1.0,
    "cache_read": 0.1,
    "cache_write_5m": 1.25,
    "cache_write_1h": 2.0,
    "output": 5.0,
}

# USD per MTok per model (Anthropic first-party), one rate per billed token category. Every
# response is priced by the model that incurred it. "<synthetic>" (CC-internal, never billed)
# prices at zero and is never reported as unpriced.
TOKEN_CATEGORIES = ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h")


def _rates(inp: float, out: float, read: float, w5: float, w1: float) -> dict[str, float]:
    return dict(zip(TOKEN_CATEGORIES, (inp, out, read, w5, w1)))


RATE_CARD: dict[str, dict[str, float]] = {
    "claude-opus-5-5": _rates(4.00, 20.00, 0.20, 5.00, 8.00),
    "claude-sonnet-5-5": _rates(2.00, 10.00, 0.20, 2.50, 4.00),
    "claude-opus-5": _rates(5.00, 25.00, 0.50, 6.25, 10.00),
    "claude-sonnet-5": _rates(2.00, 10.00, 0.20, 2.50, 4.00),
    "claude-opus-4-8": _rates(5.00, 25.00, 0.50, 6.25, 10.00),
    "claude-opus-4-7": _rates(5.00, 25.00, 0.50, 6.25, 10.00),
    "claude-opus-4-6": _rates(5.00, 25.00, 0.50, 6.25, 10.00),
    "claude-sonnet-4-6": _rates(3.00, 15.00, 0.30, 3.75, 6.00),
    "claude-haiku-4-5": _rates(1.00, 5.00, 0.10, 1.25, 2.00),
    "claude-fable-5-1": _rates(10.00, 50.00, 0.25, 12.50, 20.00),
    "claude-fable-5": _rates(10.00, 50.00, 1.00, 12.50, 20.00),
    "<synthetic>": _rates(0.0, 0.0, 0.0, 0.0, 0.0),
}
# Base-input USD per MTok, derived from the rate card (kept for importers).
INPUT_USD_PER_MTOK = {m: r["input"] for m, r in RATE_CARD.items() if m != "<synthetic>"}

NO_MODEL = "<none>"  # model_usage / unpriced key for responses whose record carries no model

_DATED_MODEL = re.compile(r"^(.+)-\d{8}$")

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


def normalize_model(raw: str | None) -> str | None:
    """RATE_CARD key for a raw model id: the exact key, or the base of a trailing -YYYYMMDD
    date suffix when that base is an exact key. No prefix or fuzzy matching; else None."""
    if not isinstance(raw, str) or not raw:
        return None
    if raw in RATE_CARD:
        return raw
    m = _DATED_MODEL.match(raw)
    if m and m.group(1) in RATE_CARD:
        return m.group(1)
    return None


def usage_tokens(usage: dict) -> dict[str, int]:
    """The five billed token categories of one response's usage (5m/1h cache-write split
    via _split_cache_creation)."""
    c5, c1 = _split_cache_creation(usage)
    return {
        "input": usage.get("input_tokens", 0) or 0,
        "output": usage.get("output_tokens", 0) or 0,
        "cache_read": usage.get("cache_read_input_tokens", 0) or 0,
        "cache_write_5m": c5,
        "cache_write_1h": c1,
    }


def price_tokens(tokens: dict, model_key: str) -> float:
    """USD for a token-category mapping at one RATE_CARD model's rates."""
    if model_key not in RATE_CARD:
        raise KeyError(f"model {model_key!r} is not a RATE_CARD key; normalize_model first")
    rates = RATE_CARD[model_key]
    return sum((tokens.get(c, 0) or 0) * rates[c] for c in TOKEN_CATEGORIES) / 1_000_000


def price_response(usage: dict, model_key: str) -> float:
    """USD for one API response's usage, priced by the model that incurred it."""
    return price_tokens(usage_tokens(usage), model_key)


def _record_model(msg: dict) -> str | None:
    model = msg.get("model")
    return model if isinstance(model, str) and model else None


def _non_output_fields(usage: dict) -> tuple:
    cc = usage.get("cache_creation")
    cc = cc if isinstance(cc, dict) else {}
    return (usage.get("input_tokens"), usage.get("cache_read_input_tokens"),
            usage.get("cache_creation_input_tokens"),
            cc.get("ephemeral_5m_input_tokens"), cc.get("ephemeral_1h_input_tokens"))


def _classify_repeats(history: list[tuple[dict, str | None]]) -> str:
    """Classify the records of one message.id: "identical", "streaming" (same model, same
    non-output fields, output_tokens non-decreasing with at least one increase) or
    "conflict"."""
    first_usage, first_model = history[0]
    if all(u == first_usage and m == first_model for u, m in history[1:]):
        return "identical"
    if any(m != first_model for _, m in history[1:]):
        return "conflict"
    base = _non_output_fields(first_usage)
    if any(_non_output_fields(u) != base for u, _ in history[1:]):
        return "conflict"
    outputs = [u.get("output_tokens") for u, _ in history]
    if not all(isinstance(o, int) and not isinstance(o, bool) for o in outputs):
        return "conflict"
    steps = list(zip(outputs, outputs[1:]))
    if all(b >= a for a, b in steps) and any(b > a for a, b in steps):
        return "streaming"
    return "conflict"


def _differing(history: list[tuple[dict, str | None]]) -> list[str]:
    first_usage, first_model = history[0]
    out = []
    if any(u != first_usage for u, _ in history[1:]):
        out.append("usage")
    if any(m != first_model for _, m in history[1:]):
        out.append("model")
    return out


def _scan_responses(path: str) -> dict:
    """One pass over a transcript: assistant usage records deduped into API responses.

    Key is message.id. Id-less records are each their own response. Repeats of an id keep
    the LAST record's usage/model at the FIRST record's position and are classified:
    identical repeats collapse silently; streaming snapshots (same model and non-output
    fields, output_tokens non-decreasing with at least one increase) are counted in
    `streaming_snapshot_updates` with no warning; anything else is a duplicate_id_conflict.
    """
    responses: list[dict] = []
    by_id: dict[str, dict] = {}
    history: dict[str, list] = {}
    records = 0
    first_ts = last_ts = None
    for ev in read_jsonl(path, errors="ignore"):
        if not isinstance(ev, dict):
            continue
        ts = ev.get("timestamp")
        if isinstance(ts, str) and ts:
            first_ts = first_ts or ts
            last_ts = ts
        if ev.get("type") != "assistant":
            continue
        msg = ev.get("message")
        if not isinstance(msg, dict) or not isinstance(msg.get("usage"), dict):
            continue
        records += 1
        usage = dict(msg["usage"])
        model = _record_model(msg)
        mid = msg.get("id")
        if not isinstance(mid, str) or not mid:
            responses.append({"message_id": None, "usage": usage, "model": model,
                              "records": 1})
            continue
        resp = by_id.get(mid)
        if resp is None:
            resp = {"message_id": mid, "usage": usage, "model": model, "records": 1}
            by_id[mid] = resp
            history[mid] = [(usage, model)]
            responses.append(resp)
            continue
        resp["records"] += 1
        history[mid].append((usage, model))
        resp["usage"] = usage
        resp["model"] = model
    conflicts = []
    streaming = 0
    for r in responses:
        h = history.get(r["message_id"]) if r["message_id"] else None
        if not h or len(h) < 2:
            continue
        kind = _classify_repeats(h)
        if kind == "streaming":
            streaming += 1
        elif kind == "conflict":
            conflicts.append({"kind": "duplicate_id_conflict", "message_id": r["message_id"],
                              "records": r["records"], "differing": _differing(h)})
    return {"responses": responses, "records": records, "conflicts": conflicts,
            "streaming_snapshot_updates": streaming,
            "first_ts": first_ts, "last_ts": last_ts}


def _turn(resp: dict) -> dict:
    u = dict(resp["usage"])
    u["_model"] = resp["model"] or ""
    return u


def parse_turns(transcript_path: str) -> list[dict]:
    """Per-API-response usage dicts from a CC transcript jsonl (the four token fields + any
    cache_creation split + model under `_model`), deduped by message.id in first-seen order.
    Non-assistant / usage-less lines are skipped."""
    return [_turn(r) for r in _scan_responses(transcript_path)["responses"]]


def _empty_bucket() -> dict[str, int]:
    return {"responses": 0, **{c: 0 for c in TOKEN_CATEGORIES}}


def _add_tokens(bucket: dict, tokens: dict, responses: int) -> None:
    bucket["responses"] += responses
    for c in TOKEN_CATEGORIES:
        bucket[c] += tokens.get(c, 0) or 0


def _model_usage(responses: list[dict]) -> dict[str, dict[str, int]]:
    """{raw model or "<none>": {responses, input, output, cache_read, cache_write_5m,
    cache_write_1h}} over deduped responses. Raw ids are kept; normalization is a pricing
    concern."""
    out: dict[str, dict[str, int]] = {}
    for r in responses:
        _add_tokens(out.setdefault(r["model"] or NO_MODEL, _empty_bucket()),
                    usage_tokens(r["usage"]), 1)
    return out


def _summarize_scan(scan: dict) -> dict:
    n = len(scan["responses"])
    return {
        "responses": n,
        "records": scan["records"],
        "duplicates_collapsed": scan["records"] - n,
        "conflicts": len(scan["conflicts"]),
        "duplicate_conflicts": len(scan["conflicts"]),
        "streaming_snapshot_updates": scan["streaming_snapshot_updates"],
        "warnings": [dict(w) for w in scan["conflicts"]],
        "model_usage": _model_usage(scan["responses"]),
        "first_ts": scan["first_ts"],
        "last_ts": scan["last_ts"],
        "child_dispatches": {},
    }


def _check_file_schema(path, responses: list[dict]) -> None:
    for i, r in enumerate(responses):
        missing = [f for f in _REQUIRED_USAGE if f not in r["usage"]]
        if missing:
            raise TokenAuditSchemaError(
                f"{path}: usage record {i} (message.id {r['message_id']!r}) missing field(s) "
                f"{missing}; the CC transcript schema may have changed. Refusing to emit a "
                f"scorecard on an unverified schema."
            )


def _file_summary(path, seen_ids: set | None = None, with_children: bool = True) -> dict:
    """aggregate_file_usage body. With `seen_ids`, responses whose message.id was already
    counted in another file of the tree are dropped (cross_file_duplicate_id warning) and the
    remaining ids are added to the set."""
    scan = _scan_responses(path)
    _check_file_schema(path, scan["responses"])
    cross: list[dict] = []
    if seen_ids is not None:
        kept = []
        for r in scan["responses"]:
            mid = r["message_id"]
            if mid is not None and mid in seen_ids:
                cross.append({"kind": "cross_file_duplicate_id", "message_id": mid,
                              "file": str(path)})
                continue
            if mid is not None:
                seen_ids.add(mid)
            kept.append(r)
        scan = {**scan, "responses": kept}
    summary = _summarize_scan(scan)
    summary["warnings"].extend(cross)
    if with_children:
        summary["child_dispatches"] = {d.dispatch_id: d.agent_id
                                       for d in token_tree.extract_dispatches(path)}
    return summary


def aggregate_file_usage(path: str) -> dict:
    """Deduped per-model token usage of one transcript file (main or subagent).

    Returns {responses, records, duplicates_collapsed, conflicts (== duplicate_conflicts),
    duplicate_conflicts, streaming_snapshot_updates, warnings, model_usage, first_ts,
    last_ts, child_dispatches}; child_dispatches maps each Agent tool_use id in the
    file to its toolUseResult.agentId (or None). A file with no usage records is valid (zero
    responses). A usage record missing a required field raises TokenAuditSchemaError; a
    missing/unreadable path raises OSError."""
    return _file_summary(path)


SUMMARY_EVENT = "subagent_usage"
SUMMARY_SCHEMA = 1
SUMMARY_NO_TRANSCRIPT = "no_transcript"
SUMMARY_ERROR = "error"
_SUMMARY_COUNTS = ("responses", "records", "duplicates_collapsed",
                   "streaming_snapshot_updates", "conflicts")


def _json_dict(path) -> dict | None:
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _summary_dispatch_id(agent_id: str, transcript_path) -> str | None:
    """The dispatching tool_use id: the transcript's sibling .meta.json toolUseId, else the
    toolUseId of the sidecar subagent_role.sidecar_path finds for agent_id, else None."""
    meta = token_tree.read_meta(transcript_path) if transcript_path else None
    if meta is None:
        from writ.session.subagent_role import sidecar_path
        found = sidecar_path(agent_id)
        meta = _json_dict(found) if found else None
    tool_use_id = (meta or {}).get("toolUseId")
    return tool_use_id if isinstance(tool_use_id, str) and tool_use_id else None


def usage_summary_event(agent_id: str, parent_session: str, transcript_path,
                        role: str | None, role_source: str | None) -> dict:
    """The durable `subagent_usage` row the SubagentStop hook appends to the metrics stream.

    Built on aggregate_file_usage, so the hook and the audit share one dedup rule. Tokens
    only, never dollars: pricing happens at audit time. status is "ok" when the transcript
    was read, "no_transcript" when there is no path or no file, and "error" (with the
    exception class name) when reading or the schema check failed."""
    row = {
        "event": SUMMARY_EVENT, "session": agent_id, "agent_id": agent_id,
        "parent_session": parent_session,
        "dispatch_id": _summary_dispatch_id(agent_id, transcript_path),
        "role": token_tree.normalize_role(role), "role_source": role_source or "unresolved",
        "status": SUMMARY_NO_TRANSCRIPT, "schema": SUMMARY_SCHEMA,
        **{k: 0 for k in _SUMMARY_COUNTS},
        "model_usage": {}, "child_dispatches": {}, "first_ts": None, "last_ts": None,
    }
    if not transcript_path or not os.path.exists(transcript_path):
        return row
    try:
        agg = aggregate_file_usage(str(transcript_path))
    except Exception as e:
        row["status"] = SUMMARY_ERROR
        row["error"] = type(e).__name__
        return row
    row.update({k: agg[k] for k in _SUMMARY_COUNTS})
    row.update({"status": token_tree.SUMMARY_OK, "model_usage": agg["model_usage"],
                "child_dispatches": agg["child_dispatches"],
                "first_ts": agg["first_ts"], "last_ts": agg["last_ts"]})
    return row


class UsageSummaries(dict):
    """{agent_id: first subagent_usage row}. `conflicts` holds one summary_conflict warning
    per agent_id whose later rows differ from its first (ts excluded)."""

    def __init__(self, session_id: str | None = None) -> None:
        super().__init__()
        self.session_id = session_id
        self.conflicts: dict[str, dict] = {}


def load_usage_summaries(session_id: str, project: str) -> UsageSummaries:
    """subagent_usage rows from the project's metrics stream, live file plus rotated archives.

    First row per agent_id wins; a later row that differs is ignored and recorded as a
    summary_conflict warning. Rows are keyed by agent_id alone (agent ids are unique), so a
    row whose parent_session is not `session_id` still matches; the audit flags that as
    summary_parent_mismatch."""
    from writ.shared.logging import read_streams
    out = UsageSummaries(session_id)
    for row in read_streams(project, ["metrics"]):
        if not isinstance(row, dict) or row.get("event") != SUMMARY_EVENT:
            continue
        agent_id = row.get("agent_id")
        if not isinstance(agent_id, str) or not agent_id:
            continue
        first = out.get(agent_id)
        if first is None:
            out[agent_id] = row
            continue
        differing = {k for k in set(first) | set(row)
                     if k != "ts" and first.get(k) != row.get(k)}
        if differing:
            w = out.conflicts.setdefault(agent_id, {"kind": "summary_conflict",
                                                    "agent_id": agent_id,
                                                    "conflicting_rows": 0, "differing": []})
            w["conflicting_rows"] += 1
            w["differing"] = sorted(set(w["differing"]) | differing)
    return out


def _count(v) -> int:
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else 0


def _summary_usage(row: dict) -> dict:
    """A stored summary row in the shape _file_summary returns, with a sanitized model_usage
    (non-dict buckets dropped, non-integer counts read as 0)."""
    raw = row.get("model_usage")
    model_usage = {}
    for key, bucket in (raw.items() if isinstance(raw, dict) else ()):
        if isinstance(key, str) and isinstance(bucket, dict):
            model_usage[key] = {k: _count(bucket.get(k)) for k in ("responses",) + TOKEN_CATEGORIES}
    responses = sum(b["responses"] for b in model_usage.values())
    return {
        "responses": responses,
        "records": _count(row.get("records")) or responses,
        "duplicates_collapsed": _count(row.get("duplicates_collapsed")),
        "streaming_snapshot_updates": _count(row.get("streaming_snapshot_updates")),
        "duplicate_conflicts": _count(row.get("conflicts")),
        "model_usage": model_usage,
        "warnings": [],
    }


def price_model_usage(model_usage: dict, fallback_model: str | None = None,
                      scope: str | None = None) -> dict:
    """Price a model_usage mapping (raw model or "<none>" -> token bucket).

    Precedence: the raw record model is authoritative even when it does not normalize; only
    the "<none>" bucket uses `fallback_model`; anything that does not normalize is unpriced.
    Returns {usd, priced_responses, unpriced_responses, by_model, unpriced}: by_model is keyed
    by the RATE_CARD key when priced (usd float) and by the raw key when unpriced (usd None);
    unpriced entries carry raw counts plus `scope: [scope]` when a scope label is given."""
    by_model: dict[str, dict] = {}
    unpriced: dict[str, dict] = {}
    usd = 0.0
    priced_responses = unpriced_responses = 0
    for raw, bucket in model_usage.items():
        effective = fallback_model if raw == NO_MODEL else raw
        key = normalize_model(effective)
        responses = bucket.get("responses", 0) or 0
        if key is None:
            entry = unpriced.setdefault(raw, _empty_bucket())
            _add_tokens(entry, bucket, responses)
            if scope is not None and scope not in entry.setdefault("scope", []):
                entry["scope"].append(scope)
            row = by_model.setdefault(raw, {**_empty_bucket(), "usd": None})
            _add_tokens(row, bucket, responses)
            unpriced_responses += responses
            continue
        cost = price_tokens(bucket, key)
        row = by_model.setdefault(key, {**_empty_bucket(), "usd": 0.0})
        _add_tokens(row, bucket, responses)
        row["usd"] += cost
        usd += cost
        priced_responses += responses
    return {"usd": usd, "priced_responses": priced_responses,
            "unpriced_responses": unpriced_responses, "by_model": by_model,
            "unpriced": unpriced}


def unpriced_warnings(unpriced: dict) -> list[dict]:
    """One `unpriced_model` warning per unpriced model key."""
    return [{"kind": "unpriced_model", "model": m} for m in unpriced]


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


WORKFLOW_LAYOUT_NOTE = "unsupported: listed as orphans, not in session total"
MAIN_ROLE = "main"


def _sum_tokens(model_usage: dict) -> dict[str, int]:
    return {c: sum((b.get(c, 0) or 0) for b in model_usage.values()) for c in TOKEN_CATEGORIES}


def _scope_usd(priced: dict) -> float | None:
    """A scope's USD: the priced floor, or None when it has responses and none are priced."""
    if priced["unpriced_responses"] and not priced["priced_responses"]:
        return None
    return priced["usd"]


def _merge_by_model(target: dict, by_model: dict) -> None:
    for key, row in by_model.items():
        t = target.get(key)
        if t is None:
            target[key] = dict(row)
            continue
        _add_tokens(t, row, row.get("responses", 0) or 0)
        if t["usd"] is not None and row["usd"] is not None:
            t["usd"] += row["usd"]


def _merge_unpriced(target: dict, unpriced: dict) -> None:
    for raw, entry in unpriced.items():
        t = target.setdefault(raw, {**_empty_bucket(), "scope": []})
        _add_tokens(t, entry, entry.get("responses", 0) or 0)
        for sc in entry.get("scope", []):
            if sc not in t["scope"]:
                t["scope"].append(sc)


def _add_role(roles: dict, role: str, tokens: dict, responses: int, usd: float,
              dispatches: int) -> None:
    r = roles.setdefault(role, {"dispatches": 0, **_empty_bucket(), "usd": 0.0})
    r["dispatches"] += dispatches
    _add_tokens(r, tokens, responses)
    r["usd"] += usd


_DEDUP_COUNTS = ("records", "responses", "duplicates_collapsed",
                 "streaming_snapshot_updates", "duplicate_conflicts")


def _dispatch_row(td, summary: dict | None, priced: dict | None) -> dict:
    row = {
        "dispatch_id": td.dispatch_id, "agent_id": td.agent_id, "role": td.role,
        "parent_dispatch_id": td.parent_dispatch_id, "depth": td.depth,
        "status": td.status, "source": td.source, "meta_present": td.meta_present,
        "models": [], "resolved_model": td.resolved_model,
        "tokens": {c: 0 for c in TOKEN_CATEGORIES}, "usd": None,
        "partial": True, "empty": None,
        "first_ts": td.first_ts, "last_ts": td.last_ts, "summary_status": td.summary_status,
        **{k: None for k in _DEDUP_COUNTS},
    }
    if summary is not None and priced is not None:
        row.update({k: summary[k] for k in _DEDUP_COUNTS})
        row.update({
            "models": sorted(priced["by_model"]),
            "tokens": _sum_tokens(summary["model_usage"]),
            "usd": _scope_usd(priced),
            "partial": bool(priced["unpriced"]),
            "empty": summary["responses"] == 0,
        })
    return row


def _summary_warnings(tree, session_id: str, usage_summaries) -> list[dict]:
    """summary_parent_mismatch for every consulted row filed under neither the audited
    session nor the parent dispatch's agent, and summary_conflict for consulted agents."""
    agent_of = {td.dispatch_id: td.agent_id for td in tree.dispatches}
    conflicts = getattr(usage_summaries, "conflicts", {}) or {}
    out: list[dict] = []
    for td in tree.dispatches:
        if td.summary is None:
            continue
        parent = td.summary.get("parent_session")
        if parent != session_id and parent != agent_of.get(td.parent_dispatch_id):
            out.append({"kind": "summary_parent_mismatch", "agent_id": td.agent_id,
                        "parent_session": parent, "session": session_id})
        if td.agent_id in conflicts:
            out.append(dict(conflicts[td.agent_id]))
    return out


def _account_tree(transcript_path: str, main: dict, main_priced: dict, main_ids: set,
                  model: str | None, usage_summaries=None) -> dict:
    """Walk the session tree and price every accounted dispatch (from its transcript, or
    from its subagent_usage row when the transcript is gone) and every orphan file."""
    tree = token_tree.walk_tree(transcript_path, summaries=usage_summaries)
    seen = set(main_ids)
    warnings: list[dict] = _summary_warnings(
        tree, token_tree.session_dir(transcript_path).name, usage_summaries)
    by_model: dict = {}
    unpriced: dict = {}
    roles: dict = {}
    _merge_by_model(by_model, main_priced["by_model"])
    _merge_unpriced(unpriced, main_priced["unpriced"])
    _add_role(roles, MAIN_ROLE, _sum_tokens(main["model_usage"]), main["responses"],
              main_priced["usd"], 0)

    rows: list[dict] = []
    subagents_usd = 0.0
    partial = bool(main_priced["unpriced"])
    for td in tree.dispatches:
        summary = priced = None
        if td.status == token_tree.ACCOUNTED:
            if td.source == token_tree.SOURCE_SUMMARY:
                summary = _summary_usage(td.summary)
            else:
                summary = _file_summary(td.file.path, seen, with_children=False)
            priced = price_model_usage(summary["model_usage"], model, scope=td.dispatch_id)
            warnings.extend(summary["warnings"])
            _merge_by_model(by_model, priced["by_model"])
            _merge_unpriced(unpriced, priced["unpriced"])
            _add_role(roles, td.role, _sum_tokens(summary["model_usage"]),
                      summary["responses"], priced["usd"], 1)
            subagents_usd += priced["usd"]
            partial = partial or bool(priced["unpriced"])
        else:
            partial = True
        rows.append(_dispatch_row(td, summary, priced))

    orphans: list[dict] = []
    orphan_usd = 0.0
    for o in tree.orphans:
        summary = _file_summary(o.file.path, seen, with_children=False)
        priced = price_model_usage(summary["model_usage"], model)
        warnings.extend(summary["warnings"])
        orphan_usd += priced["usd"]
        orphans.append({"agent_id": o.agent_id, "layout": o.layout,
                        "usd": _scope_usd(priced), "spawn_depth": o.spawn_depth,
                        "role": o.role, "responses": summary["responses"],
                        "partial": bool(priced["unpriced"]),
                        "unpriced_models": sorted(priced["unpriced"])})
    warnings.extend(tree.warnings)

    counts = {k: sum(1 for r in rows if r["status"] == k)
              for k in (token_tree.ACCOUNTED, token_tree.MISSING_TRANSCRIPT,
                        token_tree.MISSING_METADATA)}
    by_source = {"transcript": 0, "summary": 0}
    for r in rows:
        if r["status"] == token_tree.ACCOUNTED and r["source"] in by_source:
            by_source[r["source"]] += 1
    workflow = any(o["layout"] == "workflow" for o in orphans)
    coverage = {
        "dispatches": len(rows),
        "accounted": counts[token_tree.ACCOUNTED],
        "missing_transcript": counts[token_tree.MISSING_TRANSCRIPT],
        "missing_metadata": counts[token_tree.MISSING_METADATA],
        "orphan_transcripts": len(orphans),
        "by_source": by_source,
        "workflow_layout": WORKFLOW_LAYOUT_NOTE if workflow else None,
        "summary": f"{counts[token_tree.ACCOUNTED]}/{len(rows)} dispatches accounted",
    }
    main_usd = main_priced["usd"]
    session = {"total_usd": main_usd + subagents_usd, "partial": partial,
               "main_usd": main_usd, "subagents_usd": subagents_usd,
               "orphan_usd_excluded": orphan_usd}
    return {"session": session, "cost_by_model": by_model, "cost_by_role": roles,
            "cost_by_dispatch": rows, "orphans": orphans, "dispatch_coverage": coverage,
            "unpriced": unpriced, "warnings": warnings}


def _num(v) -> float:
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def _tok4(bucket: dict) -> dict:
    return {"input": bucket.get("input", 0) or 0, "output": bucket.get("output", 0) or 0,
            "cache_read": bucket.get("cache_read", 0) or 0,
            "cache_write": (bucket.get("cache_write_5m", 0) or 0)
            + (bucket.get("cache_write_1h", 0) or 0)}


def _nonzero(tok_map: dict) -> dict:
    return {k: v for k, v in tok_map.items() if any(v.values())}


def _last_cost_state(transcript_path: str) -> dict | None:
    last = None
    for ev in read_jsonl(transcript_path, errors="ignore"):
        if isinstance(ev, dict) and ev.get("type") == "cost-state":
            last = ev
    return last


def reconcile_cost_state(transcript_path: str, main_by_model: dict, session_by_model: dict,
                         session_usd: float) -> dict:
    """Compare Writ's session pricing with the LAST Claude Code `cost-state` record of the main
    transcript (flat record: top-level totalCostUSD, hasUnknownModelCost and modelUsage{model:
    {inputTokens, outputTokens, cacheReadInputTokens, cacheCreationInputTokens, costUSD}}).
    delta_usd is writ minus cc. Never raises: an unreadable or malformed record is
    reported, not fatal."""
    try:
        rec = _last_cost_state(transcript_path)
    except OSError:
        return {"present": False}
    if rec is None:
        return {"present": False}
    model_usage = rec.get("modelUsage")
    model_usage = model_usage if isinstance(model_usage, dict) else {}
    cc: dict[str, dict] = {}
    for raw, mu in model_usage.items():
        if not isinstance(mu, dict):
            continue
        key = normalize_model(raw) or str(raw)
        entry = cc.setdefault(key, {"usd": 0.0, "tokens": {"input": 0, "output": 0,
                                                           "cache_read": 0,
                                                           "cache_write": 0}})
        entry["usd"] += _num(mu.get("costUSD"))
        for field, src in (("input", "inputTokens"), ("output", "outputTokens"),
                           ("cache_read", "cacheReadInputTokens"),
                           ("cache_write", "cacheCreationInputTokens")):
            entry["tokens"][field] += _num(mu.get(src))
    writ_tokens = {k: _tok4(v) for k, v in session_by_model.items()}
    per_model = {}
    for key in list(cc) + [k for k in session_by_model if k not in cc]:
        cc_entry = cc.get(key)
        w = session_by_model.get(key)
        cc_usd = cc_entry["usd"] if cc_entry else None
        writ_usd = w["usd"] if w else None
        per_model[key] = {
            "cc_usd": cc_usd, "writ_usd": writ_usd,
            "delta_usd": (writ_usd - cc_usd
                          if writ_usd is not None and cc_usd is not None else None),
            "cc_tokens": cc_entry["tokens"] if cc_entry else None,
            "writ_tokens": writ_tokens.get(key),
        }
    cc_map = _nonzero({k: v["tokens"] for k, v in cc.items()})
    if cc_map == _nonzero({k: _tok4(v) for k, v in main_by_model.items()}):
        scope = "main_only"
    elif cc_map == _nonzero(writ_tokens):
        scope = "main_plus_subagents"
    else:
        scope = "superset_or_unknown"
    total = rec.get("totalCostUSD")
    cc_total = total if isinstance(total, (int, float)) and not isinstance(total, bool) else None
    unknown = rec.get("hasUnknownModelCost")
    return {
        "present": True,
        "cc_total_usd": cc_total,
        "writ_session_usd": session_usd,
        "delta_usd": session_usd - cc_total if cc_total is not None else None,
        "has_unknown_model_cost": unknown if isinstance(unknown, bool) else None,
        "per_model": per_model,
        "scope": scope,
    }


def scorecard(transcript_path: str, friction_path: str | None, model: str | None = None,
              usage_summaries: dict | None = None) -> dict:
    """Per-session FOOTPRINT scorecard. Runs the schema canary FIRST -- refuses on drift.

    `model` is only a fallback for responses whose record carries no model; None means no
    fallback (such responses are unpriced). `measured` covers the main thread only; `session`,
    `cost_by_*`, `orphans` and `dispatch_coverage` cover the subagent tree.
    `usage_summaries` ({agent_id: subagent_usage row}, e.g. load_usage_summaries) prices a
    dispatch whose transcript is gone; None means no fallback."""
    scan = _scan_responses(transcript_path)
    turns = [_turn(r) for r in scan["responses"]]
    assert_usage_schema(turns)  # fail loud before computing anything
    main = _summarize_scan(scan)
    priced = price_model_usage(main["model_usage"], model, scope="main")
    main_ids = {r["message_id"] for r in scan["responses"] if r["message_id"]}
    tree = _account_tree(transcript_path, main, priced, main_ids, model, usage_summaries)
    tokens = {c: sum(b[c] for b in main["model_usage"].values()) for c in TOKEN_CATEGORIES}

    read_cost = sum((u.get("cache_read_input_tokens", 0) or 0) * COST_WEIGHTS["cache_read"]
                    for u in turns)
    out_cost = sum((u.get("output_tokens", 0) or 0) * COST_WEIGHTS["output"] for u in turns)
    inp_cost = sum((u.get("input_tokens", 0) or 0) * COST_WEIGHTS["input"] for u in turns)
    write_cost = sum(weighted_cost(u) for u in turns) - read_cost - out_cost - inp_cost
    total = read_cost + out_cost + inp_cost + write_cost

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
            # priced main-thread USD; a floor when usd_partial; None when nothing is priced
            "total_usd": priced["usd"] if priced["priced_responses"] else None,
            "responses": main["responses"],
            "records": main["records"],
            "duplicates_collapsed": main["duplicates_collapsed"],
            "streaming_snapshot_updates": main["streaming_snapshot_updates"],
            "duplicate_conflicts": main["duplicate_conflicts"],
            "tokens": tokens,
            "weighted_token_cost": total,
            "priced_total_usd": priced["usd"],
            "usd_partial": bool(priced["unpriced"]),
            "unpriced_responses": priced["unpriced_responses"],
        },
        "attributed": attributed,
        "prevented": prevented,
        "segments": segment_lengths(turns),
        "compounding_curve": compounding_curve(turns),
        "coverage": _coverage(friction),
        "session": tree["session"],
        "cost_by_model": tree["cost_by_model"],
        "cost_by_role": tree["cost_by_role"],
        "cost_by_dispatch": tree["cost_by_dispatch"],
        "orphans": tree["orphans"],
        "dispatch_coverage": tree["dispatch_coverage"],
        "reconciliation": reconcile_cost_state(transcript_path, priced["by_model"],
                                               tree["cost_by_model"],
                                               tree["session"]["total_usd"]),
        "unpriced": tree["unpriced"],
        "warnings": (main["warnings"] + tree["warnings"]
                     + unpriced_warnings(tree["unpriced"])),
    }


def render_json(card: dict) -> str:
    return json.dumps(card, indent=2)


def _total_usd_label(m: dict) -> str:
    """USD suffix of the TOTAL line; a partial figure is labeled PARTIAL, never as the total."""
    if m.get("usd_partial"):
        return (f"   (PARTIAL priced ~${m.get('priced_total_usd') or 0.0:,.2f}; "
                f"{m.get('unpriced_responses', 0)} unpriced responses)")
    if m.get("total_usd") is not None:
        return f"   (~${m['total_usd']:,.2f})"
    return ""


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
        f"  TOTAL        {m['total_cost']:>14,.0f}" + _total_usd_label(m),
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
    lines.extend(_render_tree_sections(card))
    return "\n".join(lines)


def _usd(v, missing: str = "unpriced") -> str:
    return missing if v is None else f"${v:,.4f}"


def _tok_summary(row: dict) -> str:
    return (f"in={row.get('input', 0):,} out={row.get('output', 0):,} "
            f"read={row.get('cache_read', 0):,} w5m={row.get('cache_write_5m', 0):,} "
            f"w1h={row.get('cache_write_1h', 0):,}")


def _render_tree_sections(card: dict) -> list[str]:
    s = card.get("session") or {}
    cov = card.get("dispatch_coverage") or {}
    m = card["measured"]
    lines = ["-- SESSION TREE (main thread + accounted subagent dispatches) --",
             f"  main       {_usd(s.get('main_usd'))}",
             f"  subagents  {_usd(s.get('subagents_usd'))}"]
    if s.get("partial"):
        lines.append(f"  session    {_usd(s.get('total_usd'))}   "
                     f"(PARTIAL priced floor; unpriced usage or unaccounted dispatches)")
    else:
        lines.append(f"  session    {_usd(s.get('total_usd'))}")
    lines.append(f"  coverage   {cov.get('summary', '')}  "
                 f"(missing_transcript={cov.get('missing_transcript', 0)} "
                 f"missing_metadata={cov.get('missing_metadata', 0)} "
                 f"orphans={cov.get('orphan_transcripts', 0)})")
    for d in card.get("cost_by_dispatch") or []:
        if d["status"] != "accounted":
            lines.append(f"  gap  {d['dispatch_id']}  role={d['role']}  status={d['status']}"
                         f"  agent_id={d['agent_id']}")
    lines.append("-- BY MODEL --")
    for key, row in sorted((card.get("cost_by_model") or {}).items()):
        lines.append(f"  {key:<28} responses={row['responses']:<4} {_tok_summary(row)}  "
                     f"{_usd(row['usd'])}")
    lines.append("-- BY ROLE --")
    for role, row in sorted((card.get("cost_by_role") or {}).items()):
        lines.append(f"  {role:<28} dispatches={row['dispatches']:<3} "
                     f"responses={row['responses']:<4} {_usd(row['usd'])}")
    lines.append("-- UNPRICED (no rate-card entry; dollar totals are floors) --")
    unpriced = card.get("unpriced") or {}
    if unpriced:
        lines.append(f"  WARNING: {len(unpriced)} unpriced model(s); "
                     f"these tokens carry no USD in any total")
        for key, row in sorted(unpriced.items()):
            lines.append(f"  {key:<28} responses={row['responses']:<4} {_tok_summary(row)}"
                         f"  scope={','.join(row.get('scope', []))}")
    else:
        lines.append("  (none)")
    lines.append("-- ORPHANS (subagent transcripts with no linked dispatch; excluded) --")
    orphans = card.get("orphans") or []
    for o in orphans:
        lines.append(f"  {o['agent_id']}  layout={o['layout']}  role={o['role']}  "
                     f"spawn_depth={o['spawn_depth']}  {_usd(o['usd'])}")
    if orphans:
        lines.append(f"  orphan_usd_excluded {_usd(s.get('orphan_usd_excluded'))}")
    else:
        lines.append("  (none)")
    if cov.get("workflow_layout"):
        lines.append(f"  workflow layout: {cov['workflow_layout']}")
    lines.append("-- RECONCILIATION (Claude Code cost-state; advisory) --")
    r = card.get("reconciliation") or {}
    if not r.get("present"):
        lines.append("  cost-state: absent")
    else:
        lines.append(f"  cc_total {_usd(r.get('cc_total_usd'), 'n/a')}  "
                     f"writ_session {_usd(r.get('writ_session_usd'), 'n/a')}  "
                     f"delta(writ-cc) {_usd(r.get('delta_usd'), 'n/a')}  scope={r.get('scope')}")
        for key, pm in sorted((r.get("per_model") or {}).items()):
            lines.append(f"  {key:<28} cc={_usd(pm['cc_usd'], 'n/a')}  "
                         f"writ={_usd(pm['writ_usd'], 'n/a')}  "
                         f"delta={_usd(pm['delta_usd'], 'n/a')}")
    lines.append("-- ACCOUNTING WARNINGS --")
    totals = {k: m.get(k, 0) or 0 for k in _DEDUP_COUNTS}
    for d in card.get("cost_by_dispatch") or []:
        if d["status"] == "accounted":
            for k in _DEDUP_COUNTS:
                totals[k] += d.get(k) or 0
    lines.append(f"  session (main + accounted dispatches): records {totals['records']}, "
                 f"responses {totals['responses']}, collapsed {totals['duplicates_collapsed']}, "
                 f"streaming_snapshot_updates {totals['streaming_snapshot_updates']}, "
                 f"duplicate_conflicts {totals['duplicate_conflicts']}")
    lines.append(f"  main thread: records={m.get('records', 0)} responses={m.get('responses', 0)}"
                 f" collapsed={m.get('duplicates_collapsed', 0)}")
    warnings = card.get("warnings") or []
    for w in warnings:
        detail = "  ".join(f"{k}={v}" for k, v in w.items() if k != "kind")
        lines.append(f"  {w.get('kind')}  {detail}")
    if not warnings:
        lines.append("  (none)")
    return lines
