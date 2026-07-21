"""Change A: RULE-START blocks support an ### Edges section.

Today parse_rules_from_file ignores any `### Edges` section.  The incoming
change adds that section to SECTION_HEADERS and teaches _parse_rule_block to
emit declared edges from lines of the form `- TYPE: TARGET-ID`.

All three tests are RED until the parser is updated.
"""
from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BIBLE = Path(__file__).resolve().parent.parent / "bible"

_MINIMAL_RULE_BLOCK = dedent("""\
    <!-- RULE START: TEST-EDGE-001 -->
    **Domain**: testing
    **Severity**: low
    **Scope**: session

    ### Trigger
    When an edge declaration test runs.

    ### Statement
    This rule exists only to test edge declarations.

    ### Edges
    - DEPENDS_ON: TGT-001
    - SUPPLEMENTS: TGT-002
    <!-- RULE END: TEST-EDGE-001 -->
""")

_RULE_BLOCK_MALFORMED_EDGES = dedent("""\
    <!-- RULE START: TEST-EDGE-002 -->
    **Domain**: testing
    **Severity**: low
    **Scope**: session

    ### Trigger
    When a malformed edge section test runs.

    ### Statement
    This rule has a malformed Edges section.

    ### Edges
    This line is prose and should be silently skipped.
    - DEPENDS_ON: GOOD-TARGET-001
    Also this line has no dash prefix.
    <!-- RULE END: TEST-EDGE-002 -->
""")


# ---------------------------------------------------------------------------
# Test A1: unit -- parse path emits declared edges from ### Edges section
# ---------------------------------------------------------------------------

class TestRuleStartEdgesSectionParsed:
    """parse_rules_from_file (or the declared-edge surface it exposes) must
    return the two edges declared under ### Edges in a RULE-START block.

    RED today: SECTION_HEADERS does not contain 'edges', so _parse_rule_block
    never populates `_declared_edges` (or the equivalent field); the parse
    result for the block contains no edge data.
    """

    def test_rule_start_edges_section_parsed(self, tmp_path: Path) -> None:
        """A RULE-START block with a `### Edges` section yields both declared
        edges in the parsed result, with correct source/target/type values.
        """
        from writ.graph.ingest import parse_rules_from_file

        md = tmp_path / "rules.md"
        md.write_text(_MINIMAL_RULE_BLOCK, encoding="utf-8")

        rules = parse_rules_from_file(md)
        assert len(rules) == 1, (
            f"Expected 1 parsed rule, got {len(rules)}"
        )
        rule = rules[0]
        assert rule["rule_id"] == "TEST-EDGE-001"

        # The declared edges should be on the parsed result under
        # `_declared_edges` (matching the cross-reference key convention) or
        # under an `edges` key -- whatever surface the implementer chooses.
        # The test checks both candidate keys to avoid being over-specific
        # about the internal key name while still being explicit about content.
        declared_edges = rule.get("_declared_edges") or rule.get("edges") or []
        assert len(declared_edges) == 2, (
            f"Expected 2 declared edges on TEST-EDGE-001, got {len(declared_edges)}: "
            f"{declared_edges!r}"
        )

        edge_set = {(e["source"], e["type"], e["target"]) for e in declared_edges}
        assert ("TEST-EDGE-001", "DEPENDS_ON", "TGT-001") in edge_set, (
            f"DEPENDS_ON edge to TGT-001 missing from {edge_set!r}"
        )
        assert ("TEST-EDGE-001", "SUPPLEMENTS", "TGT-002") in edge_set, (
            f"SUPPLEMENTS edge to TGT-002 missing from {edge_set!r}"
        )


# ---------------------------------------------------------------------------
# Test A2: end-to-end -- live Neo4j (mirrors db_corpus fixture shape)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def _edge_decl_db(tmp_path: Path):
    """Spin up a clean Neo4j graph, ingest a minimal bible containing a
    RULE-START block with an `### Edges` declaration to a real existing target
    id, yield the (db, target_id) pair, then tear down the seeded nodes.
    """
    pytest.importorskip("neo4j")
    from writ.config import get_neo4j_password, get_neo4j_uri, get_neo4j_user
    from writ.graph.db import Neo4jConnection
    from writ.graph.methodology_ingest import ingest_path

    db = Neo4jConnection(get_neo4j_uri(), get_neo4j_user(), get_neo4j_password())
    try:
        async with db._driver.session(database=db._database) as s:
            await (await s.run("RETURN 1 AS ok")).consume()
    except Exception:
        await db.close()
        pytest.skip("Neo4j unreachable")

    # Use a source rule that actually exists in the real corpus so the
    # declared edge target is resolvable. Pick one that is unlikely to be
    # removed: ENF-COMMS-001 exists in the real bible.
    target_rule_id = "ENF-COMMS-001"
    source_rule_id = "TEST-EDGEDECL-E2E-001"

    # Build a minimal bible dir containing one rules.md with both the source
    # rule (declares an edge) and the target rule (edge destination).
    bible_dir = tmp_path / "bible" / "testing"
    bible_dir.mkdir(parents=True)
    rules_md = bible_dir / "rules.md"
    rules_md.write_text(
        dedent(f"""\
            <!-- RULE START: {source_rule_id} -->
            **Domain**: testing
            **Severity**: low
            **Scope**: session

            ### Trigger
            When testing edge declarations end-to-end.

            ### Statement
            Source rule for edge-declaration end-to-end test.

            ### Violation
            The edge declaration is ignored on ingest.

            ### Pass
            The declared edge is written to the graph.

            ### Enforcement
            advisory-only

            ### Rationale
            Pins the RULE-START ### Edges ingest path end to end.

            ### Edges
            - DEPENDS_ON: {target_rule_id}
            <!-- RULE END: {source_rule_id} -->

            <!-- RULE START: {target_rule_id} -->
            **Domain**: testing
            **Severity**: low
            **Scope**: session

            ### Trigger
            When an edge target is needed.

            ### Statement
            Target rule for edge-declaration end-to-end test.

            ### Violation
            The target rule is missing from the graph.

            ### Pass
            The target rule exists so the declared edge resolves.

            ### Enforcement
            advisory-only

            ### Rationale
            Provides a resolvable endpoint for the declared edge.
            <!-- RULE END: {target_rule_id} -->
        """),
        encoding="utf-8",
    )

    await db.clear_all()
    await ingest_path(tmp_path / "bible", db)

    yield db, source_rule_id, target_rule_id

    # Teardown: delete the seeded nodes.
    async with db._driver.session(database=db._database) as s:
        await s.run(
            "MATCH (n:Rule) WHERE n.rule_id IN $ids DETACH DELETE n",
            ids=[source_rule_id, target_rule_id],
        )
    await db.close()


@pytest.mark.asyncio
async def test_rule_start_edges_end_to_end(_edge_decl_db) -> None:
    """After ingesting a RULE-START block with a `### Edges` declaration, the
    declared edge must exist in Neo4j as a live relationship.

    RED today: parse_rules_from_file ignores `### Edges`, so ingest_edges never
    sees the declaration and no edge is written.
    """
    db, source_rule_id, target_rule_id = _edge_decl_db

    # Query for the DEPENDS_ON edge that the ### Edges section declared.
    async with db._driver.session(database=db._database) as session:
        result = await session.run(
            "MATCH (a:Rule {rule_id: $src})-[:DEPENDS_ON]->(b:Rule {rule_id: $tgt}) "
            "RETURN count(*) AS c",
            src=source_rule_id,
            tgt=target_rule_id,
        )
        record = await result.single()

    assert record is not None and record["c"] == 1, (
        f"Expected a DEPENDS_ON edge from {source_rule_id} to {target_rule_id} "
        "in Neo4j after ingesting a RULE-START block with a ### Edges section; "
        f"got count={record['c'] if record else 'no record'}"
    )


# ---------------------------------------------------------------------------
# Test A3: malformed lines in ### Edges section are skipped without error
# ---------------------------------------------------------------------------

class TestMalformedEdgesSectionIgnored:
    """Lines in `### Edges` that are not `- TYPE: ID` must be silently skipped;
    the parse must not raise, and well-formed lines in the same section are
    still parsed.

    RED today: SECTION_HEADERS does not include 'edges' at all, so the
    `### Edges` section content is never processed.  The test is written to
    check the post-implementation behavior: malformed prose lines produce no
    edge records, the one valid line is emitted, and no exception is raised.
    """

    def test_malformed_edges_section_ignored(self, tmp_path: Path) -> None:
        from writ.graph.ingest import parse_rules_from_file

        md = tmp_path / "rules.md"
        md.write_text(_RULE_BLOCK_MALFORMED_EDGES, encoding="utf-8")

        # Must not raise.
        rules = parse_rules_from_file(md)
        assert len(rules) == 1

        rule = rules[0]
        declared_edges = rule.get("_declared_edges") or rule.get("edges") or []

        # The one well-formed line `- DEPENDS_ON: GOOD-TARGET-001` must be present.
        assert len(declared_edges) == 1, (
            f"Expected exactly 1 declared edge (only the well-formed line), "
            f"got {len(declared_edges)}: {declared_edges!r}"
        )
        edge = declared_edges[0]
        assert edge["type"] == "DEPENDS_ON"
        assert edge["target"] == "GOOD-TARGET-001"


# ---------------------------------------------------------------------------
# Test A4 (BUG 1): the `### Edges` section MUST NOT leak its target ids into
# the prose cross-reference scan, which would derive a spurious RELATED_TO edge
# to the same target alongside the intended typed edge.
# ---------------------------------------------------------------------------

_RULE_BLOCK_EDGE_ONLY_TARGET = dedent("""\
    <!-- RULE START: ZZZ-CROSSREF-SRC-001 -->
    **Domain**: testing
    **Severity**: low
    **Scope**: session

    ### Trigger
    When the cross-ref scan runs over a block with an Edges section.

    ### Statement
    The declared edge target must not also appear as a prose cross-reference.

    ### Edges
    - DEPENDS_ON: ZZZ-CROSSREF-TGT-001
    <!-- RULE END: ZZZ-CROSSREF-SRC-001 -->
""")


class TestEdgesSectionNotCrossReferenced:
    """A target id that appears ONLY inside the `### Edges` section must produce
    the declared typed edge but NOT a derived RELATED_TO cross-reference edge.

    RED today: _extract_cross_refs / CROSS_REF_PATTERN scans the entire block
    text including the `### Edges` section, so `ZZZ-CROSSREF-TGT-001` is captured
    as a `_cross_reference`, and derive_edges emits a spurious RELATED_TO edge to
    the same target.
    """

    def test_declared_edge_target_not_in_cross_references(self, tmp_path: Path) -> None:
        """The parsed rule's `_cross_references` must NOT contain the edge-only
        target id (it appears nowhere in prose).
        """
        from writ.graph.ingest import parse_rules_from_file

        md = tmp_path / "rules.md"
        md.write_text(_RULE_BLOCK_EDGE_ONLY_TARGET, encoding="utf-8")

        rules = parse_rules_from_file(md)
        assert len(rules) == 1
        rule = rules[0]

        cross_refs = rule.get("_cross_references", [])
        assert "ZZZ-CROSSREF-TGT-001" not in cross_refs, (
            "edge-only target id leaked into prose cross-references: "
            f"{cross_refs!r}"
        )

        declared = rule.get("_declared_edges") or rule.get("edges") or []
        edge_set = {(e["type"], e["target"]) for e in declared}
        assert ("DEPENDS_ON", "ZZZ-CROSSREF-TGT-001") in edge_set, (
            f"declared DEPENDS_ON edge missing from {edge_set!r}"
        )

    def test_no_spurious_related_to_for_declared_edge(self, tmp_path: Path) -> None:
        """After derive_edges, there must be a DEPENDS_ON edge to the target and
        NO RELATED_TO edge to the same target.

        Both endpoints exist as parsed Rule nodes so the typed edge survives the
        known-id filter; the absence of a RELATED_TO proves the `### Edges`
        section did not leak into the prose cross-ref scan.
        """
        from writ.graph.ingest import parse_rules_from_file
        from writ.graph.methodology_ingest import derive_edges

        # Source block declares the edge; a sibling block supplies the target so
        # both endpoints are known ids (RELATED_TO derivation only fires for a
        # cross-ref whose target is itself a parsed rule id).
        src_block = _RULE_BLOCK_EDGE_ONLY_TARGET
        tgt_block = dedent("""\
            <!-- RULE START: ZZZ-CROSSREF-TGT-001 -->
            **Domain**: testing
            **Severity**: low
            **Scope**: session

            ### Trigger
            When a cross-ref edge target is needed.

            ### Statement
            Resolvable endpoint for the declared edge.
            <!-- RULE END: ZZZ-CROSSREF-TGT-001 -->
        """)
        md = tmp_path / "rules.md"
        md.write_text(src_block + "\n" + tgt_block, encoding="utf-8")

        rules = parse_rules_from_file(md)
        for r in rules:
            r.setdefault("node_type", "Rule")
        known_ids = {r["rule_id"] for r in rules}

        declared_edges: list[dict] = []
        for r in rules:
            declared_edges.extend(r.get("_declared_edges", []))

        edges, _dangling = derive_edges(rules, declared_edges, known_ids)
        edge_set = {(e["type"], e["source"], e["target"]) for e in edges}

        assert ("DEPENDS_ON", "ZZZ-CROSSREF-SRC-001", "ZZZ-CROSSREF-TGT-001") in edge_set, (
            f"expected declared DEPENDS_ON edge, got {edge_set!r}"
        )
        assert ("RELATED_TO", "ZZZ-CROSSREF-SRC-001", "ZZZ-CROSSREF-TGT-001") not in edge_set, (
            "spurious RELATED_TO edge derived from an edge-only target id: "
            f"{edge_set!r}"
        )
