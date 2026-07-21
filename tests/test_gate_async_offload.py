"""Wave 1 Cycle 3 (M3): structural_gate must not block the async event loop.

structural_gate runs a synchronous ONNX encode + vector search. It is called from the
async propose_rule (writ/gate.py) and promote_candidate (writ/promotion.py). Both must
offload it via asyncio.to_thread so the daemon event loop is not stalled during inference
(the server.py:283 / PERF-IO convention). We assert the offload deterministically: the
monkeypatched encode records the thread it runs on; it must differ from the event-loop
thread. A regression (calling structural_gate synchronously on the loop) makes encode run
on the loop thread and fails the test.

Hermetic: no Neo4j, no disk. `db` is a MagicMock/AsyncMock (not the live Neo4jConnection
tests/test_phase6_promote.py uses), and `pipeline` is a MagicMock in the same shape
tests/test_gate.py's `_make_mock_pipeline` builds (encode/vector-search/metadata/
adjacency), so no live dependency is needed and nothing to skip on.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest


@dataclass
class _Scored:
    rule_id: str
    score: float


def _candidate() -> dict:
    return {
        "rule_id": "TEST-OFFLOAD-001",
        "domain": "Testing",
        "severity": "high",
        "scope": "file",
        "trigger": "When writing a function that exceeds thirty lines.",
        "statement": "Functions must not exceed thirty lines of logic.",
        "violation": "A function body is forty-five lines.",
        "pass_example": "The function is decomposed into helpers.",
        "enforcement": "Reviewed in the findings table.",
        "rationale": "Long functions resist testing and reuse.",
        "last_validated": date.today().isoformat(),
    }


def _pipeline_recording_encode_thread(holder: dict) -> MagicMock:
    p = MagicMock()

    def _encode(_text):
        holder["encode_thread"] = threading.get_ident()
        return np.zeros(384, dtype=np.float32)

    p._model.encode.side_effect = _encode
    # A high-similarity hit -> gate rejects -> propose/promote return before any db
    # write, so no real DB/export is needed; encode still ran and recorded its thread.
    p._vector.search.return_value = [_Scored("EXISTING-001", 0.99)]
    p._metadata = {}
    p._cache.get_neighbors.return_value = []
    return p


@pytest.mark.asyncio
async def test_propose_rule_offloads_structural_gate() -> None:
    from writ.gate import propose_rule

    holder: dict = {}
    pipeline = _pipeline_recording_encode_thread(holder)
    db = MagicMock()
    db.create_rule = AsyncMock()

    loop_thread = threading.get_ident()
    result = await propose_rule(_candidate(), pipeline, db, origin_db_path=None)

    assert result["accepted"] is False  # redundancy hit -> rejected, no db write
    db.create_rule.assert_not_awaited()
    assert holder.get("encode_thread") is not None, "encode was never called"
    assert holder["encode_thread"] != loop_thread, (
        "structural_gate's blocking encode ran on the event-loop thread; "
        "it must be offloaded via asyncio.to_thread"
    )


@pytest.mark.asyncio
async def test_promote_candidate_offloads_structural_gate() -> None:
    from writ.promotion import promote_candidate

    holder: dict = {}
    pipeline = _pipeline_recording_encode_thread(holder)

    node = _candidate()
    node["provenance"] = "graduation_pending"
    db = MagicMock()
    db.get_rule = AsyncMock(return_value=node)
    db.create_rule = AsyncMock()

    loop_thread = threading.get_ident()
    result = await promote_candidate("TEST-OFFLOAD-001", pipeline, db, output_dir=None)

    assert result["promoted"] is False  # redundancy hit -> rejected, no export
    db.create_rule.assert_not_awaited()
    assert holder.get("encode_thread") is not None, "encode was never called"
    assert holder["encode_thread"] != loop_thread, (
        "promote_candidate ran structural_gate's blocking encode on the event-loop "
        "thread; it must be offloaded via asyncio.to_thread"
    )
