"""POL-6-A3: dedup server VALID_MODES -> import from writ.session.mode_engine.

The server's hardcoded VALID_MODES literal is replaced by an import from the canonical
mode_engine module (single source of truth). The POL-6 split made this safe: mode_engine is a
real, normally-imported module, so the ~19 server route tests that mock the PATH-LOADED
writ_session (patch("writ.server.writ_session", ...)) do not affect it. RED until the change lands.

Per TEST-TDD-001: skeletons approved before implementation.

W2 (server package split, branch refactor/w2-server-split): TestSourceShape reads via
writ_server_source() (tests/conftest.py), which is layout-agnostic -- it scans every
*.py under writ/server/ if that directory exists (post-split: the import line and the
absence of the literal both live in writ/server/__init__.py per the plan), else the
single writ/server.py file (pre-split). This keeps the content assertions correct
across the refactor; only the package-structure itself is guarded elsewhere
(tests/test_server_split_seam.py).
"""

from __future__ import annotations

import importlib
import os
import sys

import pytest

from tests.conftest import writ_server_source

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))

EXPECTED_MODES = {"conversation", "debug", "review", "work", "investigate"}


def _imp(name):
    if SKILL_ROOT not in sys.path:
        sys.path.insert(0, SKILL_ROOT)
    return importlib.import_module(name)


class TestSingleSource:
    def test_server_valid_modes_is_mode_engine_object(self):
        server = _imp("writ.server")
        mode_engine = _imp("writ.session.mode_engine")
        # single source: the SAME set object, not a duplicated literal.
        assert server.VALID_MODES is mode_engine.VALID_MODES

    def test_content_is_the_five_modes(self):
        server = _imp("writ.server")
        assert server.VALID_MODES == EXPECTED_MODES


class TestValidationVocabulary:
    def test_membership_predicate_the_route_relies_on(self):
        # writ/server/routes/session_state.py:109 does `if mode not in VALID_MODES`; verify the predicate semantics.
        server = _imp("writ.server")
        assert "work" in server.VALID_MODES
        assert "investigate" in server.VALID_MODES
        assert "workflow" not in server.VALID_MODES  # the 400-path input


class TestSourceShape:
    def test_imports_from_mode_engine(self):
        src = writ_server_source()
        assert "from writ.session.mode_engine import VALID_MODES" in src

    def test_no_hardcoded_literal(self):
        src = writ_server_source()
        assert "VALID_MODES = {" not in src, "server must not redefine the mode set literal"
