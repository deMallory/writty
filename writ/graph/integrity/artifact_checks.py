"""Artifact-freshness check (bible/abstractions.json vs live rules).

Moved verbatim from the former writ/graph/integrity.py (Wave 2 mixin split); methods read self._driver / self._database set by IntegrityChecker.__init__."""
from __future__ import annotations

from pathlib import Path


class ArtifactChecksMixin:
    async def detect_artifact_dangling_rule_ids(
        self, artifact_path: Path | None = None, project: str = "writ"
    ) -> list | None:
        """Freshness guard on bible/abstractions.json (Approach A).

        The cached abstraction artifact names rule_ids that must exist as Rule
        nodes in the graph. A rule_id absent from the graph is a dangling
        reference -- the artifact has drifted from the corpus (a rule was renamed
        or deleted without regenerating the artifact). Returns a list of
        {"rule_id", "abstraction_id"} for each dangling ref, or None when every
        rule_id resolves. When the artifact file is absent (no `writ compress`
        has run yet), returns None (skip). Default path is the repo-root
        bible/abstractions.json (DEFAULT_ABSTRACTIONS_ARTIFACT). Project-scoped
        existence mirrors the parity detectors' coalesce(project, 'writ') idiom.
        """
        if artifact_path is None:
            from writ.compression.abstractions import DEFAULT_ABSTRACTIONS_ARTIFACT

            artifact_path = DEFAULT_ABSTRACTIONS_ARTIFACT
        if not artifact_path.exists() or self._driver is None:
            return None

        # Corpus-presence guard (mirrors detect_domain_enum_invariant /
        # detect_floor_completeness): the artifact describes the real corpus,
        # so checking it against a crafted unit-test graph of a few rules would
        # false-fire every rule_id as dangling. The real corpus always carries
        # Category nodes; a crafted test graph does not. Skip when absent.
        if await self.get_category_count() == 0:
            return None

        import json as _json

        data = _json.loads(artifact_path.read_text(encoding="utf-8"))
        artifact_project = data.get("project", project)
        abstractions = data.get("abstractions", [])

        referenced: set[str] = set()
        for abst in abstractions:
            for rid in abst.get("rule_ids", []):
                referenced.add(rid)
        if not referenced:
            return None

        async with self._driver.session(database=self._database) as session:
            result = await session.run(
                "MATCH (r:Rule) WHERE coalesce(r.project, 'writ') = $project "
                "AND r.rule_id IN $ids RETURN r.rule_id AS rule_id",
                project=artifact_project,
                ids=sorted(referenced),
            )
            present = {record["rule_id"] async for record in result}

        dangling: list[dict] = []
        for abst in abstractions:
            abs_id = abst.get("abstraction_id")
            for rid in abst.get("rule_ids", []):
                if rid not in present:
                    dangling.append({"rule_id": rid, "abstraction_id": abs_id})
        return dangling or None
