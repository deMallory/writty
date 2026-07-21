"""Phase 3.5: detect_domain_enum_invariant -- node domains in a closed set.

RED-FIRST. VALID_DOMAINS = the 16 top-level bible/ rule dirs + 'routing' (the
Category tree's domain). The live corpus carries 12 non-slug domain values on 42
Rule nodes (e.g. 'AI Enforcement', 'PHP / Error Handling', casing dup
'Architecture'); each normalizes to its canonical slug, with PHP+Python+SQL-idiom
collapsed to 'languages' (maintainer decision 2026-06-14).

The validator has a Category-presence guard (mirrors detect_category_reachability)
so it skips non-corpus graphs and never false-fires on the placeholder-domain
fixtures unit tests build. Each test is isolated (TEST-ISO-001).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import pytest_asyncio

from writ.config import get_neo4j_password, get_neo4j_uri, get_neo4j_user
from writ.graph.db import Neo4jConnection
from writ.graph.ingest import discover_rule_files, parse_rules_from_file
from writ.graph.integrity import IntegrityChecker
from writ.graph.schema import VALID_DOMAINS, VALID_ROUTES

NEO4J_URI = get_neo4j_uri()
NEO4J_USER = get_neo4j_user()
NEO4J_PASSWORD = get_neo4j_password()

BIBLE_DIR = Path(__file__).resolve().parent.parent / "bible"

_A_ROUTE = sorted(VALID_ROUTES)[0]


def _make_rule(rule_id: str, domain: str) -> dict:
    return {
        "rule_id": rule_id,
        "domain": domain,
        "severity": "medium",
        "scope": "file",
        "trigger": "Default trigger.",
        "statement": "Default statement.",
        "violation": "Bad.",
        "pass_example": "Good.",
        "enforcement": "Review.",
        "rationale": "Testing.",
        "mandatory": False,
        "confidence": "production-validated",
        "evidence": "doc:original-bible",
        "staleness_window": 365,
        "last_validated": date.today().isoformat(),
    }


async def _seed_category(db: Neo4jConnection) -> None:
    """Satisfy the corpus-presence guard so the domain check actually runs."""
    await db.create_methodology_node(
        "Category", {"category_id": "CAT-TEST-001", "name": "Test", "routes": [_A_ROUTE]}
    )


@pytest_asyncio.fixture()
async def db():
    conn = Neo4jConnection(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    await conn.clear_all()
    yield conn
    await conn.clear_all()
    await conn.close()


@pytest.fixture()
def checker(db: Neo4jConnection) -> IntegrityChecker:
    return IntegrityChecker(db._driver, db._database)


class TestValidDomainsConstant:
    def test_contains_the_16_slugs_plus_routing(self) -> None:
        expected = {
            "api-design", "architecture", "code-quality", "communication",
            "database", "documentation", "enforcement", "frameworks", "languages",
            "meta-authoring", "performance", "process", "research", "scaling",
            "security", "testing", "routing",
        }
        assert expected <= VALID_DOMAINS

    def test_excludes_the_non_slug_drift_values(self) -> None:
        for bad in ("AI Enforcement", "Architecture", "Database / SQL",
                    "Frameworks / Magento 2", "PHP / Error Handling",
                    "Python / Async", "System Dynamics", "Operations"):
            assert bad not in VALID_DOMAINS


class TestDetectDomainEnumInvariant:
    @pytest.mark.asyncio
    async def test_guard_skips_when_no_category(self, db, checker) -> None:
        # No Category -> not the real corpus -> skip even with a bad domain.
        await db.create_rule(_make_rule("BAD-DOM-001", "AI Enforcement"))
        result = await checker.detect_domain_enum_invariant()
        assert result is None

    @pytest.mark.asyncio
    async def test_bad_domain_flagged_with_corpus(self, db, checker) -> None:
        await _seed_category(db)
        await db.create_rule(_make_rule("BAD-DOM-002", "AI Enforcement"))
        result = await checker.detect_domain_enum_invariant()
        assert result is not None
        assert any(d["node_id"] == "BAD-DOM-002" and d["domain"] == "AI Enforcement"
                   for d in result)

    @pytest.mark.asyncio
    async def test_good_domain_not_flagged(self, db, checker) -> None:
        await _seed_category(db)
        await db.create_rule(_make_rule("OK-DOM-001", "security"))
        result = await checker.detect_domain_enum_invariant()
        assert result is None

    @pytest.mark.asyncio
    async def test_collapsed_languages_is_valid(self, db, checker) -> None:
        await _seed_category(db)
        await db.create_rule(_make_rule("OK-DOM-002", "languages"))
        result = await checker.detect_domain_enum_invariant()
        assert result is None


class TestWiring:
    @pytest.mark.asyncio
    async def test_domain_enum_in_findings_and_exit_code(self, db, checker) -> None:
        await _seed_category(db)
        await db.create_rule(_make_rule("BAD-DOM-003", "Frameworks / Magento 2"))
        findings = await checker.run_all_checks(skip_redundancy=True)
        assert "domain_enum" in findings
        assert findings["domain_enum"]
        assert findings["exit_code"] == 1


class TestLiveCorpusDomainsValid:
    """Every Rule domain in the shipped bible must be in VALID_DOMAINS.

    RED until the 42 non-slug occurrences are normalized. Reads source directly.
    """

    def test_all_corpus_rule_domains_in_valid_set(self) -> None:
        offenders: list[tuple[str, str]] = []
        for f in discover_rule_files(BIBLE_DIR):
            if "methodology" in f.parts:
                continue
            for rule in parse_rules_from_file(f):
                dom = rule.get("domain")
                if dom is not None and dom not in VALID_DOMAINS:
                    offenders.append((rule["rule_id"], dom))
        assert offenders == [], (
            f"{len(offenders)} rule(s) with a non-slug domain: "
            + "; ".join(f"{rid}={dom!r}" for rid, dom in sorted(set(offenders)))
        )
