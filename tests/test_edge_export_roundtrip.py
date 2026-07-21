"""BUG 2: RULE-START export must render the `### Edges` section.

rule_to_markdown previously emitted no edge section, so regenerating a domain
rules.md from the graph silently dropped any declared edge (asymmetric round
trip). These tests pin:

- rule_to_markdown renders DECLARED edges (`### Edges` + `- TYPE: TARGET`).
- rule_to_markdown OMITS derived edges (RELATED_TO from prose cross-refs and
  BELONGS_TO from the **Category** field) -- rendering those would pollute every
  rule and break idempotency.
- a full ingest -> export -> re-import cycle preserves a declared edge
  (live Neo4j; RED today because export drops it).

The DECLARED edge-type set is ALLOWED_EDGE_TYPES - {RELATED_TO, BELONGS_TO}.
"""
from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest
import pytest_asyncio


# ---------------------------------------------------------------------------
# Unit: rule_to_markdown renders declared edges
# ---------------------------------------------------------------------------

def test_rule_to_markdown_renders_declared_edges() -> None:
    """A rule whose outgoing edges include a DEPENDS_ON must render an
    `### Edges` section containing `- DEPENDS_ON: <target>`.
    """
    from writ.export import rule_to_markdown

    rule = {
        "rule_id": "TEST-EXPORT-EDGE-001",
        "domain": "Testing",
        "severity": "low",
        "scope": "session",
        "trigger": "When exporting a rule with edges.",
        "statement": "Declared edges must survive export.",
        "violation": "The edge is dropped on export.",
        "pass_example": "The edge appears in an ### Edges section.",
        "enforcement": "advisory-only",
        "rationale": "Round-trip symmetry.",
    }
    edges = [{"type": "DEPENDS_ON", "target": "TEST-EXPORT-TGT-001"}]

    md = rule_to_markdown(rule, edges=edges)

    assert "### Edges" in md, f"no ### Edges section rendered:\n{md}"
    assert "- DEPENDS_ON: TEST-EXPORT-TGT-001" in md, (
        f"declared DEPENDS_ON edge not rendered:\n{md}"
    )
    # The Edges section must sit BEFORE the RULE END marker.
    assert md.index("### Edges") < md.index("<!-- RULE END:"), (
        "### Edges section rendered after the RULE END marker"
    )


def test_rule_to_markdown_omits_derived_edges() -> None:
    """RELATED_TO (derived from prose cross-refs) and BELONGS_TO (derived from
    the **Category** field) must NOT be rendered in the `### Edges` section.
    """
    from writ.export import rule_to_markdown

    rule = {
        "rule_id": "TEST-EXPORT-EDGE-002",
        "domain": "Testing",
        "category": "CAT-TESTING-001",
        "severity": "low",
        "scope": "session",
        "trigger": "When a rule has both declared and derived edges.",
        "statement": "Only declared edge types are rendered.",
        "violation": "Derived edges pollute the Edges section.",
        "pass_example": "Only DEPENDS_ON shows up.",
        "enforcement": "advisory-only",
        "rationale": "Idempotency.",
    }
    edges = [
        {"type": "DEPENDS_ON", "target": "TEST-EXPORT-TGT-001"},
        {"type": "RELATED_TO", "target": "TEST-EXPORT-OTHER-001"},
        {"type": "BELONGS_TO", "target": "CAT-TESTING-001"},
    ]

    md = rule_to_markdown(rule, edges=edges)

    assert "- DEPENDS_ON: TEST-EXPORT-TGT-001" in md, (
        f"declared DEPENDS_ON edge not rendered:\n{md}"
    )
    assert "RELATED_TO" not in md, (
        f"derived RELATED_TO leaked into export:\n{md}"
    )
    # BELONGS_TO must not appear as an edge line. (The **Category** metadata line
    # is unaffected; we only forbid the edge-declaration form.)
    assert "- BELONGS_TO:" not in md, (
        f"derived BELONGS_TO leaked into the Edges section:\n{md}"
    )


def test_declared_edge_type_set_excludes_derived() -> None:
    """Document + lock the DECLARED edge-type set used by the export filter:
    every allowed type EXCEPT the two derived ones.
    """
    from writ.export import DECLARED_EDGE_TYPES
    from writ.graph.db import ALLOWED_EDGE_TYPES

    assert DECLARED_EDGE_TYPES == (ALLOWED_EDGE_TYPES - {"RELATED_TO", "BELONGS_TO"})
    assert "RELATED_TO" not in DECLARED_EDGE_TYPES
    assert "BELONGS_TO" not in DECLARED_EDGE_TYPES
    assert "DEPENDS_ON" in DECLARED_EDGE_TYPES


# ---------------------------------------------------------------------------
# Live Neo4j: declared edge round-trips through ingest -> export -> re-import
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def _roundtrip_db(tmp_path: Path):
    """Clean graph, ingest a bible with a RULE-START `### Edges` DEPENDS_ON
    declaration (both endpoints present), yield (db, src, tgt, src_bible_dir),
    then tear down the seeded nodes.
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

    src_rule_id = "TEST-EDGE-RT-SRC-001"
    tgt_rule_id = "TEST-EDGE-RT-TGT-001"

    bible_dir = tmp_path / "bible" / "testing"
    bible_dir.mkdir(parents=True)
    rules_md = bible_dir / "rules.md"
    rules_md.write_text(
        dedent(f"""\
            <!-- RULE START: {src_rule_id} -->
            **Domain**: testing
            **Category**: CAT-TESTING-001
            **Severity**: low
            **Scope**: session

            ### Trigger
            When testing edge export round trip.

            ### Statement
            Source rule for the edge-export round-trip test.

            ### Violation
            The declared edge is dropped on export.

            ### Pass
            The declared edge survives export and re-import.

            ### Enforcement
            advisory-only

            ### Rationale
            Pins the RULE-START ### Edges export round trip.

            ### Edges
            - DEPENDS_ON: {tgt_rule_id}
            <!-- RULE END: {src_rule_id} -->

            <!-- RULE START: {tgt_rule_id} -->
            **Domain**: testing
            **Category**: CAT-TESTING-001
            **Severity**: low
            **Scope**: session

            ### Trigger
            When an edge target is needed.

            ### Statement
            Target rule for the edge-export round-trip test.

            ### Violation
            The target rule is missing from the graph.

            ### Pass
            The target rule exists so the declared edge resolves.

            ### Enforcement
            advisory-only

            ### Rationale
            Provides a resolvable endpoint for the declared edge.
            <!-- RULE END: {tgt_rule_id} -->
        """),
        encoding="utf-8",
    )

    await db.clear_all()
    await ingest_path(tmp_path / "bible", db)

    yield db, src_rule_id, tgt_rule_id, tmp_path / "bible"

    # Teardown: delete the seeded test rules, then RESTORE the shared corpus.
    # Both this fixture's setup AND the test body call clear_all() (a whole-graph
    # wipe across every project), so deleting only the 2 test rule ids would
    # leave the corpus empty for the remainder of the pytest run. Mirror the
    # pipeline_db contract (test_retrieval.py) and re-import bible/ so downstream
    # tests see a populated graph. A fixture-only clear_project switch would not
    # heal the clear_all in the test body, so restore-in-teardown is required.
    async with db._driver.session(database=db._database) as s:
        await s.run(
            "MATCH (n:Rule) WHERE n.rule_id IN $ids DETACH DELETE n",
            ids=[src_rule_id, tgt_rule_id],
        )
    await db.close()

    import subprocess
    import sys

    from tests._writ_cmd import WRIT_CMD_PREFIX

    try:
        subprocess.run(
            [*WRIT_CMD_PREFIX, "import-markdown", "bible/"],
            cwd=str(Path(__file__).resolve().parent.parent),
            capture_output=True,
            timeout=60,
            check=False,
        )
    except (subprocess.SubprocessError, OSError) as e:
        sys.stderr.write(
            "[test_edge_export_roundtrip teardown] writ import-markdown "
            f"restore failed: {e}\n"
        )


@pytest.mark.asyncio
async def test_edge_declaration_roundtrips(_roundtrip_db, tmp_path: Path) -> None:
    """Ingest a RULE-START `### Edges` declaration, export back to a tmp dir,
    assert the exported rules.md still carries the `### Edges` DEPENDS_ON line,
    and a re-import reproduces the edge in the graph.

    RED today: rule_to_markdown emits no edge section, so the exported file drops
    the declaration and the re-import recreates no edge.
    """
    from writ.export import export_rules_to_markdown
    from writ.graph.methodology_ingest import ingest_path

    db, src_rule_id, tgt_rule_id, src_bible = _roundtrip_db

    export_dir = tmp_path / "export"
    export_dir.mkdir()
    stats = await export_rules_to_markdown(db, output_dir=export_dir, bible_dir=src_bible)
    assert stats["files_written"] > 0

    # 1. The exported markdown must contain the declared edge.
    exported_text = "\n".join(
        p.read_text(encoding="utf-8") for p in sorted(export_dir.rglob("*.md"))
    )
    assert "### Edges" in exported_text, (
        f"export dropped the ### Edges section:\n{exported_text}"
    )
    assert f"- DEPENDS_ON: {tgt_rule_id}" in exported_text, (
        f"export dropped the declared DEPENDS_ON edge:\n{exported_text}"
    )

    # 2. Re-import the exported markdown into a clean graph and confirm the edge.
    await db.clear_all()
    await ingest_path(export_dir, db)
    try:
        async with db._driver.session(database=db._database) as session:
            result = await session.run(
                "MATCH (a:Rule {rule_id: $src})-[:DEPENDS_ON]->(b:Rule {rule_id: $tgt}) "
                "RETURN count(*) AS c",
                src=src_rule_id,
                tgt=tgt_rule_id,
            )
            record = await result.single()
        assert record is not None and record["c"] == 1, (
            f"re-import of the exported markdown did not reproduce the DEPENDS_ON "
            f"edge from {src_rule_id} to {tgt_rule_id}; "
            f"got count={record['c'] if record else 'no record'}"
        )
    finally:
        # The re-import wrote the rules into a non-testing bible path; clean both.
        async with db._driver.session(database=db._database) as s:
            await s.run(
                "MATCH (n:Rule) WHERE n.rule_id IN $ids DETACH DELETE n",
                ids=[src_rule_id, tgt_rule_id],
            )
