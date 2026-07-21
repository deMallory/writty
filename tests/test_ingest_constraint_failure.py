"""C3 (Wave 1 Cycle 1, plan.md): a constraint-application failure during ingest
must surface, not be silently swallowed.

writ/graph/methodology_ingest.py:341-346 wraps `await db.apply_constraints()`
in a blanket `try: ... except Exception: pass`. The DDL is idempotent
(DROP/CREATE ... IF [NOT] EXISTS), so "already exists" is never the exception
that gets caught -- what gets swallowed is a REAL failure (a pre-existing
duplicate violating a UNIQUE constraint, permissions, DB outage), silently
leaving the composite-uniqueness race guard unapplied.

Fix (plan.md ## Analysis, C3): remove the swallow so `apply_constraints()`
raises through `_write_nodes` / `ingest_path` (fail-loud).

RED today: with the swallow in effect, `_write_nodes` discards the fake db's
RuntimeError and runs to completion (through batch_create_nodes and the
edges pass), so `pytest.raises(RuntimeError)` fails with "DID NOT RAISE".
"""

from __future__ import annotations

import pytest

from writ.graph.methodology_ingest import IngestReport, _write_nodes


class _FakeDbApplyConstraintsRaises:
    """Minimal async fake whose apply_constraints raises a real failure.

    The FIXED `_write_nodes` (no swallow) never calls anything past
    apply_constraints, so batch_create_nodes/get_all_rules/batch_create_edges
    are never reached there. They ARE reached today (RED path) because the
    current swallow lets execution continue into batch_create_nodes and then
    the unconditional edges pass (methodology_ingest.py:357-361 calls
    ingest_edges whenever `parsed_nodes` is non-empty, regardless of whether
    the node write succeeded) -- so the fake must survive that path too rather
    than fail on an unrelated AttributeError, which would mask the real
    (swallowed-exception) RED reason this test is pinning.
    """

    async def apply_constraints(self) -> None:
        raise RuntimeError("constraint failed")

    async def batch_create_nodes(self, *args, **kwargs):
        raise AssertionError(
            "batch_create_nodes must not be called when apply_constraints raises"
        )

    async def get_all_rules(self, *args, **kwargs) -> list[dict]:
        return []

    async def batch_create_edges(self, *args, **kwargs) -> tuple[int, int]:
        return (0, 0)


def _minimal_write_spec() -> tuple[list[tuple[str, dict, dict]], list[dict]]:
    """One minimal Rule node: enough for `_write_nodes` to take the non-dry-run,
    non-empty `parsed_nodes` branch that calls `db.apply_constraints()`."""
    node = {"rule_id": "TEST-CONSTRAINT-001", "node_type": "Rule"}
    clean = {"rule_id": "TEST-CONSTRAINT-001", "project": "writ"}
    cleaned = [("Rule", clean, node)]
    parsed_nodes = [node]
    return cleaned, parsed_nodes


class TestWriteNodesSurfacesApplyConstraintsFailure:
    """A real apply_constraints failure must propagate out of _write_nodes,
    per the fail-loud decision in plan.md ## Analysis, C3."""

    @pytest.mark.asyncio
    async def test_write_nodes_surfaces_apply_constraints_failure(self) -> None:
        cleaned, parsed_nodes = _minimal_write_spec()
        fake_db = _FakeDbApplyConstraintsRaises()
        report = IngestReport()

        with pytest.raises(RuntimeError) as excinfo:
            await _write_nodes(
                fake_db,
                cleaned=cleaned,
                parsed_nodes=parsed_nodes,
                parsed_edges=[],
                node_source={},
                dry_run=False,
                project="writ",
                report=report,
            )

        assert "constraint failed" in str(excinfo.value), (
            f"expected the raised RuntimeError to carry 'constraint failed', "
            f"got {excinfo.value!r} -- if this instead reports 'DID NOT RAISE', "
            f"the current try/except Exception: pass around apply_constraints() "
            f"is still swallowing the failure"
        )
        assert not report.errors, (
            f"a swallowed-and-continued path would record a batch-write error "
            f"instead of raising; report.errors should be empty when the "
            f"exception propagates before batch_create_nodes runs, got "
            f"{report.errors!r}"
        )


class TestDryRunSkipsApplyConstraints:
    """Guard against a false-positive fail-loud: dry_run must never touch the
    db at all, so a failing apply_constraints on a dry-run fake must not raise."""

    @pytest.mark.asyncio
    async def test_dry_run_does_not_call_apply_constraints(self) -> None:
        cleaned, parsed_nodes = _minimal_write_spec()
        fake_db = _FakeDbApplyConstraintsRaises()
        report = IngestReport(dry_run=True)

        # Must NOT raise: dry_run takes the record-only branch and never calls
        # apply_constraints or batch_create_nodes.
        await _write_nodes(
            fake_db,
            cleaned=cleaned,
            parsed_nodes=parsed_nodes,
            parsed_edges=[],
            node_source={},
            dry_run=True,
            project="writ",
            report=report,
        )

        assert report.counts_by_type.get("Rule") == 1, (
            f"dry_run should still record the node in report.counts_by_type, "
            f"got {report.counts_by_type!r}"
        )


class _FakeDbGetAllRulesRaises:
    """Minimal async fake whose apply_constraints/batch_create_nodes succeed
    (so the unconditional edges pass at methodology_ingest.py:357-361 is
    reached) but whose get_all_rules raises a real failure."""

    async def apply_constraints(self) -> None:
        return None

    async def batch_create_nodes(self, *args, **kwargs):
        return None

    async def get_all_rules(self, *args, **kwargs):
        raise RuntimeError("get_all_rules failed")

    async def batch_create_edges(self, *args, **kwargs):
        return (0, 0)  # reached only in the RED (swallowed) path


class TestIngestEdgesSurfacesGetAllRulesFailure:
    """S3 (Wave 1 Cycle 4, plan.md): a real get_all_rules failure must propagate
    out of _write_nodes (via ingest_edges), not be swallowed to an empty set --
    which mislabels every valid cross-reference to an existing Rule as dangling.

    RED today: ingest_edges wraps `await db.get_all_rules(project=project)` in
    `except Exception: existing_rule_ids = set()`, so the RuntimeError never
    reaches _write_nodes and pytest.raises(RuntimeError) fails with
    "DID NOT RAISE".
    """

    @pytest.mark.asyncio
    async def test_get_all_rules_failure_propagates(self) -> None:
        cleaned, parsed_nodes = _minimal_write_spec()
        fake_db = _FakeDbGetAllRulesRaises()
        report = IngestReport()
        with pytest.raises(RuntimeError) as excinfo:
            await _write_nodes(
                fake_db, cleaned=cleaned, parsed_nodes=parsed_nodes,
                parsed_edges=[], node_source={}, dry_run=False,
                project="writ", report=report,
            )
        assert "get_all_rules failed" in str(excinfo.value), (
            "if this reports DID NOT RAISE, the except Exception swallow in "
            "ingest_edges is still converting the failure to an empty set"
        )
