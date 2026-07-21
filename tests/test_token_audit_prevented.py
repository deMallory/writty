"""Tests for the prevented-cost term added to writ/analysis/token_audit.py.

Pure unit tests -- no Neo4j, no daemon, no hook subprocess.
Mirrors tests/test_token_audit.py in structure: lazy _ta() importlib loader,
_usage()/_write_transcript() helpers, class-per-contract.

attribute_prevented does NOT exist yet -> AttributeError on import-time access,
or AttributeError on call -> RED for the right reason.

The scorecard() and render_text() tests exercise the wiring of attribute_prevented
into the existing functions; those functions already exist, but the "prevented"
key they are expected to return does not, so they will also fail for the right reason.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.fixtures.token_audit_helpers import load_token_audit
from tests.fixtures.token_audit_helpers import usage as _usage
from tests.fixtures.token_audit_helpers import write_transcript as _write_transcript


def _ta():
    # Force reimport so edits to token_audit.py are picked up without a new process.
    return load_token_audit(force_reimport=True)


def _friction(path: Path, events: list[dict]) -> Path:
    """Write one JSON object per line to a friction log file."""
    with open(path, "w") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")
    return path


def _read_blocked_event(
    *,
    prevented_tokens_floor: int = 100,
    gross_bytes_upper_bound: int = 400,
    file_path: str = "/project/node_modules/x.js",
) -> dict:
    return {
        "event": "read_blocked",
        "file_path": file_path,
        "prevented_tokens_floor": prevented_tokens_floor,
        "gross_bytes_upper_bound": gross_bytes_upper_bound,
        "block_reason": "path_blocklist",
        "would_block": True,
        "enforced": False,
    }


# ---------------------------------------------------------------------------
# TestAttributePrevented
# ---------------------------------------------------------------------------

class TestAttributePrevented:
    def test_returns_prevented_cost_floor_summed_at_cache_read_weight(self):
        ta = _ta()
        events = [
            _read_blocked_event(prevented_tokens_floor=400, gross_bytes_upper_bound=1600),
            _read_blocked_event(prevented_tokens_floor=200, gross_bytes_upper_bound=800),
        ]
        result = ta.attribute_prevented(events)
        # 600 tokens * 0.1 (cache_read weight) = 60.0
        expected_cost = 600 * ta.COST_WEIGHTS["cache_read"]
        assert result["prevented_cost_floor"] == pytest.approx(expected_cost)

    def test_non_read_blocked_events_are_ignored(self):
        ta = _ta()
        events = [
            {"event": "rag_query", "tokens_injected": 500},
            {"event": "always_on_inject", "tokens": 1171},
            _read_blocked_event(prevented_tokens_floor=100),
        ]
        result = ta.attribute_prevented(events)
        # Only the one read_blocked event contributes.
        expected_cost = 100 * ta.COST_WEIGHTS["cache_read"]
        assert result["prevented_cost_floor"] == pytest.approx(expected_cost)
        assert result["blocked_count"] == 1

    def test_binary_event_with_floor_zero_adds_zero_cost_but_contributes_gross_bytes(self):
        ta = _ta()
        gross = 8192
        events = [
            _read_blocked_event(prevented_tokens_floor=0, gross_bytes_upper_bound=gross),
        ]
        result = ta.attribute_prevented(events)
        assert result["prevented_cost_floor"] == pytest.approx(0.0)
        assert result["gross_blocked_bytes"] == gross

    def test_blocked_count_counts_only_read_blocked_events(self):
        ta = _ta()
        events = [
            {"event": "rag_query", "tokens_injected": 300},
            _read_blocked_event(prevented_tokens_floor=100),
            _read_blocked_event(prevented_tokens_floor=200),
        ]
        result = ta.attribute_prevented(events)
        assert result["blocked_count"] == 2

    def test_empty_list_returns_zero_cost_without_crash(self):
        ta = _ta()
        result = ta.attribute_prevented([])
        assert result["prevented_cost_floor"] == 0
        assert result["blocked_count"] == 0

    def test_basis_field_is_correct_label(self):
        ta = _ta()
        result = ta.attribute_prevented([_read_blocked_event()])
        assert result["basis"] == "bytes/4_floor*cache_read"

    def test_gross_blocked_bytes_sums_all_read_blocked_events(self):
        ta = _ta()
        events = [
            _read_blocked_event(gross_bytes_upper_bound=1000),
            _read_blocked_event(gross_bytes_upper_bound=2000),
        ]
        result = ta.attribute_prevented(events)
        assert result["gross_blocked_bytes"] == 3000


# ---------------------------------------------------------------------------
# TestScorecardPrevented
# ---------------------------------------------------------------------------

class TestScorecardPrevented:
    def test_scorecard_returns_prevented_key_distinct_from_attributed(self, tmp_path):
        ta = _ta()
        tpath = _write_transcript(
            tmp_path / "t.jsonl",
            [_usage(inp=100, out=10, read=1000, write=200)],
        )
        fpath = _friction(tmp_path / "friction.log", [_read_blocked_event()])
        card = ta.scorecard(str(tpath), str(fpath), "claude-opus-4-8")
        assert "prevented" in card, (
            f"scorecard must contain a 'prevented' key; keys: {list(card.keys())}"
        )
        assert "attributed" in card
        # prevented and attributed are separate objects, not the same dict.
        assert card["prevented"] is not card["attributed"]

    def test_scorecard_attributed_net_cost_subtracts_prevented_floor(self, tmp_path):
        ta = _ta()
        # Inject known write and reread costs by using a transcript with no cache_read
        # (so reread=0) and a friction log with one injection + one read_blocked event.
        tpath = _write_transcript(
            tmp_path / "t.jsonl",
            [_usage(inp=0, out=0, read=0, write=400)],
        )
        # One injection event (write cost = 400 * 1.25 = 500)
        # One read_blocked event (floor = 80 tokens * 0.1 = 8.0 cost floor)
        flog_events = [
            {"event": "always_on_inject", "tokens": 400},
            _read_blocked_event(prevented_tokens_floor=80, gross_bytes_upper_bound=320),
        ]
        fpath = _friction(tmp_path / "friction.log", flog_events)
        card = ta.scorecard(str(tpath), str(fpath), "claude-opus-4-8")

        attr = card["attributed"]
        prev = card["prevented"]
        expected_net = attr["injected_write_cost"] + attr["injected_reread_cost"] - prev["prevented_cost_floor"]
        assert attr["net_cost"] == pytest.approx(expected_net)

    def test_scorecard_prevented_blocked_count_matches_friction_events(self, tmp_path):
        ta = _ta()
        tpath = _write_transcript(tmp_path / "t.jsonl", [_usage()])
        flog_events = [
            _read_blocked_event(prevented_tokens_floor=50),
            _read_blocked_event(prevented_tokens_floor=75),
            {"event": "rag_query", "tokens_injected": 200},  # must NOT count
        ]
        fpath = _friction(tmp_path / "friction.log", flog_events)
        card = ta.scorecard(str(tpath), str(fpath), "claude-opus-4-8")
        assert card["prevented"]["blocked_count"] == 2


# ---------------------------------------------------------------------------
# TestRenderText
# ---------------------------------------------------------------------------

class TestRenderText:
    def _card_with_prevented(self, tmp_path) -> dict:
        ta = _ta()
        tpath = _write_transcript(
            tmp_path / "t.jsonl",
            [_usage(inp=100, out=10, read=1000, write=200)],
        )
        fpath = _friction(
            tmp_path / "friction.log",
            [_read_blocked_event(prevented_tokens_floor=400, gross_bytes_upper_bound=1600)],
        )
        return ta.scorecard(str(tpath), str(fpath), "claude-opus-4-8")

    def test_render_text_contains_prevented_section_header(self, tmp_path):
        ta = _ta()
        card = self._card_with_prevented(tmp_path)
        text = ta.render_text(card)
        assert "PREVENTED" in text, (
            f"render_text output must contain 'PREVENTED'; got:\n{text}"
        )

    def test_render_text_labels_gross_bytes_as_not_a_token_count(self, tmp_path):
        ta = _ta()
        card = self._card_with_prevented(tmp_path)
        text = ta.render_text(card).lower()
        # The plan specifies the label "(GROSS BYTES, not a token count)" in render_text.
        assert "not a token" in text or "gross bytes" in text, (
            f"render_text must label gross bytes as not a token count; got (lowercased):\n{text}"
        )
