"""Bulk clear (test/admin support).

Moved verbatim from the former writ/graph/db.py (Wave 2 mixin split); methods read self._driver / self._database set by Neo4jConnection.__init__."""
from __future__ import annotations



class MaintenanceStoreMixin:
    async def clear_all(self) -> None:
        """Delete ALL nodes and edges across EVERY project. For test cleanup and
        the explicit --all-projects path only. Project-scoped callers use
        clear_project (M.1) so wiping one project never touches another."""
        async with self._driver.session(database=self._database) as session:
            await session.run("MATCH (n) DETACH DELETE n")

    async def execute(self, statement: str) -> None:
        """Run a single raw Cypher statement with no return value expected.

        For the graph-dump import path (writ/graph/dump.py), which replays a
        pre-rendered script of literal CREATE/MATCH statements.
        """
        async with self._driver.session(database=self._database) as session:
            await session.run(statement)

    async def clear_project(self, project: str = "writ") -> int:
        """Delete all nodes (and their edges) for one project. M.1: the scoped
        analog of clear_all -- the safe default once the graph holds >1 project.
        Returns the node count deleted."""
        rec = await self._run_single(
            "MATCH (n) WHERE n.project = $project "
            "WITH collect(n) AS ns, count(n) AS c "
            "FOREACH (x IN ns | DETACH DELETE x) "
            "RETURN c AS deleted",
            project=project,
        )
        return rec["deleted"] if rec else 0
