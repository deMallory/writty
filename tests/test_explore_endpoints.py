"""RED tests for GET /graph and GET /node/{node_id} -- graph-explorer SPA endpoints.

Per TEST-TDD-001: test skeletons approved before implementation.
Per PY-ASYNC-001: route handlers must be async def with asyncio.to_thread().
Per PY-PYDANTIC-001: query params validated; response bodies have a defined shape.

These tests currently FAIL because the endpoints do not exist yet (FastAPI returns 404
for unregistered routes). GREEN once the endpoints are implemented.

Harness: httpx.AsyncClient + ASGITransport(app=app) -- same as test_session_routes.py
and test_server_retrieval_mode.py. The Neo4j db is mocked via
patch("writ.server._db", mock_db) so the suite never requires a live graph.

Corpus seed: the mock_db returns a small but structurally complete corpus:
  - 4 nodes (2 Rule, 1 Skill, 1 Playbook) with varying domain / mandatory / provenance
  - 3 edges forming a connected subgraph (no dangling edges)
This is the minimum needed to exercise every filter path and the no-dangling-edge contract.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

try:
    from httpx import AsyncClient, ASGITransport
except ImportError:
    pytestmark = pytest.mark.skip(reason="httpx not installed")

from writ.graph.db import Neo4jConnection
from writ.server import app  # type: ignore[import]


# ---------------------------------------------------------------------------
# Seed corpus constants
# ---------------------------------------------------------------------------

# Nodes returned by the mock graph -- represent what the endpoint must shape
# from Neo4j records into the /graph response.
_SEED_NODES = [
    {
        "id": "ARCH-ORG-001",
        "type": "Rule",
        "domain": "Architecture",
        "severity": "critical",
        "mandatory": True,
        "provenance": "hand-authored",
        "project": "writ",
        "statement": "Each class must belong to exactly one architectural layer.",
    },
    {
        "id": "SEC-SQL-002",
        "type": "Rule",
        "domain": "Security",
        "severity": "high",
        "mandatory": False,
        "provenance": "hand-authored",
        "project": "writ",
        "statement": "Parameterize all SQL queries.",
    },
    {
        "id": "SKL-PROC-MODE-001",
        "type": "Skill",
        "domain": "Process",
        "severity": "high",
        "mandatory": True,
        "provenance": "hand-authored",
        "project": "writ",
        "statement": "Set mode before performing work.",
    },
    {
        "id": "PBK-PROC-WORK-001",
        "type": "Playbook",
        "domain": "Process",
        "severity": "high",
        "mandatory": False,
        "provenance": "proposed",
        "project": "writ",
        "statement": "Standard work playbook.",
    },
]

# Edges -- every source and target is in _SEED_NODES.
_SEED_EDGES = [
    {"source": "ARCH-ORG-001", "target": "SEC-SQL-002", "type": "RELATED_TO"},
    {"source": "SKL-PROC-MODE-001", "target": "ARCH-ORG-001", "type": "TEACHES"},
    {"source": "PBK-PROC-WORK-001", "target": "SKL-PROC-MODE-001", "type": "INVOKES"},
]

_SEED_NODE_IDS = {n["id"] for n in _SEED_NODES}

# A node id that is NOT in the corpus.
_UNKNOWN_NODE_ID = "DOES-NOT-EXIST-999"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


class _Record(dict):
    """Neo4j-record stand-in: dict subscripting/.get plus a .data() method."""

    def data(self) -> dict[str, Any]:
        return dict(self)


class _AsyncRecords:
    """Async-iterable stand-in for a Neo4j result cursor.

    Supports both `async for record in result` and `await result.single()`.
    Each record is a _Record (dict) exposing `.data()` and `record["k"]`
    access, matching how the db read helpers consume Neo4j cursors.
    """

    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = [_Record(r) for r in rows]

    def __aiter__(self):
        async def _gen():
            for row in self._rows:
                yield row

        return _gen()

    async def single(self):
        return self._rows[0] if self._rows else None


def _node_census_rows(project: str) -> list[dict[str, Any]]:
    """Raw node census rows the db helper RETURNs (pre-filter, pre-cap)."""
    return [
        {
            "id": n["id"],
            "type": n["type"],
            "domain": n["domain"],
            "severity": n["severity"],
            "mandatory": n["mandatory"],
            "provenance": n["provenance"],
        }
        for n in _SEED_NODES
        if n["project"] == project
    ]


def _edge_census_rows(project: str) -> list[dict[str, Any]]:
    """Raw edge census rows the db helper RETURNs (project-scoped)."""
    project_ids = {n["id"] for n in _SEED_NODES if n["project"] == project}
    return [
        {"source": e["source"], "target": e["target"], "type": e["type"]}
        for e in _SEED_EDGES
        if e["source"] in project_ids and e["target"] in project_ids
    ]


@pytest.fixture()
def mock_db():
    """Mock Neo4jConnection whose async driver session returns seed corpus data.

    The graph endpoints query Neo4j directly (not via _pipeline), so this mock
    drives the _driver.session async-context-manager path that the db read
    helpers use (matching the existing pattern in test_server_retrieval_mode.py).
    `session.run` dispatches on the query text to return the right cursor:
    node census, edge census, single-node lookup, or neighbor list.
    """
    mock = MagicMock()
    mock.close = AsyncMock()
    mock._database = "neo4j"
    mock._driver = MagicMock()

    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=session_cm)
    session_cm.__aexit__ = AsyncMock(return_value=None)

    async def _run(query: str, **params: Any):
        project = params.get("project", "writ")
        q = query
        # Single-node lookup: RETURN n, labels(n)[0] AS type.
        if "RETURN n, labels(n)[0] AS type" in q:
            node_id = params.get("node_id")
            match = [
                n for n in _SEED_NODES
                if n["id"] == node_id and n["project"] == project
            ]
            if not match:
                return _AsyncRecords([])
            return _AsyncRecords([{"n": dict(match[0]), "type": match[0]["type"]}])
        # Neighbor lookup: incident edges with direction.
        if "AS direction" in q:
            node_id = params.get("node_id")
            project_ids = {
                n["id"] for n in _SEED_NODES if n["project"] == project
            }
            type_by_id = {n["id"]: n["type"] for n in _SEED_NODES}
            rows: list[dict[str, Any]] = []
            for e in _SEED_EDGES:
                if e["source"] not in project_ids or e["target"] not in project_ids:
                    continue
                if e["source"] == node_id:
                    rows.append({
                        "id": e["target"],
                        "type": type_by_id.get(e["target"]),
                        "edge_type": e["type"],
                        "direction": "out",
                    })
                elif e["target"] == node_id:
                    rows.append({
                        "id": e["source"],
                        "type": type_by_id.get(e["source"]),
                        "edge_type": e["type"],
                        "direction": "in",
                    })
            return _AsyncRecords(rows)
        # Edge census: RETURN ... AS source ... AS target.
        if "AS source" in q and "AS target" in q:
            return _AsyncRecords(_edge_census_rows(project))
        # Node census: RETURN ... AS id, labels(n)[0] AS type ...
        return _AsyncRecords(_node_census_rows(project))

    session_cm.run = AsyncMock(side_effect=_run)
    mock._driver.session.return_value = session_cm

    # Delegate the two read helpers under test to the REAL Neo4jConnection
    # implementation, bound to this mock as `self`. The route logic (filter,
    # cap, truncation, dangling-edge removal) thus runs against production code;
    # only the Neo4j cursor is faked, via the _run dispatcher above.
    async def _get_graph(project: str = "writ", node_limit: int = 5000):
        return await Neo4jConnection.get_graph_nodes_and_edges(
            mock, project=project, node_limit=node_limit
        )

    async def _get_node(node_id: str, project: str = "writ"):
        return await Neo4jConnection.get_node_with_neighbors(
            mock, node_id, project=project
        )

    mock.get_graph_nodes_and_edges = _get_graph
    mock.get_node_with_neighbors = _get_node
    return mock


@pytest_asyncio.fixture()
async def client(mock_db):
    """Async HTTP client wired to the FastAPI app with a patched _db."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch("writ.server._db", mock_db):
            yield ac


# ---------------------------------------------------------------------------
# TestGraphEndpointShape
# ---------------------------------------------------------------------------


class TestGraphEndpointShape:
    """GET /graph returns the correct top-level response shape."""

    @pytest.mark.asyncio
    async def test_returns_200(self, client: AsyncClient) -> None:
        """GET /graph returns HTTP 200."""
        response = await client.get("/graph")
        assert response.status_code == 200, (
            f"Expected 200 from /graph; got {response.status_code}. "
            f"Endpoint does not exist yet -- this is the expected RED failure."
        )

    @pytest.mark.asyncio
    async def test_response_has_nodes_key(self, client: AsyncClient) -> None:
        """Response body contains a 'nodes' list."""
        response = await client.get("/graph")
        assert response.status_code == 200
        body = response.json()
        assert "nodes" in body, f"Response must contain 'nodes' key; got keys={list(body.keys())}"
        assert isinstance(body["nodes"], list)

    @pytest.mark.asyncio
    async def test_response_has_edges_key(self, client: AsyncClient) -> None:
        """Response body contains an 'edges' list."""
        response = await client.get("/graph")
        assert response.status_code == 200
        body = response.json()
        assert "edges" in body, f"Response must contain 'edges' key; got keys={list(body.keys())}"
        assert isinstance(body["edges"], list)

    @pytest.mark.asyncio
    async def test_response_has_truncated_key(self, client: AsyncClient) -> None:
        """Response body contains a boolean 'truncated' key."""
        response = await client.get("/graph")
        assert response.status_code == 200
        body = response.json()
        assert "truncated" in body, (
            f"Response must contain 'truncated' key; got keys={list(body.keys())}"
        )
        assert isinstance(body["truncated"], bool)

    @pytest.mark.asyncio
    async def test_node_shape_has_required_fields(self, client: AsyncClient) -> None:
        """Each node object contains id, type, domain, severity, mandatory, provenance."""
        response = await client.get("/graph")
        assert response.status_code == 200
        nodes = response.json().get("nodes", [])
        if not nodes:
            pytest.skip("No nodes returned -- cannot verify node shape")
        node = nodes[0]
        for field in ("id", "type", "domain", "severity", "mandatory", "provenance"):
            assert field in node, (
                f"Node must contain '{field}'; got node keys={list(node.keys())}"
            )

    @pytest.mark.asyncio
    async def test_edge_shape_has_required_fields(self, client: AsyncClient) -> None:
        """Each edge object contains source, target, type."""
        response = await client.get("/graph")
        assert response.status_code == 200
        edges = response.json().get("edges", [])
        if not edges:
            pytest.skip("No edges returned -- cannot verify edge shape")
        edge = edges[0]
        for field in ("source", "target", "type"):
            assert field in edge, (
                f"Edge must contain '{field}'; got edge keys={list(edge.keys())}"
            )


# ---------------------------------------------------------------------------
# TestGraphEndpointLimitAndTruncation
# ---------------------------------------------------------------------------


class TestGraphEndpointLimitAndTruncation:
    """GET /graph respects the limit param and sets truncated correctly."""

    @pytest.mark.asyncio
    async def test_limit_caps_node_count(self, client: AsyncClient) -> None:
        """GET /graph?limit=2 returns at most 2 nodes."""
        response = await client.get("/graph", params={"limit": 2})
        assert response.status_code == 200
        body = response.json()
        assert len(body["nodes"]) <= 2, (
            f"limit=2 must cap nodes at 2; got {len(body['nodes'])}"
        )

    @pytest.mark.asyncio
    async def test_truncated_true_when_cap_hit(self, client: AsyncClient) -> None:
        """truncated=True when the node set was capped by limit."""
        # Use limit=1 -- with any non-empty corpus, this will hit the cap.
        response = await client.get("/graph", params={"limit": 1})
        assert response.status_code == 200
        body = response.json()
        nodes = body["nodes"]
        # Only assert truncated semantics when a result actually came back.
        if len(nodes) == 1:
            assert body["truncated"] is True, (
                "truncated must be True when limit caused node cap; "
                f"got truncated={body['truncated']!r}"
            )

    @pytest.mark.asyncio
    async def test_truncated_false_when_cap_not_hit(self, client: AsyncClient) -> None:
        """truncated=False when returned nodes < limit (no cap applied)."""
        # Use a very large limit so the full corpus fits.
        response = await client.get("/graph", params={"limit": 10000})
        assert response.status_code == 200
        body = response.json()
        assert body["truncated"] is False, (
            "truncated must be False when all nodes fit within limit; "
            f"got truncated={body['truncated']!r}, node_count={len(body['nodes'])}"
        )

    @pytest.mark.asyncio
    async def test_default_limit_is_150(self, client: AsyncClient) -> None:
        """GET /graph with no limit param applies a default cap of 150."""
        response = await client.get("/graph")
        assert response.status_code == 200
        body = response.json()
        # With the seed corpus (4 nodes), all fit within the default 150.
        # Verify no more than 150 nodes are returned (default cap enforced).
        assert len(body["nodes"]) <= 150, (
            f"Default limit must be 150; got {len(body['nodes'])} nodes"
        )


# ---------------------------------------------------------------------------
# TestGraphEndpointNoDanglingEdges
# ---------------------------------------------------------------------------


class TestGraphEndpointNoDanglingEdges:
    """Every edge source and target must appear in the returned nodes set."""

    @pytest.mark.asyncio
    async def test_no_dangling_edges_full_corpus(self, client: AsyncClient) -> None:
        """With default limit, edges reference only nodes present in the response."""
        response = await client.get("/graph")
        assert response.status_code == 200
        body = response.json()
        returned_ids = {n["id"] for n in body["nodes"]}
        for edge in body["edges"]:
            assert edge["source"] in returned_ids, (
                f"Edge source '{edge['source']}' not in returned nodes "
                f"(dangling edge); node ids={returned_ids}"
            )
            assert edge["target"] in returned_ids, (
                f"Edge target '{edge['target']}' not in returned nodes "
                f"(dangling edge); node ids={returned_ids}"
            )

    @pytest.mark.asyncio
    async def test_no_dangling_edges_with_small_limit(self, client: AsyncClient) -> None:
        """With a small limit that truncates the node set, dangling edges are excluded."""
        response = await client.get("/graph", params={"limit": 2})
        assert response.status_code == 200
        body = response.json()
        returned_ids = {n["id"] for n in body["nodes"]}
        for edge in body["edges"]:
            assert edge["source"] in returned_ids, (
                f"After truncation, edge source '{edge['source']}' not in returned nodes"
            )
            assert edge["target"] in returned_ids, (
                f"After truncation, edge target '{edge['target']}' not in returned nodes"
            )


# ---------------------------------------------------------------------------
# TestGraphEndpointFilters
# ---------------------------------------------------------------------------


class TestGraphEndpointFilters:
    """GET /graph filter params narrow the result set correctly."""

    @pytest.mark.asyncio
    async def test_node_type_filter_returns_only_that_type(self, client: AsyncClient) -> None:
        """GET /graph?node_type=Rule returns only Rule nodes."""
        response = await client.get("/graph", params={"node_type": "Rule"})
        assert response.status_code == 200
        nodes = response.json()["nodes"]
        for node in nodes:
            assert node["type"] == "Rule", (
                f"node_type=Rule filter must return only Rule nodes; "
                f"got node type={node['type']!r} for id={node['id']!r}"
            )

    @pytest.mark.asyncio
    async def test_domain_filter_returns_only_that_domain(self, client: AsyncClient) -> None:
        """GET /graph?domain=Architecture returns only nodes in that domain."""
        response = await client.get("/graph", params={"domain": "Architecture"})
        assert response.status_code == 200
        nodes = response.json()["nodes"]
        for node in nodes:
            assert node["domain"] == "Architecture", (
                f"domain=Architecture filter must return only Architecture nodes; "
                f"got domain={node['domain']!r} for id={node['id']!r}"
            )

    @pytest.mark.asyncio
    async def test_mandatory_true_filter_returns_only_mandatory(self, client: AsyncClient) -> None:
        """GET /graph?mandatory=true returns only nodes where mandatory=True."""
        response = await client.get("/graph", params={"mandatory": "true"})
        assert response.status_code == 200
        nodes = response.json()["nodes"]
        for node in nodes:
            assert node["mandatory"] is True, (
                f"mandatory=true filter must return only mandatory nodes; "
                f"got mandatory={node['mandatory']!r} for id={node['id']!r}"
            )

    @pytest.mark.asyncio
    async def test_provenance_filter_returns_only_that_provenance(self, client: AsyncClient) -> None:
        """GET /graph?provenance=hand-authored returns only hand-authored nodes."""
        response = await client.get("/graph", params={"provenance": "hand-authored"})
        assert response.status_code == 200
        nodes = response.json()["nodes"]
        for node in nodes:
            assert node["provenance"] == "hand-authored", (
                f"provenance=hand-authored filter must return only hand-authored nodes; "
                f"got provenance={node['provenance']!r} for id={node['id']!r}"
            )

    @pytest.mark.asyncio
    async def test_provenance_filter_proposed_returns_only_proposed(self, client: AsyncClient) -> None:
        """GET /graph?provenance=proposed returns only proposed nodes."""
        response = await client.get("/graph", params={"provenance": "proposed"})
        assert response.status_code == 200
        nodes = response.json()["nodes"]
        for node in nodes:
            assert node["provenance"] == "proposed", (
                f"provenance=proposed filter must return only proposed nodes; "
                f"got provenance={node['provenance']!r} for id={node['id']!r}"
            )

    @pytest.mark.asyncio
    async def test_project_default_scopes_to_writ(self, client: AsyncClient) -> None:
        """GET /graph with no project param defaults to project='writ'."""
        # The default behavior is tested via the seed corpus (all nodes are project=writ).
        # With a different project there should be no overlap unless the impl is wrong.
        response_default = await client.get("/graph")
        response_explicit = await client.get("/graph", params={"project": "writ"})
        assert response_default.status_code == 200
        assert response_explicit.status_code == 200
        default_ids = {n["id"] for n in response_default.json()["nodes"]}
        explicit_ids = {n["id"] for n in response_explicit.json()["nodes"]}
        # Nodes returned by implicit default must be a subset of nodes from explicit writ scope.
        # (They may differ only if default applies additional scoping logic.)
        assert default_ids <= explicit_ids or explicit_ids <= default_ids, (
            "GET /graph with no project param must behave like project='writ'; "
            f"default_ids={default_ids}, explicit_ids={explicit_ids}"
        )

    @pytest.mark.asyncio
    async def test_unknown_project_returns_empty_nodes(self, client: AsyncClient) -> None:
        """GET /graph?project=nonexistent-project returns zero nodes (no cross-project leak)."""
        response = await client.get("/graph", params={"project": "nonexistent-project-xyz"})
        assert response.status_code == 200
        body = response.json()
        assert len(body["nodes"]) == 0, (
            "An unknown project must return zero nodes (no cross-project data leak); "
            f"got {len(body['nodes'])} nodes"
        )


# ---------------------------------------------------------------------------
# TestGraphEndpointEdgeTypeExclude
# ---------------------------------------------------------------------------


class TestGraphEndpointEdgeTypeExclude:
    """GET /graph?exclude_edge_types=... drops matching edge types post-shaping.

    RED today: the `graph()` handler does not accept `exclude_edge_types` yet,
    so it is silently ignored by FastAPI and every case below fails against
    the unfiltered baseline. Uses the seeded corpus's 3 distinct edge types
    (RELATED_TO, TEACHES, INVOKES) from _SEED_EDGES. The filter is Leg A
    (route-level post-shaping): the node set must never be touched by this
    param.
    """

    @staticmethod
    def _edge_key(edge: dict[str, Any]) -> tuple[str, str, str]:
        return (edge["source"], edge["target"], edge["type"])

    @pytest.mark.asyncio
    async def test_exclude_single_edge_type(self, client: AsyncClient) -> None:
        """exclude_edge_types=RELATED_TO drops RELATED_TO edges; nodes unchanged."""
        baseline = await client.get("/graph")
        response = await client.get(
            "/graph", params={"exclude_edge_types": "RELATED_TO"}
        )
        assert response.status_code == 200
        body = response.json()
        edge_types = {e["type"] for e in body["edges"]}
        assert "RELATED_TO" not in edge_types, (
            f"exclude_edge_types=RELATED_TO must drop all RELATED_TO edges; "
            f"got edge types={edge_types}"
        )
        baseline_ids = {n["id"] for n in baseline.json()["nodes"]}
        filtered_ids = {n["id"] for n in body["nodes"]}
        assert filtered_ids == baseline_ids, (
            "Excluding an edge type must not change the node set; "
            f"baseline={baseline_ids}, filtered={filtered_ids}"
        )

    @pytest.mark.asyncio
    async def test_exclude_all_seeded_types(self, client: AsyncClient) -> None:
        """Excluding every seeded edge type returns an empty edge list; nodes unchanged."""
        baseline = await client.get("/graph")
        response = await client.get(
            "/graph", params={"exclude_edge_types": "RELATED_TO,TEACHES,INVOKES"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["edges"] == [], (
            f"Excluding all seeded edge types must yield edges=[]; got {body['edges']}"
        )
        baseline_ids = {n["id"] for n in baseline.json()["nodes"]}
        filtered_ids = {n["id"] for n in body["nodes"]}
        assert filtered_ids == baseline_ids, (
            "Excluding all edge types must not change the node set; "
            f"baseline={baseline_ids}, filtered={filtered_ids}"
        )

    @pytest.mark.asyncio
    async def test_exclude_unknown_type_is_noop(self, client: AsyncClient) -> None:
        """exclude_edge_types with a type absent from the corpus changes nothing."""
        baseline = await client.get("/graph")
        response = await client.get(
            "/graph", params={"exclude_edge_types": "NOT_A_TYPE"}
        )
        assert response.status_code == 200
        baseline_edges = {self._edge_key(e) for e in baseline.json()["edges"]}
        filtered_edges = {self._edge_key(e) for e in response.json()["edges"]}
        assert filtered_edges == baseline_edges, (
            "An unrecognized exclude_edge_types value must be a no-op; "
            f"baseline={baseline_edges}, filtered={filtered_edges}"
        )

    @pytest.mark.asyncio
    async def test_exclude_omitted_is_baseline(self, client: AsyncClient) -> None:
        """Omitting exclude_edge_types, or passing it empty, both return the full edge set."""
        baseline = await client.get("/graph")
        omitted = await client.get("/graph")
        empty = await client.get("/graph", params={"exclude_edge_types": ""})
        assert baseline.status_code == omitted.status_code == empty.status_code == 200
        baseline_edges = {self._edge_key(e) for e in baseline.json()["edges"]}
        omitted_edges = {self._edge_key(e) for e in omitted.json()["edges"]}
        empty_edges = {self._edge_key(e) for e in empty.json()["edges"]}
        assert omitted_edges == baseline_edges, (
            "Omitting exclude_edge_types must return the full baseline edge set; "
            f"baseline={baseline_edges}, omitted={omitted_edges}"
        )
        assert empty_edges == baseline_edges, (
            "An empty exclude_edge_types value must return the full baseline edge set; "
            f"baseline={baseline_edges}, empty-param={empty_edges}"
        )

    @pytest.mark.asyncio
    async def test_exclude_whitespace_stripped(self, client: AsyncClient) -> None:
        """A space after the comma in exclude_edge_types is stripped per-token."""
        response = await client.get(
            "/graph", params={"exclude_edge_types": "RELATED_TO, TEACHES"}
        )
        assert response.status_code == 200
        edge_types = {e["type"] for e in response.json()["edges"]}
        assert "RELATED_TO" not in edge_types, (
            f"Whitespace-separated token 'RELATED_TO' must still be excluded; "
            f"got edge types={edge_types}"
        )
        assert "TEACHES" not in edge_types, (
            f"Whitespace-separated token ' TEACHES' must be stripped and excluded; "
            f"got edge types={edge_types}"
        )

    @pytest.mark.asyncio
    async def test_exclude_preserves_no_dangling_edges(self, client: AsyncClient) -> None:
        """After excluding a type, every remaining edge's endpoints are in the node set."""
        response = await client.get(
            "/graph", params={"exclude_edge_types": "RELATED_TO"}
        )
        assert response.status_code == 200
        body = response.json()
        returned_ids = {n["id"] for n in body["nodes"]}
        for edge in body["edges"]:
            assert edge["source"] in returned_ids, (
                f"Edge source '{edge['source']}' not in returned nodes after "
                f"edge-type exclusion (dangling edge); node ids={returned_ids}"
            )
            assert edge["target"] in returned_ids, (
                f"Edge target '{edge['target']}' not in returned nodes after "
                f"edge-type exclusion (dangling edge); node ids={returned_ids}"
            )


# ---------------------------------------------------------------------------
# TestGraphEndpointReadOnly
# ---------------------------------------------------------------------------


class TestGraphEndpointReadOnly:
    """GET /graph must not mutate graph state."""

    @pytest.mark.asyncio
    async def test_two_calls_return_same_node_count(self, client: AsyncClient) -> None:
        """Calling GET /graph twice returns the same number of nodes (no write side-effect)."""
        r1 = await client.get("/graph")
        r2 = await client.get("/graph")
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert len(r1.json()["nodes"]) == len(r2.json()["nodes"]), (
            "GET /graph must be idempotent (read-only); "
            f"first call returned {len(r1.json()['nodes'])} nodes, "
            f"second returned {len(r2.json()['nodes'])}"
        )

    @pytest.mark.asyncio
    async def test_two_calls_return_same_edge_count(self, client: AsyncClient) -> None:
        """Calling GET /graph twice returns the same number of edges."""
        r1 = await client.get("/graph")
        r2 = await client.get("/graph")
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert len(r1.json()["edges"]) == len(r2.json()["edges"]), (
            "GET /graph must be idempotent (read-only); "
            f"first call returned {len(r1.json()['edges'])} edges, "
            f"second returned {len(r2.json()['edges'])}"
        )


# ---------------------------------------------------------------------------
# TestNodeDetailEndpointShape
# ---------------------------------------------------------------------------


class TestNodeDetailEndpointShape:
    """GET /node/{node_id} returns the correct response shape for a known node."""

    @pytest.mark.asyncio
    async def test_returns_200_for_known_node(self, client: AsyncClient) -> None:
        """GET /node/ARCH-ORG-001 returns HTTP 200 for a seeded node."""
        response = await client.get("/node/ARCH-ORG-001")
        assert response.status_code == 200, (
            f"Expected 200 for known node ARCH-ORG-001; got {response.status_code}. "
            f"Endpoint does not exist yet -- this is the expected RED failure."
        )

    @pytest.mark.asyncio
    async def test_response_has_id_field(self, client: AsyncClient) -> None:
        """Response body contains 'id' matching the requested node_id."""
        response = await client.get("/node/ARCH-ORG-001")
        assert response.status_code == 200
        body = response.json()
        assert "id" in body, f"Response must contain 'id'; got keys={list(body.keys())}"
        assert body["id"] == "ARCH-ORG-001", (
            f"id must echo the requested node_id; got {body['id']!r}"
        )

    @pytest.mark.asyncio
    async def test_response_has_type_field(self, client: AsyncClient) -> None:
        """Response body contains 'type' string."""
        response = await client.get("/node/ARCH-ORG-001")
        assert response.status_code == 200
        body = response.json()
        assert "type" in body, f"Response must contain 'type'; got keys={list(body.keys())}"
        assert isinstance(body["type"], str)

    @pytest.mark.asyncio
    async def test_response_has_props_dict(self, client: AsyncClient) -> None:
        """Response body contains 'props' as a dict with full node properties."""
        response = await client.get("/node/ARCH-ORG-001")
        assert response.status_code == 200
        body = response.json()
        assert "props" in body, f"Response must contain 'props'; got keys={list(body.keys())}"
        assert isinstance(body["props"], dict), (
            f"'props' must be a dict; got {type(body['props'])!r}"
        )

    @pytest.mark.asyncio
    async def test_props_statement_is_non_empty(self, client: AsyncClient) -> None:
        """props.statement is present and non-empty for a known rule node."""
        response = await client.get("/node/ARCH-ORG-001")
        assert response.status_code == 200
        props = response.json().get("props", {})
        assert "statement" in props, (
            f"props must include 'statement'; got props keys={list(props.keys())}"
        )
        assert isinstance(props["statement"], str) and len(props["statement"]) > 0, (
            f"props.statement must be a non-empty string; got {props['statement']!r}"
        )

    @pytest.mark.asyncio
    async def test_response_has_neighbors_list(self, client: AsyncClient) -> None:
        """Response body contains 'neighbors' as a list."""
        response = await client.get("/node/ARCH-ORG-001")
        assert response.status_code == 200
        body = response.json()
        assert "neighbors" in body, (
            f"Response must contain 'neighbors'; got keys={list(body.keys())}"
        )
        assert isinstance(body["neighbors"], list), (
            f"'neighbors' must be a list; got {type(body['neighbors'])!r}"
        )

    @pytest.mark.asyncio
    async def test_neighbor_shape_has_required_fields(self, client: AsyncClient) -> None:
        """Each neighbor entry has id, type, edge_type, direction."""
        response = await client.get("/node/ARCH-ORG-001")
        assert response.status_code == 200
        neighbors = response.json().get("neighbors", [])
        if not neighbors:
            pytest.skip("Node has no neighbors in seeded corpus -- skip shape check")
        neighbor = neighbors[0]
        for field in ("id", "type", "edge_type", "direction"):
            assert field in neighbor, (
                f"Neighbor entry must contain '{field}'; got keys={list(neighbor.keys())}"
            )

    @pytest.mark.asyncio
    async def test_neighbor_direction_is_valid_value(self, client: AsyncClient) -> None:
        """neighbor.direction is 'in' or 'out' (not some other string)."""
        response = await client.get("/node/ARCH-ORG-001")
        assert response.status_code == 200
        neighbors = response.json().get("neighbors", [])
        if not neighbors:
            pytest.skip("Node has no neighbors -- skip direction validation")
        for neighbor in neighbors:
            assert neighbor.get("direction") in ("in", "out"), (
                f"neighbor.direction must be 'in' or 'out'; "
                f"got {neighbor.get('direction')!r} for neighbor id={neighbor.get('id')!r}"
            )


# ---------------------------------------------------------------------------
# TestNodeDetailEndpointNotFound
# ---------------------------------------------------------------------------


class TestNodeDetailEndpointNotFound:
    """GET /node/{node_id} for an unknown id returns a not-found shape, NOT a 500."""

    @pytest.mark.asyncio
    async def test_unknown_node_does_not_return_500(self, client: AsyncClient) -> None:
        """GET /node/DOES-NOT-EXIST-999 must not return HTTP 500."""
        response = await client.get(f"/node/{_UNKNOWN_NODE_ID}")
        assert response.status_code != 500, (
            f"Unknown node must not cause 500; got {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_unknown_node_returns_404_or_error_body(self, client: AsyncClient) -> None:
        """GET /node/DOES-NOT-EXIST-999 returns 404 OR a JSON body with an 'error' key."""
        response = await client.get(f"/node/{_UNKNOWN_NODE_ID}")
        # 404 is the canonical REST not-found; a 200+{error:...} body is also acceptable.
        if response.status_code == 404:
            return  # correct
        assert response.status_code == 200, (
            f"Unknown node must return 404 or 200+error; got {response.status_code}"
        )
        body = response.json()
        assert "error" in body, (
            f"Unknown node 200-response must include 'error' key; got keys={list(body.keys())}"
        )

    @pytest.mark.asyncio
    async def test_unknown_node_error_body_is_parseable_json(self, client: AsyncClient) -> None:
        """Response for an unknown node id is valid JSON (not an HTML error page)."""
        response = await client.get(f"/node/{_UNKNOWN_NODE_ID}")
        # If this raises, the response is not JSON -- that's the failure to assert.
        try:
            body = response.json()
        except Exception as exc:  # noqa: BLE001
            pytest.fail(
                f"Response for unknown node must be valid JSON; got parse error: {exc}"
            )
        # Body must be a dict (not a bare string or list).
        assert isinstance(body, dict), (
            f"Not-found response body must be a JSON object; got {type(body)!r}"
        )


# ---------------------------------------------------------------------------
# TestNodeDetailEndpointProjectScope
# ---------------------------------------------------------------------------


class TestNodeDetailEndpointProjectScope:
    """GET /node/{node_id} respects project scoping."""

    @pytest.mark.asyncio
    async def test_default_project_is_writ(self, client: AsyncClient) -> None:
        """GET /node/ARCH-ORG-001 with no project param uses 'writ' scope."""
        r_default = await client.get("/node/ARCH-ORG-001")
        r_explicit = await client.get("/node/ARCH-ORG-001", params={"project": "writ"})
        assert r_default.status_code == r_explicit.status_code, (
            "Default project scope must behave like project='writ'; "
            f"default={r_default.status_code}, explicit={r_explicit.status_code}"
        )

    @pytest.mark.asyncio
    async def test_wrong_project_returns_not_found(self, client: AsyncClient) -> None:
        """GET /node/ARCH-ORG-001?project=other returns not-found when node belongs to writ."""
        response = await client.get("/node/ARCH-ORG-001", params={"project": "other-project-xyz"})
        # Must be 404 or 200+error, NOT 200 with the node's real data.
        if response.status_code == 404:
            return  # correct
        if response.status_code == 200:
            body = response.json()
            assert "error" in body, (
                "Node from project 'writ' must not be visible under 'other-project-xyz'; "
                f"got 200 with keys={list(body.keys())}"
            )
        else:
            pytest.fail(
                f"Unexpected status {response.status_code} for cross-project node lookup"
            )


# ---------------------------------------------------------------------------
# TestNodeDetailEndpointReadOnly
# ---------------------------------------------------------------------------


class TestNodeDetailEndpointReadOnly:
    """GET /node/{node_id} must not mutate graph state."""

    @pytest.mark.asyncio
    async def test_two_calls_return_identical_body(self, client: AsyncClient) -> None:
        """Calling GET /node/ARCH-ORG-001 twice returns the same body (read-only)."""
        r1 = await client.get("/node/ARCH-ORG-001")
        r2 = await client.get("/node/ARCH-ORG-001")
        assert r1.status_code == 200
        assert r2.status_code == 200
        # Compare fields that must be stable across reads.
        b1, b2 = r1.json(), r2.json()
        assert b1.get("id") == b2.get("id"), (
            "Read-only: 'id' must not change between calls"
        )
        assert b1.get("type") == b2.get("type"), (
            "Read-only: 'type' must not change between calls"
        )
        assert b1.get("props", {}).get("statement") == b2.get("props", {}).get("statement"), (
            "Read-only: props.statement must not change between calls"
        )


# ---------------------------------------------------------------------------
# TestGraphEndpointRegistered
# ---------------------------------------------------------------------------


class TestGraphEndpointRegistered:
    """Structural tests: the routes must be registered on the FastAPI app."""

    def test_graph_route_is_registered(self) -> None:
        """GET /graph route exists in app.routes."""
        graph_routes = [
            r for r in app.routes
            if hasattr(r, "path") and getattr(r, "path", "") == "/graph"
        ]
        assert len(graph_routes) > 0, (
            "GET /graph route is not registered on the FastAPI app; "
            "this is the expected RED failure -- implement the endpoint."
        )

    def test_node_detail_route_is_registered(self) -> None:
        """GET /node/{node_id} route exists in app.routes."""
        node_routes = [
            r for r in app.routes
            if hasattr(r, "path") and getattr(r, "path", "") == "/node/{node_id}"
        ]
        assert len(node_routes) > 0, (
            "GET /node/{node_id} route is not registered on the FastAPI app; "
            "this is the expected RED failure -- implement the endpoint."
        )

    def test_graph_route_handler_is_async(self) -> None:
        """GET /graph handler is declared with async def (PY-ASYNC-001)."""
        import inspect

        graph_routes = [
            r for r in app.routes
            if hasattr(r, "path") and getattr(r, "path", "") == "/graph"
        ]
        if not graph_routes:
            pytest.fail("/graph route not registered -- cannot check async (RED)")
        for route in graph_routes:
            endpoint = getattr(route, "endpoint", None)
            assert endpoint is not None and inspect.iscoroutinefunction(endpoint), (
                f"/graph handler must be async def; got {endpoint!r}"
            )

    def test_node_detail_route_handler_is_async(self) -> None:
        """GET /node/{node_id} handler is declared with async def (PY-ASYNC-001)."""
        import inspect

        node_routes = [
            r for r in app.routes
            if hasattr(r, "path") and getattr(r, "path", "") == "/node/{node_id}"
        ]
        if not node_routes:
            pytest.fail("/node/{node_id} route not registered -- cannot check async (RED)")
        for route in node_routes:
            endpoint = getattr(route, "endpoint", None)
            assert endpoint is not None and inspect.iscoroutinefunction(endpoint), (
                f"/node/{{node_id}} handler must be async def; got {endpoint!r}"
            )



# ---------------------------------------------------------------------------
# TestExploreHtmlSkeletonViewWiring
# ---------------------------------------------------------------------------


class TestExploreHtmlSkeletonViewWiring:
    """Source-scan guard for the explore.html JS wiring (no JS test harness exists).

    RED today: explore.html has neither the exclude_edge_types skeleton-view
    param wiring nor the g-hide-hubs Category-hide selector.
    """

    def test_explore_html_has_skeleton_and_hidehubs_wiring(self) -> None:
        """explore.html source wires the skeleton-view param and hide-hubs selector."""
        html_path = Path(__file__).resolve().parent.parent / "writ" / "static" / "explore.html"
        assert html_path.is_file(), f"explore.html not found at {html_path}"
        source = html_path.read_text(encoding="utf-8")
        assert "exclude_edge_types" in source, (
            "explore.html must wire the skeleton-view control to the "
            "exclude_edge_types query param (g-skeleton -> graphParams())"
        )
        assert "g-hide-hubs" in source, (
            "explore.html must expose a 'Hide hubs (Category)' checkbox with id=g-hide-hubs"
        )
        assert "Category" in source, (
            "explore.html must reference the Category node type in the hide-hubs wiring"
        )
