"""Phase M.3: project-scoped retrieval + :Project registry.

RED-FIRST. Today query() is unconditionally search-all -- at project 2 it would
inject repo B's rules into repo A's agent. M.3 adds:
  - a :Project registry ({name, repo_root, bible_root}) + cwd->project resolver
    (longest repo_root prefix match; default 'writ').
  - pipeline.query(project=...) post-filtering ranked results to
    {caller_project, '_shared'} (a no-op at single-project = backward compatible;
    the anti-leak guarantee at project 2). Mirrors the existing domain post-filter.

Setup-for-the-future: dormant-but-correct with one project, fully tested.
Each test isolated (TEST-ISO-001).
"""

from __future__ import annotations

import numpy as np
import pytest
import pytest_asyncio

from writ.config import get_neo4j_password, get_neo4j_uri, get_neo4j_user
from writ.graph.db import Neo4jConnection


# --- pipeline project post-filter (stub pipeline, no Neo4j/ONNX) -------------

def _stub_pipeline(metadata: dict):
    from unittest.mock import MagicMock

    from writ.retrieval.embeddings import ScoredResult
    from writ.retrieval.pipeline import RetrievalPipeline
    from writ.retrieval.traversal import AdjacencyCache

    ids = list(metadata.keys())
    keyword_stub = MagicMock()
    keyword_stub.search.return_value = [{"rule_id": r, "score": 0.9} for r in ids]
    vector_stub = MagicMock()
    vector_stub.search.return_value = [ScoredResult(rule_id=r, score=0.9) for r in ids]
    encoder_stub = MagicMock()
    encoder_stub.encode.return_value = np.zeros(384, dtype=np.float32)
    return RetrievalPipeline(
        keyword_index=keyword_stub,
        vector_store=vector_stub,
        adjacency_cache=AdjacencyCache(),
        embedding_model=encoder_stub,
        rule_metadata=metadata,
    )


def _meta(node_type="Rule", domain="security", project="writ"):
    return {
        "node_type": node_type, "routes": ["semantic"], "domain": domain,
        "severity": "high", "confidence": "production-validated",
        "statement": "s.", "trigger": "t.", "project": project,
    }


def _result_ids(out: dict) -> set:
    return {r["rule_id"] for r in out.get("rules", [])}


class TestProjectQueryScope:
    def _meta_two_projects(self):
        return {
            "SEC-WRIT-001": _meta(project="writ"),
            "SEC-PROJ2-001": _meta(project="proj2"),
            "SEC-SHARED-001": _meta(project="_shared"),
        }

    def test_query_writ_excludes_proj2(self) -> None:
        p = _stub_pipeline(self._meta_two_projects())
        ids = _result_ids(p.query("secret", project="writ"))
        assert "SEC-WRIT-001" in ids
        assert "SEC-PROJ2-001" not in ids, "leak: proj2 rule served to writ"

    def test_query_proj2_excludes_writ(self) -> None:
        p = _stub_pipeline(self._meta_two_projects())
        ids = _result_ids(p.query("secret", project="proj2"))
        assert "SEC-PROJ2-001" in ids
        assert "SEC-WRIT-001" not in ids, "leak: writ rule served to proj2"

    def test_shared_project_always_included(self) -> None:
        p = _stub_pipeline(self._meta_two_projects())
        ids = _result_ids(p.query("secret", project="proj2"))
        assert "SEC-SHARED-001" in ids, "_shared rules must reach every project"

    def test_no_project_is_search_all_backward_compatible(self) -> None:
        p = _stub_pipeline(self._meta_two_projects())
        ids = _result_ids(p.query("secret"))  # no project -> unchanged behavior
        assert {"SEC-WRIT-001", "SEC-PROJ2-001", "SEC-SHARED-001"} <= ids


# --- :Project registry + cwd->project resolver -------------------------------

@pytest_asyncio.fixture()
async def db():
    conn = Neo4jConnection(get_neo4j_uri(), get_neo4j_user(), get_neo4j_password())
    await conn.clear_all()
    yield conn
    await conn.clear_all()
    await conn.close()


class TestProjectRegistry:
    @pytest.mark.asyncio
    async def test_create_and_list_projects(self, db) -> None:
        await db.create_project("writ", repo_root="/home/u/.claude/skills/writ", bible_root="bible")
        await db.create_project("proj2", repo_root="/home/u/repos/proj2", bible_root="bible/proj2")
        projects = {p["name"]: p for p in await db.get_projects()}
        assert {"writ", "proj2"} <= set(projects)
        assert projects["proj2"]["repo_root"] == "/home/u/repos/proj2"

    @pytest.mark.asyncio
    async def test_resolve_project_for_cwd_longest_prefix(self, db) -> None:
        await db.create_project("writ", repo_root="/home/u/.claude/skills/writ", bible_root="bible")
        await db.create_project("proj2", repo_root="/home/u/repos/proj2", bible_root="bible/proj2")
        # A cwd under proj2's repo resolves to proj2.
        assert await db.resolve_project_for_cwd("/home/u/repos/proj2/app/api.py") == "proj2"
        # A cwd under writ's repo resolves to writ.
        assert await db.resolve_project_for_cwd("/home/u/.claude/skills/writ/writ/cli.py") == "writ"

    @pytest.mark.asyncio
    async def test_resolve_unknown_cwd_defaults_writ(self, db) -> None:
        await db.create_project("writ", repo_root="/home/u/.claude/skills/writ", bible_root="bible")
        assert await db.resolve_project_for_cwd("/tmp/some/other/place") == "writ"
