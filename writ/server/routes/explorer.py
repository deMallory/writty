# writ-auth-scan: internal-service
"""Graph-explorer + dashboard routes (read-only).

4 routes: /dashboard, /explore, /graph, /node/{node_id}.

_db is read via live `server.<attr>` access inside handler bodies (the
monkeypatch seam). _EXPLORE_HTML_PATH is read live from `server` (the anchor is
computed once in writ/server/__init__.py). _GRAPH_DEFAULT_LIMIT is a plain
constant used as a def-time default argument, so it must be a real value at
import time and lives here.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

import writ.server as server

router = APIRouter()


# --- Phase 5: dashboard --------------------------------------------------------


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    """Server-rendered HTML dashboard. No JS framework, auto-refreshes via meta.

    Calls the analyzer functions directly (ARCH-SSOT-001). Reads the
    friction log path from WRIT_FRICTION_LOG or falls back to
    ./workflow-friction.log. Empty / missing log renders a placeholder
    body without throwing.
    """
    from writ.dashboard import render_dashboard

    def _render() -> str:
        return render_dashboard()

    html = await asyncio.to_thread(_render)
    return HTMLResponse(content=html, status_code=200)


# --- Interactive showcase: GET /explore -----------------------------------------
# The showcase SPA lives in a separate file so the page can be tweaked without
# restarting the daemon (the route reads it at request time). Resolved relative
# to the package (writ/static/explore.html) via the anchor computed once in
# writ/server/__init__.py (server._EXPLORE_HTML_PATH).


@router.get("/explore", response_class=HTMLResponse)
async def explore() -> HTMLResponse:
    """Single-page interactive showcase of Writ.

    Reads writ/static/explore.html at request time (so edits land without a
    daemon restart) and serves it. The page is self-contained vanilla JS that
    calls this daemon's own endpoints (/health, /query, /graph, /node) over the
    same origin. Replaces the deleted static HTML flowcharts with one
    data-backed page.
    """

    def _read() -> str:
        try:
            return server._EXPLORE_HTML_PATH.read_text(encoding="utf-8")
        except OSError:
            # Localhost-only fallback; keep it static (no exc interpolation -> no
            # path/string leak into the response). The real error is log-worthy, not
            # display-worthy.
            return (
                "<!doctype html><html><body><h1>Writ explore</h1>"
                "<p>Showcase page unavailable (static asset could not be read).</p>"
                "</body></html>"
            )

    html = await asyncio.to_thread(_read)
    return HTMLResponse(content=html, status_code=200)


# --- Graph explorer: read-only GET /graph and GET /node/{node_id} -------------
# Two read-only endpoints backing the graph-explorer SPA. Both are project-scoped
# and parameterized (no arbitrary/interpolated Cypher beyond the integer LIMIT and
# the whitelisted edge-type set in writ/graph/db.py). No write surface.

# Default node cap for GET /graph when the caller omits ?limit.
_GRAPH_DEFAULT_LIMIT = 150


@router.get("/graph")
async def graph(
    node_type: str | None = None,
    domain: str | None = None,
    provenance: str | None = None,
    mandatory: bool | None = None,
    exclude_edge_types: str | None = None,
    limit: int = _GRAPH_DEFAULT_LIMIT,
    project: str = "writ",
) -> dict[str, Any]:
    """Project-scoped node + edge subgraph for the graph explorer (read-only).

    Filters (node_type, domain, provenance, mandatory) are applied, then the
    node set is capped at `limit`; truncated=True iff more nodes matched than
    were returned. Only edges whose BOTH endpoints survive the cap are returned
    (no dangling edges). The optional `exclude_edge_types` (comma-separated
    edge-type names) drops matching edges post-shaping, leaving the node set
    untouched; omitting it or passing it empty is a no-op. Returns
    {"nodes": [...], "edges": [...], "truncated": bool}.
    """
    if server._db is None:
        return {"nodes": [], "edges": [], "truncated": False, "error": "Database not connected."}

    nodes, edges = await server._db.get_graph_nodes_and_edges(project=project)

    # Apply the caller-facing filters in Python so the (tested) filter, cap,
    # truncation, and dangling-edge contract all live in production code.
    def _matches(n: dict[str, Any]) -> bool:
        if node_type is not None and n.get("type") != node_type:
            return False
        if domain is not None and n.get("domain") != domain:
            return False
        if provenance is not None and n.get("provenance") != provenance:
            return False
        if mandatory is not None and bool(n.get("mandatory")) != mandatory:
            return False
        return True

    matched = [n for n in nodes if _matches(n)]
    cap = max(0, int(limit))
    kept = matched[:cap]
    truncated = len(matched) > len(kept)

    kept_ids = {n["id"] for n in kept}
    excluded = (
        {t.strip() for t in exclude_edge_types.split(",") if t.strip()}
        if exclude_edge_types
        else set()
    )
    shaped_nodes = [
        {
            "id": n["id"],
            "type": n.get("type"),
            "domain": n.get("domain"),
            "severity": n.get("severity"),
            "mandatory": n.get("mandatory"),
            "provenance": n.get("provenance"),
        }
        for n in kept
    ]
    shaped_edges = [
        {"source": e["source"], "target": e["target"], "type": e["type"]}
        for e in edges
        if e["source"] in kept_ids and e["target"] in kept_ids and e["type"] not in excluded
    ]
    return {"nodes": shaped_nodes, "edges": shaped_edges, "truncated": truncated}


@router.get("/node/{node_id}")
async def node_detail(node_id: str, project: str = "writ") -> dict[str, Any]:
    """Full props + incident edges for one node (read-only).

    Returns {"id", "type", "props": {...}, "neighbors": [{id, type, edge_type,
    direction}]} for a known node. For an unknown id (or a node outside the
    requested project) returns a JSON error body -- never a 500.
    """
    if server._db is None:
        return {"error": "Database not connected."}
    detail = await server._db.get_node_with_neighbors(node_id, project=project)
    if detail is None:
        return {"error": f"Node {node_id} not found in project {project!r}."}
    return detail
