"""POL-5b-2c + #3: the write-only `failed_writes` cache field stays removed, and
the dead track-failed-writes hook is gone.

History: failed_writes was write-only dead (written, never read) and was removed.
The hook kept logging the `write_failure` friction event -- but #3 proved that
event NEVER fired in production: its only trigger was `PostToolUseFailure
Write|Edit`, and Write/Edit failures do not raise PostToolUseFailure (verified:
in 2560 blackbox captures, PostToolUseFailure fired only for Read and Bash, and a
freshly-triggered failing Edit raised none). So the hook + its matcher were
removed. The friction analyzer keeps the generic write_failure counter as dormant
infra in case a future, observable surface emits it.
"""

from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path

import pytest

SKILL_DIR = Path.home() / ".claude/skills/writ"
WRIT_SESSION_PY = str(SKILL_DIR / "bin" / "lib" / "writ-session.py")
TRACK_HOOK = SKILL_DIR / "hooks" / "scripts" / "track-failed-writes.sh"
HOOKS_JSON = SKILL_DIR / "hooks" / "hooks.json"
FRICTION_PY = SKILL_DIR / "writ" / "analysis" / "friction.py"


def _load_writ_session():
    spec = importlib.util.spec_from_file_location("writ_session_5b2c", WRIT_SESSION_PY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def mod():
    return _load_writ_session()


@pytest.fixture()
def session_id():
    sid = f"test-5b2c-{uuid.uuid4().hex[:8]}"
    yield sid


# --------------------------------------------------------------------------- #
# 1. failed_writes removed (write-only dead field)
# --------------------------------------------------------------------------- #
class TestFieldRemoved:
    def test_gone_from_writ_session_source(self) -> None:
        assert "failed_writes" not in Path(WRIT_SESSION_PY).read_text(), (
            "failed_writes is write-only dead and must be removed from writ-session.py"
        )

    def test_add_failed_write_arg_gone(self) -> None:
        assert "--add-failed-write" not in Path(WRIT_SESSION_PY).read_text(), (
            "the --add-failed-write update handler must be removed"
        )

    def test_absent_from_fresh_cache(self, mod, session_id) -> None:
        cache = mod._read_cache(session_id)
        assert "failed_writes" not in cache, "a fresh session cache must not contain failed_writes"


# --------------------------------------------------------------------------- #
# 2. dead track-failed-writes hook removed (#3)
# --------------------------------------------------------------------------- #
class TestDeadHookRemoved:
    def test_hook_script_removed(self) -> None:
        assert not TRACK_HOOK.exists(), (
            "track-failed-writes.sh is dead (PostToolUseFailure Write|Edit never "
            "fires) and must be removed"
        )

    def test_matcher_removed_from_hooks_json(self) -> None:
        text = HOOKS_JSON.read_text()
        assert "track-failed-writes" not in text, (
            "the dead track-failed-writes registration must be gone from hooks.json"
        )

    def test_friction_counter_kept_as_dormant_infra(self) -> None:
        # The generic write_failure -> write_failures counter stays; it is harmless
        # dormant infra ready for a future observable producer.
        src = FRICTION_PY.read_text()
        assert "write_failure" in src and "write_failures" in src
