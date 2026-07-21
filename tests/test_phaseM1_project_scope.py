"""Phase M.1: the multi-project data-loss KEYSTONE.

RED-FIRST. reconcile() is a whole-graph source-of-truth machine -- it
DETACH-DELETEs every live node not in the single bible it is handed. With no
project dimension, reconciling project 1 would DELETE project 2. This pins the
fix: a `project` property on every node+edge + project-scoped reconcile/parity/
clear, defaulting to 'writ' (today's single-project behavior is unchanged).

THE KEYSTONE TEST: absorb a 2nd project, reconcile the 1st, the 2nd survives.

Each test isolated (TEST-ISO-001).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from writ.config import get_neo4j_password, get_neo4j_uri, get_neo4j_user
from writ.graph.db import Neo4jConnection
from writ.graph.integrity import IntegrityChecker
from writ.graph.methodology_ingest import ingest_path, reconcile

NEO4J_URI = get_neo4j_uri()
NEO4J_USER = get_neo4j_user()
NEO4J_PASSWORD = get_neo4j_password()


def _rule_md(rule_id: str, domain: str = "security") -> str:
    return f"""<!-- RULE START: {rule_id} -->
## Rule {rule_id}

**Domain**: {domain}
**Severity**: Medium
**Scope**: Component

### Trigger
When a thing happens.

### Statement
A statement for {rule_id}.

### Violation
```python
x = 1
```

### Pass
```python
y = 2
```

### Enforcement
Code review.

### Rationale
A rationale for {rule_id}.

<!-- RULE END: {rule_id} -->
"""


def _make_bible(tmp: Path, name: str, rule_ids: list[str]) -> Path:
    d = tmp / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "rules.md").write_text("\n".join(_rule_md(r) for r in rule_ids), encoding="utf-8")
    return d


async def _project_of(db: Neo4jConnection, rule_id: str) -> str | None:
    async with db._driver.session(database=db._database) as s:
        res = await s.run("MATCH (r:Rule {rule_id: $id}) RETURN r.project AS p", id=rule_id)
        rec = await res.single()
        return rec["p"] if rec else "__absent__"


async def _exists(db: Neo4jConnection, rule_id: str) -> bool:
    async with db._driver.session(database=db._database) as s:
        res = await s.run("MATCH (r:Rule {rule_id: $id}) RETURN count(r) AS c", id=rule_id)
        return (await res.single())["c"] > 0


@pytest_asyncio.fixture()
async def db():
    conn = Neo4jConnection(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    await conn.clear_all()
    yield conn
    await conn.clear_all()
    await conn.close()


class TestProjectStamping:
    @pytest.mark.asyncio
    async def test_ingest_stamps_default_project_writ(self, db, tmp_path) -> None:
        b = _make_bible(tmp_path, "writ", ["PROJ-DEF-001"])
        await ingest_path(b, db)  # default project
        assert await _project_of(db, "PROJ-DEF-001") == "writ"

    @pytest.mark.asyncio
    async def test_ingest_stamps_explicit_project(self, db, tmp_path) -> None:
        b = _make_bible(tmp_path, "proj2", ["PROJ-EXP-001"])
        await ingest_path(b, db, project="proj2")
        assert await _project_of(db, "PROJ-EXP-001") == "proj2"


class TestKeystoneReconcileScoped:
    @pytest.mark.asyncio
    async def test_reconcile_project1_does_not_delete_project2(self, db, tmp_path) -> None:
        b1 = _make_bible(tmp_path, "writ", ["P1-A-001", "P1-B-001"])
        b2 = _make_bible(tmp_path, "proj2", ["P2-A-001", "P2-B-001"])
        await ingest_path(b1, db, project="writ")
        await ingest_path(b2, db, project="proj2")

        # Reconcile project 'writ' against its OWN bible. Project 2 must survive.
        await reconcile(b1, db, project="writ")

        assert await _exists(db, "P2-A-001"), "KEYSTONE BREACH: reconcile deleted project 2"
        assert await _exists(db, "P2-B-001"), "KEYSTONE BREACH: reconcile deleted project 2"
        assert await _exists(db, "P1-A-001")
        assert await _exists(db, "P1-B-001")

    @pytest.mark.asyncio
    async def test_reconcile_still_prunes_within_project(self, db, tmp_path) -> None:
        # A node present in project 'writ' but ABSENT from its bible is pruned.
        b1_full = _make_bible(tmp_path, "writ", ["KEEP-A-001", "STALE-A-001"])
        await ingest_path(b1_full, db, project="writ")
        b1_trim = _make_bible(tmp_path, "writ_trim", ["KEEP-A-001"])
        await reconcile(b1_trim, db, project="writ")
        assert await _exists(db, "KEEP-A-001")
        assert not await _exists(db, "STALE-A-001"), "in-project prune must still work"


class TestParityScoped:
    @pytest.mark.asyncio
    async def test_parity_does_not_flag_other_project(self, db, tmp_path) -> None:
        b1 = _make_bible(tmp_path, "writ", ["PAR-A-001"])
        b2 = _make_bible(tmp_path, "proj2", ["PAR-B-001"])
        await ingest_path(b1, db, project="writ")
        await ingest_path(b2, db, project="proj2")
        checker = IntegrityChecker(db._driver, db._database)
        # Parity for 'writ' against b1: PAR-B-001 (another project) must NOT be
        # flagged as "absent from markdown".
        violations = await checker.detect_parity_violations(b1, project="writ")
        ids = {v.get("id") for v in violations}
        assert "PAR-B-001" not in ids, "parity false-flagged another project's node"


class TestClearProject:
    @pytest.mark.asyncio
    async def test_clear_project_scopes_to_one_project(self, db, tmp_path) -> None:
        b1 = _make_bible(tmp_path, "writ", ["CLR-A-001"])
        b2 = _make_bible(tmp_path, "proj2", ["CLR-B-001"])
        await ingest_path(b1, db, project="writ")
        await ingest_path(b2, db, project="proj2")
        await db.clear_project("proj2")
        assert await _exists(db, "CLR-A-001")
        assert not await _exists(db, "CLR-B-001")
