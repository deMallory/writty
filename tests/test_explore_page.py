"""Tests for GET /explore -- the interactive showcase SPA.

The route reads writ/static/explore.html at request time and serves it as HTML.
These are light tests: visual correctness is out of scope. We assert the route
returns 200 + an HTML content-type, that the page references the live daemon
endpoints it calls (/graph, /node, /query, /health), and that the seven section
anchors are present so the left-nav contract holds.

Harness: httpx.AsyncClient + ASGITransport(app=app), the same pattern as
test_explore_endpoints.py and test_session_routes.py.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

try:
    from httpx import AsyncClient, ASGITransport
except ImportError:
    pytestmark = pytest.mark.skip(reason="httpx not installed")

from writ.server import app  # type: ignore[import]


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture()
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestExplorePageServes:
    """GET /explore returns the showcase HTML page."""

    @pytest.mark.asyncio
    async def test_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/explore")
        assert response.status_code == 200, (
            f"GET /explore must return 200; got {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_content_type_is_html(self, client: AsyncClient) -> None:
        response = await client.get("/explore")
        assert response.status_code == 200
        ctype = response.headers.get("content-type", "")
        assert "text/html" in ctype, (
            f"GET /explore must serve HTML; got content-type={ctype!r}"
        )

    @pytest.mark.asyncio
    async def test_body_is_an_html_document(self, client: AsyncClient) -> None:
        response = await client.get("/explore")
        body = response.text
        assert "<!doctype html>" in body.lower(), "Body must be an HTML document"
        assert "</html>" in body.lower()


class TestExploreReferencesLiveEndpoints:
    """The page must call the daemon's own endpoints (no invented ones)."""

    @pytest.mark.asyncio
    async def test_references_query_endpoint(self, client: AsyncClient) -> None:
        body = (await client.get("/explore")).text
        assert "/query" in body, "Page must call POST /query (live query playground)"

    @pytest.mark.asyncio
    async def test_references_graph_endpoint(self, client: AsyncClient) -> None:
        body = (await client.get("/explore")).text
        assert "/graph" in body, "Page must call GET /graph (graph explorer)"

    @pytest.mark.asyncio
    async def test_references_node_endpoint(self, client: AsyncClient) -> None:
        body = (await client.get("/explore")).text
        assert "/node/" in body, "Page must call GET /node/{id} (node detail panel)"

    @pytest.mark.asyncio
    async def test_references_health_endpoint(self, client: AsyncClient) -> None:
        body = (await client.get("/explore")).text
        assert "/health" in body, "Page must call GET /health (live counts)"


class TestExploreSectionAnchors:
    """The left-nav sections must be present as anchors."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "anchor",
        ["overview", "pieces", "pipeline", "modes", "corpus", "authoring", "requirements"],
    )
    async def test_section_anchor_present(self, client: AsyncClient, anchor: str) -> None:
        body = (await client.get("/explore")).text
        assert f'id="{anchor}"' in body, (
            f"Section anchor id={anchor!r} must be present for the left-nav"
        )


class TestExploreLayoutSelector:
    """The graph explorer must expose a layout selector with concentric/grid options."""

    @pytest.mark.asyncio
    async def test_layout_selector_present(self, client: AsyncClient) -> None:
        body = (await client.get("/explore")).text
        assert 'id="g-layout"' in body, (
            'Page must expose a layout selector with id="g-layout"'
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("value", ["concentric", "grid"])
    async def test_layout_option_present(self, client: AsyncClient, value: str) -> None:
        body = (await client.get("/explore")).text
        assert f'value="{value}"' in body, (
            f"Layout selector must offer the {value!r} option"
        )


class TestExploreCdnNote:
    """A visible note must tell the visitor the graph view needs the CDN/internet."""

    @pytest.mark.asyncio
    async def test_cdn_offline_note_present(self, client: AsyncClient) -> None:
        body = (await client.get("/explore")).text.lower()
        assert "cdn" in body, "Page must note the graph view loads from a CDN"
        assert "offline" in body, "Page must note the rest of the page works offline"

    @pytest.mark.asyncio
    async def test_loads_cytoscape_from_cdn(self, client: AsyncClient) -> None:
        body = (await client.get("/explore")).text
        assert "cytoscape" in body.lower(), "Page must load Cytoscape.js"
        assert "unpkg.com/cytoscape" in body, "Cytoscape.js must load from the unpkg CDN"


class TestExploreRouteRegistered:
    """Structural: the route is registered and async."""

    def test_explore_route_is_registered(self) -> None:
        routes = [
            r for r in app.routes
            if hasattr(r, "path") and getattr(r, "path", "") == "/explore"
        ]
        assert len(routes) > 0, "GET /explore route is not registered on the app"

    def test_explore_route_handler_is_async(self) -> None:
        import inspect

        routes = [
            r for r in app.routes
            if hasattr(r, "path") and getattr(r, "path", "") == "/explore"
        ]
        assert routes, "/explore route not registered"
        for route in routes:
            endpoint = getattr(route, "endpoint", None)
            assert endpoint is not None and inspect.iscoroutinefunction(endpoint), (
                f"/explore handler must be async def; got {endpoint!r}"
            )
