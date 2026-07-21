"""Cypher-script graph dump: pure rendering tests plus one live round-trip.

Requires Neo4j running for TestCypherDumpRoundTrip only; the literal/render
tests below it are pure functions and need no database.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from typer.testing import CliRunner

from writ.cli import app
from writ.config import get_neo4j_password, get_neo4j_uri, get_neo4j_user
from writ.graph.db import Neo4jConnection
from writ.graph.dump import cypher_literal, import_cypher_dump, render_cypher_dump

NEO4J_URI = get_neo4j_uri()
NEO4J_USER = get_neo4j_user()
NEO4J_PASSWORD = get_neo4j_password()

runner = CliRunner()


class TestCLIDefaultPaths:
    def test_export_cypher_help_shows_writ_corpus_cypher_default(self) -> None:
        result = runner.invoke(app, ["export-cypher", "--help"])
        assert "writ-corpus.cypher" in result.output

    def test_import_cypher_help_shows_writ_corpus_cypher_default(self) -> None:
        result = runner.invoke(app, ["import-cypher", "--help"])
        assert "writ-corpus.cypher" in result.output


class TestCypherLiteral:
    def test_renders_plain_string_single_quoted(self) -> None:
        assert cypher_literal("hello") == "'hello'"

    def test_escapes_single_quote(self) -> None:
        assert cypher_literal("O'Brien") == "'O\\'Brien'"

    def test_escapes_backslash_before_other_escapes(self) -> None:
        # a trailing literal backslash must not swallow the closing quote
        assert cypher_literal("a\\b") == "'a\\\\b'"

    def test_escapes_newline_and_tab(self) -> None:
        assert cypher_literal("line1\nline2\ttab") == "'line1\\nline2\\ttab'"

    def test_renders_int_without_quotes(self) -> None:
        assert cypher_literal(42) == "42"

    def test_renders_float_without_quotes(self) -> None:
        assert cypher_literal(3.5) == "3.5"

    def test_renders_bool_lowercase(self) -> None:
        assert cypher_literal(True) == "true"
        assert cypher_literal(False) == "false"

    def test_renders_list_of_strings(self) -> None:
        assert cypher_literal(["a", "b"]) == "['a', 'b']"


class TestRenderCypherDump:
    def _node(self, id_: str, label: str, **props: object) -> dict:
        return {"id": id_, "label": label, "props": props}

    def _edge(self, source_id: str, target_id: str, type_: str) -> dict:
        return {"source_id": source_id, "target_id": target_id, "type": type_}

    def test_single_node_renders_create_with_staging_property(self) -> None:
        nodes = [self._node("R-1", "Rule", rule_id="R-1", severity="high")]
        script = render_cypher_dump(nodes, [])
        assert "CREATE (:Rule {" in script
        assert "rule_id: 'R-1'" in script
        assert "severity: 'high'" in script
        assert "_dump_id: 'R-1'" in script

    def test_none_valued_property_is_omitted(self) -> None:
        nodes = [self._node("R-1", "Rule", rule_id="R-1", authority=None)]
        script = render_cypher_dump(nodes, [])
        assert "authority" not in script

    def test_single_edge_renders_match_by_staging_property_then_create(self) -> None:
        nodes = [
            self._node("R-1", "Rule", rule_id="R-1"),
            self._node("R-2", "Rule", rule_id="R-2"),
        ]
        edges = [self._edge("R-1", "R-2", "RELATED_TO")]
        script = render_cypher_dump(nodes, edges)
        assert (
            "MATCH (a {_dump_id: 'R-1'}), (b {_dump_id: 'R-2'}) "
            "CREATE (a)-[:RELATED_TO]->(b);" in script
        )

    def test_final_statement_removes_staging_property_exactly_once(self) -> None:
        nodes = [self._node("R-1", "Rule", rule_id="R-1")]
        script = render_cypher_dump(nodes, [])
        cleanup = "MATCH (n) WHERE n._dump_id IS NOT NULL REMOVE n._dump_id;"
        assert script.count(cleanup) == 1
        assert script.rstrip().endswith(cleanup)

    def test_output_is_deterministic_regardless_of_input_order(self) -> None:
        nodes_a = [self._node("R-2", "Rule", rule_id="R-2"), self._node("R-1", "Rule", rule_id="R-1")]
        nodes_b = list(reversed(nodes_a))
        assert render_cypher_dump(nodes_a, []) == render_cypher_dump(nodes_b, [])


class TestCypherDumpRoundTrip:
    """Requires Neo4j running."""

    @pytest_asyncio.fixture
    async def db(self):
        conn = Neo4jConnection(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
        await conn.clear_all()
        yield conn
        await conn.clear_all()
        await conn.close()

    @pytest.mark.asyncio
    async def test_dump_then_import_reproduces_node_and_edge_counts(self, db) -> None:
        await db.create_rule({"rule_id": "TEST-DUMP-001", "statement": "first"})
        await db.create_rule({"rule_id": "TEST-DUMP-002", "statement": "second"})
        await db.create_edge("RELATED_TO", "TEST-DUMP-001", "TEST-DUMP-002")

        nodes_before = await db.get_all_nodes_for_dump()
        edges_before = await db.get_all_edges_cross_type()

        script = render_cypher_dump(nodes_before, edges_before)
        await db.clear_all()
        await import_cypher_dump(db, script)

        nodes_after = await db.get_all_nodes_for_dump()
        edges_after = await db.get_all_edges_cross_type()
        assert len(nodes_after) == len(nodes_before)
        assert len(edges_after) == len(edges_before)

    @pytest.mark.asyncio
    async def test_imported_graph_has_no_staging_property_left(self, db) -> None:
        await db.create_rule({"rule_id": "TEST-DUMP-003", "statement": "third"})
        nodes_before = await db.get_all_nodes_for_dump()
        script = render_cypher_dump(nodes_before, [])
        await db.clear_all()
        await import_cypher_dump(db, script)

        nodes_after = await db.get_all_nodes_for_dump()
        assert all("_dump_id" not in n["props"] for n in nodes_after)
