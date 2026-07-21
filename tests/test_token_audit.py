"""P0: `writ token-audit` -- the FOOTPRINT observer (WRIT-TOKEN-BLUEPRINT.md).

Pure tests (no Neo4j, no daemon). RED until writ/analysis/token_audit.py + the cli command exist.
Covers: the loud schema canary, exact cost weighting against the blueprint table, the compounding
(cumulative cache_read) curve, labeled-estimate attribution, scorecard shape, and CLI exit-2 on a
canary failure.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from tests.fixtures.token_audit_helpers import load_token_audit
from tests.fixtures.token_audit_helpers import usage as _usage
from tests.fixtures.token_audit_helpers import write_transcript as _write_transcript

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def _ta():
    return load_token_audit(force_reimport=False)


class TestTokenAudit:
    # --- schema canary (fail loud, refuse to emit) ---
    def test_canary_passes_on_wellformed(self):
        ta = _ta()
        ta.assert_usage_schema([_usage(), _usage()])  # no raise

    def test_canary_fails_missing_field(self):
        ta = _ta()
        bad = _usage()
        del bad["cache_read_input_tokens"]
        with pytest.raises(ta.TokenAuditSchemaError) as e:
            ta.assert_usage_schema([bad])
        assert "cache_read_input_tokens" in str(e.value)

    def test_canary_fails_empty(self):
        ta = _ta()
        with pytest.raises(ta.TokenAuditSchemaError):
            ta.assert_usage_schema([])

    # --- cost weighting against the blueprint table ---
    def test_weighted_cost_matches_table(self):
        ta = _ta()
        # input 100*1.0 + output 10*5.0 + read 1000*0.1 + write 200*1.25(default 5m)
        # = 100 + 50 + 100 + 250 = 500
        assert ta.weighted_cost(_usage()) == pytest.approx(500.0)

    def test_cache_creation_split_defaults_5m(self):
        ta = _ta()
        # no ephemeral split -> all cache_creation weighted at 1.25 (5m), not 2.0 (1h)
        u = _usage(inp=0, out=0, read=0, write=400)
        assert ta.weighted_cost(u) == pytest.approx(500.0)  # 400 * 1.25

    def test_cache_creation_split_honored(self):
        ta = _ta()
        # explicit split: 100 @ 5m (1.25) + 100 @ 1h (2.0) = 125 + 200 = 325
        u = _usage(inp=0, out=0, read=0, write=200, c5=100, c1=100)
        assert ta.weighted_cost(u) == pytest.approx(325.0)

    # --- compounding curve (the super-linear re-read) ---
    def test_compounding_curve_monotonic(self):
        ta = _ta()
        turns = [_usage(read=0), _usage(read=100), _usage(read=200)]
        curve = ta.compounding_curve(turns)
        assert all(curve[i] <= curve[i + 1] for i in range(len(curve) - 1))  # nondecreasing
        assert curve[-1] == pytest.approx((0 + 100 + 200) * 0.1)  # == sum(read)*0.1

    # --- attribution is a LABELED estimate, never ground truth ---
    def test_attribution_labeled_estimate(self):
        ta = _ta()
        friction = [{"event": "rag_query", "tokens_injected": 300},
                    {"event": "always_on_inject", "tokens": 1171}]
        attr = ta.attribute_writ(friction)
        assert attr["basis"] == "estimate"
        assert "injected_write_cost" in attr and "injected_reread_cost" in attr

    # --- reread attribution fix: per-segment + clamp (numerator <= denominator) ---
    def test_segment_lengths_splits_on_compaction_drop(self):
        ta = _ta()
        # cache_read climbs, then a sharp drop (compaction), then climbs again -> 2 segments
        turns = [_usage(read=100), _usage(read=200), _usage(read=300),
                 _usage(read=50), _usage(read=120)]  # drop 300->50 is the boundary
        segs = ta.segment_lengths(turns)
        assert len(segs) == 2
        assert sum(segs) == len(turns)

    def test_reread_clamped_to_measured(self):
        ta = _ta()
        # huge injection, tiny measured cache_read cap -> reread cannot exceed the cap
        friction = [{"event": "always_on_inject", "tokens": 10_000_000}]
        attr = ta.attribute_writ(friction, n_turns=100, segments=[100],
                                 cache_read_cost_cap=42.0)
        assert attr["injected_reread_cost"] == 42.0
        assert attr["reread_basis"] == "upper_bound_clamped_to_measured"

    def test_reread_zero_without_segments(self):
        ta = _ta()
        attr = ta.attribute_writ([{"event": "rag_query", "tokens_injected": 500}])
        assert attr["injected_reread_cost"] == 0.0

    # --- scorecard shape + the load-bearing invariant: reread <= measured cache_read ---
    def test_scorecard_shape(self, tmp_path: Path):
        ta = _ta()
        tpath = _write_transcript(tmp_path / "t.jsonl", [_usage(), _usage(read=5000)])
        card = ta.scorecard(str(tpath), None, "claude-opus-4-8")
        for key in ("measured", "attributed", "compounding_curve", "coverage", "cc_version",
                    "segments"):
            assert key in card
        assert card["measured"]["total_cost"] > 0

    def test_scorecard_reread_never_exceeds_measured(self, tmp_path: Path):
        ta = _ta()
        # tiny cache_read, but a friction log claiming a massive injection -> the clamp must hold
        tpath = _write_transcript(tmp_path / "t.jsonl",
                                  [_usage(read=10), _usage(read=10), _usage(read=10)])
        fpath = tmp_path / "friction.log"
        with open(fpath, "w") as f:
            f.write(json.dumps({"event": "always_on_inject", "tokens": 9_000_000}) + "\n")
        card = ta.scorecard(str(tpath), str(fpath), "claude-opus-4-8")
        assert card["attributed"]["injected_reread_cost"] <= card["measured"]["cache_read_cost"]

    # --- CLI fails loud (exit 2) on a canary failure ---
    def test_cli_exit_2_on_canary_fail(self, tmp_path: Path):
        from typer.testing import CliRunner
        if SKILL_ROOT not in sys.path:
            sys.path.insert(0, SKILL_ROOT)
        from writ.cli import app
        # a transcript whose only assistant turn is missing a usage field
        bad = tmp_path / "bad.jsonl"
        with open(bad, "w") as f:
            f.write(json.dumps({"type": "assistant",
                                "message": {"usage": {"input_tokens": 1}}}) + "\n")
        result = CliRunner().invoke(app, ["token-audit", str(bad)])
        assert result.exit_code == 2
        try:
            err = result.stderr or ""
        except (ValueError, Exception):  # old Click mixes stderr into output
            err = ""
        assert "SCHEMA CANARY FAILED" in (result.output + err)
