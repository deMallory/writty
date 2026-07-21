"""Decision-memory records (Decision/FileChange/Commit).

Moved verbatim from the former writ/graph/db.py (Wave 2 mixin split); methods read self._driver / self._database set by Neo4jConnection.__init__."""
from __future__ import annotations

from writ.graph.schema import Commit, Decision, FileChange
from writ.graph.db._common import _coerce_neo4j_value, _now_iso


class RecordStoreMixin:
    async def _create_record(self, model, id_field: str) -> str:
        """MERGE a decision-memory record node and return its id.

        Shared by create_decision/create_filechange/create_commit, which differ
        only by (label, id_field) and their pre-build ts handling. label and
        id_field are code-controlled (a model class name and a fixed literal),
        never user input, so interpolating them into the Cypher is safe -- the
        same controlled interpolation create_methodology_node uses; the values
        still pass as $params. label is type(model).__name__, which must equal
        the model's Neo4j node label (holds for Decision/FileChange/Commit); a
        future caller whose class name diverges from its label must not use this.
        """
        props = {
            k: _coerce_neo4j_value(v) for k, v in model.model_dump().items()
        }
        props["provenance"] = "record"
        props["source_origin"] = "graph-authored"
        label = type(model).__name__
        record = await self._run_single(
            f"MERGE (n:{label} {{{id_field}: ${id_field}, project: $project}}) "
            "SET n += $props "
            f"RETURN n.{id_field} AS {id_field}",
            **{id_field: getattr(model, id_field), "project": model.project, "props": props},
        )
        return record[id_field]

    async def create_decision(self, **decision_data) -> str:
        """Create or update a Decision record. Idempotent via MERGE on (decision_id, project)."""
        return await self._create_record(Decision(**decision_data), "decision_id")

    async def create_filechange(self, **filechange_data) -> str:
        """Create or update a FileChange record. Idempotent via MERGE on (change_id, project)."""
        filechange_data.setdefault("ts", _now_iso())
        return await self._create_record(FileChange(**filechange_data), "change_id")

    async def create_commit(self, **commit_data) -> str:
        """Create or update a Commit record. Idempotent via MERGE on (commit_hash, project)."""
        commit_data.setdefault("ts", _now_iso())
        return await self._create_record(Commit(**commit_data), "commit_hash")

    @staticmethod
    def _parse_planned_files(raw) -> list[dict]:
        """Parse the planned_files property into a list[dict].

        An empty list is stored natively (the _coerce_neo4j_value `and v` guard
        means [] never becomes the string '[]'), so handle both the JSON-string
        and the native-list forms.
        """
        import json
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except (ValueError, TypeError):
                return []
        elif isinstance(raw, list):
            parsed = raw
        else:
            return []
        return [c for c in parsed if isinstance(c, dict)]

    async def get_open_decisions_for_path(
        self, project: str, path: str
    ) -> list[dict]:
        """Decisions in `project` with an OPEN claim on `path`, most-recent first.

        A Decision matches when any planned_files entry has the given path and
        resolved is False. Results are the Decision node dicts, sorted by ts
        descending. A Decision with empty planned_files never matches.
        """
        rows = [dict(r) for r in await self._run(
            "MATCH (d:Decision {project: $project}) "
            "RETURN d.decision_id AS decision_id, d.planned_files AS planned_files, "
            "d.governing_rule_ids AS governing_rule_ids, d.ts AS ts",
            project=project,
        )]

        matches = []
        for row in rows:
            claims = self._parse_planned_files(row.get("planned_files"))
            if any(
                c.get("path") == path and c.get("resolved") is False
                for c in claims
            ):
                matches.append(row)
        matches.sort(key=lambda r: r.get("ts") or "", reverse=True)
        return matches

    async def resolve_file_claims(self, project: str, path: str) -> int:
        """Flip resolved False->True on every Decision claim for `path` in `project`.

        Read-modify-write on the JSON blob: for each matching Decision, set only
        the matching-path entries to resolved=True (never the reverse, so a re-run
        is a no-op), re-encode, and persist. Returns the number of Decisions
        updated.
        """
        import json
        async with self._driver.session(database=self._database) as session:
            result = await session.run(
                "MATCH (d:Decision {project: $project}) "
                "RETURN d.decision_id AS decision_id, d.planned_files AS planned_files",
                project=project,
            )
            rows = [dict(r) async for r in result]

            updated = 0
            for row in rows:
                claims = self._parse_planned_files(row.get("planned_files"))
                changed = False
                for claim in claims:
                    if claim.get("path") == path and claim.get("resolved") is False:
                        claim["resolved"] = True
                        changed = True
                if not changed:
                    continue
                await session.run(
                    "MATCH (d:Decision {decision_id: $decision_id, project: $project}) "
                    "SET d.planned_files = $planned_files",
                    decision_id=row["decision_id"], project=project,
                    planned_files=json.dumps(claims),
                )
                updated += 1
        return updated

    async def get_latest_filechange_per_path(
        self, project: str, paths: list[str]
    ) -> dict[str, dict]:
        """Return the most-recent FileChange reason per path for `project`.

        One batched, index-backed read (filechange_project_path) over the given
        paths. For a path with multiple FileChange records the latest by `ts`
        wins: ORDER BY n.ts DESC then collect(n)[0] (Community Edition has no
        APOC, so no apoc.agg.first). The caller passes ALREADY-NORMALIZED paths so
        the IN-list join cannot silently miss. Returns
        {path -> {reason, change_type, commit_hash, ts}} for MATCHED paths only;
        an unmatched path is simply absent (skipped, no comment).
        """
        if not paths:
            return {}
        rows = [dict(r) for r in await self._run(
            "MATCH (n:FileChange) "
            "WHERE n.project = $project AND n.path IN $paths "
            "WITH n ORDER BY n.ts DESC "
            "WITH n.path AS path, collect(n)[0] AS latest "
            "OPTIONAL MATCH (c:Commit {commit_hash: latest.commit_hash, project: $project}) "
            "RETURN path, latest.reason AS reason, "
            "latest.change_type AS change_type, "
            "latest.commit_hash AS commit_hash, latest.ts AS ts, "
            "latest.queried_rule_ids AS queried_rule_ids, "
            "latest.cited_rule_ids AS cited_rule_ids, "
            "c.subject AS commit_subject",
            project=project, paths=paths,
        )]
        return {
            row["path"]: {
                "reason": row.get("reason"),
                "change_type": row.get("change_type"),
                "commit_hash": row.get("commit_hash"),
                "ts": row.get("ts"),
                "queried_rule_ids": row.get("queried_rule_ids") or [],
                "cited_rule_ids": row.get("cited_rule_ids") or [],
                "commit_subject": row.get("commit_subject"),
            }
            for row in rows
        }

    async def get_recent_decisions(
        self, project: str, limit: int = 20
    ) -> list[dict]:
        """The most-recent Decisions in `project`, newest first (Phase 2 recall).

        One project-scoped, ts-ordered read backed by the decision_project index.
        planned_files is a JSON STRING in Community Edition (no APOC), so it is
        parsed Python-side with _parse_planned_files. Returns decision dicts with
        the fields recall renders: decision_id, title, rationale, planned_files
        (parsed), governing_rule_ids, phase, ts. Recall is intentionally a
        SEPARATE query, not /query: Decision is excluded from
        RETRIEVABLE_NODE_TYPES and must never enter the RAG pipeline.
        """
        rows = [dict(r) for r in await self._run(
            "MATCH (d:Decision {project: $project}) "
            "RETURN d.decision_id AS decision_id, d.title AS title, "
            "d.rationale AS rationale, d.planned_files AS planned_files, "
            "d.governing_rule_ids AS governing_rule_ids, "
            "d.phase AS phase, d.ts AS ts "
            "ORDER BY d.ts DESC LIMIT $limit",
            project=project, limit=limit,
        )]
        for row in rows:
            row["planned_files"] = self._parse_planned_files(
                row.get("planned_files")
            )
            row["governing_rule_ids"] = row.get("governing_rule_ids") or []
        return rows
