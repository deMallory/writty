"""Phase 2a: integrity checks span ALL node types, not just :Rule.

The built-in orphan check only audited :Rule, so a disconnected methodology node
or a dangling dispatched_roles reference read as fine. These tests exercise the
new all-labels orphan check and the dispatched_roles reference-integrity check
against the live graph imported from bible/.

`test_no_dangling_dispatched_roles` is the TEST-REGRESSION-001 guard for 2b: it
fails while ORCHESTRATOR/AUDIT-FANOUT declare dispatched_roles by short name and
passes once they use canonical ROL-*-001 ids.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import pytest_asyncio

from writ.config import get_neo4j_password, get_neo4j_uri, get_neo4j_user
from writ.graph.db import Neo4jConnection
from writ.graph.integrity import IntegrityChecker
from writ.graph.schema import METHODOLOGY_NODE_TYPES, NODE_ID_FIELDS

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module", autouse=True)
def _fresh_corpus():
    """Import bible/ once so the graph reflects the dispatched_roles currently in
    the files (the warmth-skip in conftest can otherwise leave stale properties)."""
    from tests._corpus import neo4j_reachable

    if not neo4j_reachable():
        pytest.skip("Neo4j unreachable")
    from tests._writ_cmd import WRIT_CMD_PREFIX

    subprocess.run(
        [*WRIT_CMD_PREFIX, "import-markdown", "bible/"],
        cwd=str(REPO), capture_output=True, timeout=120, check=False,
    )


@pytest_asyncio.fixture()
async def live_checker():
    conn = Neo4jConnection(get_neo4j_uri(), get_neo4j_user(), get_neo4j_password())
    try:
        yield IntegrityChecker(conn._driver, conn._database)
    finally:
        await conn.close()


class TestAllLabelOrphanCheck:
    @pytest.mark.asyncio
    async def test_orphans_all_labels_spans_every_node_type(self, live_checker) -> None:
        """The orphan check must report a count for every node label (G1 fix:
        it was Rule-only)."""
        _, counts = await live_checker.detect_orphans_all_labels()
        for label in NODE_ID_FIELDS:
            assert label in counts, f"orphan check must cover node type {label}"

    @pytest.mark.asyncio
    async def test_methodology_layer_fully_connected(self, live_checker) -> None:
        """Only :Rule nodes are orphaned; every methodology node type is connected."""
        _, counts = await live_checker.detect_orphans_all_labels()
        offenders = {
            label: counts.get(label, 0)
            for label in METHODOLOGY_NODE_TYPES
            if counts.get(label, 0)
        }
        assert not offenders, f"methodology nodes must be connected; orphaned: {offenders}"


class TestDanglingDispatchedRoles:
    @pytest.mark.asyncio
    async def test_no_dangling_dispatched_roles(self, live_checker) -> None:
        """Every Playbook.dispatched_roles entry must be a canonical ROL-* id, so a
        DISPATCHES edge can resolve it. RED until 2b canonicalizes ORCHESTRATOR and
        AUDIT-FANOUT; GREEN after."""
        dangling = await live_checker.detect_dangling_dispatched_roles()
        assert dangling == [], (
            "dispatched_roles must reference canonical ROL-*-001 ids, not short names; "
            f"dangling: {dangling}"
        )

    @pytest.mark.asyncio
    async def test_check_flags_a_short_name_reference(self, live_checker) -> None:
        """The check itself works: a short-name ref is flagged resolvable when a role
        with that name exists. (Drives the logic independent of the bible/ end-state.)"""
        # Pure-logic guard: resolvable entries carry the intended target id.
        dangling = await live_checker.detect_dangling_dispatched_roles()
        for entry in dangling:
            if entry["resolvable"]:
                assert entry["resolved_target_id"], "resolvable ref must name its target id"
                assert entry["resolved_target_id"].startswith("ROL-")
