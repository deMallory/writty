"""Rule-content lint & closed-vocabulary invariants.

Moved verbatim from the former writ/graph/integrity.py (Wave 2 mixin split); methods read self._driver / self._database set by IntegrityChecker.__init__."""
from __future__ import annotations

from writ.graph.integrity._common import (
    VALID_DOMAINS,
    _GRAPH_ID_COALESCE,
    _normalized_code_blocks,
    lint_rule_examples,
)


class ContentChecksMixin:
    async def detect_example_lint(self) -> dict | None:
        """3.2: every python example must parse; no deprecated-v1 API in PASS.

        Operates on Rule nodes' violation/pass_example fields. Returns None when
        clean, else {rule_id: [finding, ...]}. See lint_rule_examples for the
        per-rule logic and the dropped-checks rationale.
        """
        if self._driver is None:
            return None
        out: dict[str, list[dict]] = {}
        async with self._driver.session(database=self._database) as session:
            res = await session.run(
                "MATCH (r:Rule) RETURN r.rule_id AS rid, r.violation AS v, "
                "r.pass_example AS p"
            )
            async for r in res:
                findings = lint_rule_examples(r["rid"], r["v"], r["p"])
                if findings:
                    out[r["rid"]] = findings
        return out or None

    async def detect_domain_enum_invariant(self) -> list[dict] | None:
        """3.5: every node's `domain` must be in the closed VALID_DOMAINS set.

        Catches taxonomy drift (non-slug `AI Enforcement`, casing dup
        `Architecture`, granular `PHP / Error Handling`). Corpus-presence
        guard: skips when no Category nodes exist (mirrors
        detect_category_reachability) so it never false-fires on the small
        crafted graphs unit tests build with placeholder domains. Returns the
        offending [{node_id, label, domain}] sorted; None when clean/skipped.
        """
        if self._driver is None:
            return None
        nid = _GRAPH_ID_COALESCE.format(v="n")
        async with self._driver.session(database=self._database) as session:
            cats = await session.run("MATCH (c:Category) RETURN count(c) AS c")
            if (await cats.single())["c"] == 0:
                return None  # not the real corpus -- skip
            res = await session.run(
                f"MATCH (n) WHERE n.domain IS NOT NULL AND NOT n.domain IN $valid "
                f"RETURN {nid} AS id, labels(n)[0] AS label, n.domain AS domain",
                valid=sorted(VALID_DOMAINS),
            )
            bad = [
                {"node_id": r["id"], "label": r["label"], "domain": r["domain"]}
                async for r in res
            ]
        return sorted(bad, key=lambda d: (d["domain"], d["node_id"])) or None

    async def detect_enforceable_severity_coupling(self) -> list[dict] | None:
        """3.1: a critical/high rule WITH a mechanical_enforcement_path must be
        mandatory.

        Severity = how bad the violation; mandatory = whether a machine can catch
        it out-of-band. A rule that IS mechanically enforceable (carries an MEP)
        yet is left advisory is the flag -- it should be always-on. This LOCKS a
        MEASURED-0 state (all 27 MEP-bearing rules are already mandatory), so a
        future authored enforceable critical can't silently land advisory. Bulk
        reclassification of advisory critical/high rules WITHOUT an MEP is policy
        (severity alone is NOT the trigger) and explicitly out of scope. Returns
        [{rule_id, severity}]; None when clean.
        """
        if self._driver is None:
            return None
        async with self._driver.session(database=self._database) as session:
            res = await session.run(
                "MATCH (r:Rule) WHERE toLower(r.severity) IN ['critical', 'high'] "
                "AND r.mechanical_enforcement_path IS NOT NULL "
                "AND r.mechanical_enforcement_path <> '' "
                "AND coalesce(r.mandatory, false) = false "
                "RETURN r.rule_id AS id, r.severity AS sev ORDER BY id"
            )
            bad = [{"rule_id": r["id"], "severity": r["sev"]} async for r in res]
        return bad or None

    async def detect_forbidden_phrase_overlap(self) -> list[dict] | None:
        """3.3: a forbidden phrase must belong to exactly one ForbiddenResponse.

        A phrase in >1 FRB node blurs the node boundaries (e.g. FRB-COMMS-001
        'performative agreement' vs FRB-COMMS-002 'unverified success claims'
        both carrying the same success-claim phrases). Returns [{phrase, nodes}];
        None when clean. Comparison is case-insensitive on the stripped phrase.
        """
        if self._driver is None:
            return None
        from collections import defaultdict
        by_phrase: dict[str, set] = defaultdict(set)
        async with self._driver.session(database=self._database) as session:
            res = await session.run(
                "MATCH (f:ForbiddenResponse) "
                "RETURN f.forbidden_id AS id, f.forbidden_phrases AS phrases"
            )
            async for r in res:
                for p in (r["phrases"] or []):
                    by_phrase[p.strip().lower()].add(r["id"])
        out = [
            {"phrase": p, "nodes": sorted(ids)}
            for p, ids in by_phrase.items() if len(ids) > 1
        ]
        return sorted(out, key=lambda d: d["phrase"]) or None

    async def detect_shared_code_example(self, min_len: int = 40) -> list[dict] | None:
        """3.3: a verbatim code example must not appear in >1 rule.

        Two rules carrying an identical (whitespace-normalized) fenced block are
        a dedup signal the cosine-0.95 redundancy gate misses (the dedup-gate-gap:
        measured max pair-cosine ~0.76 << 0.95). Either differentiate the example
        or merge/cross-link the rules. Returns [{rules, block}]; None when clean.
        """
        if self._driver is None:
            return None
        from collections import defaultdict
        by_block: dict[str, set] = defaultdict(set)
        async with self._driver.session(database=self._database) as session:
            res = await session.run(
                "MATCH (r:Rule) RETURN r.rule_id AS id, r.violation AS v, "
                "r.pass_example AS p"
            )
            async for r in res:
                for fld in ("v", "p"):
                    for block in _normalized_code_blocks(r[fld], min_len):
                        by_block[block].add(r["id"])
        out = [
            {"rules": sorted(ids), "block": b[:120]}
            for b, ids in by_block.items() if len(ids) > 1
        ]
        return sorted(out, key=lambda d: d["rules"]) or None
