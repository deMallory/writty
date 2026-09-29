"""Token-audit accounting: response-level dedup, per-model USD rate card, unpriced/partial
semantics, cache-write tiers, --model precedence, legacy compatibility, cost-state
reconciliation, schema canary and render_text sections.

Pure tests (no Neo4j, no daemon). RED until the token-audit correctness repair lands.
Expected dollar values are literal arithmetic on the approved USD/MTok rates; they never go
through RATE_CARD or price_response.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from tests.fixtures.token_audit_helpers import (
    agent_tool_use,
    cost_state_record,
    isolate_log_env,
    load_token_audit,
    response_records,
    tool_result_record,
    write_e2e_tree,
    write_records,
    write_session_tree,
    write_metrics_rows,
    write_transcript,
)
from tests.fixtures.token_audit_helpers import usage as _usage

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))

OPUS48 = "claude-opus-4-8"
SONNET46 = "claude-sonnet-4-6"
OPUS55 = "claude-opus-5-5"
SONNET55 = "claude-sonnet-5-5"
HAIKU_DATED = "claude-haiku-4-5-20251001"


def _ta():
    return load_token_audit(force_reimport=False)


@pytest.fixture(autouse=True)
def _hermetic_log_env(tmp_path, monkeypatch):
    """token-audit CLI runs load subagent_usage summaries; never from the real stream."""
    return isolate_log_env(monkeypatch, tmp_path)


def _main_only(tmp_path: Path, records: list[dict], name: str = "sess") -> Path:
    return write_records(tmp_path / f"{name}.jsonl", records)


def _audit(tmp_path: Path, records: list[dict], model=None) -> dict:
    path = _main_only(tmp_path, records)
    return _ta().scorecard(str(path), None, model)


def _one(model, inp=0, out=0, read=0, write=0, c5=None, c1=None, msg_id="msg_1") -> list[dict]:
    return response_records(msg_id, model, _usage(inp=inp, out=out, read=read, write=write,
                                                  c5=c5, c1=c1))


def _cli(args: list[str]):
    from typer.testing import CliRunner
    if SKILL_ROOT not in sys.path:
        sys.path.insert(0, SKILL_ROOT)
    from writ.cli import app
    return CliRunner().invoke(app, args)


def _kinds(card: dict) -> list[str]:
    return [w["kind"] for w in card["warnings"]]


class TestResponseDedup:
    def test_same_id_identical_usage_is_one_response(self, tmp_path: Path):
        recs = response_records("msg_X", OPUS48, _usage(), n_records=3)
        card = _audit(tmp_path, recs)
        m = card["measured"]
        assert m["responses"] == 1
        assert m["records"] == 3
        assert m["duplicates_collapsed"] == 2
        assert card["turns"] == 1
        assert "duplicate_id_conflict" not in _kinds(card)

    def test_deduped_tokens_counted_once(self, tmp_path: Path):
        recs = response_records("msg_X", OPUS48, _usage(inp=100, out=10, read=1000, write=200),
                                n_records=4)
        m = _audit(tmp_path, recs)["measured"]
        assert m["tokens"] == {"input": 100, "output": 10, "cache_read": 1000,
                               "cache_write_5m": 200, "cache_write_1h": 0}
        assert m["total_cost"] == pytest.approx(500.0)

    def test_distinct_ids_are_separate_responses(self, tmp_path: Path):
        recs = (response_records("msg_A", OPUS48, _usage(), n_records=2)
                + response_records("msg_B", OPUS48, _usage(), n_records=2))
        m = _audit(tmp_path, recs)["measured"]
        assert m["responses"] == 2
        assert m["records"] == 4
        assert m["duplicates_collapsed"] == 2

    def test_conflicting_usage_last_record_wins_at_first_position(self, tmp_path: Path):
        first = response_records("msg_X", OPUS48, _usage(inp=100, out=10))[0]
        other = response_records("msg_Y", OPUS48, _usage(inp=7, out=7))[0]
        last = response_records("msg_X", SONNET46, _usage(inp=100, out=99))[0]
        path = _main_only(tmp_path, [first, other, last])
        turns = _ta().parse_turns(str(path))
        assert len(turns) == 2
        assert turns[0]["output_tokens"] == 99
        assert turns[0]["_model"] == SONNET46
        assert turns[1]["output_tokens"] == 7

    def test_conflict_warning_names_id_and_differing_fields(self, tmp_path: Path):
        first = response_records("msg_X", OPUS48, _usage(out=10))[0]
        last = response_records("msg_X", SONNET46, _usage(out=99))[0]
        card = _audit(tmp_path, [first, last])
        warns = [w for w in card["warnings"] if w["kind"] == "duplicate_id_conflict"]
        assert len(warns) == 1
        assert warns[0]["message_id"] == "msg_X"
        assert warns[0]["records"] == 2
        assert "model" in warns[0]["differing"]
        assert len(warns[0]["differing"]) >= 2
        assert card["measured"]["responses"] == 1
        assert card["measured"]["tokens"]["output"] == 99

    def test_conflict_usage_only_does_not_name_model(self, tmp_path: Path):
        # a non-output field differs (cache_read), so this is a real conflict, not a
        # streaming snapshot
        first = response_records("msg_X", OPUS48, _usage(out=10, read=1000))[0]
        last = response_records("msg_X", OPUS48, _usage(out=10, read=2000))[0]
        card = _audit(tmp_path, [first, last])
        warns = [w for w in card["warnings"] if w["kind"] == "duplicate_id_conflict"]
        assert len(warns) == 1
        assert warns[0]["differing"]
        assert "model" not in warns[0]["differing"]

    # --- streaming snapshots vs real conflicts -------------------------------

    def _snapshots(self, steps: list[dict], models=None) -> list[dict]:
        """One record per step for message id msg_S; each step is a _usage kwargs dict."""
        models = models or [OPUS48] * len(steps)
        return [response_records("msg_S", m, _usage(**kw))[0] for m, kw in zip(models, steps)]

    def _conflicts(self, card: dict) -> list[dict]:
        return [w for w in card["warnings"] if w["kind"] == "duplicate_id_conflict"]

    def test_streaming_output_growth_is_a_silent_snapshot_update(self, tmp_path: Path):
        base = {"inp": 100, "read": 1000, "write": 200, "c5": 150, "c1": 50}
        recs = self._snapshots([{**base, "out": 120}, {**base, "out": 180},
                                {**base, "out": 243}])
        card = _audit(tmp_path, recs)
        m = card["measured"]
        assert self._conflicts(card) == []
        assert m["streaming_snapshot_updates"] == 1
        assert m["duplicate_conflicts"] == 0
        assert m["responses"] == 1
        assert m["records"] == 3
        assert m["tokens"]["output"] == 243
        turns = _ta().parse_turns(str(tmp_path / "sess.jsonl"))
        assert [t["output_tokens"] for t in turns] == [243]

    def test_output_decrease_is_a_conflict(self, tmp_path: Path):
        recs = self._snapshots([{"out": 243}, {"out": 180}])
        card = _audit(tmp_path, recs)
        assert len(self._conflicts(card)) == 1
        assert card["measured"]["duplicate_conflicts"] == 1
        assert card["measured"]["streaming_snapshot_updates"] == 0
        assert card["measured"]["tokens"]["output"] == 180  # last record still wins

    def test_output_growth_with_input_change_is_a_conflict(self, tmp_path: Path):
        card = _audit(tmp_path, self._snapshots([{"inp": 100, "out": 120},
                                                 {"inp": 200, "out": 180}]))
        assert len(self._conflicts(card)) == 1
        assert card["measured"]["streaming_snapshot_updates"] == 0

    def test_output_growth_with_cache_read_change_is_a_conflict(self, tmp_path: Path):
        card = _audit(tmp_path, self._snapshots([{"read": 1000, "out": 120},
                                                 {"read": 1500, "out": 180}]))
        assert len(self._conflicts(card)) == 1
        assert card["measured"]["duplicate_conflicts"] == 1

    def test_output_growth_with_cache_split_change_is_a_conflict(self, tmp_path: Path):
        card = _audit(tmp_path, self._snapshots([{"write": 200, "c5": 200, "c1": 0, "out": 120},
                                                 {"write": 200, "c5": 0, "c1": 200,
                                                  "out": 180}]))
        assert len(self._conflicts(card)) == 1

    def test_output_growth_with_model_change_is_a_conflict_naming_model(self, tmp_path: Path):
        card = _audit(tmp_path, self._snapshots([{"out": 120}, {"out": 180}],
                                                models=[OPUS48, SONNET46]))
        warns = self._conflicts(card)
        assert len(warns) == 1
        assert "model" in warns[0]["differing"]
        assert card["measured"]["streaming_snapshot_updates"] == 0

    def test_aggregate_file_usage_reports_both_counts(self, tmp_path: Path):
        recs = (self._snapshots([{"out": 120}, {"out": 180}])
                + [response_records("msg_T", OPUS48, _usage(out=10, read=1))[0],
                   response_records("msg_T", OPUS48, _usage(out=10, read=2))[0]])
        agg = _ta().aggregate_file_usage(str(_main_only(tmp_path, recs)))
        assert agg["streaming_snapshot_updates"] == 1
        assert agg["duplicate_conflicts"] == 1
        assert agg["conflicts"] == agg["duplicate_conflicts"]
        assert [w["message_id"] for w in agg["warnings"]] == ["msg_T"]

    def test_render_line_shows_session_wide_dedup_totals(self, tmp_path: Path):
        # e2e tree: main 3 records/2 responses, aaa 3/1, bbb 1/1; the orphan is excluded
        text = _ta().render_text(_ta().scorecard(str(write_e2e_tree(tmp_path)), None, None))
        assert ("records 7, responses 4, collapsed 3, streaming_snapshot_updates 0, "
                "duplicate_conflicts 0") in text

    def test_idless_records_each_billed_separately(self, tmp_path: Path):
        recs = []
        for _ in range(3):
            recs += response_records(None, OPUS48, _usage())
        card = _audit(tmp_path, recs)
        m = card["measured"]
        assert m["responses"] == 3
        assert m["records"] == 3
        assert m["duplicates_collapsed"] == 0
        assert card["turns"] == 3

    def test_idless_fixture_legacy_total_unchanged(self, tmp_path: Path):
        tpath = write_transcript(tmp_path / "t.jsonl", [_usage(), _usage(read=5000)])
        card = _ta().scorecard(str(tpath), None, OPUS48)
        # (100 + 10*5 + 1000*0.1 + 200*1.25) + (100 + 50 + 5000*0.1 + 250) = 500 + 900
        assert card["measured"]["total_cost"] == pytest.approx(1400.0)
        assert card["turns"] == 2


class TestRatesAndNormalization:
    def test_mixed_models_priced_per_response(self, tmp_path: Path):
        recs = (_one(OPUS55, inp=1000, out=2000, read=100000, msg_id="msg_o")
                + _one(SONNET55, inp=2000, out=4000, read=50000, msg_id="msg_s"))
        card = _audit(tmp_path, recs)
        # opus-5-5: 1000*4 + 2000*20 + 100000*0.20 = 64,000 ; sonnet-5-5: 2000*2 + 4000*10 + 50000*0.2 = 54,000
        assert card["cost_by_model"][OPUS55]["usd"] == pytest.approx(0.064)
        assert card["cost_by_model"][SONNET55]["usd"] == pytest.approx(0.054)
        assert card["measured"]["total_usd"] == pytest.approx(0.118)
        assert card["session"]["total_usd"] == pytest.approx(0.118)
        assert card["session"]["partial"] is False

    def test_opus_5_and_sonnet_5_all_five_rates(self, tmp_path: Path):
        recs = (response_records("msg_o", "claude-opus-5",
                                 _usage(inp=1000, out=2000, read=100000, write=10000,
                                        c5=4000, c1=6000))
                + response_records("msg_s", "claude-sonnet-5",
                                   _usage(inp=2000, out=4000, read=50000, write=8000,
                                          c5=3000, c1=5000)))
        card = _audit(tmp_path, recs)
        # opus-5: 1000*5 + 2000*25 + 100000*0.50 + 4000*6.25 + 6000*10
        #       = 5,000 + 50,000 + 50,000 + 25,000 + 60,000 = 190,000 -> $0.19
        # sonnet-5: 2000*2 + 4000*10 + 50000*0.20 + 3000*2.50 + 5000*4
        #       = 4,000 + 40,000 + 10,000 + 7,500 + 20,000 = 81,500 -> $0.0815
        assert card["cost_by_model"]["claude-opus-5"]["usd"] == pytest.approx(0.19)
        assert card["cost_by_model"]["claude-sonnet-5"]["usd"] == pytest.approx(0.0815)
        assert card["measured"]["total_usd"] == pytest.approx(0.2715)
        assert card["unpriced"] == {}

    def test_dated_haiku_prices_as_base_model(self, tmp_path: Path):
        card = _audit(tmp_path, _one(HAIKU_DATED, inp=1_000_000, out=1_000_000))
        # 1_000_000 * 1.0 + 1_000_000 * 5.0 = $6.00
        assert card["measured"]["total_usd"] == pytest.approx(6.0)
        assert "claude-haiku-4-5" in card["cost_by_model"]
        assert HAIKU_DATED not in card["cost_by_model"]
        assert card["unpriced"] == {}

    def test_opus_5_6_unpriced_never_priced_as_5_5(self, tmp_path: Path):
        recs = (_one("claude-opus-5-6", inp=1_000_000, msg_id="msg_a")
                + _one(OPUS55, inp=1_000_000, msg_id="msg_b"))
        card = _audit(tmp_path, recs)
        assert "claude-opus-5-6" in card["unpriced"]
        assert card["cost_by_model"]["claude-opus-5-6"]["usd"] is None
        # only the 5.5 response is priced: 1_000_000 * 4.0 = $4.00
        assert card["measured"]["total_usd"] == pytest.approx(4.0)
        assert card["cost_by_model"][OPUS55]["usd"] == pytest.approx(4.0)

    def test_normalize_model_contract(self):
        ta = _ta()
        assert ta.normalize_model(OPUS55) == OPUS55
        assert ta.normalize_model(HAIKU_DATED) == "claude-haiku-4-5"
        assert ta.normalize_model("claude-opus-5-6") is None
        assert ta.normalize_model("claude-opus-5-5-preview") is None
        assert ta.normalize_model("") is None

    def test_opus_5_5_cache_read_is_twenty_cents(self, tmp_path: Path):
        card = _audit(tmp_path, _one(OPUS55, read=1_000_000))
        # 1_000_000 * 0.20 / 1e6 = $0.20 (not $0.40, not $0.50)
        assert card["measured"]["total_usd"] == pytest.approx(0.20)

    def test_five_minute_cache_write_split(self, tmp_path: Path):
        card = _audit(tmp_path, _one(OPUS48, write=1_000_000, c5=1_000_000, c1=0))
        assert card["measured"]["total_usd"] == pytest.approx(6.25)
        assert card["measured"]["tokens"]["cache_write_5m"] == 1_000_000

    def test_unsplit_cache_creation_prices_as_five_minute(self, tmp_path: Path):
        card = _audit(tmp_path, _one(OPUS48, write=1_000_000))
        assert card["measured"]["total_usd"] == pytest.approx(6.25)
        assert card["measured"]["tokens"]["cache_write_5m"] == 1_000_000
        assert card["measured"]["tokens"]["cache_write_1h"] == 0

    def test_one_hour_cache_write(self, tmp_path: Path):
        card = _audit(tmp_path, _one(OPUS48, write=1_000_000, c5=0, c1=1_000_000))
        assert card["measured"]["total_usd"] == pytest.approx(10.0)
        assert card["measured"]["tokens"]["cache_write_1h"] == 1_000_000


class TestUnpricedAndPartial:
    def _mixed(self, tmp_path: Path) -> dict:
        recs = (_one(OPUS48, inp=1_000_000, msg_id="msg_ok")
                + _one("claude-mystery-9", inp=300, out=40, read=5, write=7, msg_id="msg_bad"))
        return _audit(tmp_path, recs)

    def test_unknown_model_listed_with_raw_counts(self, tmp_path: Path):
        u = self._mixed(tmp_path)["unpriced"]["claude-mystery-9"]
        assert u["responses"] == 1
        assert u["input"] == 300
        assert u["output"] == 40
        assert u["cache_read"] == 5
        assert u["cache_write_5m"] == 7
        assert u["cache_write_1h"] == 0
        assert "main" in u["scope"]

    def test_unknown_model_warns(self, tmp_path: Path):
        card = self._mixed(tmp_path)
        warns = [w for w in card["warnings"] if w["kind"] == "unpriced_model"]
        assert [w["model"] for w in warns] == ["claude-mystery-9"]

    def test_partial_flags_and_priced_floor(self, tmp_path: Path):
        card = self._mixed(tmp_path)
        assert card["measured"]["usd_partial"] is True
        assert card["session"]["partial"] is True
        # floor = the priced opus-4-8 response: 1_000_000 * 5.0 = $5.00
        assert card["measured"]["total_usd"] == pytest.approx(5.0)
        assert card["measured"]["priced_total_usd"] == pytest.approx(5.0)

    def test_render_text_labels_partial(self, tmp_path: Path):
        ta = _ta()
        text = ta.render_text(self._mixed(tmp_path))
        assert "PARTIAL" in text
        assert "UNPRICED" in text

    def test_total_usd_none_when_nothing_priced_on_main(self, tmp_path: Path):
        card = _audit(tmp_path, _one("claude-mystery-9", inp=300))
        assert card["measured"]["total_usd"] is None
        assert card["measured"]["usd_partial"] is True
        assert card["session"]["partial"] is True

    def test_fully_priced_session_is_not_partial(self, tmp_path: Path):
        card = _audit(tmp_path, _one(OPUS48, inp=1000))
        assert card["measured"]["usd_partial"] is False
        assert card["session"]["partial"] is False
        assert card["unpriced"] == {}
        assert "unpriced_model" not in _kinds(card)

    def test_synthetic_prices_zero_and_is_never_unpriced(self, tmp_path: Path):
        recs = (_one("<synthetic>", inp=5000, out=5000, read=5000, write=5000, msg_id="msg_syn")
                + _one(OPUS48, inp=1_000_000, msg_id="msg_real"))
        card = _audit(tmp_path, recs)
        assert "<synthetic>" not in card["unpriced"]
        assert not [w for w in card["warnings"] if w.get("model") == "<synthetic>"]
        assert "unpriced_model" not in _kinds(card)
        assert card["measured"]["usd_partial"] is False
        assert card["measured"]["total_usd"] == pytest.approx(5.0)


class TestModelFallbackPrecedence:
    def _modelless(self, tmp_path: Path) -> Path:
        return _main_only(tmp_path, response_records("msg_1", None, _usage(inp=1_000_000,
                                                                          out=0, read=0, write=0)))

    def test_scorecard_model_arg_prices_modelless_record(self, tmp_path: Path):
        card = _ta().scorecard(str(self._modelless(tmp_path)), None, OPUS48)
        assert card["measured"]["total_usd"] == pytest.approx(5.0)  # 1_000_000 * 5.0
        assert card["unpriced"] == {}

    def test_modelless_without_fallback_is_unpriced(self, tmp_path: Path):
        card = _ta().scorecard(str(self._modelless(tmp_path)), None, None)
        assert "<none>" in card["unpriced"]
        assert card["unpriced"]["<none>"]["input"] == 1_000_000
        assert card["measured"]["total_usd"] is None
        assert card["measured"]["usd_partial"] is True

    def test_cli_default_has_no_fallback(self, tmp_path: Path):
        result = _cli(["token-audit", str(self._modelless(tmp_path)), "--json"])
        assert result.exit_code == 0
        card = json.loads(result.output)
        assert "<none>" in card["unpriced"]
        assert card["measured"]["total_usd"] is None

    def test_cli_model_option_is_fallback(self, tmp_path: Path):
        result = _cli(["token-audit", str(self._modelless(tmp_path)), "--model", OPUS48,
                       "--json"])
        assert result.exit_code == 0
        card = json.loads(result.output)
        assert card["unpriced"] == {}
        assert card["measured"]["total_usd"] == pytest.approx(5.0)

    def test_fallback_never_overrides_record_model(self, tmp_path: Path):
        path = _main_only(tmp_path, _one(SONNET46, inp=1_000_000))
        card = _ta().scorecard(str(path), None, OPUS48)
        assert card["measured"]["total_usd"] == pytest.approx(3.0)  # sonnet-4-6, not 5.0

    def test_cli_model_never_overrides_record_model(self, tmp_path: Path):
        path = _main_only(tmp_path, _one(SONNET46, inp=1_000_000))
        card = json.loads(_cli(["token-audit", str(path), "--model", OPUS48, "--json"]).output)
        assert card["measured"]["total_usd"] == pytest.approx(3.0)

    def test_unknown_record_model_stays_unpriced_despite_fallback(self, tmp_path: Path):
        path = _main_only(tmp_path, _one("claude-mystery-9", inp=1_000_000))
        card = _ta().scorecard(str(path), None, OPUS48)
        assert "claude-mystery-9" in card["unpriced"]
        assert card["measured"]["total_usd"] is None


class TestLegacyCompatibility:
    def test_total_cost_equals_weighted_token_cost(self, tmp_path: Path):
        tpath = write_transcript(tmp_path / "t.jsonl", [_usage(), _usage(read=5000)])
        m = _ta().scorecard(str(tpath), None, OPUS48)["measured"]
        assert m["weighted_token_cost"] == m["total_cost"]
        assert m["total_cost"] == pytest.approx(1400.0)

    def test_cost_weights_unchanged(self):
        assert _ta().COST_WEIGHTS == {"input": 1.0, "cache_read": 0.1, "cache_write_5m": 1.25,
                                      "cache_write_1h": 2.0, "output": 5.0}

    def test_input_usd_per_mtok_keeps_existing_entries(self):
        table = _ta().INPUT_USD_PER_MTOK
        for model, rate in {OPUS48: 5.0, "claude-opus-4-7": 5.0, "claude-opus-4-6": 5.0,
                            SONNET46: 3.0, "claude-haiku-4-5": 1.0,
                            "claude-fable-5": 10.0}.items():
            assert table[model] == rate
        assert "<synthetic>" not in table

    @pytest.mark.parametrize("model,input_rate", [
        (OPUS48, 5.0), ("claude-opus-4-7", 5.0), ("claude-opus-4-6", 5.0),
        (SONNET46, 3.0), ("claude-haiku-4-5", 1.0), ("claude-fable-5", 10.0),
    ])
    def test_4x_and_fable_total_usd_matches_old_formula(self, tmp_path: Path, model, input_rate):
        tpath = write_transcript(tmp_path / "t.jsonl", [_usage(), _usage(read=5000)],
                                 model=model)
        m = _ta().scorecard(str(tpath), None, None)["measured"]
        assert m["total_usd"] == pytest.approx(m["total_cost"] / 1e6 * input_rate)
        assert m["total_usd"] == pytest.approx(1400.0 / 1e6 * input_rate)


class TestCostStateReconciliation:
    def _main_with_state(self, tmp_path: Path, state_records: list[dict]) -> Path:
        recs = _one(OPUS48, inp=1_000_000) + state_records
        return _main_only(tmp_path, recs)

    def test_absent_reports_present_false(self, tmp_path: Path):
        card = _audit(tmp_path, _one(OPUS48, inp=1000))
        assert card["reconciliation"]["present"] is False
        assert card["session"]["total_usd"] == pytest.approx(0.005)  # 1000 * 5.0 / 1e6

    def test_absent_render_text_says_so(self, tmp_path: Path):
        ta = _ta()
        text = ta.render_text(_audit(tmp_path, _one(OPUS48, inp=1000)))
        assert "RECONCILIATION" in text
        assert "cost-state: absent" in text

    def test_present_reports_totals_and_delta(self, tmp_path: Path):
        state = cost_state_record(5.5, {OPUS48: {"usd": 5.5, "input": 1_000_000, "output": 0,
                                                 "cache_read": 0, "cache_write": 0}})
        card = _ta().scorecard(str(self._main_with_state(tmp_path, [state])), None, None)
        r = card["reconciliation"]
        assert r["present"] is True
        assert r["cc_total_usd"] == pytest.approx(5.5)
        assert r["writ_session_usd"] == pytest.approx(5.0)
        assert abs(r["delta_usd"]) == pytest.approx(0.5)
        assert r["per_model"][OPUS48]["cc_usd"] == pytest.approx(5.5)
        assert r["per_model"][OPUS48]["writ_usd"] == pytest.approx(5.0)
        assert abs(r["per_model"][OPUS48]["delta_usd"]) == pytest.approx(0.5)
        assert r["per_model"][OPUS48]["cc_tokens"]["input"] == 1_000_000
        assert r["per_model"][OPUS48]["writ_tokens"]["input"] == 1_000_000

    def test_last_cost_state_record_is_used(self, tmp_path: Path):
        pm = {"usd": 1.0, "input": 1, "output": 0, "cache_read": 0, "cache_write": 0}
        early = cost_state_record(1.0, {OPUS48: pm})
        late = cost_state_record(5.0, {OPUS48: {**pm, "usd": 5.0, "input": 1_000_000}})
        card = _ta().scorecard(str(self._main_with_state(tmp_path, [early, late])), None, None)
        assert card["reconciliation"]["cc_total_usd"] == pytest.approx(5.0)

    def test_scope_main_only_when_tokens_match_main(self, tmp_path: Path):
        state = cost_state_record(5.0, {OPUS48: {"usd": 5.0, "input": 1_000_000, "output": 0,
                                                 "cache_read": 0, "cache_write": 0}})
        card = _ta().scorecard(str(self._main_with_state(tmp_path, [state])), None, None)
        assert card["reconciliation"]["scope"] == "main_only"

    def test_scope_superset_when_state_lists_unused_model(self, tmp_path: Path):
        state = cost_state_record(5.5, {
            OPUS48: {"usd": 5.0, "input": 1_000_000, "output": 0, "cache_read": 0,
                     "cache_write": 0},
            "claude-haiku-4-5": {"usd": 0.5, "input": 500_000, "output": 0, "cache_read": 0,
                                 "cache_write": 0}})
        card = _ta().scorecard(str(self._main_with_state(tmp_path, [state])), None, None)
        assert card["reconciliation"]["scope"] == "superset_or_unknown"

    def test_scope_main_plus_subagents_when_tokens_match_tree(self, tmp_path: Path):
        main = (response_records("msg_m", OPUS48, _usage(inp=1_000_000, out=0, read=0, write=0),
                                 tool_uses=[agent_tool_use("toolu_1")])
                + [tool_result_record("toolu_1", "aaa")]
                + [cost_state_record(7.5, {OPUS48: {"usd": 7.5, "input": 1_500_000, "output": 0,
                                                    "cache_read": 0, "cache_write": 0}})])
        sub = response_records("msg_s", OPUS48, _usage(inp=500_000, out=0, read=0, write=0))
        path = write_session_tree(tmp_path, "sess-r", main, {
            "aaa": {"records": sub, "meta": {"agentType": "writ-explorer",
                                             "toolUseId": "toolu_1", "spawnDepth": 1}}})
        card = _ta().scorecard(str(path), None, None)
        assert card["session"]["total_usd"] == pytest.approx(7.5)
        assert card["reconciliation"]["scope"] == "main_plus_subagents"
        assert card["reconciliation"]["delta_usd"] == pytest.approx(0.0, abs=1e-9)

    def test_reconciliation_never_changes_exit_code(self, tmp_path: Path):
        state = cost_state_record(999.0, {"claude-mystery-9": {
            "usd": 999.0, "input": 1, "output": 1, "cache_read": 1, "cache_write": 1}})
        path = self._main_with_state(tmp_path, [state])
        result = _cli(["token-audit", str(path), "--json"])
        assert result.exit_code == 0
        assert json.loads(result.output)["reconciliation"]["present"] is True


class TestSchemaCanary:
    def test_cli_exit_2_on_drifted_main_transcript(self, tmp_path: Path):
        bad = tmp_path / "bad.jsonl"
        bad.write_text(json.dumps({"type": "assistant", "message": {
            "id": "msg_1", "model": OPUS48, "usage": {"input_tokens": 1}}}) + "\n")
        result = _cli(["token-audit", str(bad)])
        assert result.exit_code == 2
        try:
            err = result.stderr or ""
        except (ValueError, Exception):
            err = ""
        assert "[token-audit] SCHEMA CANARY FAILED" in (result.output + err)

    def _tree_with_bad_subagent(self, tmp_path: Path) -> Path:
        main = (response_records("msg_m", OPUS48, _usage(),
                                 tool_uses=[agent_tool_use("toolu_1")])
                + [tool_result_record("toolu_1", "aaa")])
        bad_usage = _usage()
        del bad_usage["cache_read_input_tokens"]
        sub = response_records("msg_s", OPUS48, bad_usage)
        return write_session_tree(tmp_path, "sess-bad", main, {
            "aaa": {"records": sub, "meta": {"agentType": "writ-explorer",
                                             "toolUseId": "toolu_1", "spawnDepth": 1}}})

    def test_subagent_missing_usage_field_raises(self, tmp_path: Path):
        ta = _ta()
        path = self._tree_with_bad_subagent(tmp_path)
        with pytest.raises(ta.TokenAuditSchemaError) as e:
            ta.scorecard(str(path), None, None)
        assert "cache_read_input_tokens" in str(e.value)

    def test_subagent_missing_usage_field_cli_exit_2(self, tmp_path: Path):
        result = _cli(["token-audit", str(self._tree_with_bad_subagent(tmp_path))])
        assert result.exit_code == 2


class TestRenderText:
    def _full_card(self, tmp_path: Path) -> dict:
        path = write_e2e_tree(tmp_path)
        extra = (response_records("msg_bad", "claude-mystery-9", _usage(inp=10, out=1, read=0,
                                                                        write=0))
                 + [cost_state_record(0.283, {OPUS55: {
                     "usd": 0.194, "input": 1500, "output": 3000, "cache_read": 300000,
                     "cache_write": 10000}})])
        with open(path, "a") as f:
            for rec in extra:
                f.write(json.dumps(rec) + "\n")
        return _ta().scorecard(str(path), None, None)

    def test_keeps_legacy_sections(self, tmp_path: Path):
        text = _ta().render_text(_audit(tmp_path, _one(OPUS48, inp=1000)))
        assert "-- MEASURED cost" in text
        assert "-- ATTRIBUTED to Writ" in text
        assert "-- PREVENTED (floor; read_blocked events) --" in text
        assert "prevented_cost_floor" in text

    def test_adds_all_new_sections(self, tmp_path: Path):
        text = _ta().render_text(self._full_card(tmp_path))
        for heading in ("SESSION TREE", "BY MODEL", "BY ROLE", "UNPRICED", "ORPHANS",
                        "RECONCILIATION", "ACCOUNTING WARNINGS"):
            assert heading in text, heading

    def test_session_tree_shows_coverage_summary(self, tmp_path: Path):
        card = self._full_card(tmp_path)
        assert card["dispatch_coverage"]["summary"] == "2/2 dispatches accounted"
        assert "2/2 dispatches accounted" in _ta().render_text(card)

    def test_complete_session_is_not_labeled_partial(self, tmp_path: Path):
        text = _ta().render_text(_audit(tmp_path, _one(OPUS48, inp=1000)))
        assert "PARTIAL" not in text


# ---------------------------------------------------------------------------
# Review fixes: reconciliation floor flag, CLI hermeticity and summary-load degradation
# ---------------------------------------------------------------------------

def _partial_tree_with_state(tmp_path: Path) -> Path:
    """Main opus-4-8 1M input dispatching toolu_Z -> zzz (no transcript) plus a cost-state."""
    main = (response_records("msg_m", OPUS48, _usage(inp=1_000_000, out=0, read=0, write=0),
                             tool_uses=[agent_tool_use("toolu_Z")])
            + [tool_result_record("toolu_Z", "zzz")]
            + [cost_state_record(5.0, {OPUS48: {"usd": 5.0, "input": 1_000_000, "output": 0,
                                                "cache_read": 0, "cache_write": 0}})])
    return write_session_tree(tmp_path, "sess-floor", main)


class TestReconciliationWritPartial:
    def test_writ_partial_true_when_session_is_partial(self, tmp_path: Path):
        card = _ta().scorecard(str(_partial_tree_with_state(tmp_path)), None, None)
        assert card["session"]["partial"] is True
        assert card["reconciliation"]["writ_partial"] is True

    def test_writ_partial_false_when_session_is_complete(self, tmp_path: Path):
        state = cost_state_record(5.0, {OPUS48: {"usd": 5.0, "input": 1_000_000, "output": 0,
                                                 "cache_read": 0, "cache_write": 0}})
        path = _main_only(tmp_path, _one(OPUS48, inp=1_000_000) + [state])
        card = _ta().scorecard(str(path), None, None)
        assert card["session"]["partial"] is False
        assert card["reconciliation"]["writ_partial"] is False

    def test_render_text_labels_writ_figure_a_floor_when_partial(self, tmp_path: Path):
        ta = _ta()
        text = ta.render_text(ta.scorecard(str(_partial_tree_with_state(tmp_path)), None, None))
        line = next(ln for ln in text.splitlines() if ln.strip().startswith("cc_total"))
        assert line.endswith("(Writ figure is a floor)")

    def test_render_text_no_floor_label_when_complete(self, tmp_path: Path):
        state = cost_state_record(5.0, {OPUS48: {"usd": 5.0, "input": 1_000_000, "output": 0,
                                                 "cache_read": 0, "cache_write": 0}})
        ta = _ta()
        text = ta.render_text(ta.scorecard(
            str(_main_only(tmp_path, _one(OPUS48, inp=1_000_000) + [state])), None, None))
        assert "cc_total" in text
        assert "(Writ figure is a floor)" not in text


def _summary_main(tmp_path: Path) -> Path:
    """Main opus-4-8 1M input dispatching toolu_S -> sss, whose transcript is gone."""
    main = (response_records("msg_m", OPUS48, _usage(inp=1_000_000, out=0, read=0, write=0),
                             tool_uses=[agent_tool_use("toolu_S")])
            + [tool_result_record("toolu_S", "sss")])
    return write_session_tree(tmp_path / "tree", "sess-cli-sum", main)


def _sss_row(parent_session: str = "sess-cli-sum") -> dict:
    return {"event": "subagent_usage", "session": "sss", "agent_id": "sss",
            "parent_session": parent_session, "dispatch_id": "toolu_S",
            "role": "writ-explorer", "role_source": "sidecar", "status": "ok", "schema": 1,
            "responses": 1, "records": 1, "duplicates_collapsed": 0,
            "streaming_snapshot_updates": 0, "conflicts": 0,
            "model_usage": {OPUS48: {"responses": 1, "input": 200_000, "output": 0,
                                     "cache_read": 0, "cache_write_5m": 0,
                                     "cache_write_1h": 0}},
            "child_dispatches": {}, "first_ts": None, "last_ts": None}


class TestCliSummaryLoading:
    def test_cli_reads_summaries_from_the_sandboxed_log_root(self, tmp_path: Path):
        write_metrics_rows(Path(os.environ["WRIT_LOG_ROOT"]), [_sss_row()])
        result = _cli(["token-audit", str(_summary_main(tmp_path)), "--json"])
        assert result.exit_code == 0, result.output
        card = json.loads(result.output)
        assert card["dispatch_coverage"]["by_source"]["summary"] == 1
        assert card["session"]["total_usd"] == pytest.approx(1_200_000 * 5 / 1e6)

    def test_cli_degrades_when_loading_summaries_raises(self, tmp_path: Path, monkeypatch):
        def boom(*_a, **_k):
            raise RuntimeError("metrics stream unreadable")
        monkeypatch.setattr(_ta(), "load_usage_summaries", boom)
        result = _cli(["token-audit", str(_summary_main(tmp_path)), "--json"])
        assert result.exit_code == 0, result.output
        card = json.loads(result.output)
        assert {"kind": "usage_summaries_unavailable", "error": "RuntimeError"} \
            in card["warnings"]
        assert card["dispatch_coverage"]["missing_transcript"] == 1
        assert card["session"]["partial"] is True

    def test_cli_degrades_when_resolving_the_project_raises(self, tmp_path: Path,
                                                            monkeypatch):
        import writ.shared.logging as wlog

        def boom(*_a, **_k):
            raise ValueError("no project")
        monkeypatch.setattr(wlog, "resolve_project", boom)
        result = _cli(["token-audit", str(_summary_main(tmp_path)), "--json"])
        assert result.exit_code == 0, result.output
        card = json.loads(result.output)
        assert {"kind": "usage_summaries_unavailable", "error": "ValueError"} \
            in card["warnings"]

    def test_cli_text_output_shows_the_degradation_warning(self, tmp_path: Path, monkeypatch):
        def boom(*_a, **_k):
            raise RuntimeError("x")
        monkeypatch.setattr(_ta(), "load_usage_summaries", boom)
        result = _cli(["token-audit", str(_summary_main(tmp_path))])
        assert result.exit_code == 0, result.output
        assert "usage_summaries_unavailable" in result.output

    def test_canary_exit_code_unchanged_when_summaries_fail(self, tmp_path: Path,
                                                            monkeypatch):
        def boom(*_a, **_k):
            raise RuntimeError("x")
        monkeypatch.setattr(_ta(), "load_usage_summaries", boom)
        bad = tmp_path / "bad.jsonl"
        bad.write_text(json.dumps({"type": "assistant",
                                   "message": {"usage": {"input_tokens": 1}}}) + "\n")
        assert _cli(["token-audit", str(bad)]).exit_code == 2

    def test_cli_no_warning_when_summaries_load(self, tmp_path: Path):
        result = _cli(["token-audit", str(_summary_main(tmp_path)), "--json"])
        assert result.exit_code == 0, result.output
        kinds = _kinds(json.loads(result.output))
        assert "usage_summaries_unavailable" not in kinds
