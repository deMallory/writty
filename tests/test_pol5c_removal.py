"""POL-5c: the dead InstructionsLoaded hook + instructions_rule_ids feature is removed.

The hook was a no-op in current Claude Code (the payload carries no instruction
content) and addressed a need Writ's architecture does not have (rule bodies live
in the RAG, CLAUDE.md only references node IDs). Removed end-to-end.

Removal guards (RED until removal lands):
  - writ-instructions-loaded.sh gone
  - instructions_rule_ids gone from writ-session.py + fresh cache
  - writ-rag-inject.sh no longer extracts/merges it
  - InstructionsLoaded unregistered in all 3 surfaces + permission entries gone

Preservation guards (green now, must STAY green):
  - the phase-tracked exclusion (loaded_rule_ids_by_phase -> exclude_rule_ids) intact
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import uuid
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
WRIT_SESSION_PY = str(SKILL_DIR / "bin" / "lib" / "writ-session.py")
INSTRUCTIONS_HOOK = SKILL_DIR / "hooks" / "scripts" / "writ-instructions-loaded.sh"
RAG_INJECT = SKILL_DIR / "hooks" / "scripts" / "writ-rag-inject.sh"
GLOBAL_SETTINGS = Path.home() / ".claude" / "settings.json"
PLUGIN_HOOKS = SKILL_DIR / "hooks" / "hooks.json"


def _load_writ_session():
    spec = importlib.util.spec_from_file_location("writ_session_pol5c", WRIT_SESSION_PY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def mod():
    return _load_writ_session()


@pytest.fixture()
def session_id():
    sid = f"test-pol5c-{uuid.uuid4().hex[:8]}"
    yield sid
    path = Path(tempfile.gettempdir()) / f"writ-session-{sid}.json"
    if path.exists():
        path.unlink()


# --------------------------------------------------------------------------- #
# 1. hook + feature removed
# --------------------------------------------------------------------------- #
class TestHookRemoved:
    def test_hook_script_deleted(self) -> None:
        assert not INSTRUCTIONS_HOOK.exists(), (
            "writ-instructions-loaded.sh is a no-op in current CC and must be deleted"
        )

    def test_field_gone_from_writ_session_source(self) -> None:
        src = Path(WRIT_SESSION_PY).read_text()
        assert "instructions_rule_ids" not in src, (
            "instructions_rule_ids must be removed from writ-session.py"
        )

    def test_field_absent_from_fresh_cache(self, mod, session_id) -> None:
        cache = mod._read_cache(session_id)
        assert "instructions_rule_ids" not in cache, (
            "a fresh session cache must not contain instructions_rule_ids"
        )

    def test_consumer_gone_from_rag_inject(self) -> None:
        src = RAG_INJECT.read_text()
        assert "instructions_rule_ids" not in src, "rag-inject must not read instructions_rule_ids"
        assert "INSTRUCTIONS_RULE_IDS" not in src, "rag-inject must not extract INSTRUCTIONS_RULE_IDS"


# --------------------------------------------------------------------------- #
# 2. unregistered across all three surfaces
# --------------------------------------------------------------------------- #
class TestUnregistered:
    @pytest.mark.parametrize(
        "path",
        [
            pytest.param(
                GLOBAL_SETTINGS,
                marks=pytest.mark.skipif(
                    not GLOBAL_SETTINGS.exists(),
                    reason="operator ~/.claude/settings.json not present",
                ),
                id="global",
            ),
            pytest.param(PLUGIN_HOOKS, id="plugin"),
        ],
    )
    def test_instructionsloaded_event_absent(self, path: Path) -> None:
        data = json.loads(path.read_text())
        hooks = data.get("hooks", {})
        assert "InstructionsLoaded" not in hooks, (
            f"InstructionsLoaded event must be removed from {path}"
        )

    @pytest.mark.skipif(
        not GLOBAL_SETTINGS.exists(),
        reason="operator ~/.claude/settings.json not present",
    )
    @pytest.mark.parametrize(
        "path", [GLOBAL_SETTINGS], ids=["global"],
    )
    def test_permission_entry_absent(self, path: Path) -> None:
        data = json.loads(path.read_text())
        allow = data.get("permissions", {}).get("allow", [])
        assert not any("writ-instructions-loaded.sh" in a for a in allow), (
            f"writ-instructions-loaded.sh permission-allow entry must be removed from {path}"
        )

    def test_no_reference_to_hook_script_anywhere_in_settings(self) -> None:
        # PLUGIN_HOOKS is a repo file (always present in a checkout); its
        # assertion stays unconditional.
        assert "writ-instructions-loaded.sh" not in PLUGIN_HOOKS.read_text(), (
            f"no reference to the deleted hook should remain in {PLUGIN_HOOKS}"
        )
        # GLOBAL_SETTINGS is the operator's real file; guard on existence so the
        # check runs where installed and is skipped (not crashed) where absent.
        if GLOBAL_SETTINGS.exists():
            assert "writ-instructions-loaded.sh" not in GLOBAL_SETTINGS.read_text(), (
                f"no reference to the deleted hook should remain in {GLOBAL_SETTINGS}"
            )


# --------------------------------------------------------------------------- #
# 3. real dedup path preserved (regression guards)
# --------------------------------------------------------------------------- #
class TestExclusionPathPreserved:
    def test_rag_inject_still_builds_exclude_rule_ids(self) -> None:
        src = RAG_INJECT.read_text()
        assert "exclude_rule_ids" in src, "the real exclusion path must stay"
        assert "LOADED_RULE_IDS" in src, "phase-tracked loaded rule IDs must still feed excludes"

    def test_loaded_rule_ids_still_defaults(self, mod, session_id) -> None:
        cache = mod._read_cache(session_id)
        assert "loaded_rule_ids" in cache, (
            "the loaded-rule-ids exclusion field (real dedup) must remain in the cache"
        )
