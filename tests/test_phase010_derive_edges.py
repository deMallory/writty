"""0.10-A: derive_edges is the PURE edge-derivation shared by the writer
(ingest_edges) and the reconcile oracle (compute_expected_graph).

A derive-vs-derive divergence between the writer and the oracle is the
silent-drift class 0.10 closes, so this pins the 4 edge sources (declared,
RELATED_TO, BELONGS_TO, category-tree) and the pre-write dangling count with no
DB at all -- the function must be sync and side-effect-free.
"""

from __future__ import annotations

from writ.graph.methodology_ingest import derive_edges


def _tuples(edges: list[dict]) -> set[tuple[str, str, str]]:
    return {(e["type"], e["source"], e["target"]) for e in edges}


class TestDeriveEdges:
    def test_declared_edge_both_ids_known(self) -> None:
        nodes = [
            {"node_type": "Rule", "rule_id": "A-001"},
            {"node_type": "Rule", "rule_id": "B-001"},
        ]
        decl = [{"type": "COUNTERS", "source": "A-001", "target": "B-001"}]
        edges, dangling = derive_edges(nodes, decl, {"A-001", "B-001"})
        assert ("COUNTERS", "A-001", "B-001") in _tuples(edges)
        assert dangling == 0

    def test_declared_edge_unknown_target_is_dangling(self) -> None:
        nodes = [{"node_type": "Rule", "rule_id": "A-001"}]
        decl = [{"type": "COUNTERS", "source": "A-001", "target": "GONE-999"}]
        edges, dangling = derive_edges(nodes, decl, {"A-001"})
        assert _tuples(edges) == set()
        assert dangling == 1

    def test_declared_edge_missing_field_is_dangling(self) -> None:
        decl = [{"type": "COUNTERS", "source": "A-001"}]  # no target
        edges, dangling = derive_edges([], decl, {"A-001"})
        assert edges == []
        assert dangling == 1

    def test_related_to_only_when_ref_is_a_parsed_rule(self) -> None:
        nodes = [
            {"node_type": "Rule", "rule_id": "A-001",
             "_cross_references": ["B-001", "NOPE-001"]},
            {"node_type": "Rule", "rule_id": "B-001"},
        ]
        edges, dangling = derive_edges(nodes, [], {"A-001", "B-001"})
        t = _tuples(edges)
        assert ("RELATED_TO", "A-001", "B-001") in t
        # ref that is not a parsed Rule is SKIPPED, not counted dangling
        assert ("RELATED_TO", "A-001", "NOPE-001") not in t
        assert dangling == 0

    def test_belongs_to_from_category_value(self) -> None:
        nodes = [{"node_type": "Rule", "rule_id": "A-001", "category": "CAT-SEC-001"}]
        edges, _ = derive_edges(nodes, [], {"A-001"})
        assert ("BELONGS_TO", "A-001", "CAT-SEC-001") in _tuples(edges)

    def test_category_tree_child_to_parent_root_skipped(self) -> None:
        nodes = [
            {"node_type": "Category", "category_id": "CAT-SEC-INJ-001",
             "parent": "CAT-SEC-001"},
            {"node_type": "Category", "category_id": "CAT-ROOT-001", "parent": None},
        ]
        edges, _ = derive_edges(
            nodes, [], {"CAT-SEC-INJ-001", "CAT-SEC-001", "CAT-ROOT-001"}
        )
        t = _tuples(edges)
        assert ("BELONGS_TO", "CAT-SEC-INJ-001", "CAT-SEC-001") in t
        assert not any(src == "CAT-ROOT-001" for (_, src, _) in t)

    def test_pure_and_db_free(self) -> None:
        # No DB, no await: derive_edges is callable with only parsed data.
        edges, dangling = derive_edges([], [], set())
        assert edges == []
        assert dangling == 0
