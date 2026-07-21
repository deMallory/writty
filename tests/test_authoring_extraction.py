"""RED unit tests for the Wave 2 Cycle 5 extraction of add/edit/review/propose
business logic out of `writ/cli.py` into `writ/authoring.py`.

Five new public names are being added to `writ/authoring.py`:
`build_rule_dict`, `finalize_conflict_and_export`, `promote`, `reject`,
`downweight`, and `IllegalAuthorityTransitionError`.

RED: none of these names exist yet, so the import below fails at collection
time (ImportError: cannot import name ... from 'writ.authoring'). GREEN once
the plan's implementation step lands them in `writ/authoring.py`.

There are NO CliRunner/subprocess tests for `writ add` / `writ edit` /
`writ review` (fully interactive commands), so this file is the primary
safety net for the business logic those commands delegate to. No live
Neo4j: every `db` is either an opaque sentinel or a fake exposing only the
async methods under test, and `check_conflicts` /
`export_rules_to_markdown` are monkeypatched at ORIGIN.

Derived directly from the current source being extracted:
- `_authored_rule_dict` (writ/cli.py:628-657)
- `_conflict_check_and_export` (writ/cli.py:660-674)
- review's promote/reject/downweight (writ/cli.py:1153-1185)
"""

from __future__ import annotations

import inspect
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from writ.authoring import (
    IllegalAuthorityTransitionError,
    assert_ai_provisional,
    build_rule_dict,
    downweight,
    finalize_conflict_and_export,
    promote,
    reject,
)


# ---------------------------------------------------------------------------
# build_rule_dict -- verbatim move of _authored_rule_dict (cli.py:628-657)
# ---------------------------------------------------------------------------


class TestBuildRuleDict:
    """Pure function: the 10 keyword args pass through verbatim, plus a
    stamped last_validated (today's date, ISO format)."""

    def test_returns_all_fields(self) -> None:
        result = build_rule_dict(
            rule_id="X-1",
            domain="d",
            severity="High",
            scope="Component",
            trigger="t",
            statement="s",
            violation="v",
            pass_example="p",
            enforcement="e",
            rationale="r",
        )

        assert result == {
            "rule_id": "X-1",
            "domain": "d",
            "severity": "High",
            "scope": "Component",
            "trigger": "t",
            "statement": "s",
            "violation": "v",
            "pass_example": "p",
            "enforcement": "e",
            "rationale": "r",
            "last_validated": date.today().isoformat(),
        }
        assert len(result) == 11


# ---------------------------------------------------------------------------
# finalize_conflict_and_export -- de-echoed move of _conflict_check_and_export
# (cli.py:660-674)
# ---------------------------------------------------------------------------


class _FakeDB:
    """Opaque sentinel: finalize_conflict_and_export forwards it verbatim to
    cache.build_from_db and export_rules_to_markdown; it never calls a
    method on db itself."""


class _FakeCache:
    """Fake AdjacencyCache exposing only the async build_from_db hook that
    finalize_conflict_and_export awaits. check_conflicts is monkeypatched
    at origin, so no other cache method is ever touched."""

    def __init__(self) -> None:
        self.build_from_db = AsyncMock()


@pytest.fixture
def fake_db() -> _FakeDB:
    return _FakeDB()


@pytest.fixture
def fake_cache() -> _FakeCache:
    return _FakeCache()


class TestFinalizeConflictAndExport:
    """Rebuilds the caller-passed cache in place, checks CONFLICTS_WITH
    neighbors, then auto-exports -- returning structured data instead of
    echoing, so cli.py drives the exact echo strings from the return value."""

    @pytest.mark.asyncio
    async def test_returns_conflicts_and_export(
        self,
        fake_db: _FakeDB,
        fake_cache: _FakeCache,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        conflicts = [{"rule_id": "C-1"}, {"rule_id": "C-2"}]
        check_conflicts_spy = MagicMock(return_value=conflicts)
        export_spy = AsyncMock(return_value={"rules_exported": 7})
        monkeypatch.setattr("writ.authoring.check_conflicts", check_conflicts_spy)
        monkeypatch.setattr("writ.export.export_rules_to_markdown", export_spy)

        result = await finalize_conflict_and_export(fake_db, fake_cache, "R-1")

        assert result == {
            "conflicts": conflicts,
            "rules_exported": 7,
            "export_dir": "bible/",
        }
        fake_cache.build_from_db.assert_awaited_once_with(fake_db)
        check_conflicts_spy.assert_called_once_with("R-1", fake_cache)
        export_spy.assert_awaited_once_with(fake_db, Path("bible/"))

    @pytest.mark.asyncio
    async def test_empty_conflicts(
        self,
        fake_db: _FakeDB,
        fake_cache: _FakeCache,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        check_conflicts_spy = MagicMock(return_value=[])
        export_spy = AsyncMock(return_value={"rules_exported": 7})
        monkeypatch.setattr("writ.authoring.check_conflicts", check_conflicts_spy)
        monkeypatch.setattr("writ.export.export_rules_to_markdown", export_spy)

        result = await finalize_conflict_and_export(fake_db, fake_cache, "R-1")

        assert result["conflicts"] == []
        assert result["rules_exported"] == 7
        fake_cache.build_from_db.assert_awaited_once_with(fake_db)

    @pytest.mark.asyncio
    async def test_custom_bible_dir(
        self,
        fake_db: _FakeDB,
        fake_cache: _FakeCache,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        check_conflicts_spy = MagicMock(return_value=[])
        export_spy = AsyncMock(return_value={"rules_exported": 7})
        monkeypatch.setattr("writ.authoring.check_conflicts", check_conflicts_spy)
        monkeypatch.setattr("writ.export.export_rules_to_markdown", export_spy)

        result = await finalize_conflict_and_export(
            fake_db, fake_cache, "R-1", bible_dir="custom/"
        )

        assert result["export_dir"] == "custom/"
        export_spy.assert_awaited_once_with(fake_db, Path("custom/"))


# ---------------------------------------------------------------------------
# review authority state machine -- promote / reject / downweight
# (cli.py:1153-1185)
# ---------------------------------------------------------------------------


class _FakeReviewDB:
    """Fake db exposing only the three async methods the review authority
    transitions call, as bare recorders (no live Neo4j)."""

    def __init__(self) -> None:
        self.update_rule_authority = AsyncMock()
        self.update_rule_confidence = AsyncMock()
        self.delete_rule = AsyncMock()


@pytest.fixture
def review_db() -> _FakeReviewDB:
    return _FakeReviewDB()


class TestPromote:
    """promote GUARDS on existing.get('authority') != 'ai-provisional':
    illegal transitions raise and touch neither db method; a legal
    transition updates BOTH authority and confidence as a unit."""

    @pytest.mark.asyncio
    async def test_promote_ai_provisional_updates_both(
        self, review_db: _FakeReviewDB
    ) -> None:
        existing = {"authority": "ai-provisional"}

        await promote(review_db, "R-1", existing)

        review_db.update_rule_authority.assert_awaited_once_with(
            "R-1", "ai-promoted"
        )
        review_db.update_rule_confidence.assert_awaited_once_with(
            "R-1", "peer-reviewed"
        )

    @pytest.mark.asyncio
    async def test_promote_non_provisional_raises_and_no_db(
        self, review_db: _FakeReviewDB
    ) -> None:
        existing = {"authority": "ai-promoted"}

        with pytest.raises(IllegalAuthorityTransitionError) as exc_info:
            await promote(review_db, "R-1", existing)

        review_db.update_rule_authority.assert_not_awaited()
        review_db.update_rule_confidence.assert_not_awaited()

        err = exc_info.value
        assert err.rule_id == "R-1"
        assert err.current_authority == "ai-promoted"
        assert err.action == "promote"


class TestReject:
    """reject GUARDS identically to promote: illegal transitions raise and
    never call delete_rule; a legal transition deletes the rule."""

    @pytest.mark.asyncio
    async def test_reject_ai_provisional_deletes(
        self, review_db: _FakeReviewDB
    ) -> None:
        existing = {"authority": "ai-provisional"}

        await reject(review_db, "R-1", existing)

        review_db.delete_rule.assert_awaited_once_with("R-1")

    @pytest.mark.asyncio
    async def test_reject_non_provisional_raises_and_no_delete(
        self, review_db: _FakeReviewDB
    ) -> None:
        existing = {"authority": "human"}

        with pytest.raises(IllegalAuthorityTransitionError) as exc_info:
            await reject(review_db, "R-1", existing)

        review_db.delete_rule.assert_not_awaited()

        err = exc_info.value
        assert err.rule_id == "R-1"
        assert err.current_authority == "human"
        assert err.action == "reject"


class TestDownweight:
    """downweight is the one asymmetric transition: it takes NO `existing`
    argument (signature is `(db, rule_id)` only) and applies NO authority
    guard, so it must succeed identically no matter what authority the rule
    would have had under promote/reject's guard."""

    def test_signature_has_no_existing_param(self) -> None:
        params = list(inspect.signature(downweight).parameters)
        assert params == ["db", "rule_id"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "existing_authority",
        ["ai-provisional", "ai-promoted", "human", None],
        ids=["ai-provisional", "ai-promoted", "human", "missing"],
    )
    async def test_downweight_any_authority_no_guard(
        self, review_db: _FakeReviewDB, existing_authority: str | None
    ) -> None:
        # existing_authority is documentation-only: downweight's signature
        # has no `existing` parameter, so it cannot consult authority at
        # all -- this pins that there is nothing to branch on.
        await downweight(review_db, "R-1")

        review_db.update_rule_confidence.assert_awaited_once_with(
            "R-1", "speculative"
        )
        review_db.update_rule_authority.assert_not_awaited()
        review_db.delete_rule.assert_not_awaited()


# ---------------------------------------------------------------------------
# assert_ai_provisional -- single-source legality guard (DRY-DUP-002) shared
# by promote/reject and the cli.py review pre-confirm check
# ---------------------------------------------------------------------------


class TestAssertAiProvisional:
    """The one legality check for promote/reject: returns None for an
    ai-provisional rule, raises IllegalAuthorityTransitionError otherwise,
    carrying rule_id / current_authority / action for the caller."""

    def test_passes_for_ai_provisional(self) -> None:
        existing = {"authority": "ai-provisional"}

        assert assert_ai_provisional(existing, "R-1", "promote") is None

    def test_raises_for_non_provisional(self) -> None:
        existing = {"authority": "ai-promoted"}

        with pytest.raises(IllegalAuthorityTransitionError) as exc_info:
            assert_ai_provisional(existing, "R-1", "promote")

        err = exc_info.value
        assert err.action == "promote"
        assert err.rule_id == "R-1"
        assert err.current_authority == "ai-promoted"
