"""Shared token-audit test helpers (Wave-5 Cycle 5.3c).

Consolidates the `_ta`/`_usage`/`_write_transcript` trio formerly duplicated in
`test_token_audit.py` and `test_token_audit_prevented.py`. The two files differ
only in their module-loading semantics: the prevented file force-reimports a
fresh module each call, while the base file returns the cached module. That
difference is preserved via the `force_reimport` flag on `load_token_audit`, so
each consumer keeps its current behavior.

SKILL_ROOT is resolved two parents up from `tests/fixtures/` (both source files
compute it one parent up from `tests/`).
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))


def load_token_audit(force_reimport: bool = False):
    """Import writ.analysis.token_audit, optionally force-reimporting it.

    With ``force_reimport=False`` this returns the cached module (matching
    test_token_audit.py's `_ta`); with ``force_reimport=True`` it drops the
    cached module first so on-disk edits are picked up (matching
    test_token_audit_prevented.py's `_ta`).
    """
    if SKILL_ROOT not in sys.path:
        sys.path.insert(0, SKILL_ROOT)
    mod_name = "writ.analysis.token_audit"
    if force_reimport and mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


def usage(inp=100, out=10, read=1000, write=200, c5=None, c1=None):
    """A well-formed CC assistant-turn usage dict.

    The superset builder: with ``c5``/``c1`` left as None the emitted dict is
    the 4-key form; supplying either adds the `cache_creation` sub-dict.
    """
    u = {
        "input_tokens": inp,
        "output_tokens": out,
        "cache_read_input_tokens": read,
        "cache_creation_input_tokens": write,
    }
    if c5 is not None or c1 is not None:
        u["cache_creation"] = {"ephemeral_5m_input_tokens": c5 or 0,
                               "ephemeral_1h_input_tokens": c1 or 0}
    return u


def write_transcript(path: Path, usages: list[dict], model="claude-opus-4-8") -> Path:
    """Write a minimal CC transcript jsonl: assistant turns carrying message.usage."""
    with open(path, "w") as f:
        for u in usages:
            f.write(json.dumps({"type": "assistant",
                                "message": {"model": model, "usage": u}}) + "\n")
    return path


# ---------------------------------------------------------------------------
# Token-audit accounting / tree builders (response ids, Agent dispatches,
# cost-state, on-disk session trees). The three helpers above stay unchanged.
# ---------------------------------------------------------------------------

def agent_tool_use(tool_use_id: str, subagent_type: str = "writ-explorer") -> dict:
    """An assistant content block dispatching a subagent via the Agent tool."""
    return {"type": "tool_use", "id": tool_use_id, "name": "Agent",
            "input": {"subagent_type": subagent_type, "description": "d", "prompt": "p"}}


def response_records(msg_id, model, usage_dict, n_records: int = 1, tool_uses=(),
                     ts: str | None = None) -> list[dict]:
    """The assistant records Claude Code writes for ONE API response.

    Claude Code writes one record per content block; every record carries the same
    ``message.id`` and the same ``message.usage``. ``tool_uses`` (content blocks from
    ``agent_tool_use``) ride on the trailing records, the rest are text blocks. A
    ``msg_id`` of None omits ``message.id`` (an id-less record); a ``model`` of None
    omits ``message.model``.
    """
    assert n_records >= len(tool_uses), "need at least one record per tool_use block"
    blocks = [{"type": "text", "text": "t"}] * (n_records - len(tool_uses)) + list(tool_uses)
    records = []
    for block in blocks:
        message = {"usage": dict(usage_dict), "content": [block]}
        if msg_id is not None:
            message["id"] = msg_id
        if model is not None:
            message["model"] = model
        rec = {"type": "assistant", "message": message}
        if ts is not None:
            rec["timestamp"] = ts
        records.append(rec)
    return records


def tool_result_record(tool_use_id: str, agent_id: str | None = None,
                       resolved_model: str | None = None, status: str = "completed",
                       ts: str | None = None) -> dict:
    """A user record returning an Agent tool_result, with top-level ``toolUseResult``."""
    tur: dict = {"status": status}
    if agent_id is not None:
        tur["agentId"] = agent_id
    if resolved_model is not None:
        tur["resolvedModel"] = resolved_model
    rec = {"type": "user",
           "message": {"role": "user",
                       "content": [{"type": "tool_result", "tool_use_id": tool_use_id,
                                    "content": "done"}]},
           "toolUseResult": tur}
    if ts is not None:
        rec["timestamp"] = ts
    return rec


def cost_state_record(total_usd: float, per_model: dict) -> dict:
    """A Claude Code ``cost-state`` record (flat: totals and modelUsage at the top level).

    ``per_model`` maps model -> {"usd", "input", "output", "cache_read", "cache_write"}.
    """
    return {"type": "cost-state",
            "totalCostUSD": total_usd,
            "hasUnknownModelCost": False,
            "modelUsage": {m: {"costUSD": v["usd"],
                               "inputTokens": v["input"],
                               "outputTokens": v["output"],
                               "cacheReadInputTokens": v["cache_read"],
                               "cacheCreationInputTokens": v["cache_write"]}
                           for m, v in per_model.items()}}


def write_records(path: Path, records: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    return path


def write_subagent(session_dir: Path, agent_id: str, records: list[dict],
                   meta: dict | None = None, workflow: str | None = None) -> Path:
    """Write ``<session_dir>/subagents/[workflows/<workflow>/]agent-<id>.jsonl`` plus its
    ``.meta.json`` sidecar (skipped when ``meta`` is None)."""
    base = session_dir / "subagents"
    if workflow is not None:
        base = base / "workflows" / workflow
    path = write_records(base / f"agent-{agent_id}.jsonl", records)
    if meta is not None:
        (base / f"agent-{agent_id}.meta.json").write_text(json.dumps(meta))
    return path


def write_session_tree(tmp_path: Path, session_id: str, main_records: list[dict],
                       subagents: dict | None = None) -> Path:
    """Write ``<tmp>/<session>.jsonl`` and ``<tmp>/<session>/subagents/agent-<id>.jsonl``
    (+ ``.meta.json``). ``subagents`` maps agent_id -> {"records", "meta"?, "workflow"?}.
    Returns the main transcript path."""
    main = write_records(tmp_path / f"{session_id}.jsonl", main_records)
    for agent_id, spec in (subagents or {}).items():
        write_subagent(tmp_path / session_id, agent_id, spec["records"],
                       meta=spec.get("meta"), workflow=spec.get("workflow"))
    return main


def write_e2e_tree(tmp_path: Path, session_id: str = "sess-e2e") -> Path:
    """The hand-computed end-to-end fixture (plan: 'End-to-end fixture').

    main m1 opus-5-5 (2 records, dispatches toolu_A) + m2 opus-5-5 (dispatches toolu_B);
    agent-aaa sonnet-5-5 (3 records, meta writ:writ-explorer); agent-bbb dated haiku
    (meta writ-planner); agent-ccc an undispatched orphan. Returns the main path.
    """
    m1 = response_records(
        "msg_m1", "claude-opus-5-5",
        usage(inp=1000, out=2000, read=100000, write=10000, c5=4000, c1=6000),
        n_records=2, tool_uses=[agent_tool_use("toolu_A", "writ:writ-explorer")],
        ts="2026-09-01T10:00:00Z")
    m2 = response_records(
        "msg_m2", "claude-opus-5-5",
        usage(inp=500, out=1000, read=200000, write=0),
        tool_uses=[agent_tool_use("toolu_B", "writ-planner")], ts="2026-09-01T10:05:00Z")
    main_records = (m1
                    + [tool_result_record("toolu_A", "aaa", "claude-sonnet-5-5",
                                          ts="2026-09-01T10:02:00Z")]
                    + m2
                    + [tool_result_record("toolu_B", "bbb", "claude-haiku-4-5-20251001",
                                          ts="2026-09-01T10:06:00Z")])
    subagents = {
        "aaa": {
            "records": response_records(
                "msg_a1", "claude-sonnet-5-5",
                usage(inp=2000, out=4000, read=50000, write=8000),
                n_records=3, ts="2026-09-01T10:01:00Z"),
            "meta": {"agentType": "writ:writ-explorer", "toolUseId": "toolu_A",
                     "spawnDepth": 1},
        },
        "bbb": {
            "records": response_records(
                "msg_b1", "claude-haiku-4-5-20251001",
                usage(inp=10000, out=1000, read=0, write=0), ts="2026-09-01T10:05:30Z"),
            "meta": {"agentType": "writ-planner", "toolUseId": "toolu_B", "spawnDepth": 1},
        },
        "ccc": {
            "records": response_records(
                "msg_c1", "claude-opus-5-5",
                usage(inp=1000, out=0, read=0, write=0), ts="2026-09-01T10:07:00Z"),
            "meta": {"agentType": "writ-explorer", "toolUseId": "toolu_NEVER",
                     "spawnDepth": 1},
        },
    }
    return write_session_tree(tmp_path, session_id, main_records, subagents)
