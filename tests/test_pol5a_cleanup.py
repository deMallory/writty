"""POL-5a-cleanup: the dead detect-compaction chain + vestigial
context_warning_emitted_at_pct field are removed; the statusLine-critical
context-percent path is preserved.

Removal guards (RED until the cleanup lands):
  - cmd_detect_compaction gone from writ-session.py
  - /detect-compaction route + DetectCompactionRequest gone from server.py
  - detect-compaction + context-percent case branches gone from common.sh
  - context_warning_emitted_at_pct gone everywhere (writ-session.py + server.py)

Preservation guards (green now, must STAY green -- statusLine + should-skip):
  - /context-percent route + ContextPercentRequest.context_percent kept
  - cmd_should_skip still gates at >=75 on context_percent
  - cmd_reset_after_compaction still resets remaining_budget + clears phase rules
"""

from __future__ import annotations

import importlib.util
import tempfile
import uuid
from pathlib import Path

import pytest

from tests.conftest import writ_server_source

SKILL_DIR = Path.home() / ".claude/skills/writ"
WRIT_SESSION_PY = str(SKILL_DIR / "bin" / "lib" / "writ-session.py")
COMMON_SH = SKILL_DIR / "bin" / "lib" / "common.sh"
POSTCOMPACT_SH = SKILL_DIR / "hooks" / "scripts" / "writ-postcompact.sh"


def _load_writ_session():
    """Load writ-session.py as a module without installing it."""
    spec = importlib.util.spec_from_file_location("writ_session_cleanup", WRIT_SESSION_PY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def mod():
    return _load_writ_session()


@pytest.fixture()
def session_id(mod):
    sid = f"test-pol5a-cleanup-{uuid.uuid4().hex[:8]}"
    yield sid
    path = Path(tempfile.gettempdir()) / f"writ-session-{sid}.json"
    if path.exists():
        path.unlink()


# --------------------------------------------------------------------------- #
# 1. detect-compaction chain removed
# --------------------------------------------------------------------------- #
class TestChainRemoved:
    def test_cmd_detect_compaction_gone(self, mod) -> None:
        assert not hasattr(mod, "cmd_detect_compaction"), (
            "cmd_detect_compaction is dead (PostCompact is authoritative) and must be removed"
        )

    def test_detect_compaction_dispatch_gone_from_help(self) -> None:
        src = Path(WRIT_SESSION_PY).read_text()
        assert "detect-compaction" not in src, (
            "writ-session.py must no longer reference the detect-compaction subcommand"
        )

    def test_detect_compaction_route_gone_from_server(self) -> None:
        src = writ_server_source()
        assert "DetectCompactionRequest" not in src, "DetectCompactionRequest must be removed"
        assert "/detect-compaction" not in src, "the /detect-compaction route must be removed"
        assert "detect_compaction" not in src, "no detect_compaction handler should remain"

    def test_detect_compaction_subcommand_gone_from_common(self) -> None:
        src = COMMON_SH.read_text()
        assert '"detect-compaction")' not in src, (
            "common.sh must no longer have a detect-compaction case branch"
        )

    def test_context_percent_subcommand_gone_from_common(self) -> None:
        """The context-percent subcommand's only caller was the deleted context-watcher."""
        src = COMMON_SH.read_text()
        assert '"context-percent")' not in src, (
            "common.sh context-percent case branch is dead (statusLine POSTs via urllib) "
            "and must be removed"
        )


# --------------------------------------------------------------------------- #
# 2. vestigial field removed
# --------------------------------------------------------------------------- #
class TestFieldRemoved:
    def test_field_gone_from_writ_session_source(self) -> None:
        src = Path(WRIT_SESSION_PY).read_text()
        assert "context_warning_emitted_at_pct" not in src, (
            "context_warning_emitted_at_pct is vestigial (no writer/reader) and must be removed"
        )

    def test_field_gone_from_server_source(self) -> None:
        src = writ_server_source()
        assert "context_warning_emitted_at_pct" not in src, (
            "context_warning_emitted_at_pct must be removed from server.py"
        )

    def test_field_absent_from_fresh_cache(self, mod, session_id) -> None:
        cache = mod._read_cache(session_id)
        assert "context_warning_emitted_at_pct" not in cache, (
            "a fresh session cache must not contain the removed field"
        )

    def test_postcompact_comment_no_stale_field_ref(self) -> None:
        src = POSTCOMPACT_SH.read_text()
        assert "context_warning_emitted_at_pct" not in src, (
            "writ-postcompact.sh comment must not reference the removed field"
        )


# --------------------------------------------------------------------------- #
# 3. statusLine-critical path preserved (regression guards)
# --------------------------------------------------------------------------- #
class TestContextPercentPreserved:
    def test_context_percent_route_kept(self) -> None:
        src = writ_server_source()
        assert "/context-percent" in src, "the /context-percent route must stay (statusLine uses it)"
        assert "ContextPercentRequest" in src
        assert "context_percent" in src

    def test_should_skip_gates_high_context(self, mod, session_id) -> None:
        cache = mod._read_cache(session_id)
        cache["context_percent"] = 80
        cache["remaining_budget"] = mod.DEFAULT_SESSION_BUDGET
        mod._write_cache(session_id, cache)
        assert mod.cmd_should_skip(session_id, 75) is True, "should-skip must still gate at >=75"

    def test_should_skip_allows_low_context(self, mod, session_id) -> None:
        cache = mod._read_cache(session_id)
        cache["context_percent"] = 10
        cache["remaining_budget"] = mod.DEFAULT_SESSION_BUDGET
        mod._write_cache(session_id, cache)
        assert mod.cmd_should_skip(session_id, 75) is False, "low context must not skip"


class TestResetAfterCompactionPreserved:
    def test_reset_restores_budget(self, mod, session_id) -> None:
        cache = mod._read_cache(session_id)
        cache["remaining_budget"] = 0
        cache["current_phase"] = "implementation"
        cache["loaded_rule_ids_by_phase"] = {"implementation": ["ENF-X-001"]}
        mod._write_cache(session_id, cache)
        mod.cmd_reset_after_compaction(session_id)
        after = mod._read_cache(session_id)
        assert after["remaining_budget"] == mod.DEFAULT_SESSION_BUDGET, (
            "cmd_reset_after_compaction must still reset the budget"
        )

    def test_reset_clears_phase_rules(self, mod, session_id) -> None:
        cache = mod._read_cache(session_id)
        cache["current_phase"] = "implementation"
        cache["loaded_rule_ids_by_phase"] = {"implementation": ["ENF-X-001"]}
        mod._write_cache(session_id, cache)
        mod.cmd_reset_after_compaction(session_id)
        after = mod._read_cache(session_id)
        assert after.get("loaded_rule_ids_by_phase", {}).get("implementation", []) == [], (
            "cmd_reset_after_compaction must still clear the current phase's loaded rules"
        )
