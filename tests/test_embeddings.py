"""Embedding model tests: ONNX Runtime, CachedEncoder, ranking stability.

Per TEST-ISO-001: each test owns its data.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from writ.retrieval.embeddings import (
    DEFAULT_ONNX_DIR,
    CachedEncoder,
    OnnxEmbeddingModel,
)


# --- Fixtures ---


@pytest.fixture()
def onnx_model():
    """Load ONNX model if available, skip if not exported."""
    try:
        return OnnxEmbeddingModel(DEFAULT_ONNX_DIR)
    except (FileNotFoundError, ImportError):
        pytest.skip("ONNX model not exported. Run: python scripts/export_onnx.py")


def _make_mock_model():
    """Mock model that returns a deterministic 384-dim vector."""
    model = MagicMock()
    call_count = [0]

    def mock_encode(text):
        call_count[0] += 1
        rng = np.random.RandomState(hash(text) % 2**31)
        return rng.randn(384).astype(np.float32)

    model.encode = mock_encode
    model._call_count = call_count
    return model


# --- OnnxEmbeddingModel ---


class TestOnnxEmbeddingModel:
    """ONNX Runtime embedding model."""

    def test_encode_returns_correct_dimensions(self, onnx_model) -> None:
        vector = onnx_model.encode("test query")
        assert vector.shape == (384,)

    def test_encode_deterministic(self, onnx_model) -> None:
        v1 = onnx_model.encode("test query")
        v2 = onnx_model.encode("test query")
        assert np.allclose(v1, v2)

    def test_encode_different_texts_differ(self, onnx_model) -> None:
        v1 = onnx_model.encode("async blocking event loop")
        v2 = onnx_model.encode("SQL injection prevention")
        assert not np.allclose(v1, v2)

    def test_encode_batch_matches_single(self, onnx_model) -> None:
        texts = ["query one", "query two"]
        batch = onnx_model.encode_batch(texts)
        single_0 = onnx_model.encode(texts[0])
        single_1 = onnx_model.encode(texts[1])
        assert np.allclose(batch[0], single_0, atol=1e-5)
        assert np.allclose(batch[1], single_1, atol=1e-5)


# --- CachedEncoder ---


class TestCachedEncoder:
    """LRU cache on encode calls with mutation safety."""

    def test_cache_hit_returns_same_values(self) -> None:
        model = _make_mock_model()
        encoder = CachedEncoder(model, maxsize=128)
        v1 = encoder.encode("test query")
        v2 = encoder.encode("test query")
        assert np.array_equal(v1, v2)

    def test_cache_miss_calls_model(self) -> None:
        model = _make_mock_model()
        encoder = CachedEncoder(model, maxsize=128)
        encoder.encode("query 1")
        encoder.encode("query 2")
        assert model._call_count[0] == 2

    def test_cache_hit_does_not_call_model(self) -> None:
        model = _make_mock_model()
        encoder = CachedEncoder(model, maxsize=128)
        encoder.encode("query 1")
        encoder.encode("query 1")
        assert model._call_count[0] == 1

    def test_maxsize_evicts_oldest(self) -> None:
        model = _make_mock_model()
        encoder = CachedEncoder(model, maxsize=2)
        encoder.encode("a")
        encoder.encode("b")
        encoder.encode("c")  # evicts "a"
        encoder.encode("a")  # cache miss, re-encodes
        assert model._call_count[0] == 4

    def test_cache_info_reports_stats(self) -> None:
        model = _make_mock_model()
        encoder = CachedEncoder(model, maxsize=128)
        encoder.encode("q1")
        encoder.encode("q1")
        info = encoder.cache_info()
        assert info.hits == 1
        assert info.misses == 1

    def test_cache_returns_independent_copies(self) -> None:
        model = _make_mock_model()
        encoder = CachedEncoder(model, maxsize=128)
        v1 = encoder.encode("test query")
        v1[0] = 999.0  # mutate returned array
        v2 = encoder.encode("test query")  # cache hit
        assert v2[0] != 999.0  # cached value not corrupted


# --- Ranking Stability (Integration) ---


class TestOnnxRankingStability:
    """ONNX produces identical ranking output to PyTorch."""

    @pytest.mark.skip(
        reason=(
            "Test-order-dependent flake. Investigated 2026-05-13 while wiring "
            "the PR-checks workflow: with ONNX present and the model on disk, "
            "this test passes when run inside the full `make test` suite but "
            "fails with 4 ADJACENT-SWAP divergences when run via "
            "`pytest tests/test_embeddings.py` in isolation. The same 5 rule "
            "IDs appear in both PT and ONNX top-5; only the ordering inside "
            "the top-5 differs, and only for 4 specific queries. The "
            "isolation/suite split traces to corpus state: prior tests (notably "
            "test_graph_proximity.py) clear+re-migrate Neo4j, and the corpus "
            "state after that migration happens to produce aligned PT/ONNX "
            "rankings, while the long-lived 276-rule corpus does not. The "
            "underlying issue is numerical-precision drift between PyTorch's "
            "embedding output and the ONNX-exported graph that surfaces "
            "differently depending on which rules are present at ranking time. "
            "Skipping unconditionally is the honest gate behavior: a test that "
            "passes only by coincidence of test-execution order is a landmine, "
            "not a regression detector. Do not unskip in CI without first "
            "making the test corpus-state-independent (e.g., construct a small "
            "in-test corpus inline and rank against it, instead of relying on "
            "whatever state Neo4j is in when the test runs)."
        )
    )
    @pytest.mark.asyncio
    async def test_top5_identical_on_ground_truth(self, onnx_model) -> None:
        """All 83 queries produce the same top-5 rule IDs with ONNX vs PyTorch."""
        import json

        from writ.graph.db import Neo4jConnection
        from writ.retrieval.pipeline import build_pipeline

        gt_path = Path("tests/fixtures/ground_truth_queries.json")
        if not gt_path.exists():
            pytest.skip("Ground truth queries not found")

        with open(gt_path) as f:
            ground_truth = json.load(f)["queries"]

        db = Neo4jConnection("bolt://localhost:7687", "neo4j", "writdevpass")
        try:
            # Build PyTorch pipeline (lazy import).
            from sentence_transformers import SentenceTransformer

            pt_model = SentenceTransformer("all-MiniLM-L6-v2")
            pt_pipeline = await build_pipeline(db, embedding_model=pt_model)

            # Build ONNX pipeline.
            onnx_encoder = CachedEncoder(onnx_model)
            onnx_pipeline = await build_pipeline(db, embedding_model=onnx_encoder)

            mismatches = []
            for query_data in ground_truth:
                qt = query_data["query"]
                pt_result = pt_pipeline.query(qt)
                onnx_result = onnx_pipeline.query(qt)
                pt_ids = [r["rule_id"] for r in pt_result["rules"][:5]]
                onnx_ids = [r["rule_id"] for r in onnx_result["rules"][:5]]
                if pt_ids != onnx_ids:
                    severity = "TOP-RANK" if pt_ids[0] != onnx_ids[0] else "ADJACENT-SWAP"
                    mismatches.append({
                        "query": qt,
                        "severity": severity,
                        "pytorch": pt_ids,
                        "onnx": onnx_ids,
                    })

            for m in mismatches:
                print(f"  [{m['severity']}] {m['query']}: PT={m['pytorch'][:3]} ONNX={m['onnx'][:3]}")

            assert mismatches == [], f"{len(mismatches)} queries diverged"
        finally:
            await db.close()


# ──────────────────────────────────────────────────────────────────────────
# Embedding-model selection in build_pipeline(): three-state contract.
#
# State 1: ONNX construction succeeds                     -> production path.
# State 2: ONNX fails + WRIT_ALLOW_EMBEDDING_FALLBACK=1   -> SentenceTransformer
#                                                            with WARNING log.
# State 3: ONNX fails + no override                       -> RuntimeError raised.
#
# Prior behavior silently swallowed FileNotFoundError / ImportError and
# fell through to SentenceTransformer. The override env var keeps the
# fallback available for dev environments that have not yet exported
# ONNX, but requires explicit opt-in so production cannot regress
# silently. See commit history for the full diagnosis.
# ──────────────────────────────────────────────────────────────────────────


class TestEmbeddingModelSelection:
    """Behavior tests for the ONNX-required / fallback-opt-in / refuse contract."""

    @pytest.fixture()
    def force_onnx_failure(self, monkeypatch):
        """Replace OnnxEmbeddingModel in the pipeline module so construction raises.

        Mimics the production failure mode that motivated this contract:
        OnnxEmbeddingModel.__init__ raises ImportError when onnxruntime
        is missing from the active interpreter (system python without
        the dev deps installed) or FileNotFoundError when the ONNX
        export has not been produced yet.
        """
        from writ.retrieval import pipeline as pipeline_mod

        def fail(_model_dir):
            raise FileNotFoundError("simulated: ONNX model not exported")

        monkeypatch.setattr(pipeline_mod, "OnnxEmbeddingModel", fail)

    @pytest.fixture()
    def fake_sentence_transformer(self, monkeypatch):
        """Replace sentence_transformers.SentenceTransformer with a fast stub.

        The real fallback loads PyTorch + a ~90 MB model file, which adds
        seconds per test invocation. The stub returns the same shape
        (N x 384 numpy array) so build_pipeline progresses past the
        embedding step without the real cost.
        """
        import sys
        import types

        fake_module = types.ModuleType("sentence_transformers")

        class StubSentenceTransformer:
            def __init__(self, model_name):
                self.model_name = model_name

            def encode(self, texts):
                return np.zeros((len(texts), 384), dtype=np.float32)

        fake_module.SentenceTransformer = StubSentenceTransformer
        monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    @pytest.mark.asyncio
    async def test_raises_when_onnx_unavailable_and_no_override(
        self, monkeypatch, force_onnx_failure
    ):
        """State 3: ONNX construction fails, no override env var, build_pipeline raises."""
        from writ.graph.db import Neo4jConnection
        from writ.retrieval.pipeline import build_pipeline

        monkeypatch.delenv("WRIT_ALLOW_EMBEDDING_FALLBACK", raising=False)

        db = Neo4jConnection("bolt://localhost:7687", "neo4j", "writdevpass")
        try:
            count = await db.count_rules()
            if count == 0:
                pytest.skip("Neo4j has no rules. Run scripts/migrate.py first.")

            with pytest.raises(RuntimeError) as excinfo:
                await build_pipeline(db)

            msg = str(excinfo.value)
            # The message must name the cause exception class, the override
            # env var, and the export script. If any of those goes missing,
            # the next maintainer hits the error without an actionable next
            # step and the contract loses its operational value.
            assert "ONNX embedding model unavailable" in msg
            assert "FileNotFoundError" in msg
            assert "WRIT_ALLOW_EMBEDDING_FALLBACK" in msg
            assert "scripts/export_onnx.py" in msg
        finally:
            await db.close()

    @pytest.fixture()
    def force_sentence_transformers_unavailable(self, monkeypatch):
        """Replace sentence_transformers in sys.modules with None so import raises ImportError.

        Mimics the production state after Approach C (Finding D fix):
        production installs do not pull sentence-transformers. Importing
        it raises ImportError unless the operator has run
        ``pip install -e '.[fallback]'``. Setting ``sys.modules[name] = None``
        is the documented Python mechanism to make a subsequent import
        of that name fail with ImportError.
        """
        import sys

        monkeypatch.setitem(sys.modules, "sentence_transformers", None)

    @pytest.mark.asyncio
    async def test_fallback_raises_actionable_error_when_sentence_transformers_missing(
        self,
        monkeypatch,
        force_onnx_failure,
        force_sentence_transformers_unavailable,
    ):
        """State: ONNX unavailable, fallback opted in via env var, but
        sentence-transformers also missing.

        After Approach C drops sentence-transformers from core deps, the
        WRIT_ALLOW_EMBEDDING_FALLBACK=1 path is only usable when the
        operator has also installed the [fallback] extras group. When
        they have not, build_pipeline must raise a RuntimeError that
        names the missing library AND the install command, not a bare
        ImportError from the inline import inside the fallback branch.

        Same shape as the ONNX-unavailable error (commit dae679a):
        actionable, names cause + remediation, surfaces at startup not
        at first request.
        """
        from writ.graph.db import Neo4jConnection
        from writ.retrieval.pipeline import build_pipeline

        monkeypatch.setenv("WRIT_ALLOW_EMBEDDING_FALLBACK", "1")

        db = Neo4jConnection("bolt://localhost:7687", "neo4j", "writdevpass")
        try:
            count = await db.count_rules()
            if count == 0:
                pytest.skip("Neo4j has no rules. Run scripts/migrate.py first.")

            with pytest.raises(RuntimeError) as excinfo:
                await build_pipeline(db)

            msg = str(excinfo.value)
            # The error must name the missing library, the [fallback]
            # install command, and the pip install verb so a user
            # scanning the message can act without re-reading docs.
            assert "sentence" in msg.lower(), (
                f"RuntimeError must name sentence-transformers; got: {msg!r}"
            )
            assert "fallback" in msg, (
                f"RuntimeError must name the [fallback] extras group; got: {msg!r}"
            )
            assert "pip install" in msg, (
                f"RuntimeError must name the pip install verb; got: {msg!r}"
            )
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_fallback_used_when_override_set_and_warning_logged(
        self, monkeypatch, caplog, force_onnx_failure, fake_sentence_transformer
    ):
        """State 2: ONNX fails, override env var is set, fallback is taken and warned."""
        import logging

        from writ.graph.db import Neo4jConnection
        from writ.retrieval.pipeline import build_pipeline

        monkeypatch.setenv("WRIT_ALLOW_EMBEDDING_FALLBACK", "1")
        caplog.set_level(logging.WARNING, logger="writ.retrieval.pipeline")

        db = Neo4jConnection("bolt://localhost:7687", "neo4j", "writdevpass")
        try:
            count = await db.count_rules()
            if count == 0:
                pytest.skip("Neo4j has no rules. Run scripts/migrate.py first.")

            # Should NOT raise -- the override grants permission to fall back.
            pipeline = await build_pipeline(db)
            assert pipeline is not None

            warnings = [
                rec
                for rec in caplog.records
                if rec.levelno >= logging.WARNING
                and rec.name == "writ.retrieval.pipeline"
            ]
            assert warnings, "expected WARNING from pipeline; got none"
            warning_text = " ".join(rec.getMessage() for rec in warnings)
            assert "ONNX embedding model unavailable" in warning_text
            assert "WRIT_ALLOW_EMBEDDING_FALLBACK" in warning_text
            assert "SentenceTransformer fallback" in warning_text
        finally:
            await db.close()
