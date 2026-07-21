"""RED unit tests for `finish_import` (Wave 2 Cycle 4).

`finish_import(report, db, path, *, dry_run, no_export, compress, parsed_only,
is_default_root) -> dict` is the new async orchestrator being extracted from
`writ/cli.py::import_markdown` (blocks (b) auto-export gate and (c)
compress/materialize precedence) into `writ/graph/methodology_ingest.py`.

RED: `finish_import` does not exist yet, so the import below fails at
collection time. GREEN once the plan's implementation step lands the
function in `writ/graph/methodology_ingest.py`.

No live Neo4j: `db` is an opaque sentinel forwarded verbatim to the patched
export/compression callables (finish_import never calls a db method itself).
`export_rules_to_markdown`, `run_compression`, and
`materialize_abstractions_from_artifact` are monkeypatched at their ORIGIN
modules (`writ.export`, `writ.compression.abstractions`) -- mirroring
tests/test_compress_on_ingest.py:288-296 -- because `finish_import` is
required to import `export_rules_to_markdown` deferred and call
`_ab.run_compression` / `_ab.materialize_abstractions_from_artifact`
module-qualified, so only origin-module patches can intercept.

Two independent gates are under test:
- export gate: not dry_run and not no_export and not report.errors and
  total_nodes > 0 and parsed_only is None and is_default_root
- compress/materialize gate: not dry_run and not report.errors and
  total_nodes > 0 and parsed_only is None (independent of no_export and
  is_default_root)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from writ.graph.methodology_ingest import IngestError, IngestReport, finish_import


# ---------------------------------------------------------------------------
# Shared fixtures (TEST-FIXTURE-001 / TEST-FIXTURE-002: minimal, factory-built)
# ---------------------------------------------------------------------------

class _FakeDB:
    """Opaque sentinel: finish_import forwards it to the patched
    export/compression callables without calling any method on it."""


@pytest.fixture
def fake_db() -> _FakeDB:
    return _FakeDB()


@pytest.fixture
def make_report():
    """Factory for a minimal IngestReport: each test sets only the two
    fields finish_import's gates actually read (counts_by_type, errors)."""

    def _make(
        counts_by_type: dict[str, int] | None = None,
        errors: list[IngestError] | None = None,
    ) -> IngestReport:
        return IngestReport(
            counts_by_type={"Rule": 5} if counts_by_type is None else counts_by_type,
            errors=[] if errors is None else errors,
        )

    return _make


class _AsyncSpy:
    """Async callable that records calls and returns a fixed value, or
    raises a fixed exception instance, on every invocation."""

    def __init__(self, return_value: Any = None, exception: Exception | None = None) -> None:
        self.return_value = return_value
        self.exception = exception
        self.calls: list[tuple[tuple, dict]] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        if self.exception is not None:
            raise self.exception
        return self.return_value


def _default_kwargs(**overrides: Any) -> dict[str, Any]:
    """Keyword-only args for finish_import, defaulted to the 'everything
    eligible, plain default-root import' case; each test overrides only the
    knob(s) it is exercising."""
    base: dict[str, Any] = dict(
        dry_run=False,
        no_export=False,
        compress=False,
        parsed_only=None,
        is_default_root=True,
    )
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 1. Default-root full import: export fires, compress/materialize idle
# ---------------------------------------------------------------------------

class TestDefaultRootFullImport:
    """Auto-export fires for a full-corpus import against the default bible
    root; with no --compress and no artifact present, compressed and
    materialized both stay None."""

    @pytest.mark.asyncio
    async def test_default_root_full_import_exports(
        self,
        make_report,
        fake_db: _FakeDB,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        report = make_report(counts_by_type={"Rule": 5})
        export_spy = _AsyncSpy(return_value={"rules_exported": 5})
        monkeypatch.setattr("writ.export.export_rules_to_markdown", export_spy)

        result = await finish_import(
            report, fake_db, tmp_path, **_default_kwargs(is_default_root=True)
        )

        assert result["exported"] == {"rules_exported": 5}
        assert result["compressed"] is None
        assert result["materialized"] is None
        assert result["compress_import_error"] is None
        assert export_spy.calls == [((fake_db, tmp_path), {})]


# ---------------------------------------------------------------------------
# 2. --compress gate: success and ImportError degrade
# ---------------------------------------------------------------------------

class TestCompressGate:
    """--compress recomputes clusters via run_compression; a missing
    [fallback] dep degrades to compress_import_error without raising."""

    @pytest.mark.asyncio
    async def test_compress_success(
        self,
        make_report,
        fake_db: _FakeDB,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        report = make_report(counts_by_type={"Rule": 5})
        export_spy = _AsyncSpy(return_value={"rules_exported": 5})
        compress_spy = _AsyncSpy(
            return_value={"abstractions": [{"abstraction_id": "ABS-1"}]}
        )
        monkeypatch.setattr("writ.export.export_rules_to_markdown", export_spy)
        monkeypatch.setattr(
            "writ.compression.abstractions.run_compression", compress_spy
        )

        result = await finish_import(
            report,
            fake_db,
            tmp_path,
            **_default_kwargs(compress=True, is_default_root=True),
        )

        assert result["compressed"] == {"abstractions": [{"abstraction_id": "ABS-1"}]}
        assert result["exported"] == {"rules_exported": 5}
        assert result["materialized"] is None
        assert result["compress_import_error"] is None
        assert compress_spy.calls == [
            ((fake_db,), {"artifact_path": tmp_path / "abstractions.json"})
        ]

    @pytest.mark.asyncio
    async def test_compress_import_error_degrades(
        self,
        make_report,
        fake_db: _FakeDB,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        report = make_report(counts_by_type={"Rule": 5})
        import_error = ImportError("No module named 'sentence_transformers'")
        export_spy = _AsyncSpy(return_value={"rules_exported": 5})
        compress_spy = _AsyncSpy(exception=import_error)
        monkeypatch.setattr("writ.export.export_rules_to_markdown", export_spy)
        monkeypatch.setattr(
            "writ.compression.abstractions.run_compression", compress_spy
        )

        result = await finish_import(
            report,
            fake_db,
            tmp_path,
            **_default_kwargs(compress=True, is_default_root=True),
        )

        # Pins the WARN-and-continue contract: the exception is captured as
        # data, finish_import does not raise, and the (independent) export
        # gate still fires.
        assert result["compress_import_error"] is import_error
        assert result["compressed"] is None
        assert result["exported"] == {"rules_exported": 5}
        assert result["materialized"] is None


# ---------------------------------------------------------------------------
# 3. Subdirectory import: export gate needs is_default_root, compress doesn't
# ---------------------------------------------------------------------------

class TestSubdirectoryImport:
    """is_default_root=False disables ONLY the export gate; compress and
    materialize are independent of it."""

    @pytest.mark.asyncio
    async def test_subdir_no_export_but_compress_eligible(
        self,
        make_report,
        fake_db: _FakeDB,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        report = make_report(counts_by_type={"Rule": 3})
        export_spy = _AsyncSpy(return_value={"rules_exported": 3})
        compress_spy = _AsyncSpy(
            return_value={"abstractions": [{"abstraction_id": "ABS-1"}]}
        )
        monkeypatch.setattr("writ.export.export_rules_to_markdown", export_spy)
        monkeypatch.setattr(
            "writ.compression.abstractions.run_compression", compress_spy
        )

        result = await finish_import(
            report,
            fake_db,
            tmp_path,
            **_default_kwargs(compress=True, is_default_root=False, no_export=False),
        )

        assert result["exported"] is None
        assert export_spy.calls == []
        assert result["compressed"] == {"abstractions": [{"abstraction_id": "ABS-1"}]}


# ---------------------------------------------------------------------------
# 4. Materialize-from-artifact: dep-free path, gated on file existence
# ---------------------------------------------------------------------------

class TestMaterializeGate:
    """With compress=False, materialize fires only when
    <path>/abstractions.json exists; otherwise it is a no-op."""

    @pytest.mark.asyncio
    async def test_materialize_when_artifact_exists(
        self,
        make_report,
        fake_db: _FakeDB,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        artifact_path = tmp_path / "abstractions.json"
        artifact_path.write_text("{}", encoding="utf-8")
        report = make_report(counts_by_type={"Rule": 5})
        materialize_spy = _AsyncSpy(return_value=2)
        monkeypatch.setattr(
            "writ.compression.abstractions.materialize_abstractions_from_artifact",
            materialize_spy,
        )

        result = await finish_import(
            report,
            fake_db,
            tmp_path,
            **_default_kwargs(compress=False, is_default_root=False),
        )

        assert result["materialized"] == 2
        assert result["compressed"] is None
        assert result["compress_import_error"] is None
        assert materialize_spy.calls == [((artifact_path, fake_db), {})]

    @pytest.mark.asyncio
    async def test_materialize_skipped_when_artifact_absent(
        self,
        make_report,
        fake_db: _FakeDB,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        report = make_report(counts_by_type={"Rule": 5})
        materialize_spy = _AsyncSpy(return_value=2)
        monkeypatch.setattr(
            "writ.compression.abstractions.materialize_abstractions_from_artifact",
            materialize_spy,
        )

        result = await finish_import(
            report,
            fake_db,
            tmp_path,
            **_default_kwargs(compress=False, is_default_root=False),
        )

        assert result["materialized"] is None
        assert materialize_spy.calls == []


# ---------------------------------------------------------------------------
# 5. parsed_only gate: a --only import skips BOTH export and compress/materialize
# ---------------------------------------------------------------------------

class TestParsedOnlyGate:
    """A --only-filtered (surgical partial) import must not trigger export
    or the abstraction-layer rebuild, even if an artifact exists and
    --compress was requested."""

    @pytest.mark.asyncio
    async def test_parsed_only_skips_both(
        self,
        make_report,
        fake_db: _FakeDB,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Artifact present so a missing-gate bug would surface as a
        # materialize/compress call, not silently pass via a missing file.
        artifact_path = tmp_path / "abstractions.json"
        artifact_path.write_text("{}", encoding="utf-8")
        report = make_report(counts_by_type={"Rule": 5})
        export_spy = _AsyncSpy(return_value={"rules_exported": 5})
        compress_spy = _AsyncSpy(return_value={"abstractions": []})
        materialize_spy = _AsyncSpy(return_value=1)
        monkeypatch.setattr("writ.export.export_rules_to_markdown", export_spy)
        monkeypatch.setattr(
            "writ.compression.abstractions.run_compression", compress_spy
        )
        monkeypatch.setattr(
            "writ.compression.abstractions.materialize_abstractions_from_artifact",
            materialize_spy,
        )

        result = await finish_import(
            report,
            fake_db,
            tmp_path,
            **_default_kwargs(
                compress=True, is_default_root=True, parsed_only={"Rule"}
            ),
        )

        assert result == {
            "exported": None,
            "compressed": None,
            "materialized": None,
            "compress_import_error": None,
        }
        assert export_spy.calls == []
        assert compress_spy.calls == []
        assert materialize_spy.calls == []


# ---------------------------------------------------------------------------
# 6. Shared short-circuits: dry_run / report.errors / zero nodes
# ---------------------------------------------------------------------------

class TestBothGatesShortCircuit:
    """dry_run, a non-empty report.errors, and total_nodes == 0 each
    independently disable BOTH the export gate and the compress/materialize
    gate, regardless of the compress/is_default_root flags."""

    @pytest.mark.asyncio
    async def test_dry_run_skips_all(
        self,
        make_report,
        fake_db: _FakeDB,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        report = make_report(counts_by_type={"Rule": 5})
        export_spy = _AsyncSpy(return_value={"rules_exported": 5})
        compress_spy = _AsyncSpy(return_value={"abstractions": []})
        monkeypatch.setattr("writ.export.export_rules_to_markdown", export_spy)
        monkeypatch.setattr(
            "writ.compression.abstractions.run_compression", compress_spy
        )

        result = await finish_import(
            report,
            fake_db,
            tmp_path,
            **_default_kwargs(dry_run=True, compress=True, is_default_root=True),
        )

        assert result == {
            "exported": None,
            "compressed": None,
            "materialized": None,
            "compress_import_error": None,
        }
        assert export_spy.calls == []
        assert compress_spy.calls == []

    @pytest.mark.asyncio
    async def test_report_errors_skips_all(
        self,
        make_report,
        fake_db: _FakeDB,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        report = make_report(
            counts_by_type={"Rule": 5},
            errors=[IngestError(Path("x.md"), "Rule", "R-1", None, "boom")],
        )
        export_spy = _AsyncSpy(return_value={"rules_exported": 5})
        compress_spy = _AsyncSpy(return_value={"abstractions": []})
        monkeypatch.setattr("writ.export.export_rules_to_markdown", export_spy)
        monkeypatch.setattr(
            "writ.compression.abstractions.run_compression", compress_spy
        )

        result = await finish_import(
            report,
            fake_db,
            tmp_path,
            **_default_kwargs(compress=True, is_default_root=True),
        )

        assert result == {
            "exported": None,
            "compressed": None,
            "materialized": None,
            "compress_import_error": None,
        }
        assert export_spy.calls == []
        assert compress_spy.calls == []

    @pytest.mark.asyncio
    async def test_zero_nodes_skips_all(
        self,
        make_report,
        fake_db: _FakeDB,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        report = make_report(counts_by_type={})
        export_spy = _AsyncSpy(return_value={"rules_exported": 0})
        compress_spy = _AsyncSpy(return_value={"abstractions": []})
        monkeypatch.setattr("writ.export.export_rules_to_markdown", export_spy)
        monkeypatch.setattr(
            "writ.compression.abstractions.run_compression", compress_spy
        )

        result = await finish_import(
            report,
            fake_db,
            tmp_path,
            **_default_kwargs(compress=True, is_default_root=True),
        )

        assert result == {
            "exported": None,
            "compressed": None,
            "materialized": None,
            "compress_import_error": None,
        }
        assert export_spy.calls == []
        assert compress_spy.calls == []


# ---------------------------------------------------------------------------
# 7. --no-export: disables ONLY the export gate
# ---------------------------------------------------------------------------

class TestNoExportFlag:
    """--no-export disables auto-export but must not affect the independent
    compress/materialize gate."""

    @pytest.mark.asyncio
    async def test_no_export_flag_skips_export_only(
        self,
        make_report,
        fake_db: _FakeDB,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        report = make_report(counts_by_type={"Rule": 5})
        export_spy = _AsyncSpy(return_value={"rules_exported": 5})
        compress_spy = _AsyncSpy(
            return_value={"abstractions": [{"abstraction_id": "ABS-1"}]}
        )
        monkeypatch.setattr("writ.export.export_rules_to_markdown", export_spy)
        monkeypatch.setattr(
            "writ.compression.abstractions.run_compression", compress_spy
        )

        result = await finish_import(
            report,
            fake_db,
            tmp_path,
            **_default_kwargs(no_export=True, is_default_root=True, compress=True),
        )

        assert result["exported"] is None
        assert export_spy.calls == []
        assert result["compressed"] == {"abstractions": [{"abstraction_id": "ABS-1"}]}
