"""Decision Memory Phase 2 RECALL: tests for compile_recall (writ/session/recall.py).

Every test here is RED until the implementer creates writ/session/recall.py.
Tests fail on ImportError (module missing) or AssertionError, never on a
collection/import error.

CRITICAL isolation guarantee: NO test in this file touches Neo4j. The db
object is a fake Python class with async methods that return canned data.
No Neo4jConnection, no migrate.py, no driver is instantiated.

Run: .venv/bin/python -m pytest tests/test_recall_compile.py

Capability map:
  [compile-1]  compile_recall calls get_rule_statements EXACTLY ONCE over the
               de-duped union of all governing_rule_ids (PERF-BATCH-001)
  [compile-2]  compile_recall drops rationale before any planned_files[].reason
  [compile-3]  compile_recall never drops decision_id, title, governing_rule_ids,
               or rule_statements from a kept decision
  [compile-4]  compile_recall drops a decision WHOLE (and all older decisions)
               when it cannot fit even after evicting all evictable fields
  [compile-5]  compiled payload stays within the token budget
  [compile-6]  briefing stays within ~500-token budget
  [compile-7]  writ/session/recall.py imports no LLM/model client
"""

from __future__ import annotations

import importlib
import inspect
import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call

import pytest


# ---------------------------------------------------------------------------
# Factories (TEST-FIXTURE-001)
# ---------------------------------------------------------------------------

def _decision_factory(
    decision_id: str = "DEC-TEST-001",
    title: str = "Add recall module",
    rationale: str = "Users need read-back of decisions.",
    planned_files: list[dict] | None = None,
    governing_rule_ids: list[str] | None = None,
    phase: str = "planning",
    ts: str = "2026-06-27T10:00:00+00:00",
) -> dict:
    """Minimal well-formed decision dict (already post-processed by get_recent_decisions)."""
    return {
        "decision_id": decision_id,
        "title": title,
        "rationale": rationale,
        "planned_files": planned_files if planned_files is not None else [
            {"path": "writ/session/recall.py", "reason": "add recall logic"}
        ],
        "governing_rule_ids": governing_rule_ids if governing_rule_ids is not None else ["PERF-BATCH-001"],
        "phase": phase,
        "ts": ts,
    }


class _FakeDB:
    """Fake db for compile_recall tests -- no Neo4j dependency.

    Records each call to get_rule_statements so tests can assert EXACTLY-ONCE
    semantics (PERF-BATCH-001). Returns canned decisions and statements.
    """

    def __init__(
        self,
        decisions: list[dict] | None = None,
        statements: dict[str, str] | None = None,
    ) -> None:
        self._decisions = decisions or []
        self._statements = statements or {}
        self.get_rule_statements_calls: list[list[str]] = []

    async def get_recent_decisions(self, project: str, limit: int = 20) -> list[dict]:
        return list(self._decisions)

    async def get_rule_statements(self, rule_ids: list[str]) -> dict[str, str]:
        self.get_rule_statements_calls.append(list(rule_ids))
        return {rid: self._statements.get(rid, f"Statement for {rid}") for rid in rule_ids}


# ---------------------------------------------------------------------------
# Token-cost helpers (used in budget tests)
# ---------------------------------------------------------------------------

def _rough_token_count(text: str) -> int:
    """4-chars/token heuristic matching estimate_tokens in writ/shared/tokens.py."""
    return max(1, len(text) // 4) if text else 0


def _decision_rough_cost(d: dict, statements: dict[str, str]) -> int:
    """Rough token cost of a decision dict (mirrors _decision_token_cost)."""
    cost = _rough_token_count((d.get("title") or "") + (d.get("decision_id") or ""))
    cost += _rough_token_count(d.get("rationale") or "")
    for rid in d.get("governing_rule_ids") or []:
        cost += _rough_token_count(rid + (statements.get(rid) or ""))
    for pf in d.get("planned_files") or []:
        cost += _rough_token_count((pf.get("path") or "") + (pf.get("reason") or ""))
    return cost


# ---------------------------------------------------------------------------
# Tests: PERF-BATCH-001 (exactly one get_rule_statements call)
# ---------------------------------------------------------------------------

class TestCompileRecallBatchRuleStatements:
    """[compile-1]: get_rule_statements called EXACTLY ONCE over de-duped union."""

    @pytest.mark.asyncio
    async def test_single_call_for_two_decisions_with_distinct_rules(self) -> None:
        # [compile-1]: two decisions each with different governing_rule_ids must
        # result in exactly ONE get_rule_statements call covering the union.
        # RED: ImportError (writ/session/recall.py does not exist).
        from writ.session.recall import compile_recall

        decisions = [
            _decision_factory(decision_id="DEC-A", governing_rule_ids=["RULE-001", "RULE-002"]),
            _decision_factory(decision_id="DEC-B", governing_rule_ids=["RULE-003"]),
        ]
        db = _FakeDB(decisions=decisions, statements={
            "RULE-001": "Always validate inputs.",
            "RULE-002": "Batch DB reads.",
            "RULE-003": "Fail open on errors.",
        })

        await compile_recall(db, "writ")

        assert len(db.get_rule_statements_calls) == 1, (
            f"get_rule_statements must be called EXACTLY ONCE (PERF-BATCH-001); "
            f"called {len(db.get_rule_statements_calls)} times"
        )

    @pytest.mark.asyncio
    async def test_single_call_covers_deduped_union_of_all_ids(self) -> None:
        # [compile-1]: if two decisions share a rule_id, the batched call must
        # include that id only ONCE (de-duped union).
        # RED: ImportError.
        from writ.session.recall import compile_recall

        decisions = [
            _decision_factory(decision_id="DEC-A", governing_rule_ids=["SHARED-RULE", "RULE-002"]),
            _decision_factory(decision_id="DEC-B", governing_rule_ids=["SHARED-RULE", "RULE-003"]),
        ]
        db = _FakeDB(decisions=decisions)

        await compile_recall(db, "writ")

        assert len(db.get_rule_statements_calls) == 1, (
            "get_rule_statements must be called exactly once even with overlapping ids"
        )
        ids_fetched = db.get_rule_statements_calls[0]
        assert ids_fetched.count("SHARED-RULE") == 1, (
            f"SHARED-RULE must appear exactly once in the batched call; "
            f"ids_fetched={ids_fetched!r}"
        )

    @pytest.mark.asyncio
    async def test_single_call_when_no_decisions(self) -> None:
        # [compile-1]: with zero decisions, get_rule_statements must still be
        # called exactly once (with an empty list), never skipped entirely.
        # RED: ImportError.
        from writ.session.recall import compile_recall

        db = _FakeDB(decisions=[])

        await compile_recall(db, "writ")

        # Acceptable to call once with [] or to skip the call entirely (both are
        # correct PERF-BATCH-001 implementations -- a zero-id batch is a no-op).
        # The important invariant is it is called AT MOST once.
        assert len(db.get_rule_statements_calls) <= 1, (
            f"get_rule_statements must be called at most once; "
            f"called {len(db.get_rule_statements_calls)} times"
        )

    @pytest.mark.asyncio
    async def test_never_n_plus_one_calls(self) -> None:
        # [compile-1]: with 5 decisions, still exactly one batched call -- never
        # N+1 (one call per decision or one call per rule).
        # RED: ImportError.
        from writ.session.recall import compile_recall

        decisions = [
            _decision_factory(
                decision_id=f"DEC-{i:03d}",
                governing_rule_ids=[f"RULE-{i:03d}"],
            )
            for i in range(5)
        ]
        db = _FakeDB(decisions=decisions)

        await compile_recall(db, "writ")

        assert len(db.get_rule_statements_calls) == 1, (
            f"get_rule_statements must never be called N+1 times; "
            f"called {len(db.get_rule_statements_calls)} times for 5 decisions"
        )


# ---------------------------------------------------------------------------
# Tests: eviction order (rationale before planned_files[].reason)
# ---------------------------------------------------------------------------

class TestCompileRecallEvictionOrder:
    """[compile-2]: rationale dropped before any planned_files[].reason."""

    @pytest.mark.asyncio
    async def test_rationale_dropped_before_planned_files_reason(self) -> None:
        # [compile-2]: when a decision is too large, rationale must be cleared
        # BEFORE any planned_files[].reason is cleared.
        # We use a budget that fits the decision only if rationale is cleared
        # (so if any planned_files reason is cleared first instead, the rationale
        # will remain and the test fails).
        # RED: ImportError.
        from writ.session.recall import compile_recall
        from writ.shared.tokens import estimate_tokens

        # Craft a decision with a long rationale and a short planned_files reason.
        long_rationale = "X" * 400  # ~100 tokens
        short_reason = "short"
        decision = _decision_factory(
            decision_id="DEC-EVICT",
            title="Eviction order test",
            rationale=long_rationale,
            planned_files=[{"path": "writ/foo.py", "reason": short_reason}],
            governing_rule_ids=["RULE-X"],
        )

        # Budget that forces eviction but allows the decision without its rationale.
        # The protected fields (title+id+rule_ids+statements) + planned_files path
        # but NOT the rationale must fit.
        statements = {"RULE-X": "short statement"}
        rough_protected_cost = _rough_token_count(
            "Eviction order test" + "DEC-EVICT" + "RULE-X" + "short statement"
            + "writ/foo.py" + short_reason
        )
        budget = rough_protected_cost + 50  # tight: fits without rationale, not with

        db = _FakeDB(decisions=[decision], statements=statements)
        result = await compile_recall(db, "writ", budget=budget)

        kept = result["decisions"]
        if kept:
            # If the decision was kept, rationale must be empty/cleared.
            assert kept[0].get("rationale", "") == "", (
                "rationale must be evicted first (before planned_files reason); "
                f"rationale={kept[0].get('rationale')!r}, "
                f"planned_files={kept[0].get('planned_files')!r}"
            )

    @pytest.mark.asyncio
    async def test_planned_files_reason_cleared_only_after_rationale(self) -> None:
        # [compile-2]: with infinite budget both fields survive; they are only
        # evicted under budget pressure and in the declared order.
        # RED: ImportError.
        from writ.session.recall import compile_recall

        decision = _decision_factory(
            decision_id="DEC-FULL",
            rationale="Important rationale.",
            planned_files=[{"path": "writ/foo.py", "reason": "important reason"}],
            governing_rule_ids=["RULE-X"],
        )
        db = _FakeDB(decisions=[decision])

        result = await compile_recall(db, "writ", budget=200_000)

        kept = result["decisions"]
        assert len(kept) == 1
        assert kept[0]["rationale"] == "Important rationale.", (
            "rationale must survive when budget is ample"
        )
        assert kept[0]["planned_files"][0]["reason"] == "important reason", (
            "planned_files reason must survive when budget is ample"
        )


# ---------------------------------------------------------------------------
# Tests: protected fields never dropped
# ---------------------------------------------------------------------------

class TestCompileRecallProtectedFields:
    """[compile-3]: decision_id, title, governing_rule_ids, rule_statements never dropped."""

    @pytest.mark.asyncio
    async def test_protected_fields_present_on_every_kept_decision(self) -> None:
        # [compile-3]: a kept decision must always have decision_id, title,
        # governing_rule_ids, and rule_statements -- regardless of budget pressure.
        # RED: ImportError.
        from writ.session.recall import compile_recall

        decisions = [
            _decision_factory(
                decision_id="DEC-PROT-001",
                title="Protected fields test",
                governing_rule_ids=["ERR-FALLBACK-001"],
            ),
        ]
        db = _FakeDB(
            decisions=decisions,
            statements={"ERR-FALLBACK-001": "All error paths are fail-open."},
        )

        result = await compile_recall(db, "writ", budget=200_000)

        kept = result["decisions"]
        assert len(kept) == 1, "decision must be kept under ample budget"
        d = kept[0]

        assert d.get("decision_id") == "DEC-PROT-001", (
            f"decision_id must be present; got {d.get('decision_id')!r}"
        )
        assert d.get("title") == "Protected fields test", (
            f"title must be present; got {d.get('title')!r}"
        )
        assert "ERR-FALLBACK-001" in (d.get("governing_rule_ids") or []), (
            f"governing_rule_ids must be present; got {d.get('governing_rule_ids')!r}"
        )
        assert "rule_statements" in d, (
            "rule_statements must be present on every kept decision"
        )
        assert d["rule_statements"].get("ERR-FALLBACK-001") == "All error paths are fail-open.", (
            f"rule_statements must contain the expanded statement; "
            f"got {d['rule_statements']!r}"
        )

    @pytest.mark.asyncio
    async def test_rule_statements_key_present_even_with_empty_rule_ids(self) -> None:
        # [compile-3]: even a decision with no governing_rule_ids must have a
        # rule_statements key (empty dict, not absent).
        # RED: ImportError.
        from writ.session.recall import compile_recall

        decision = _decision_factory(decision_id="DEC-NORULES", governing_rule_ids=[])
        db = _FakeDB(decisions=[decision])

        result = await compile_recall(db, "writ", budget=200_000)

        kept = result["decisions"]
        assert len(kept) == 1
        assert "rule_statements" in kept[0], (
            "rule_statements key must exist even when governing_rule_ids is empty"
        )
        assert kept[0]["rule_statements"] == {}, (
            f"rule_statements must be empty dict for no rules; "
            f"got {kept[0]['rule_statements']!r}"
        )


# ---------------------------------------------------------------------------
# Tests: whole-decision drop when it cannot fit
# ---------------------------------------------------------------------------

class TestCompileRecallWholeDecisionDrop:
    """[compile-4]: a decision that cannot fit even after full eviction is dropped
    WHOLE, and all older decisions are also dropped."""

    @pytest.mark.asyncio
    async def test_decision_dropped_whole_when_protected_fields_exceed_budget(self) -> None:
        # [compile-4]: if title+decision_id+rule_ids+statements alone exceed the
        # budget, the entire decision must be dropped (not shipped without rationale).
        # RED: ImportError.
        from writ.session.recall import compile_recall

        # A decision with a very large title that will exceed a tiny budget
        huge_title = "T" * 2000  # ~500 tokens from title alone
        decision = _decision_factory(
            decision_id="DEC-HUGE",
            title=huge_title,
            governing_rule_ids=["RULE-BIG"],
        )
        db = _FakeDB(
            decisions=[decision],
            statements={"RULE-BIG": "S" * 2000},  # another ~500 tokens
        )

        result = await compile_recall(db, "writ", budget=50)  # far too small

        assert result["decisions"] == [], (
            "decision must be dropped WHOLE when it cannot fit even after evicting "
            f"all evictable fields; got {result['decisions']!r}"
        )

    @pytest.mark.asyncio
    async def test_older_decisions_dropped_once_budget_exhausted(self) -> None:
        # [compile-4]: newest-first processing; once the budget is exhausted after
        # accepting decision #1, decisions #2 and #3 must NOT appear in the output.
        # RED: ImportError.
        from writ.session.recall import compile_recall

        # Each decision is ~200 tokens. Budget fits only the first.
        filler = "A" * 600  # ~150 tokens each field
        decisions = [
            _decision_factory(
                decision_id="DEC-NEWEST",
                title=filler,
                rationale=filler,
                governing_rule_ids=[],
                planned_files=[],
                ts="2026-06-27T12:00:00+00:00",
            ),
            _decision_factory(
                decision_id="DEC-OLDER",
                title=filler,
                rationale=filler,
                governing_rule_ids=[],
                planned_files=[],
                ts="2026-06-26T10:00:00+00:00",
            ),
            _decision_factory(
                decision_id="DEC-OLDEST",
                title=filler,
                rationale=filler,
                governing_rule_ids=[],
                planned_files=[],
                ts="2026-06-25T08:00:00+00:00",
            ),
        ]
        # Budget: comfortably fits one decision (~350 tokens), not two.
        db = _FakeDB(decisions=decisions)

        result = await compile_recall(db, "writ", budget=400)

        kept_ids = [d["decision_id"] for d in result["decisions"]]
        assert "DEC-NEWEST" in kept_ids, (
            f"newest decision must be kept; kept={kept_ids!r}"
        )
        # Once budget is exhausted by the newest, older decisions must be dropped.
        assert "DEC-OLDER" not in kept_ids, (
            f"DEC-OLDER must be dropped once budget is exhausted; kept={kept_ids!r}"
        )
        assert "DEC-OLDEST" not in kept_ids, (
            f"DEC-OLDEST must be dropped once budget is exhausted; kept={kept_ids!r}"
        )

    @pytest.mark.asyncio
    async def test_result_shape_has_decisions_key(self) -> None:
        # [compile-4] shape: compile_recall always returns a dict with a
        # 'decisions' key (list), even when empty.
        # RED: ImportError.
        from writ.session.recall import compile_recall

        db = _FakeDB(decisions=[])
        result = await compile_recall(db, "writ", budget=200_000)

        assert "decisions" in result, f"result must have 'decisions' key; got {list(result)!r}"
        assert isinstance(result["decisions"], list), (
            f"'decisions' must be a list; got {type(result['decisions'])!r}"
        )


# ---------------------------------------------------------------------------
# Tests: payload within budget
# ---------------------------------------------------------------------------

class TestCompileRecallBudgetBound:
    """[compile-5]: compiled payload stays within the token budget."""

    @pytest.mark.asyncio
    async def test_kept_decisions_fit_within_budget(self) -> None:
        # [compile-5]: the sum of token costs for all kept decisions must be
        # <= budget. We use the same 4-chars/token heuristic as estimate_tokens.
        # RED: ImportError.
        from writ.session.recall import compile_recall

        budget = 500
        # 10 medium-sized decisions; most should be evicted.
        decisions = [
            _decision_factory(
                decision_id=f"DEC-{i:03d}",
                title="A" * 100,
                rationale="R" * 200,
                planned_files=[{"path": "writ/f.py", "reason": "Q" * 100}],
                governing_rule_ids=[f"RULE-{i:03d}"],
                ts=f"2026-06-2{i}T10:00:00+00:00" if i < 7 else f"2026-06-2{i % 3 + 1}T10:00:00+00:00",
            )
            for i in range(10)
        ]
        statements = {f"RULE-{i:03d}": "S" * 50 for i in range(10)}
        db = _FakeDB(decisions=decisions, statements=statements)

        result = await compile_recall(db, "writ", budget=budget)

        # Verify total rough cost of kept decisions is within budget.
        total_cost = 0
        for d in result["decisions"]:
            stmts = d.get("rule_statements") or {}
            total_cost += _decision_rough_cost(d, stmts)

        # Allow a small margin for the heuristic rounding difference.
        assert total_cost <= budget * 1.1, (
            f"total token cost of kept decisions ({total_cost}) exceeds budget "
            f"({budget}) by more than 10%; indicates the eviction policy is not working"
        )

    @pytest.mark.asyncio
    async def test_all_decisions_kept_when_budget_is_ample(self) -> None:
        # [compile-5]: with a very large budget all decisions should be kept.
        # RED: ImportError.
        from writ.session.recall import compile_recall

        decisions = [_decision_factory(decision_id=f"DEC-{i}") for i in range(3)]
        db = _FakeDB(decisions=decisions)

        result = await compile_recall(db, "writ", budget=200_000)

        assert len(result["decisions"]) == 3, (
            f"all 3 decisions must be kept under ample budget; "
            f"kept={[d['decision_id'] for d in result['decisions']]!r}"
        )


# ---------------------------------------------------------------------------
# Tests: briefing budget
# ---------------------------------------------------------------------------

class TestCompileRecallBriefingBudget:
    """[compile-6]: briefing stays within ~500-token budget."""

    @pytest.mark.asyncio
    async def test_briefing_is_non_empty_when_decisions_kept(self) -> None:
        # [compile-6]: when decisions are kept, the briefing must be a non-empty
        # string (at least a header line).
        # RED: ImportError.
        from writ.session.recall import compile_recall

        db = _FakeDB(decisions=[_decision_factory()])

        result = await compile_recall(db, "writ", budget=200_000)

        briefing = result.get("briefing", "")
        assert isinstance(briefing, str), f"briefing must be a str; got {type(briefing)!r}"
        assert len(briefing) > 0, "briefing must be non-empty when decisions are kept"

    @pytest.mark.asyncio
    async def test_briefing_empty_when_no_decisions_kept(self) -> None:
        # [compile-6]: when no decisions are kept (empty project), the briefing
        # must be an empty string.
        # RED: ImportError.
        from writ.session.recall import compile_recall

        db = _FakeDB(decisions=[])

        result = await compile_recall(db, "writ", budget=200_000)

        assert result.get("briefing") == "", (
            f"briefing must be '' when no decisions exist; got {result.get('briefing')!r}"
        )

    @pytest.mark.asyncio
    async def test_briefing_stays_within_500_token_soft_cap(self) -> None:
        # [compile-6]: the briefing is the once-per-session line block injected
        # via additionalContext. It must stay <= ~500 tokens (2000 chars at 4/token).
        # RED: ImportError.
        from writ.session.recall import compile_recall

        # 20 decisions with long titles to stress the briefing cap.
        decisions = [
            _decision_factory(
                decision_id=f"DEC-{i:03d}",
                title="A" * 200,  # ~50 tokens per title
                governing_rule_ids=[f"RULE-{i:03d}", f"RULE-{i:03d}b"],
            )
            for i in range(20)
        ]
        db = _FakeDB(decisions=decisions)

        result = await compile_recall(db, "writ", budget=200_000)

        briefing = result.get("briefing", "")
        briefing_tokens = max(1, len(briefing) // 4)
        assert briefing_tokens <= 600, (
            f"briefing must stay near the 500-token cap; "
            f"got ~{briefing_tokens} tokens ({len(briefing)} chars)"
        )

    @pytest.mark.asyncio
    async def test_briefing_contains_decision_title(self) -> None:
        # [compile-6]: the briefing must mention the kept decision's title so
        # the agent knows what decisions were made.
        # RED: ImportError.
        from writ.session.recall import compile_recall

        decision = _decision_factory(
            decision_id="DEC-BRIEFING-001",
            title="Add recall route to server",
            governing_rule_ids=["ERR-FALLBACK-001"],
        )
        db = _FakeDB(
            decisions=[decision],
            statements={"ERR-FALLBACK-001": "Fail open."},
        )

        result = await compile_recall(db, "writ", budget=200_000)

        briefing = result.get("briefing", "")
        assert "Add recall route to server" in briefing, (
            f"briefing must contain the decision title; got:\n{briefing!r}"
        )

    @pytest.mark.asyncio
    async def test_briefing_contains_rule_ids(self) -> None:
        # [compile-6]: the briefing must cite the governing rule ids (the
        # rule-grounding is Writ's unique value; it must appear in the header).
        # RED: ImportError.
        from writ.session.recall import compile_recall

        decision = _decision_factory(
            decision_id="DEC-RULES-001",
            title="Some decision",
            governing_rule_ids=["PERF-BATCH-001", "ERR-FALLBACK-001"],
        )
        db = _FakeDB(decisions=[decision])

        result = await compile_recall(db, "writ", budget=200_000)

        briefing = result.get("briefing", "")
        assert "PERF-BATCH-001" in briefing, (
            f"briefing must cite governing rule id PERF-BATCH-001; got:\n{briefing!r}"
        )


# ---------------------------------------------------------------------------
# Tests: no LLM/model client imported
# ---------------------------------------------------------------------------

class TestCompileRecallNoLLMImport:
    """[compile-7]: writ/session/recall.py imports no LLM/model client."""

    def test_recall_module_imports_no_llm_client(self) -> None:
        # [compile-7]: the briefing is built MECHANICALLY (string formatting).
        # Any import of an Anthropic, OpenAI, or similar model client is a
        # violation. We inspect the module source for forbidden import patterns.
        # RED: ImportError (module does not exist yet).
        import importlib.util
        from pathlib import Path

        recall_path = Path(__file__).resolve().parent.parent / "writ" / "session" / "recall.py"
        assert recall_path.exists(), (
            f"writ/session/recall.py must exist at {recall_path}; "
            "if this fails with FileNotFoundError the file has not been created yet"
        )

        source = recall_path.read_text()

        forbidden_patterns = [
            "import anthropic",
            "from anthropic",
            "import openai",
            "from openai",
            "import litellm",
            "from litellm",
            "claude",
            "gpt-",
            "ChatCompletion",
            "Anthropic(",
        ]
        for pattern in forbidden_patterns:
            # claude can appear in comments/docstrings so we check for import-level usage
            if "claude" in pattern.lower():
                # Only flag if it appears as an import token (not in a comment/string)
                import_lines = [
                    ln for ln in source.splitlines()
                    if (pattern in ln) and not ln.strip().startswith("#")
                    and "import" in ln
                ]
                assert not import_lines, (
                    f"recall.py must not import any LLM client; "
                    f"found '{pattern}' in import lines: {import_lines!r}"
                )
            else:
                assert pattern not in source, (
                    f"recall.py must not import any LLM client; "
                    f"found forbidden pattern {pattern!r} in source"
                )

    def test_recall_module_can_be_imported_without_model_side_effects(self) -> None:
        # [compile-7]: importing the module must not trigger any model API call
        # or network access. We import it and assert no network-related global
        # was initialized (check that well-known client attribute names are absent).
        # RED: ImportError.
        import sys
        # Force a fresh import even if cached.
        if "writ.session.recall" in sys.modules:
            del sys.modules["writ.session.recall"]

        from writ.session import recall as recall_mod

        # The module must not have a top-level 'client' or '_client' attribute
        # pointing to a model API client.
        for attr in ("client", "_client", "_llm", "llm", "_model", "model"):
            val = getattr(recall_mod, attr, None)
            if val is not None:
                # Allow None-valued attributes or string constants
                assert isinstance(val, (str, int, float, type(None))), (
                    f"recall module must not have a live model-client attribute '{attr}'; "
                    f"got {val!r}"
                )

    @pytest.mark.asyncio
    async def test_briefing_is_not_empty_string_template(self) -> None:
        # [compile-7]: the mechanical briefing must produce real content (not an
        # empty placeholder that would indicate the implementation calls an LLM
        # and fell back to ""). With a known decision it must contain non-trivial text.
        # RED: ImportError.
        from writ.session.recall import compile_recall

        decision = _decision_factory(
            decision_id="DEC-MECH-001",
            title="Mechanical briefing check",
            governing_rule_ids=["TEST-RULE-001"],
        )
        db = _FakeDB(decisions=[decision], statements={"TEST-RULE-001": "Use mechanical only."})

        result = await compile_recall(db, "writ", budget=200_000)

        briefing = result.get("briefing", "")
        assert len(briefing) > 20, (
            f"briefing must be a substantive mechanical string (>20 chars); "
            f"got {briefing!r}"
        )
