"""Change B: Abstraction nodes are exempt from node-presence parity.

detect_parity_violations currently flags any graph node whose id is absent from
every *.md file. Abstraction nodes are materialized views created by
`writ compress` -- they are never written to bible/ source by design.

Both tests are RED today: detect_parity_violations does not exempt nodes whose
label is 'Abstraction', so a seeded Abstraction node with no bible source IS
flagged (and therefore run_all_checks sets exit_code=1).
"""
from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

BIBLE = Path(__file__).resolve().parent.parent / "bible"

# Sentinel id for the Abstraction node seeded in each test.
_ABS_ID = "ZZZ-ABS-PARITYTEST-001"


# ---------------------------------------------------------------------------
# Fixture: clean graph + ingest + seed one Abstraction node, then clean up
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def db_with_abstraction():
    """Clean corpus + one seeded Abstraction node that has no bible source.

    Follows the db_corpus fixture shape from test_phase52a_field_drift.py:
    - skip if Neo4j unreachable
    - clear_all + ingest_path
    - seed the Abstraction
    - yield db
    - teardown: delete the seeded node
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

    await db.clear_all()
    await ingest_path(BIBLE, db)

    # Seed an Abstraction node that has NO corresponding bible/ source file.
    # Shape matches what write_abstractions_to_graph passes to create_abstraction:
    # abstraction_id, summary, domain, compression_ratio, rule_count, project.
    await db.create_abstraction({
        "abstraction_id": _ABS_ID,
        "summary": "Parity test abstraction -- not written to bible source.",
        "domain": "testing",
        "compression_ratio": 0.5,
        "rule_count": 2,
        "project": "writ",
    })

    yield db

    # Teardown: remove the seeded Abstraction node.
    async with db._driver.session(database=db._database) as s:
        await s.run(
            "MATCH (a:Abstraction {abstraction_id: $id}) DETACH DELETE a",
            id=_ABS_ID,
        )
    await db.close()


# ---------------------------------------------------------------------------
# Test B1: Abstraction NOT flagged as parity violation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_abstraction_not_flagged_as_parity_violation(
    db_with_abstraction,
) -> None:
    """detect_parity_violations must not include the seeded Abstraction node.

    RED today: there is no Abstraction exemption, so the node is returned as a
    violation ({type: 'Abstraction', id: _ABS_ID}).
    """
    from writ.graph.integrity import IntegrityChecker

    db = db_with_abstraction
    checker = IntegrityChecker(db._driver, db._database)
    violations = await checker.detect_parity_violations(BIBLE)

    violation_ids = {v["id"] for v in violations}
    assert _ABS_ID not in violation_ids, (
        f"Abstraction node {_ABS_ID!r} was flagged as a parity violation but "
        "Abstraction nodes are graph-only materialized views with no bible source. "
        f"Full violation set: {sorted(violation_ids)!r}"
    )


# ---------------------------------------------------------------------------
# Test B2: run_all_checks does NOT set exit_code=1 due to the Abstraction
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_all_checks_clean_with_abstraction(
    db_with_abstraction,
) -> None:
    """After seeding one Abstraction node (no other drift), run_all_checks must
    not set exit_code=1 solely because of the Abstraction.

    RED today: parity_violations is non-empty (contains the Abstraction node),
    which triggers the `if findings["parity_violations"]: has_issues = True` branch
    and causes exit_code=1.
    """
    from writ.graph.integrity import IntegrityChecker

    db = db_with_abstraction
    checker = IntegrityChecker(db._driver, db._database)
    # skip_redundancy=True avoids the sentence-transformers optional-dep path
    # in CI; other checks still run (including parity).
    findings = await checker.run_all_checks(
        skip_redundancy=True,
        bible_dir=BIBLE,
        project="writ",
    )

    exit_code = findings.get("exit_code", 0)
    parity = findings.get("parity_violations", [])
    abs_violations = [v for v in parity if v.get("id") == _ABS_ID]

    assert not abs_violations, (
        f"Abstraction node {_ABS_ID!r} appeared in parity_violations inside "
        f"run_all_checks; Abstraction nodes must be exempt. "
        f"abs_violations={abs_violations!r}"
    )
    assert exit_code == 0, (
        f"run_all_checks returned exit_code={exit_code} after seeding an Abstraction "
        "node with no bible source. Abstraction nodes are graph-only and must not "
        "cause an exit_code=1. "
        f"parity_violations={parity!r}"
    )
