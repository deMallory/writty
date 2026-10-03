"""Writ's state file in Vibe's scratchpad (writ/harness/vibe_context.py).

Vibe re-reads `$VIBE_HOME/logs/session/unified/<sid>/scratchpad/` at the start of every
turn, so the bridge keeps Writ's state there as `0-writ.md`. The renderer tests feed it
what `writ-session.py current-phase` prints. The refresh tests run a stub of that command
in a throwaway plugin root, and one runs Writ's own against a temp cache.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from writ.harness import vibe_context, vibe_install
from writ.session.locators import plan_dir

REPO = Path(__file__).resolve().parent.parent
SID = "sid-1"
MODES = ("work", "debug", "review", "conversation", "investigate")


def _phase(mode: str | None, *, phase: str = "unclassified", gates: tuple[str, ...] = (),
           next_gate: str | None = None) -> dict:
    """The JSON `writ-session.py current-phase` prints."""
    return {"phase": phase, "mode": mode, "gates_approved": list(gates),
            "next_gate": next_gate, "plan_hash": None, "candidate_id": "", "rule_id": ""}


NO_MODE = _phase(None)
PHASE_A = _phase("work", phase="planning", next_gate="phase-a")
SKELETONS = _phase("work", phase="testing", gates=("phase-a",), next_gate="test-skeletons")
OTHER_GATE = _phase("work", phase="testing", gates=("phase-a",), next_gate="final-review")
NONE_PENDING = _phase("work", phase="implementation", gates=("phase-a", "test-skeletons"))
DEBUG = _phase("debug")
REVIEW = _phase("review")
CONVERSATION = _phase("conversation")
INVESTIGATE = _phase("investigate")
EVERY_STATE = [NO_MODE, PHASE_A, SKELETONS, OTHER_GATE, NONE_PENDING,
               DEBUG, REVIEW, CONVERSATION, INVESTIGATE]


def _render(phase: dict, root: str | None = "/work/proj") -> str:
    return vibe_context.render_state(phase, SID, root)


def _next(text: str) -> str:
    found = [line for line in text.splitlines() if line.startswith("Next: ")]
    assert len(found) <= 1, text
    return found[0] if found else ""


# --------------------------------------------------------------------------- #
# The state text
# --------------------------------------------------------------------------- #
class TestRender:
    def test_header_says_writ_rewrites_the_file_and_owns_it(self):
        header = _render(PHASE_A).split("\n\n")[0]
        assert header.startswith("Writ state for this session.")
        assert "!mistty" in header
        assert "other files" in header

    def test_no_mode_says_writ_refuses_writes_and_names_the_mode_command(self):
        text = _render(NO_MODE, None)
        assert "Mode: none" in text.splitlines()
        nxt = _next(text)
        assert "refuses every write" in nxt
        assert "!mistty mode" in nxt
        for mode in MODES:
            assert mode in nxt, mode

    @pytest.mark.parametrize("root", ["/work/proj", "/work/proj/"])
    def test_work_with_phase_a_pending_gives_the_state_and_the_plan_folder(self, root):
        text = _render(PHASE_A, root)
        lines = text.splitlines()
        assert "Mode: work" in lines
        assert "Phase: planning" in lines
        assert "Approved gates: none" in lines
        assert "Pending gate: phase-a" in lines
        assert f"Plan folder: {plan_dir(root, SID)}/" in lines
        nxt = _next(text)
        for needle in ("plan.md", "capabilities.md", "!mistty approve"):
            assert needle in nxt, needle

    def test_phase_a_next_line_names_the_sections_and_the_files_line_grammar(self):
        # Session 2709fed0: the model wrote a plan with none of these, and each miss
        # cost one rejected approval.
        nxt = _next(_render(PHASE_A, "/work/proj"))
        for needle in ("## Files", "- `path` (change) -- reason", "create, modify or delete",
                       "## Analysis", "## Rules Applied", '"No matching rules"',
                       "## Capabilities", "unchecked - [ ]"):
            assert needle in nxt, needle

    def test_work_without_a_project_root_has_no_plan_folder_line(self):
        assert "Plan folder:" not in _render(PHASE_A, None)

    def test_plan_folder_is_shown_in_work_mode_only(self):
        assert "Plan folder:" not in _render(DEBUG, "/work/proj")

    def test_work_with_test_skeletons_pending(self):
        text = _render(SKELETONS)
        assert "Approved gates: phase-a" in text.splitlines()
        assert "Pending gate: test-skeletons" in text.splitlines()
        nxt = _next(text)
        assert "test" in nxt.lower()
        assert "!mistty approve" in nxt

    def test_work_with_another_gate_pending_names_it(self):
        text = _render(OTHER_GATE)
        assert "Pending gate: final-review" in text.splitlines()
        nxt = _next(text)
        assert "final-review" in nxt
        assert "!mistty approve" in nxt

    def test_work_with_no_gate_pending_says_implement_and_names_replan(self):
        text = _render(NONE_PENDING)
        assert "Approved gates: phase-a, test-skeletons" in text.splitlines()
        assert "Pending gate: none" in text.splitlines()
        nxt = _next(text)
        assert "implement" in nxt.lower()
        assert "!mistty replan" in nxt

    @pytest.mark.parametrize("phase, needle", [
        (DEBUG, "debug.md"),
        (REVIEW, "Evaluate code against Writ's rules"),
        (CONVERSATION, "No code changes are expected"),
    ])
    def test_other_modes_get_their_next_line(self, phase, needle):
        text = _render(phase)
        assert f"Mode: {phase['mode']}" in text.splitlines()
        assert needle in _next(text)

    def test_investigate_has_no_next_line(self):
        text = _render(INVESTIGATE)
        assert "Mode: investigate" in text.splitlines()
        assert _next(text) == ""

    @pytest.mark.parametrize("phase", EVERY_STATE, ids=lambda p: f"{p['mode']}-{p['next_gate']}")
    def test_every_state_stays_under_1000_characters(self, phase):
        long_sid = "s" * 100
        long_root = "/Users/someone/" + "deep/" * 24 + "project"
        assert len(vibe_context.render_state(phase, long_sid, long_root)) < 1000


# --------------------------------------------------------------------------- #
# Where the file goes
# --------------------------------------------------------------------------- #
def test_scratchpad_dir_is_under_the_unified_session_folder(tmp_path):
    expected = tmp_path / "logs" / "session" / "unified" / SID / "scratchpad"
    assert vibe_context.scratchpad_dir(str(tmp_path), SID) == str(expected)


_VIBE_DIR = (
    "import sys\n"
    "from vibe.app_server._unified_scratchpad import scratchpad_dir\n"
    "print(scratchpad_dir(sys.argv[1], sys.argv[2]))\n"
)


def test_scratchpad_dir_matches_vibes_own(tmp_path):
    python = vibe_install.vibe_python()
    if not python:
        pytest.skip("Mistral Vibe is not installed")
    # Vibe's storage root is its session_logging.save_dir, $VIBE_HOME/logs/session.
    proc = subprocess.run([python, "-c", _VIBE_DIR, str(tmp_path / "logs" / "session"), SID],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    ours = Path(vibe_context.scratchpad_dir(str(tmp_path), SID)).resolve()
    assert Path(proc.stdout.strip()) == ours


# --------------------------------------------------------------------------- #
# The session cache
# --------------------------------------------------------------------------- #
@pytest.fixture
def cache(tmp_path, monkeypatch):
    """A temp Writ session cache. seed(state) writes sid-1's; a str is written as is."""
    root = tmp_path / "writ-cache"
    root.mkdir()
    monkeypatch.setenv("WRIT_CACHE_DIR", str(root))

    def seed(state, sid: str = SID):
        body = state if isinstance(state, str) else json.dumps(state)
        (root / f"writ-session-{sid}.json").write_text(body)
    return seed


def test_read_session_cache_returns_the_cache(cache):
    cache({"mode": "work", "project_root": "/p"})
    assert vibe_context.read_session_cache(SID) == {"mode": "work", "project_root": "/p"}


@pytest.mark.parametrize("body", [None, "{not json", "[1, 2]"])
def test_read_session_cache_is_empty_when_missing_or_unreadable(cache, body):
    if body is not None:
        cache(body)
    assert vibe_context.read_session_cache(SID) == {}


def test_read_session_cache_refuses_an_unsafe_session_id(cache):
    assert vibe_context.read_session_cache("../escape") == {}


# --------------------------------------------------------------------------- #
# refresh
# --------------------------------------------------------------------------- #
# Records its argv, prints phase.out and exits with phase.rc, both from the test log.
_STUB = (
    "import json, os, sys\n"
    "log = os.environ['VIBE_TEST_LOG']\n"
    "with open(os.path.join(log, 'phase.argv.json'), 'w') as f:\n"
    "    json.dump(sys.argv[1:], f)\n"
    "with open(os.path.join(log, 'phase.out')) as f:\n"
    "    sys.stdout.write(f.read())\n"
    "with open(os.path.join(log, 'phase.rc')) as f:\n"
    "    sys.exit(int(f.read()))\n"
)


class Vibe:
    """A throwaway plugin root with a stub phase command, and a Vibe home."""

    def __init__(self, tmp_path: Path):
        self.plugin = tmp_path / "plugin"
        (self.plugin / "bin" / "lib").mkdir(parents=True)
        (self.plugin / "bin" / "lib" / "writ-session.py").write_text(_STUB)
        self.log = tmp_path / "log"
        self.log.mkdir()
        self.home = tmp_path / "vibe-home"
        self.session = self.home / "logs" / "session" / "unified" / SID
        self.state = self.session / "scratchpad" / vibe_context.WRIT_FILE
        self.say(PHASE_A)

    def say(self, phase: dict | str, rc: int = 0) -> None:
        (self.log / "phase.out").write_text(phase if isinstance(phase, str) else json.dumps(phase))
        (self.log / "phase.rc").write_text(str(rc))

    def open_session(self) -> None:
        self.session.mkdir(parents=True)

    def refresh(self, sid: str = SID, **overrides) -> bool:
        kwargs = {"vibe_home": str(self.home), "plugin_root": str(self.plugin),
                  "base_env": {**os.environ, "VIBE_TEST_LOG": str(self.log)}, **overrides}
        return vibe_context.refresh(sid, **kwargs)

    def ran(self) -> list | None:
        path = self.log / "phase.argv.json"
        return json.loads(path.read_text()) if path.exists() else None


@pytest.fixture
def vibe_env(tmp_path, cache) -> Vibe:
    cache({"mode": "work", "project_root": "/work/proj"})
    return Vibe(tmp_path)


class TestRefresh:
    def test_writes_the_rendered_state_into_the_session_scratchpad(self, vibe_env):
        vibe_env.open_session()
        assert vibe_env.refresh() is True
        assert vibe_env.ran() == ["current-phase", SID]
        assert vibe_env.state.read_text() == vibe_context.render_state(PHASE_A, SID, "/work/proj")
        assert os.listdir(vibe_env.state.parent) == [vibe_context.WRIT_FILE]

    def test_does_nothing_without_the_unified_session_folder(self, vibe_env):
        assert vibe_env.refresh() is False
        assert not vibe_env.home.exists()
        assert vibe_env.ran() is None

    @pytest.mark.parametrize("out, rc", [("", 1), ("not json", 0), ("[1, 2]", 0)])
    def test_keeps_the_old_file_when_the_phase_command_fails(self, vibe_env, out, rc):
        vibe_env.open_session()
        vibe_env.state.parent.mkdir()
        vibe_env.state.write_text("OLD")
        vibe_env.say(out, rc)
        assert vibe_env.refresh() is False
        assert vibe_env.state.read_text() == "OLD"

    def test_leaves_an_unchanged_file_untouched(self, vibe_env):
        vibe_env.open_session()
        assert vibe_env.refresh() is True
        os.utime(vibe_env.state, (1, 1))
        assert vibe_env.refresh() is True
        assert vibe_env.state.stat().st_mtime == 1

    def test_rewrites_the_file_when_the_state_changes(self, vibe_env):
        vibe_env.open_session()
        vibe_env.refresh()
        vibe_env.say(SKELETONS)
        assert vibe_env.refresh() is True
        assert "Pending gate: test-skeletons" in vibe_env.state.read_text().splitlines()

    def test_reads_the_vibe_home_from_the_environment(self, vibe_env, monkeypatch):
        vibe_env.open_session()
        monkeypatch.setenv("VIBE_HOME", str(vibe_env.home))
        assert vibe_env.refresh(vibe_home=None) is True
        assert vibe_env.state.exists()

    def test_refuses_an_unsafe_session_id(self, vibe_env):
        escape = vibe_env.home / "logs" / "session" / "escape"
        escape.mkdir(parents=True)
        assert vibe_env.refresh("../escape") is False
        assert list(escape.iterdir()) == []
        assert vibe_env.ran() is None

    @pytest.mark.parametrize("case", ["no_plugin_root", "home_is_a_file", "scratchpad_is_a_file"])
    def test_never_raises(self, vibe_env, tmp_path, case):
        if case == "no_plugin_root":
            vibe_env.open_session()
            assert vibe_env.refresh(plugin_root=str(tmp_path / "missing")) is False
        elif case == "home_is_a_file":
            vibe_env.home.write_text("")
            assert vibe_env.refresh() is False
        else:
            vibe_env.open_session()
            (vibe_env.session / "scratchpad").write_text("")
            assert vibe_env.refresh() is False

    def test_runs_writs_own_phase_command(self, tmp_path, cache):
        cache({"mode": "work", "current_phase": "planning", "gates_approved": []})
        home = tmp_path / "vibe-home"
        (home / "logs" / "session" / "unified" / SID).mkdir(parents=True)
        (tmp_path / "home").mkdir()
        env = {**os.environ, "HOME": str(tmp_path / "home")}
        assert vibe_context.refresh(SID, vibe_home=str(home), plugin_root=str(REPO),
                                    base_env=env) is True
        text = Path(vibe_context.scratchpad_dir(str(home), SID), vibe_context.WRIT_FILE).read_text()
        assert "Mode: work" in text.splitlines()
        assert "Pending gate: phase-a" in text.splitlines()
