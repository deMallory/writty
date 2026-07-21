"""Task #7B: runtime delivery telemetry in writ.analysis.friction.summarize.

rag_query / always_on_inject events carry raw event_name + mechanism; summarize
buckets their tokens by classify_delivery so inert (debug-log) injection is
visible alongside what actually reached the model.
"""
from __future__ import annotations

from writ.analysis.friction import summarize, format_report


def _rag(source: str, tokens: int, event_name: str, mechanism: str) -> dict:
    return {
        "ts": "2026-06-19T00:00:00Z", "session": "s", "event": "rag_query",
        "query_source": source, "tokens_injected": tokens, "rule_ids": [],
        "event_name": event_name, "mechanism": mechanism,
    }


class TestDeliveryBuckets:
    def test_pretooluse_stdout_tokens_are_debug_log(self) -> None:
        s = summarize([_rag("file-read", 500, "PreToolUse", "stdout")])
        assert s["inject_tokens_by_delivery"].get("debug-log") == 500
        assert s["inject_tokens_by_delivery"].get("model") in (None, 0)
        assert s["inert_inject_sources"].get("file-read") == 500

    def test_userpromptsubmit_stdout_tokens_are_model(self) -> None:
        s = summarize([_rag("broad", 800, "UserPromptSubmit", "stdout")])
        assert s["inject_tokens_by_delivery"].get("model") == 800
        assert "debug-log" not in s["inject_tokens_by_delivery"]
        assert s["inert_inject_sources"] == {}

    def test_always_on_inject_bucketed_by_delivery(self) -> None:
        ev = {
            "ts": "2026-06-19T00:00:00Z", "session": "s", "event": "always_on_inject",
            "tokens": 300, "event_name": "UserPromptSubmit", "mechanism": "stdout",
        }
        s = summarize([ev])
        assert s["inject_tokens_by_delivery"].get("model") == 300

    def test_missing_mechanism_is_unknown_not_model(self) -> None:
        # Pre-instrument rag_query rows (no event_name/mechanism).
        legacy = {
            "ts": "2026-06-19T00:00:00Z", "session": "s", "event": "rag_query",
            "query_source": "broad", "tokens_injected": 400, "rule_ids": [],
        }
        s = summarize([legacy])
        assert s["inject_tokens_by_delivery"].get("unknown") == 400
        assert s["inject_tokens_by_delivery"].get("model") in (None, 0)

    def test_mixed_sources_split_correctly(self) -> None:
        events = [
            _rag("broad", 1000, "UserPromptSubmit", "stdout"),       # model
            _rag("file-read", 600, "PreToolUse", "stdout"),          # inert
            _rag("file-write-post", 200, "PostToolUse", "stdout"),   # inert
        ]
        s = summarize(events)
        assert s["inject_tokens_by_delivery"]["model"] == 1000
        assert s["inject_tokens_by_delivery"]["debug-log"] == 800
        assert set(s["inert_inject_sources"]) == {"file-read", "file-write-post"}


class TestFormatReport:
    def test_report_marks_inert_tokens(self) -> None:
        s = summarize([
            _rag("broad", 1000, "UserPromptSubmit", "stdout"),
            _rag("file-read", 600, "PreToolUse", "stdout"),
        ])
        report = format_report(s)
        assert "Rule-injection delivery" in report
        assert "INERT" in report
        assert "file-read" in report
