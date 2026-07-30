"""POL-6-pre: validate-test-file.sh must exempt the Writ skill's own source tree.

POL-6 adds modules under writ/session/. The Tier-1 TDD gate (ENF-PROC-TDD-001) in
.claude/hooks/validate-test-file.sh denies Write of any *.py under ^(src|lib|app|writ)/
unless tests/test_<stem>.py exists -- a heuristic the skill's increment-named tests can
never satisfy, blocking every POL-6 phase. Fix: exempt writes whose target resolves inside
the skill tree (mirrors _can_write_check's skill_dir exemption), and remove the now-dead
`writ` matcher branch that existed only to police the skill's own writ/ package.

is_work_mode now goes through `_writ_session "mode get"`, which attempts a daemon curl to
the session mode endpoint first and only falls back to reading the cache file directly, so
these behavioral guards run against the cache-file fallback with no daemon required. RED
until the hook is updated.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
HOOK = SKILL_DIR / "hooks" / "scripts" / "validate-test-file.sh"
WRIT_SESSION_PY = str(SKILL_DIR / "bin" / "lib" / "writ-session.py")
HOOK_SRC = HOOK.read_text()


def _load_writ_session():
    spec = importlib.util.spec_from_file_location("writ_session_6pre", WRIT_SESSION_PY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _seed_work(mod, sid: str) -> None:
    cache = mod._read_cache(sid)
    cache.update(mode="work")
    mod._write_cache(sid, cache)


def _cleanup(sid: str) -> None:
    p = Path(tempfile.gettempdir()) / f"writ-session-{sid}.json"
    if p.exists():
        p.unlink()


def _run_hook(sid: str, file_path, cwd) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps({
            "session_id": sid,
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(file_path)},
        }),
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env={**os.environ},
        timeout=30,
    )


def _denied(result: subprocess.CompletedProcess) -> bool:
    out = result.stdout + result.stderr
    return "ENF-PROC-TDD-001" in out or '"deny"' in out


class TestSkillTreeExemptionBehavior:
    """Writes targeting the skill's own tree are allowed; out-of-tree writes still gated."""

    def test_writ_session_module_allowed(self) -> None:
        """The real POL-6 case: writing writ/session/config.py under the skill is allowed."""
        mod = _load_writ_session()
        sid = f"test-6pre-{uuid.uuid4().hex[:8]}"
        _seed_work(mod, sid)
        try:
            r = _run_hook(sid, SKILL_DIR / "writ" / "session" / "config.py", cwd=SKILL_DIR)
            assert r.returncode == 0, f"stderr={r.stderr[:300]!r}"
            assert not _denied(r), (
                f"skill-internal write must not be denied; out={(r.stdout + r.stderr)[:400]!r}"
            )
        finally:
            _cleanup(sid)

    def test_skill_internal_src_path_allowed(self) -> None:
        """A src/-matching path that is skill-internal is allowed -- isolates the skill-tree
        exemption from the matcher change (src/ still matches the matcher)."""
        mod = _load_writ_session()
        sid = f"test-6pre-{uuid.uuid4().hex[:8]}"
        _seed_work(mod, sid)
        try:
            r = _run_hook(sid, SKILL_DIR / "src" / "fake_pol6pre.py", cwd=SKILL_DIR)
            assert r.returncode == 0
            assert not _denied(r), (
                f"skill-internal src/ write must be allowed; out={(r.stdout + r.stderr)[:400]!r}"
            )
        finally:
            _cleanup(sid)

    def test_out_of_tree_source_still_denied(self, tmp_path) -> None:
        """A *.py write to a NON-skill repo with no companion test is STILL denied
        (the exemption is scoped to the skill tree, not global)."""
        mod = _load_writ_session()
        sid = f"test-6pre-{uuid.uuid4().hex[:8]}"
        _seed_work(mod, sid)
        try:
            r = _run_hook(sid, tmp_path / "src" / "foo.py", cwd=tmp_path)
            assert r.returncode == 0
            assert _denied(r), (
                f"out-of-tree untested source must be denied; out={(r.stdout + r.stderr)[:400]!r}"
            )
        finally:
            _cleanup(sid)

    def test_out_of_tree_tests_path_allowed(self, tmp_path) -> None:
        """tests/ exemption is intact for non-skill repos (no regression)."""
        mod = _load_writ_session()
        sid = f"test-6pre-{uuid.uuid4().hex[:8]}"
        _seed_work(mod, sid)
        try:
            r = _run_hook(sid, tmp_path / "tests" / "test_x.py", cwd=tmp_path)
            assert r.returncode == 0
            assert not _denied(r)
        finally:
            _cleanup(sid)

    def test_out_of_tree_nonsource_allowed(self, tmp_path) -> None:
        """non-source extensions are not gated (no regression)."""
        mod = _load_writ_session()
        sid = f"test-6pre-{uuid.uuid4().hex[:8]}"
        _seed_work(mod, sid)
        try:
            r = _run_hook(sid, tmp_path / "src" / "notes.md", cwd=tmp_path)
            assert r.returncode == 0
            assert not _denied(r)
        finally:
            _cleanup(sid)


class TestSourceShape:
    """Pins the exemption mechanism and the redundancy removal."""

    def test_skill_tree_exemption_present(self) -> None:
        assert "WRIT_DIR_ABS" in HOOK_SRC, "the skill root must be passed into the python check"
        assert "os.path.abspath" in HOOK_SRC, "the exemption must resolve the target to an absolute path"
        assert ".startswith(" in HOOK_SRC, "the exemption must test skill-tree membership via startswith"

    def test_writ_matcher_branch_removed(self) -> None:
        assert "(src|lib|app|writ)" not in HOOK_SRC, "the dead `writ` matcher alternative must be removed"
        assert "(src|lib|app)" in HOOK_SRC, "the matcher must still gate src/lib/app"

    def test_relpath_anchoring_retained(self) -> None:
        assert "relpath" in HOOK_SRC, (
            "the relpath computation must stay -- it protects user projects whose absolute "
            "path has /src/, /lib/, /app/ ancestor dirs"
        )
