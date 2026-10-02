"""Token-audit session-tree aggregation (plan: tree aggregation, classification,
attribution invariants, hand-computed end-to-end fixture).

Pure unit tests over on-disk session trees built in tmp_path. RED until
writ/analysis/token_tree.py and the tree keys of token_audit.scorecard exist.

Expected dollars are written as literal arithmetic (USD per MTok rates typed
inline), never derived from RATE_CARD or price_response.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures.token_audit_helpers import (
    agent_tool_use,
    load_token_audit,
    response_records,
    tool_result_record,
    usage,
    write_e2e_tree,
    write_session_tree,
)


def _card(main_path: Path) -> dict:
    return load_token_audit().scorecard(str(main_path), None, None)


def _dispatch(card: dict, dispatch_id: str) -> dict:
    rows = [d for d in card["cost_by_dispatch"] if d["dispatch_id"] == dispatch_id]
    assert len(rows) == 1, f"expected exactly one cost_by_dispatch row for {dispatch_id}: {rows}"
    return rows[0]


def _priced_dispatch_usd(card: dict) -> float:
    return sum(d["usd"] for d in card["cost_by_dispatch"]
               if d["status"] == "accounted" and d["usd"] is not None)


# ---------------------------------------------------------------------------
# Main + one linked subagent
# ---------------------------------------------------------------------------

class TestSingleLinkedSubagent:
    def _tree(self, tmp_path: Path) -> Path:
        main_records = (
            response_records("msg_m1", "claude-opus-5-5",
                             usage(inp=1000, out=500, read=0, write=0),
                             tool_uses=[agent_tool_use("toolu_A", "writ:writ-explorer")])
            + [tool_result_record("toolu_A", "aaa", "claude-sonnet-5-5")]
        )
        subagents = {"aaa": {
            "records": response_records("msg_a1", "claude-sonnet-5-5",
                                        usage(inp=1000, out=1000, read=0, write=0)),
            "meta": {"agentType": "writ:writ-explorer", "toolUseId": "toolu_A",
                     "spawnDepth": 1},
        }}
        return write_session_tree(tmp_path, "sess-one", main_records, subagents)

    def test_session_total_is_main_plus_subagent(self, tmp_path: Path):
        card = _card(self._tree(tmp_path))
        main_usd = (1000 * 4 + 500 * 20) / 1e6            # 0.014
        sub_usd = (1000 * 2 + 1000 * 10) / 1e6            # 0.012
        s = card["session"]
        assert s["main_usd"] == pytest.approx(main_usd)
        assert s["subagents_usd"] == pytest.approx(sub_usd)
        assert s["total_usd"] == pytest.approx(main_usd + sub_usd)
        assert s["total_usd"] == pytest.approx(0.026)
        assert s["partial"] is False

    def test_dispatch_is_accounted_with_identity_fields(self, tmp_path: Path):
        card = _card(self._tree(tmp_path))
        assert len(card["cost_by_dispatch"]) == 1
        d = _dispatch(card, "toolu_A")
        assert d["status"] == "accounted"
        assert d["source"] == "transcript"
        assert d["agent_id"] == "aaa"
        assert d["role"] == "writ-explorer"
        assert d["parent_dispatch_id"] is None
        assert d["usd"] == pytest.approx((1000 * 2 + 1000 * 10) / 1e6)

    def test_coverage_summary_full(self, tmp_path: Path):
        card = _card(self._tree(tmp_path))
        cov = card["dispatch_coverage"]
        assert cov["summary"] == "1/1 dispatches accounted"
        assert cov["dispatches"] == 1
        assert cov["accounted"] == 1
        assert cov["missing_transcript"] == 0
        assert cov["missing_metadata"] == 0
        assert cov["orphan_transcripts"] == 0

    def test_main_thread_measured_excludes_subagent(self, tmp_path: Path):
        card = _card(self._tree(tmp_path))
        assert card["measured"]["total_usd"] == pytest.approx((1000 * 4 + 500 * 20) / 1e6)


# ---------------------------------------------------------------------------
# Multiple subagents including a nested child
# ---------------------------------------------------------------------------

class TestNestedSubagents:
    """main -> toolu_P (agent pp) -> toolu_C (agent cc1, nested); main -> toolu_Q (agent qq)."""

    def _tree(self, tmp_path: Path) -> Path:
        main_records = (
            response_records("msg_m1", "claude-opus-5-5",
                             usage(inp=1000, out=1000, read=0, write=0),
                             n_records=2,
                             tool_uses=[agent_tool_use("toolu_P", "writ-planner"),
                                        agent_tool_use("toolu_Q", "writ-explorer")])
            + [tool_result_record("toolu_P", "pp"), tool_result_record("toolu_Q", "qq")]
        )
        pp_records = (
            response_records("msg_p1", "claude-sonnet-5-5",
                             usage(inp=1000, out=1000, read=0, write=0),
                             tool_uses=[agent_tool_use("toolu_C", "writ-reviewer")])
            + [tool_result_record("toolu_C", "cc1")]
        )
        subagents = {
            "pp": {"records": pp_records,
                   "meta": {"agentType": "writ-planner", "toolUseId": "toolu_P",
                            "spawnDepth": 1}},
            "cc1": {"records": response_records(
                        "msg_c1", "claude-haiku-4-5",
                        usage(inp=1000, out=1000, read=0, write=0)),
                    "meta": {"agentType": "writ-reviewer", "toolUseId": "toolu_C",
                             "spawnDepth": 2}},
            "qq": {"records": response_records(
                        "msg_q1", "claude-opus-5-5",
                        usage(inp=500, out=500, read=0, write=0)),
                   "meta": {"agentType": "writ-explorer", "toolUseId": "toolu_Q",
                            "spawnDepth": 1}},
        }
        return write_session_tree(tmp_path, "sess-nested", main_records, subagents)

    def test_each_dispatch_accounted_once(self, tmp_path: Path):
        card = _card(self._tree(tmp_path))
        ids = sorted(d["dispatch_id"] for d in card["cost_by_dispatch"])
        assert ids == ["toolu_C", "toolu_P", "toolu_Q"]
        assert all(d["status"] == "accounted" for d in card["cost_by_dispatch"])
        assert card["dispatch_coverage"]["summary"] == "3/3 dispatches accounted"
        assert card["dispatch_coverage"]["orphan_transcripts"] == 0

    def test_parent_dispatch_id_and_depth(self, tmp_path: Path):
        card = _card(self._tree(tmp_path))
        p, q, c = (_dispatch(card, i) for i in ("toolu_P", "toolu_Q", "toolu_C"))
        assert p["parent_dispatch_id"] is None
        assert q["parent_dispatch_id"] is None
        assert c["parent_dispatch_id"] == "toolu_P"
        assert c["agent_id"] == "cc1"
        assert c["depth"] == p["depth"] + 1
        assert q["depth"] == p["depth"]

    def test_hand_computed_amounts(self, tmp_path: Path):
        card = _card(self._tree(tmp_path))
        main_usd = (1000 * 4 + 1000 * 20) / 1e6           # 0.024
        p_usd = (1000 * 2 + 1000 * 10) / 1e6              # 0.012 sonnet-5-5
        c_usd = (1000 * 1 + 1000 * 5) / 1e6               # 0.006 haiku-4-5
        q_usd = (500 * 4 + 500 * 20) / 1e6                # 0.012 opus-5-5
        assert _dispatch(card, "toolu_P")["usd"] == pytest.approx(p_usd)
        assert _dispatch(card, "toolu_C")["usd"] == pytest.approx(c_usd)
        assert _dispatch(card, "toolu_Q")["usd"] == pytest.approx(q_usd)
        assert card["session"]["total_usd"] == pytest.approx(main_usd + p_usd + c_usd + q_usd)
        assert card["session"]["total_usd"] == pytest.approx(0.054)

    def test_sums_over_model_role_and_dispatch_equal_session_total(self, tmp_path: Path):
        card = _card(self._tree(tmp_path))
        total = card["session"]["total_usd"]
        by_model = sum(v["usd"] for v in card["cost_by_model"].values())
        by_role = sum(v["usd"] for v in card["cost_by_role"].values())
        assert by_model == pytest.approx(total)
        assert by_role == pytest.approx(total)
        assert card["session"]["main_usd"] + _priced_dispatch_usd(card) == pytest.approx(total)


# ---------------------------------------------------------------------------
# missing_transcript / missing_metadata
# ---------------------------------------------------------------------------

class TestGaps:
    def test_missing_transcript_is_gap_and_marks_partial(self, tmp_path: Path):
        main_records = (
            response_records("msg_m1", "claude-opus-5-5",
                             usage(inp=1000, out=500, read=0, write=0),
                             n_records=2,
                             tool_uses=[agent_tool_use("toolu_A", "writ-explorer"),
                                        agent_tool_use("toolu_Z", "writ:writ-reviewer")])
            + [tool_result_record("toolu_A", "aaa"), tool_result_record("toolu_Z", "zzz")]
        )
        subagents = {"aaa": {
            "records": response_records("msg_a1", "claude-sonnet-5-5",
                                        usage(inp=1000, out=1000, read=0, write=0)),
            "meta": {"agentType": "writ-explorer", "toolUseId": "toolu_A", "spawnDepth": 1},
        }}
        card = _card(write_session_tree(tmp_path, "sess-missing", main_records, subagents))

        gap = _dispatch(card, "toolu_Z")
        assert gap["status"] == "missing_transcript"
        assert gap["agent_id"] == "zzz"
        assert gap["role"] == "writ-reviewer"

        cov = card["dispatch_coverage"]
        assert cov["dispatches"] == 2
        assert cov["accounted"] == 1
        assert cov["missing_transcript"] == 1
        assert cov["summary"] == "1/2 dispatches accounted"

        floor = (1000 * 4 + 500 * 20) / 1e6 + (1000 * 2 + 1000 * 10) / 1e6
        assert card["session"]["partial"] is True
        assert card["session"]["total_usd"] == pytest.approx(floor)

    def test_missing_metadata_when_no_agent_id_resolvable(self, tmp_path: Path):
        # tool_result carries no toolUseResult.agentId and no meta.toolUseId matches toolu_X
        main_records = (
            response_records("msg_m1", "claude-opus-5-5",
                             usage(inp=1000, out=500, read=0, write=0),
                             tool_uses=[agent_tool_use("toolu_X", "writ-explorer")])
            + [tool_result_record("toolu_X", agent_id=None, status="interrupted")]
        )
        subagents = {"eee": {
            "records": response_records("msg_e1", "claude-opus-5-5",
                                        usage(inp=1000, out=0, read=0, write=0)),
            "meta": {"agentType": "writ-explorer", "toolUseId": "toolu_OTHER",
                     "spawnDepth": 1},
        }}
        card = _card(write_session_tree(tmp_path, "sess-nometa", main_records, subagents))

        d = _dispatch(card, "toolu_X")
        assert d["status"] == "missing_metadata"
        cov = card["dispatch_coverage"]
        assert cov["missing_metadata"] == 1
        assert cov["accounted"] == 0
        assert cov["summary"] == "0/1 dispatches accounted"
        assert card["session"]["partial"] is True

    def test_meta_tool_use_id_links_when_tool_result_has_no_agent_id(self, tmp_path: Path):
        main_records = (
            response_records("msg_m1", "claude-opus-5-5",
                             usage(inp=1000, out=500, read=0, write=0),
                             tool_uses=[agent_tool_use("toolu_M", "writ-explorer")])
            + [tool_result_record("toolu_M", agent_id=None)]
        )
        subagents = {"mmm": {
            "records": response_records("msg_s1", "claude-opus-5-5",
                                        usage(inp=1000, out=0, read=0, write=0)),
            "meta": {"agentType": "writ-explorer", "toolUseId": "toolu_M", "spawnDepth": 1},
        }}
        card = _card(write_session_tree(tmp_path, "sess-metalink", main_records, subagents))
        d = _dispatch(card, "toolu_M")
        assert d["status"] == "accounted"
        assert d["agent_id"] == "mmm"
        assert d["usd"] == pytest.approx(1000 * 4 / 1e6)


# ---------------------------------------------------------------------------
# Orphans
# ---------------------------------------------------------------------------

class TestOrphans:
    def _main_only_dispatch_free(self) -> list[dict]:
        return response_records("msg_m1", "claude-opus-5-5",
                                usage(inp=1000, out=500, read=0, write=0))

    def test_flat_orphan_listed_and_excluded_from_total(self, tmp_path: Path):
        subagents = {"ddd": {
            "records": response_records("msg_d1", "claude-opus-5-5",
                                        usage(inp=1000, out=0, read=0, write=0)),
            "meta": {"agentType": "writ-explorer", "toolUseId": "toolu_NEVER",
                     "spawnDepth": 1},
        }}
        card = _card(write_session_tree(tmp_path, "sess-orph", self._main_only_dispatch_free(),
                                        subagents))
        orphan_usd = 1000 * 4 / 1e6                        # 0.004
        assert len(card["orphans"]) == 1
        o = card["orphans"][0]
        assert o["agent_id"] == "ddd"
        assert o["layout"] == "flat"
        assert o["usd"] == pytest.approx(orphan_usd)
        assert card["dispatch_coverage"]["orphan_transcripts"] == 1
        assert card["dispatch_coverage"]["workflow_layout"] is None or \
            "unsupported" not in str(card["dispatch_coverage"]["workflow_layout"])
        assert card["session"]["total_usd"] == pytest.approx((1000 * 4 + 500 * 20) / 1e6)
        assert card["session"]["subagents_usd"] == pytest.approx(0.0)
        assert card["session"]["orphan_usd_excluded"] == pytest.approx(orphan_usd)
        assert card["session"]["partial"] is False

    def test_workflow_layout_file_is_orphan_with_unsupported_note(self, tmp_path: Path):
        subagents = {"www": {
            "records": response_records("msg_w1", "claude-opus-5-5",
                                        usage(inp=500, out=0, read=0, write=0)),
            "meta": {"agentType": "writ-explorer", "toolUseId": "toolu_WF", "spawnDepth": 1},
            "workflow": "wf1",
        }}
        card = _card(write_session_tree(tmp_path, "sess-wf", self._main_only_dispatch_free(),
                                        subagents))
        assert len(card["orphans"]) == 1
        o = card["orphans"][0]
        assert o["agent_id"] == "www"
        assert o["layout"] == "workflow"
        assert o["usd"] == pytest.approx(500 * 4 / 1e6)
        note = card["dispatch_coverage"]["workflow_layout"]
        assert note == "unsupported: listed as orphans, not in session total"
        assert card["session"]["orphan_usd_excluded"] == pytest.approx(500 * 4 / 1e6)
        assert card["session"]["total_usd"] == pytest.approx((1000 * 4 + 500 * 20) / 1e6)

    def test_no_orphans_gives_empty_list_and_zero_excluded(self, tmp_path: Path):
        card = _card(write_session_tree(tmp_path, "sess-none", self._main_only_dispatch_free()))
        assert card["orphans"] == []
        assert card["session"]["orphan_usd_excluded"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Role normalization
# ---------------------------------------------------------------------------

class TestRoleNormalization:
    def test_writ_prefix_stripped_and_bucket_shared(self, tmp_path: Path):
        main_records = (
            response_records("msg_m1", "claude-opus-5-5",
                             usage(inp=1000, out=0, read=0, write=0),
                             n_records=2,
                             tool_uses=[agent_tool_use("toolu_1", "writ:writ-explorer"),
                                        agent_tool_use("toolu_2", "writ-explorer")])
            + [tool_result_record("toolu_1", "a01"), tool_result_record("toolu_2", "a02")]
        )
        subagents = {
            "a01": {"records": response_records(
                        "msg_1", "claude-opus-5-5", usage(inp=1000, out=0, read=0, write=0)),
                    "meta": {"agentType": "writ:writ-explorer", "toolUseId": "toolu_1",
                             "spawnDepth": 1}},
            "a02": {"records": response_records(
                        "msg_2", "claude-opus-5-5", usage(inp=2000, out=0, read=0, write=0)),
                    "meta": {"agentType": "writ-explorer", "toolUseId": "toolu_2",
                             "spawnDepth": 1}},
        }
        card = _card(write_session_tree(tmp_path, "sess-role", main_records, subagents))
        roles = card["cost_by_role"]
        assert "writ:writ-explorer" not in roles
        assert "writ-explorer" in roles
        assert roles["writ-explorer"]["dispatches"] == 2
        assert roles["writ-explorer"]["usd"] == pytest.approx((1000 * 4 + 2000 * 4) / 1e6)
        assert _dispatch(card, "toolu_1")["role"] == "writ-explorer"
        assert _dispatch(card, "toolu_2")["role"] == "writ-explorer"

    def test_role_falls_back_to_dispatch_subagent_type_when_no_meta_agent_type(
            self, tmp_path: Path):
        main_records = (
            response_records("msg_m1", "claude-opus-5-5",
                             usage(inp=1000, out=0, read=0, write=0),
                             tool_uses=[agent_tool_use("toolu_1", "writ:writ-planner")])
            + [tool_result_record("toolu_1", "a01")]
        )
        subagents = {"a01": {"records": response_records(
                                 "msg_1", "claude-opus-5-5",
                                 usage(inp=1000, out=0, read=0, write=0)),
                             "meta": {"toolUseId": "toolu_1", "spawnDepth": 1}}}
        card = _card(write_session_tree(tmp_path, "sess-role2", main_records, subagents))
        assert _dispatch(card, "toolu_1")["role"] == "writ-planner"
        assert "writ-planner" in card["cost_by_role"]


# ---------------------------------------------------------------------------
# Hand-computed end-to-end fixture
# ---------------------------------------------------------------------------

class TestEndToEndTree:
    # Literal per-MTok arithmetic; rates typed inline, not read from the module.
    M1 = (1000 * 4 + 2000 * 20 + 100000 * 0.20 + 4000 * 5 + 6000 * 8) / 1e6   # 0.132
    M2 = (500 * 4 + 1000 * 20 + 200000 * 0.20) / 1e6                          # 0.062
    MAIN = M1 + M2                                                            # 0.194
    AAA = (2000 * 2 + 4000 * 10 + 50000 * 0.20 + 8000 * 2.5) / 1e6            # 0.074
    BBB = (10000 * 1 + 1000 * 5) / 1e6                                        # 0.015
    SUBS = AAA + BBB                                                          # 0.089
    SESSION = MAIN + SUBS                                                     # 0.283
    CCC = (1000 * 4) / 1e6                                                    # 0.004 orphan

    def test_literals_agree_with_plan(self):
        assert self.MAIN == pytest.approx(0.194)
        assert self.SUBS == pytest.approx(0.089)
        assert self.SESSION == pytest.approx(0.283)

    def test_session_block(self, tmp_path: Path):
        card = _card(write_e2e_tree(tmp_path))
        s = card["session"]
        assert s["main_usd"] == pytest.approx(0.194)
        assert s["subagents_usd"] == pytest.approx(0.089)
        assert s["total_usd"] == pytest.approx(0.283)
        assert s["partial"] is False
        assert s["orphan_usd_excluded"] == pytest.approx(self.CCC)

    def test_cost_by_role(self, tmp_path: Path):
        card = _card(write_e2e_tree(tmp_path))
        roles = card["cost_by_role"]
        assert set(roles) == {"main", "writ-explorer", "writ-planner"}
        assert roles["main"]["usd"] == pytest.approx(0.194)
        assert roles["writ-explorer"]["usd"] == pytest.approx(0.074)
        assert roles["writ-planner"]["usd"] == pytest.approx(0.015)

    def test_cost_by_model_normalizes_dated_haiku(self, tmp_path: Path):
        card = _card(write_e2e_tree(tmp_path))
        models = card["cost_by_model"]
        assert set(models) == {"claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-4-5"}
        assert models["claude-opus-5-5"]["usd"] == pytest.approx(0.194)
        assert models["claude-sonnet-5-5"]["usd"] == pytest.approx(0.074)
        assert models["claude-haiku-4-5"]["usd"] == pytest.approx(0.015)

    def test_coverage_and_single_excluded_orphan(self, tmp_path: Path):
        card = _card(write_e2e_tree(tmp_path))
        cov = card["dispatch_coverage"]
        assert cov["summary"] == "2/2 dispatches accounted"
        assert cov["dispatches"] == 2
        assert cov["accounted"] == 2
        assert cov["orphan_transcripts"] == 1
        assert [o["agent_id"] for o in card["orphans"]] == ["ccc"]
        assert card["orphans"][0]["layout"] == "flat"
        assert card["orphans"][0]["usd"] == pytest.approx(self.CCC)

    def test_dispatch_rows(self, tmp_path: Path):
        card = _card(write_e2e_tree(tmp_path))
        a = _dispatch(card, "toolu_A")
        b = _dispatch(card, "toolu_B")
        assert (a["agent_id"], a["role"], a["source"]) == ("aaa", "writ-explorer", "transcript")
        assert (b["agent_id"], b["role"], b["source"]) == ("bbb", "writ-planner", "transcript")
        assert a["usd"] == pytest.approx(0.074)
        assert b["usd"] == pytest.approx(0.015)

    def test_main_thread_measured_counts_responses_not_records(self, tmp_path: Path):
        card = _card(write_e2e_tree(tmp_path))
        m = card["measured"]
        assert m["responses"] == 2
        assert m["records"] == 3
        assert m["duplicates_collapsed"] == 1
        assert m["total_usd"] == pytest.approx(0.194)

    def test_invariants_hold(self, tmp_path: Path):
        card = _card(write_e2e_tree(tmp_path))
        total = card["session"]["total_usd"]
        assert sum(v["usd"] for v in card["cost_by_model"].values()) == pytest.approx(total)
        assert sum(v["usd"] for v in card["cost_by_role"].values()) == pytest.approx(total)
        assert card["session"]["main_usd"] + _priced_dispatch_usd(card) == pytest.approx(total)


# ---------------------------------------------------------------------------
# Review fixes: cross-file duplicate record counts, duplicate agent links
# ---------------------------------------------------------------------------

class TestCrossFileDuplicateCounts:
    def _tree(self, tmp_path: Path) -> Path:
        main_records = (
            response_records("msg_m1", "claude-opus-5-5",
                             usage(inp=1000, out=0, read=0, write=0),
                             tool_uses=[agent_tool_use("toolu_A", "writ-explorer")])
            + [tool_result_record("toolu_A", "aaa")]
        )
        # the subagent file repeats main's msg_m1 in 3 records, then its own msg_a1 once
        sub_records = (
            response_records("msg_m1", "claude-opus-5-5",
                             usage(inp=1000, out=0, read=0, write=0), n_records=3)
            + response_records("msg_a1", "claude-sonnet-5-5",
                               usage(inp=1000, out=1000, read=0, write=0))
        )
        return write_session_tree(tmp_path, "sess-xdup", main_records, {
            "aaa": {"records": sub_records,
                    "meta": {"agentType": "writ-explorer", "toolUseId": "toolu_A"}}})

    def test_dropped_response_records_are_not_counted_as_collapsed(self, tmp_path: Path):
        card = _card(self._tree(tmp_path))
        d = _dispatch(card, "toolu_A")
        assert d["responses"] == 1
        assert d["records"] == 1
        assert d["duplicates_collapsed"] == 0

    def test_cross_file_duplicate_still_warns_and_bills_once(self, tmp_path: Path):
        card = _card(self._tree(tmp_path))
        warns = [w for w in card["warnings"] if w["kind"] == "cross_file_duplicate_id"]
        assert [w["message_id"] for w in warns] == ["msg_m1"]
        main_usd = 1000 * 4 / 1e6
        aaa_usd = (1000 * 2 + 1000 * 10) / 1e6
        assert card["session"]["total_usd"] == pytest.approx(main_usd + aaa_usd)

    def test_aggregate_file_usage_alone_keeps_the_full_record_count(self, tmp_path: Path):
        path = self._tree(tmp_path)
        sub = path.with_suffix("") / "subagents" / "agent-aaa.jsonl"
        agg = load_token_audit().aggregate_file_usage(str(sub))
        assert (agg["records"], agg["responses"], agg["duplicates_collapsed"]) == (4, 2, 2)


class TestDuplicateAgentLinks:
    def _tree(self, tmp_path: Path) -> Path:
        main_records = (
            response_records("msg_m1", "claude-opus-5-5",
                             usage(inp=1000, out=0, read=0, write=0), n_records=2,
                             tool_uses=[agent_tool_use("toolu_A", "writ-explorer"),
                                        agent_tool_use("toolu_B", "writ-explorer")])
            + [tool_result_record("toolu_A", "aaa"), tool_result_record("toolu_B", "aaa")]
        )
        return write_session_tree(tmp_path, "sess-duplink", main_records, {
            "aaa": {"records": response_records("msg_a1", "claude-sonnet-5-5",
                                                usage(inp=1000, out=1000, read=0, write=0)),
                    "meta": {"agentType": "writ-explorer", "toolUseId": "toolu_A"}}})

    def test_duplicate_links_counted_in_coverage(self, tmp_path: Path):
        cov = _card(self._tree(tmp_path))["dispatch_coverage"]
        assert cov["duplicate_links"] == 1
        assert cov["dispatches"] == 1
        assert cov["accounted"] == 1
        assert cov["summary"] == "1/1 dispatches accounted"

    def test_duplicate_link_neither_bills_nor_marks_partial(self, tmp_path: Path):
        card = _card(self._tree(tmp_path))
        assert card["session"]["partial"] is False
        assert card["session"]["total_usd"] == pytest.approx(
            1000 * 4 / 1e6 + (1000 * 2 + 1000 * 10) / 1e6)
        assert "duplicate_agent_link" in [w["kind"] for w in card["warnings"]]

    def test_no_duplicate_links_is_zero(self, tmp_path: Path):
        assert _card(write_e2e_tree(tmp_path))["dispatch_coverage"]["duplicate_links"] == 0
