"""Abstraction node/edge CRUD.

Moved verbatim from the former writ/graph/db.py (Wave 2 mixin split); methods read self._driver / self._database set by Neo4jConnection.__init__."""
from __future__ import annotations



class AbstractionStoreMixin:
    async def create_abstraction(self, data: dict) -> str:
        """Create or update an Abstraction node. Idempotent via MERGE.

        M.2: identity is the composite (abstraction_id, project), so the same
        abstraction_id can coexist under two projects rather than the second
        write clobbering the first. project defaults to 'writ' and -- like the
        composite key on Rule -- is excluded from the SET props.
        """
        query = """
            MERGE (a:Abstraction {abstraction_id: $abstraction_id, project: $project})
            SET a += $props
            RETURN a.abstraction_id AS abstraction_id
        """
        project = data.get("project", "writ")
        props = {
            k: v for k, v in data.items() if k not in ("abstraction_id", "project")
        }
        record = await self._run_single(
            query,
            abstraction_id=data["abstraction_id"],
            project=project,
            props=props,
        )
        return record["abstraction_id"]

    async def create_abstracts_edge(
        self, abstraction_id: str, rule_id: str, project: str = "writ"
    ) -> None:
        """Create ABSTRACTS edge from Abstraction to Rule. Idempotent via MERGE.

        M.2: both endpoints are matched WITHIN $project, so the edge never
        resolves to another project's node that happens to share the same id.
        """
        query = """
            MATCH (a:Abstraction {abstraction_id: $abstraction_id, project: $project})
            MATCH (r:Rule {rule_id: $rule_id, project: $project})
            MERGE (a)-[e:ABSTRACTS]->(r)
            SET e.project = $project
        """
        async with self._driver.session(database=self._database) as session:
            await session.run(
                query, abstraction_id=abstraction_id, rule_id=rule_id, project=project
            )

    async def get_all_abstractions(self) -> list[dict]:
        """Fetch all Abstraction nodes with member rule_ids."""
        query = """
            MATCH (a:Abstraction)
            OPTIONAL MATCH (a)-[:ABSTRACTS]->(r:Rule)
            RETURN a, collect(r.rule_id) AS member_ids
            ORDER BY a.abstraction_id
        """
        async with self._driver.session(database=self._database) as session:
            result = await session.run(query)
            abstractions = []
            async for record in result:
                data = dict(record["a"])
                data["member_ids"] = record["member_ids"]
                abstractions.append(data)
            return abstractions

    async def get_abstraction(self, abstraction_id: str) -> dict | None:
        """Fetch a single Abstraction with member rule details."""
        query = """
            MATCH (a:Abstraction {abstraction_id: $abstraction_id})
            OPTIONAL MATCH (a)-[:ABSTRACTS]->(r:Rule)
            RETURN a, collect(r {.*}) AS members
        """
        record = await self._run_single(query, abstraction_id=abstraction_id)
        if record is None:
            return None
        data = dict(record["a"])
        data["members"] = [dict(m) for m in record["members"]]
        return data

    async def delete_abstractions(self, project: str | None = None) -> int:
        """Delete Abstraction nodes + their ABSTRACTS edges (Rules unaffected).

        project=None deletes every project's abstractions (backward-compatible);
        a project scopes the delete, so recompressing one project never wipes
        another's abstractions (M.2 project isolation)."""
        if project is None:
            query = "MATCH (a:Abstraction) DETACH DELETE a RETURN count(a) AS deleted"
            params: dict = {}
        else:
            query = (
                "MATCH (a:Abstraction) WHERE coalesce(a.project, 'writ') = $project "
                "DETACH DELETE a RETURN count(a) AS deleted"
            )
            params = {"project": project}
        record = await self._run_single(query, **params)
        return record["deleted"]

    async def get_rule_abstraction(self, rule_id: str) -> dict | None:
        """Return abstraction membership for a rule: abstraction_id + sibling rule_ids.

        Returns None if the rule is not a member of any abstraction.
        """
        query = """
            MATCH (a:Abstraction)-[:ABSTRACTS]->(r:Rule {rule_id: $rule_id})
            OPTIONAL MATCH (a)-[:ABSTRACTS]->(sibling:Rule)
            WHERE sibling.rule_id <> $rule_id
            RETURN a.abstraction_id AS abstraction_id,
                   collect(sibling.rule_id) AS sibling_rule_ids
        """
        record = await self._run_single(query, rule_id=rule_id)
        if record is None or record["abstraction_id"] is None:
            return None
        return {
            "abstraction_id": record["abstraction_id"],
            "sibling_rule_ids": sorted(record["sibling_rule_ids"]),
        }
