"""Session-tree linkage for the token audit: which subagent transcripts belong to a session,
which Agent dispatch produced each one, and how every dispatch and file is classified.

Pure linkage and classification. No pricing lives here (token_audit.py prices), and this
module must not import writ.analysis.token_audit (token_audit imports this one).

Public API
----------
session_dir(transcript_path) -> Path
    The transcript path without its ``.jsonl`` suffix (Claude Code's per-session directory).

normalize_role(raw) -> str
    Strips one leading ``"writ:"``; empty/None/non-string -> ``"unknown"``.

index_subagent_files(session_dir) -> dict[str, SubagentFile]
    Flat ``subagents/agent-*.jsonl`` (layout ``"flat"``) then
    ``subagents/*/*/agent-*.jsonl`` (layout ``"workflow"``). The first file seen for an
    agent id wins. Ids failing the subagent_role allowlist shape are skipped.

extract_dispatches(path) -> list[Dispatch]
    Agent tool_use blocks in assistant records, joined to the user record whose
    ``tool_result.tool_use_id`` matches, in file order of the tool_use.

walk_tree(main_transcript_path, index=None, summaries=None) -> TreeResult
    Walks dispatches from the main transcript, recursing into each accounted subagent's
    own transcript, and lists every indexed file never reached as an orphan.

Field names
-----------
SubagentFile: agent_id, path (Path), layout ("flat"|"workflow"), meta_present (bool),
    agent_type, tool_use_id, spawn_depth, model, stopped_by_user (raw sidecar values or
    None), meta (the raw sidecar dict or None).

Dispatch: dispatch_id, subagent_type, agent_id (toolUseResult.agentId or None),
    resolved_model, result_status (toolUseResult.status), first_ts (tool_use record
    timestamp), last_ts (tool_result record timestamp, else first_ts).

TreeDispatch: dispatch_id, agent_id, role (normalized), parent_dispatch_id (None for
    main-thread dispatches), depth (1 for main-thread dispatches, parent depth + 1 below),
    status ("accounted"|"missing_transcript"|"missing_metadata"), source ("transcript"
    when accounted from a file, else None), meta_present, resolved_model, first_ts,
    last_ts, subagent_type (raw dispatch input), file (SubagentFile or None).

Orphan: agent_id, layout, spawn_depth, role (normalized meta.agentType or "unknown"),
    file (SubagentFile).

TreeResult: dispatches (list[TreeDispatch], walk order: parents before children),
    orphans (list[Orphan], index order), workflow_layout_present (bool: any indexed file
    has layout "workflow"), index (the dict used), summaries (as passed; not yet used),
    warnings (list of dicts; kind "duplicate_agent_link" when a second dispatch resolves
    to an agent already linked, in which case that second dispatch is not listed so its
    file is never billed twice).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from writ.analysis.jsonl import read_jsonl

# Same allowlist shape as writ.session.subagent_role._VALID_AGENT_ID.
_VALID_AGENT_ID = re.compile(r"\A[A-Za-z0-9_-]{1,128}\Z")
_AGENT_PREFIX = "agent-"
_ROLE_PREFIX = "writ:"

ACCOUNTED = "accounted"
MISSING_TRANSCRIPT = "missing_transcript"
MISSING_METADATA = "missing_metadata"


@dataclass
class SubagentFile:
    agent_id: str
    path: Path
    layout: str
    meta_present: bool = False
    agent_type: object = None
    tool_use_id: object = None
    spawn_depth: object = None
    model: object = None
    stopped_by_user: object = None
    meta: dict | None = None


@dataclass
class Dispatch:
    dispatch_id: str
    subagent_type: object = None
    agent_id: str | None = None
    resolved_model: object = None
    result_status: object = None
    first_ts: object = None
    last_ts: object = None


@dataclass
class TreeDispatch:
    dispatch_id: str
    agent_id: str | None
    role: str
    parent_dispatch_id: str | None
    depth: int
    status: str
    source: str | None
    meta_present: bool
    resolved_model: object
    first_ts: object
    last_ts: object
    subagent_type: object = None
    file: SubagentFile | None = None


@dataclass
class Orphan:
    agent_id: str
    layout: str
    spawn_depth: object
    role: str
    file: SubagentFile


@dataclass
class TreeResult:
    dispatches: list[TreeDispatch] = field(default_factory=list)
    orphans: list[Orphan] = field(default_factory=list)
    workflow_layout_present: bool = False
    index: dict[str, SubagentFile] = field(default_factory=dict)
    summaries: dict | None = None
    warnings: list[dict] = field(default_factory=list)


def session_dir(transcript_path) -> Path:
    p = Path(transcript_path)
    return p.with_suffix("") if p.suffix == ".jsonl" else p


def normalize_role(raw) -> str:
    if not isinstance(raw, str):
        return "unknown"
    role = raw.strip()
    if role.startswith(_ROLE_PREFIX):
        role = role[len(_ROLE_PREFIX):]
    return role or "unknown"


def _normalize_agent_id(raw) -> str | None:
    if not isinstance(raw, str):
        return None
    candidate = raw.strip()
    if candidate.startswith(_AGENT_PREFIX):
        candidate = candidate[len(_AGENT_PREFIX):]
    return candidate if _VALID_AGENT_ID.match(candidate) else None


def _read_meta(jsonl_path: Path) -> dict | None:
    meta_path = jsonl_path.with_name(jsonl_path.name[: -len(".jsonl")] + ".meta.json")
    try:
        with open(meta_path) as f:
            meta = json.load(f)
    except (OSError, ValueError):
        return None
    return meta if isinstance(meta, dict) else None


def index_subagent_files(session_dir) -> dict[str, SubagentFile]:
    root = Path(session_dir) / "subagents"
    index: dict[str, SubagentFile] = {}
    if not root.is_dir():
        return index
    for layout, pattern in (("flat", "agent-*.jsonl"), ("workflow", "*/*/agent-*.jsonl")):
        for path in sorted(root.glob(pattern)):
            if not path.is_file():
                continue
            agent_id = _normalize_agent_id(path.name[: -len(".jsonl")])
            if agent_id is None or agent_id in index:
                continue
            meta = _read_meta(path)
            m = meta or {}
            index[agent_id] = SubagentFile(
                agent_id=agent_id, path=path, layout=layout, meta_present=meta is not None,
                agent_type=m.get("agentType"), tool_use_id=m.get("toolUseId"),
                spawn_depth=m.get("spawnDepth"), model=m.get("model"),
                stopped_by_user=m.get("stoppedByUser"), meta=meta)
    return index


def _content_items(rec: dict) -> list:
    msg = rec.get("message")
    if not isinstance(msg, dict):
        return []
    content = msg.get("content")
    return [c for c in content if isinstance(c, dict)] if isinstance(content, list) else []


def extract_dispatches(path) -> list[Dispatch]:
    dispatches: dict[str, Dispatch] = {}
    for rec in read_jsonl(path, errors="ignore"):
        if not isinstance(rec, dict):
            continue
        kind = rec.get("type")
        if kind == "assistant":
            for item in _content_items(rec):
                if item.get("type") != "tool_use" or item.get("name") != "Agent":
                    continue
                did = item.get("id")
                if not isinstance(did, str) or not did or did in dispatches:
                    continue
                inp = item.get("input")
                subagent_type = inp.get("subagent_type") if isinstance(inp, dict) else None
                ts = rec.get("timestamp")
                dispatches[did] = Dispatch(dispatch_id=did, subagent_type=subagent_type,
                                           first_ts=ts, last_ts=ts)
        elif kind == "user":
            tur = rec.get("toolUseResult")
            tur = tur if isinstance(tur, dict) else {}
            for item in _content_items(rec):
                if item.get("type") != "tool_result":
                    continue
                d = dispatches.get(item.get("tool_use_id"))
                if d is None:
                    continue
                d.agent_id = _normalize_agent_id(tur.get("agentId"))
                d.resolved_model = tur.get("resolvedModel")
                d.result_status = tur.get("status")
                if rec.get("timestamp") is not None:
                    d.last_ts = rec.get("timestamp")
    return list(dispatches.values())


def walk_tree(main_transcript_path, index=None, summaries=None) -> TreeResult:
    if index is None:
        index = index_subagent_files(session_dir(main_transcript_path))
    by_tool_use_id: dict[str, str] = {}
    for agent_id, sf in index.items():
        if isinstance(sf.tool_use_id, str) and sf.tool_use_id not in by_tool_use_id:
            by_tool_use_id[sf.tool_use_id] = agent_id

    result = TreeResult(index=index, summaries=summaries,
                        workflow_layout_present=any(sf.layout == "workflow"
                                                    for sf in index.values()))
    seen_dispatches: set[str] = set()
    linked_agents: set[str] = set()
    stack = [(Path(main_transcript_path), None, 1)]
    while stack:
        path, parent_id, depth = stack.pop(0)
        for d in extract_dispatches(path):
            if d.dispatch_id in seen_dispatches:
                continue
            seen_dispatches.add(d.dispatch_id)
            agent_id = d.agent_id or by_tool_use_id.get(d.dispatch_id)
            if agent_id is not None and agent_id in linked_agents:
                result.warnings.append({"kind": "duplicate_agent_link",
                                        "dispatch_id": d.dispatch_id, "agent_id": agent_id})
                continue
            sf = index.get(agent_id) if agent_id is not None else None
            if agent_id is None:
                status, source = MISSING_METADATA, None
            elif sf is None:
                status, source = MISSING_TRANSCRIPT, None
            else:
                status, source = ACCOUNTED, "transcript"
            if agent_id is not None:
                linked_agents.add(agent_id)
            raw_role = sf.agent_type if sf is not None and sf.agent_type else d.subagent_type
            result.dispatches.append(TreeDispatch(
                dispatch_id=d.dispatch_id, agent_id=agent_id, role=normalize_role(raw_role),
                parent_dispatch_id=parent_id, depth=depth, status=status, source=source,
                meta_present=bool(sf is not None and sf.meta_present),
                resolved_model=d.resolved_model, first_ts=d.first_ts, last_ts=d.last_ts,
                subagent_type=d.subagent_type, file=sf))
            if sf is not None:
                stack.append((sf.path, d.dispatch_id, depth + 1))

    for agent_id, sf in index.items():
        if agent_id not in linked_agents:
            result.orphans.append(Orphan(agent_id=agent_id, layout=sf.layout,
                                         spawn_depth=sf.spawn_depth,
                                         role=normalize_role(sf.agent_type), file=sf))
    return result
