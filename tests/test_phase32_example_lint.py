"""Phase 3.2: detect_example_lint -- every python code example must be valid.

RED-FIRST. Two enforced sub-checks (scope settled by a deterministic ast.parse
survey of all 372 python example blocks, 2026-06-14):

  1. ast.parse validity -- every ```python block in a rule's Violation or Pass
     section must parse. Witnessed RED by TEST-FIXTURE-001 (the '...' shorthand
     placed as a positional-after-keyword arg and as a bare dict element).
  2. no deprecated Pydantic-v1 API in a PASS example -- a prescriptive "correct"
     example must not teach from_orm / .dict() / .parse_obj / @validator on a
     Pydantic-2.12 stack. Scoped to pass_example only: a Violation block may use
     bad API incidentally (its lesson is a different defect). Witnessed RED by
     SOLID-SRP-002, SEC-AUTHZ-MASS-001, SEC-DATA-PII-002, SEC-VAL-TYPE-001,
     SEC-RATE-BATCH-001.

DROPPED (evidence-backed, pinned here so they are not re-added):
  - prose-only blocks: 37 occurrences, a deliberate authoring style for
    cross-file / architectural / missing-header scenarios. NOT a defect class.
  - {placeholder} in a plain string: fires on legitimate framework route
    patterns ('/users/{user_id}'). Over-fires; dropped.

Fixtures avoid literal route-handler / mass-assignment shapes so the pre-write
auth-scan hook does not flag this test's own example strings.

Requires Neo4j running with test data. Each test is isolated (TEST-ISO-001).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import pytest_asyncio

from writ.config import get_neo4j_password, get_neo4j_uri, get_neo4j_user
from writ.graph.db import Neo4jConnection
from writ.graph.ingest import discover_rule_files, parse_rules_from_file
from writ.graph.integrity import IntegrityChecker, lint_rule_examples

NEO4J_URI = get_neo4j_uri()
NEO4J_USER = get_neo4j_user()
NEO4J_PASSWORD = get_neo4j_password()

BIBLE_DIR = Path(__file__).resolve().parent.parent / "bible"


def _make_rule(rule_id: str, violation: str, pass_example: str) -> dict:
    return {
        "rule_id": rule_id,
        "domain": "test",
        "severity": "medium",
        "scope": "file",
        "trigger": "Default trigger.",
        "statement": "Default statement.",
        "violation": violation,
        "pass_example": pass_example,
        "enforcement": "Review.",
        "rationale": "Testing.",
        "mandatory": False,
        "confidence": "production-validated",
        "evidence": "doc:original-bible",
        "staleness_window": 365,
        "last_validated": date.today().isoformat(),
    }


def _fence(code: str, lang: str = "python") -> str:
    return f"```{lang}\n{code}\n```"


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


# --- Pure-function logic tests (no graph) -------------------------------------


class TestLintRuleExamplesPure:
    """The pure lint over (violation, pass_example) text."""

    def test_valid_python_is_clean(self) -> None:
        findings = lint_rule_examples(
            "OK-001",
            _fence("def f(x):\n    return x + 1"),
            _fence("def g(y):\n    return y * 2"),
        )
        assert findings == []

    def test_syntax_error_in_violation_flagged(self) -> None:
        findings = lint_rule_examples(
            "BAD-001",
            _fence("def f(a=1, b):\n    return a"),  # non-default after default
            _fence("x = 1"),
        )
        kinds = {(f["field"], f["kind"]) for f in findings}
        assert ("violation", "syntax") in kinds

    def test_syntax_error_in_pass_flagged(self) -> None:
        findings = lint_rule_examples(
            "BAD-002",
            _fence("x = 1"),
            _fence("d = {'a': 1, ...}"),  # bare ellipsis dict element
        )
        kinds = {(f["field"], f["kind"]) for f in findings}
        assert ("pass_example", "syntax") in kinds

    def test_positional_after_keyword_flagged(self) -> None:
        # The exact TEST-FIXTURE-001 violation shape.
        findings = lint_rule_examples(
            "BAD-003",
            _fence("u = make(name='a', age=30, ...)  # 20 fields"),
            _fence("u = make(name='a')"),
        )
        assert any(f["kind"] == "syntax" and f["field"] == "violation" for f in findings)

    def test_deprecated_from_orm_in_pass_flagged(self) -> None:
        findings = lint_rule_examples(
            "DEP-001",
            _fence("x = 1"),
            _fence("out = UserPublic.from_orm(user)"),
        )
        assert any(f["kind"] == "deprecated_api" and f["field"] == "pass_example" for f in findings)

    def test_deprecated_dict_in_pass_flagged(self) -> None:
        findings = lint_rule_examples(
            "DEP-002",
            _fence("x = 1"),
            _fence("payload = UserCreate(email='a@b.co')\ndata = payload.dict()"),
        )
        assert any(f["kind"] == "deprecated_api" and f["field"] == "pass_example" for f in findings)

    def test_deprecated_in_violation_only_is_clean(self) -> None:
        # A Violation block may use deprecated API incidentally; not flagged.
        findings = lint_rule_examples(
            "DEP-003",
            _fence("out = Resp.from_orm(x).dict()"),
            _fence("out = Resp.model_validate(x).model_dump()"),
        )
        assert findings == []

    def test_prose_only_block_is_clean(self) -> None:
        # DROP decision: a python fence of pure comments is intentional style.
        findings = lint_rule_examples(
            "PROSE-001",
            _fence("# users.py imports orders.py; orders.py imports users.py"),
            _fence("# users.py, orders.py both import shared/types.py"),
        )
        assert findings == []

    def test_placeholder_in_plain_string_is_clean(self) -> None:
        # DROP decision: {placeholder} in a string is not flagged (route patterns).
        findings = lint_rule_examples(
            "ROUTE-001",
            _fence("route = '/users/{user_id}'  # framework path pattern"),
            _fence("route = '/users/{user_id}'  # framework path pattern"),
        )
        assert findings == []

    def test_non_python_fence_ignored(self) -> None:
        # A php/sql/ruby fence is not parsed as python.
        findings = lint_rule_examples(
            "PHP-001",
            _fence("$x = array(;", lang="php"),
            _fence("SELECT * FROM t WHERE", lang="sql"),
        )
        assert findings == []

    def test_unlabeled_fence_ignored(self) -> None:
        # Only ```python (or ```py) blocks are syntax-checked.
        findings = lint_rule_examples(
            "NOLANG-001",
            _fence("def f(a=1, b):\n    pass", lang=""),
            _fence("x = 1", lang=""),
        )
        assert findings == []


# --- Graph-backed detector tests ---------------------------------------------


class TestDetectExampleLint:
    """IntegrityChecker.detect_example_lint over Rule nodes in the graph."""

    @pytest.mark.asyncio
    async def test_clean_graph_returns_none(self, db: Neo4jConnection, checker: IntegrityChecker) -> None:
        await db.create_rule(_make_rule("OK-100", _fence("x = 1"), _fence("y = 2")))
        result = await checker.detect_example_lint()
        assert result is None

    @pytest.mark.asyncio
    async def test_broken_example_flagged(self, db: Neo4jConnection, checker: IntegrityChecker) -> None:
        await db.create_rule(
            _make_rule("BAD-100", _fence("def f(a=1, b):\n    pass"), _fence("y = 2"))
        )
        result = await checker.detect_example_lint()
        assert result is not None
        assert "BAD-100" in result

    @pytest.mark.asyncio
    async def test_deprecated_pass_flagged(self, db: Neo4jConnection, checker: IntegrityChecker) -> None:
        await db.create_rule(
            _make_rule("DEP-100", _fence("x = 1"), _fence("out = M.from_orm(o)"))
        )
        result = await checker.detect_example_lint()
        assert result is not None
        assert "DEP-100" in result


# --- run_all_checks wiring ----------------------------------------------------


class TestExampleLintWiredIntoValidate:
    @pytest.mark.asyncio
    async def test_example_lint_in_findings_and_exit_code(
        self, db: Neo4jConnection, checker: IntegrityChecker
    ) -> None:
        await db.create_rule(
            _make_rule("BAD-200", _fence("def f(a=1, b):\n    pass"), _fence("y = 2"))
        )
        findings = await checker.run_all_checks(skip_redundancy=True)
        assert "example_lint" in findings
        assert findings["example_lint"]
        assert findings["exit_code"] == 1


# --- Corpus RED witness -------------------------------------------------------


class TestLiveCorpusExamplesClean:
    """The shipped bible must have ZERO example-lint defects.

    RED until the known defects are fixed (TEST-FIXTURE-001 syntax + the 5
    deprecated-Pydantic-v1 PASS examples). Reads source directly via the real
    parser so it is independent of graph state.
    """

    def test_no_example_lint_defects_in_bible(self) -> None:
        defects: list[dict] = []
        for f in discover_rule_files(BIBLE_DIR):
            if "methodology" in f.parts:
                continue
            for rule in parse_rules_from_file(f):
                defects.extend(
                    lint_rule_examples(
                        rule["rule_id"],
                        rule.get("violation"),
                        rule.get("pass_example"),
                    )
                )
        assert defects == [], (
            f"{len(defects)} example-lint defect(s) in the bible: "
            + "; ".join(f"{d['rule_id']}[{d['field']}]:{d['kind']}" for d in defects)
        )
