"""Unit tests for writ/graph/methodology_ingest.py (v1.5.0).

Covers the library surface that the unified `writ import-markdown` CLI and
the `scripts/migrate.py` shim both consume. End-to-end / Neo4j-integration
behavior is exercised by tests/test_import_markdown_unified.py; this module
pins the in-process invariants:

- INGESTER_REGISTRY contains an entry for every known node type.
- KNOWN_NODE_TYPES is the registry key-set.
- IngestError stringifies to a single line with file:type 'id' -- reason
  shape (no Python traceback substring).
- IngestReport.render() includes per-type counts and a totals line.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from textwrap import dedent
from unittest.mock import AsyncMock

import pytest

from writ.graph.methodology_ingest import (
    INGESTER_REGISTRY,
    KNOWN_NODE_TYPES,
    IngestError,
    IngestReport,
    ingest_path,
)


class TestRegistry:
    def test_registry_has_rule(self) -> None:
        assert "Rule" in INGESTER_REGISTRY
        assert callable(INGESTER_REGISTRY["Rule"])

    def test_registry_has_core_methodology_types(self) -> None:
        for nt in ("Skill", "Playbook", "AntiPattern", "Technique",
                   "ForbiddenResponse", "Phase", "SubagentRole",
                   "Rationalization", "WorkedExample"):
            assert nt in INGESTER_REGISTRY, f"missing registry entry: {nt}"

    def test_known_node_types_matches_registry(self) -> None:
        assert KNOWN_NODE_TYPES == frozenset(INGESTER_REGISTRY.keys())

    def test_known_node_types_is_frozenset(self) -> None:
        assert isinstance(KNOWN_NODE_TYPES, frozenset)


class TestIngestError:
    def test_str_contains_file_type_id_reason(self) -> None:
        err = IngestError(
            file=Path("/tmp/bad.md"),
            node_type="Skill",
            node_id="SKL-X-001",
            field="staleness_window",
            reason="value is not a valid integer",
        )
        s = str(err)
        assert "bad.md" in s
        assert "Skill" in s
        assert "SKL-X-001" in s
        assert "staleness_window" in s
        assert "value is not a valid integer" in s

    def test_str_has_no_traceback(self) -> None:
        err = IngestError(
            file=Path("/tmp/bad.md"),
            node_type="Skill",
            node_id="SKL-X-001",
            field=None,
            reason="boom",
        )
        assert "Traceback (most recent call last):" not in str(err)
        assert "pydantic_core._pydantic_core.ValidationError" not in str(err)

    def test_str_handles_missing_fields(self) -> None:
        err = IngestError(
            file=Path("/tmp/nope.md"),
            node_type=None,
            node_id=None,
            field=None,
            reason="parse error",
        )
        s = str(err)
        assert "nope.md" in s
        assert "parse error" in s


class TestIngestReport:
    def test_render_empty(self) -> None:
        r = IngestReport()
        out = r.render()
        assert "Imported nodes by type" in out

    def test_render_includes_per_type_counts(self) -> None:
        r = IngestReport(counts_by_type={"Rule": 80, "Skill": 12, "Playbook": 4})
        out = r.render()
        assert "Rule" in out and "80" in out
        assert "Skill" in out and "12" in out
        assert "Playbook" in out and "4" in out

    def test_render_includes_totals(self) -> None:
        r = IngestReport(counts_by_type={"Rule": 10, "Skill": 5})
        out = r.render()
        assert "Total" in out
        assert "15" in out

    def test_render_dry_run_marker(self) -> None:
        r = IngestReport(counts_by_type={"Skill": 1}, dry_run=True)
        out = r.render()
        assert "DRY RUN" in out or "dry" in out.lower()

    def test_render_edges_line_for_live_run(self) -> None:
        r = IngestReport(
            counts_by_type={"Rule": 1},
            edges_created=3,
            edges_dangling=1,
            dry_run=False,
        )
        out = r.render()
        assert "Edges created" in out
        assert "3" in out

    def test_render_errors_line(self) -> None:
        r = IngestReport(
            counts_by_type={"Rule": 1},
            errors=[
                IngestError(
                    file=Path("/x.md"),
                    node_type="Rule",
                    node_id="X-001",
                    field=None,
                    reason="bad",
                )
            ],
        )
        out = r.render()
        assert "Errors" in out
        assert "1" in out


class TestIngestPathMissingDir:
    def test_returns_error_for_nonexistent(self) -> None:
        async def _run() -> IngestReport:
            return await ingest_path(Path("/nonexistent/path/xyz"), db=None, dry_run=True)

        report = asyncio.run(_run())
        assert report.errors
        assert any("does not exist" in e.reason for e in report.errors)


# ---------------------------------------------------------------------------
# Phase 0: Reachability invariant, dual-location dedup, registry Category
# (TDD RED skeletons)
# ---------------------------------------------------------------------------

# Minimal Skill front-matter fixture without a category field. Used to
# trigger the reachability error path in live ingest.
_SKILL_NO_CATEGORY_FM = dedent("""\
    ---
    node_type: Skill
    skill_id: SKL-TEST-NOCAT-001
    name: Test Skill Without Category
    summary: A skill that intentionally omits the category field.
    body: ''
    staleness_window: 365
    last_validated: '2026-06-11'
    ---
    Skill body: no category field present.
""")


@pytest.fixture()
def tmp_skill_no_category(tmp_path: Path) -> Path:
    f = tmp_path / "SKL-TEST-NOCAT-001.md"
    f.write_text(_SKILL_NO_CATEGORY_FM)
    return f


class TestReachabilityInvariant:
    """Phase 0: ingest_path enforces that every ingested node carries a
    'category' field during a live run; dry_run bypasses the check.

    RED until methodology_ingest.py checks for category on live runs and
    appends an IngestError with field='category' and a reason mentioning
    'reachability' when the field is absent.
    """

    def test_live_run_errors_on_node_without_category(
        self, tmp_skill_no_category: Path
    ) -> None:
        """A live ingest (dry_run=False, db=None) of a Skill missing the
        category field must append an IngestError whose field is 'category'
        and whose reason contains the word 'reachability'."""
        async def _run() -> IngestReport:
            return await ingest_path(
                tmp_skill_no_category.parent,
                db=None,
                dry_run=False,
            )

        report = asyncio.run(_run())
        reachability_errors = [
            e for e in report.errors
            if e.field == "category" and "reachability" in e.reason.lower()
        ]
        assert reachability_errors, (
            f"Expected at least one IngestError with field='category' and "
            f"'reachability' in reason. Got errors: {report.errors}"
        )

    def test_dry_run_skips_reachability(
        self, tmp_skill_no_category: Path
    ) -> None:
        """Guard test: dry_run=True must NOT produce a reachability error for
        a node that merely lacks a category field. Reachability is enforced
        only on live writes.

        This test should pass today (dry-run already doesn't check category)
        and continue to pass after implementation -- it guards against
        over-eager reachability enforcement in preview mode."""
        async def _run() -> IngestReport:
            return await ingest_path(
                tmp_skill_no_category.parent,
                db=None,
                dry_run=True,
            )

        report = asyncio.run(_run())
        reachability_errors = [
            e for e in report.errors
            if e.field == "category" and "reachability" in e.reason.lower()
        ]
        assert not reachability_errors, (
            f"dry_run=True must not produce reachability errors. "
            f"Got: {reachability_errors}"
        )


class TestDualLocationDedup:
    """Phase 0: ingest_path (dry_run=True) over the real bible directory
    counts Rule nodes by unique rule_id, not raw parsed occurrences.
    The 12 known dual-location rules each appear twice in the raw parse but
    once after dedup. Expected unique Rule count = raw_count - 12.

    RED until ingest_path deduplicates by primary ID within a single walk.
    """

    def test_dedups_dual_location_nodes(self) -> None:
        """Dry-run ingest of the live bible should report Rule count equal to
        the number of UNIQUE rule_ids (raw minus 12 duplicates)."""
        bible_dir = Path(__file__).resolve().parent.parent / "bible"
        if not bible_dir.exists():
            pytest.skip("bible/ directory not found")

        async def _run() -> IngestReport:
            return await ingest_path(bible_dir, db=None, dry_run=True)

        report = asyncio.run(_run())

        # Derive ground-truth unique count from raw parse.
        from writ.graph.ingest import parse_nodes_from_file, discover_rule_files

        files = discover_rule_files(bible_dir)
        seen_ids: set[str] = set()
        for f in files:
            try:
                for node in parse_nodes_from_file(f):
                    if node.get("node_type") == "Rule":
                        rid = node.get("rule_id")
                        if rid:
                            seen_ids.add(rid)
            except Exception:
                pass

        expected_unique = len(seen_ids)
        reported_rule_count = report.counts_by_type.get("Rule", 0)

        assert reported_rule_count == expected_unique, (
            f"Expected {expected_unique} unique Rule nodes in dry-run report "
            f"(raw minus 12 dual-location dupes), got {reported_rule_count}"
        )


class TestRegistryCategory:
    """Phase 0: INGESTER_REGISTRY must contain a 'Category' entry once the
    Category ingester is wired up.

    RED until INGESTER_REGISTRY['Category'] is populated in methodology_ingest.py.
    """

    def test_registry_has_category(self) -> None:
        """'Category' must be a key in INGESTER_REGISTRY and its value must
        be callable (an async ingester function)."""
        assert "Category" in INGESTER_REGISTRY, (
            "'Category' not found in INGESTER_REGISTRY. "
            "Implement _make_methodology_ingester('Category') entry in methodology_ingest.py."
        )
        assert callable(INGESTER_REGISTRY["Category"]), (
            "INGESTER_REGISTRY['Category'] must be callable."
        )


# ---------------------------------------------------------------------------
# Phase 0 Wave E: BELONGS_TO edge wiring on the live ingest path
# ---------------------------------------------------------------------------

# A tiny bible: one Category node and one Rule whose `category` points at it.
_CATEGORY_FM = dedent("""\
    ---
    node_type: Category
    category_id: CAT-CODE-SECURITY-001
    name: Security Coding Rules
    routes:
      - semantic
    description: Security rules.
    ---
    Category body.
""")

_RULE_WITH_CATEGORY_FM = dedent("""\
    ---
    node_type: Rule
    rule_id: SEC-INJ-001
    domain: Security
    severity: critical
    scope: component
    category: CAT-CODE-SECURITY-001
    trigger: When building a SQL query from user input.
    statement: Parameterize every query.
    violation: String-concatenated SQL.
    pass_example: Bound parameters.
    enforcement: Code review.
    rationale: Prevents injection.
    last_validated: '2026-06-11'
    body: ''
    ---
    Rule body.
""")


@pytest.fixture()
def tmp_category_and_rule_bible(tmp_path: Path) -> Path:
    """A bible dir with one Category and one Rule that belongs to it."""
    bible = tmp_path / "bible"
    bible.mkdir()
    (bible / "CAT-CODE-SECURITY-001.md").write_text(_CATEGORY_FM)
    (bible / "SEC-INJ-001.md").write_text(_RULE_WITH_CATEGORY_FM)
    return bible


class TestBelongsToEdgeWiring:
    """Phase 0 Wave E: the live ingest path (dry_run=False) must derive and
    create BELONGS_TO edges from each node's `category` value.

    Integration bug being guarded: extract_belongs_to_edges exists and is unit
    tested, but nothing called it during ingest, so a real re-import produced
    zero BELONGS_TO edges.

    Pure-unit approach: an AsyncMock db records the edges passed to
    batch_create_edges (B5.2: edges are written in one UNWIND-grouped call, not a
    create_edge per edge); we assert the rule->category BELONGS_TO edge is among
    them. Actual edge CREATION in Neo4j is covered by the 0.10 graph-identical
    oracle (test_phase010_reconcile_oracle) against a real connection.
    """

    def _make_db(self) -> AsyncMock:
        db = AsyncMock()
        # ingest_edges calls get_all_rules() to build the known-id set.
        db.get_all_rules.return_value = []
        # B5.2: ingest_edges unpacks (created, write_dangling) from batch_create_edges.
        db.batch_create_edges.return_value = (1, 0)
        return db

    def test_live_ingest_creates_belongs_to_edge(
        self, tmp_category_and_rule_bible: Path
    ) -> None:
        db = self._make_db()

        async def _run() -> IngestReport:
            return await ingest_path(
                tmp_category_and_rule_bible, db=db, dry_run=False
            )

        report = asyncio.run(_run())

        # M.2: known_ids must be project-scoped -- ingest_edges resolves the existing
        # corpus via get_all_rules(project=...), not across all projects. Pin the
        # kwarg so dropping the scoping is caught at the unit level too (the
        # behavioral guard lives in test_phaseM2b_data_integrity).
        assert db.get_all_rules.call_args is not None, "ingest_edges must call get_all_rules"
        assert db.get_all_rules.call_args.kwargs.get("project") == "writ", (
            "ingest_edges must call get_all_rules with the ingest project (scoping), "
            f"got {db.get_all_rules.call_args}"
        )

        assert db.batch_create_edges.called, (
            "ingest_path must batch-create edges (B5.2). "
            f"batch_create_edges calls: {db.batch_create_edges.call_args_list}"
        )
        # B5.2: edges are the first positional arg to the single batch call.
        call = db.batch_create_edges.call_args
        edges_arg = call.args[0] if call.args else call.kwargs["edges"]
        belongs_to = [
            (e["type"], e["source"], e["target"])
            for e in edges_arg if e.get("type") == "BELONGS_TO"
        ]
        assert belongs_to, (
            "ingest must derive a BELONGS_TO edge for nodes carrying a category. "
            f"edges passed to batch_create_edges: {edges_arg}"
        )
        # The Rule SEC-INJ-001 must belong to CAT-CODE-SECURITY-001.
        assert ("BELONGS_TO", "SEC-INJ-001", "CAT-CODE-SECURITY-001") in belongs_to, (
            f"Expected BELONGS_TO from SEC-INJ-001 to CAT-CODE-SECURITY-001; "
            f"got {belongs_to}"
        )
        # The BELONGS_TO edge must be counted in the edges-created tally.
        assert report.edges_created >= 1

    def test_dry_run_creates_no_belongs_to_edge(
        self, tmp_category_and_rule_bible: Path
    ) -> None:
        """Guard: dry_run previews must not write nodes or edges."""
        db = self._make_db()

        async def _run() -> IngestReport:
            return await ingest_path(
                tmp_category_and_rule_bible, db=db, dry_run=True
            )

        asyncio.run(_run())
        db.batch_create_edges.assert_not_called()
        db.batch_create_nodes.assert_not_called()
