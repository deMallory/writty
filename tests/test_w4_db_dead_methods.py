"""RED guard for Wave-4 Cycle 4.1 -- delete dead `NodeStoreMixin` methods.

`get_all_edges` (Rule->Rule only, zero production callers) is superseded by
`get_all_edges_cross_type` (the live edge-read used by writ/export.py).
`create_category` (a bare MERGE that skips `_node_write_spec`, zero production
callers) is superseded by `create_methodology_node("Category", ...)`, the real
Category-creation path used by the import-markdown ingest.

This guard introspects the `Neo4jConnection` class surface only -- it never
constructs a driver or touches Neo4j. `hasattr` on the class resolves each
method through the mixin MRO without instantiating.

RED today: the two `*_removed` tests fail because the dead methods still
resolve on the class. They turn GREEN once `writ/graph/db/node_store.py`
deletes `get_all_edges` and `create_category`. The two `*_survives` tests are
green now and after, guarding against an over-broad deletion.
"""
from __future__ import annotations

from writ.graph.db import Neo4jConnection


def test_get_all_edges_removed() -> None:
    assert not hasattr(Neo4jConnection, "get_all_edges"), (
        "get_all_edges is dead (zero production callers, superseded by "
        "get_all_edges_cross_type) and must be deleted from NodeStoreMixin"
    )


def test_create_category_removed() -> None:
    assert not hasattr(Neo4jConnection, "create_category"), (
        "create_category is dead (zero production callers, superseded by "
        "create_methodology_node(\"Category\", ...)) and must be deleted from "
        "NodeStoreMixin"
    )


def test_get_all_edges_cross_type_survives() -> None:
    assert hasattr(Neo4jConnection, "get_all_edges_cross_type"), (
        "get_all_edges_cross_type is the live edge-read equivalent and must "
        "survive this deletion cycle"
    )


def test_create_methodology_node_survives() -> None:
    assert hasattr(Neo4jConnection, "create_methodology_node"), (
        "create_methodology_node is the production Category-creation path "
        "and must survive this deletion cycle"
    )
