"""get_default_mode: the configurable default mode for an unset session.

Layering and fallbacks for the default-mode feature (hook wiring lives in
hooks/scripts/writ-rag-inject.sh; the resolver lives here). Env beats file beats
built-in, and an invalid value in either layer falls back to "conversation" so a
typo in the gitignored writ.toml cannot put a session into a mode the engine
does not know.
"""

from __future__ import annotations

import textwrap

from writ.config import (
    DEFAULT_SESSION_MODE,
    VALID_SESSION_MODES,
    get_default_mode,
)


def _write_config(tmp_path, body: str) -> str:
    p = tmp_path / "writ.toml"
    p.write_text(textwrap.dedent(body))
    return str(p)


class TestGetDefaultMode:
    def test_no_config_section_yields_the_builtin_default(self, tmp_path, monkeypatch):
        monkeypatch.delenv("WRIT_DEFAULT_MODE", raising=False)
        path = _write_config(tmp_path, "[service]\nport = 8765\n")
        assert get_default_mode(path) == "conversation"
        assert DEFAULT_SESSION_MODE == "conversation"

    def test_a_valid_configured_mode_is_returned(self, tmp_path, monkeypatch):
        monkeypatch.delenv("WRIT_DEFAULT_MODE", raising=False)
        path = _write_config(tmp_path, '[governance]\ndefault_mode = "review"\n')
        assert get_default_mode(path) == "review"

    def test_an_invalid_configured_mode_falls_back_to_conversation(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.delenv("WRIT_DEFAULT_MODE", raising=False)
        path = _write_config(tmp_path, '[governance]\ndefault_mode = "conversaton"\n')
        assert get_default_mode(path) == "conversation"

    def test_every_valid_mode_is_accepted_from_the_file(self, tmp_path, monkeypatch):
        monkeypatch.delenv("WRIT_DEFAULT_MODE", raising=False)
        for mode in VALID_SESSION_MODES:
            path = _write_config(tmp_path, f'[governance]\ndefault_mode = "{mode}"\n')
            assert get_default_mode(path) == mode

    def test_env_beats_the_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_DEFAULT_MODE", "debug")
        path = _write_config(tmp_path, '[governance]\ndefault_mode = "review"\n')
        assert get_default_mode(path) == "debug"

    def test_an_invalid_env_value_is_ignored_in_favor_of_the_file(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("WRIT_DEFAULT_MODE", "not-a-mode")
        path = _write_config(tmp_path, '[governance]\ndefault_mode = "review"\n')
        assert get_default_mode(path) == "review"

    def test_invalid_env_and_invalid_file_yield_the_builtin_default(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("WRIT_DEFAULT_MODE", "nope")
        path = _write_config(tmp_path, '[governance]\ndefault_mode = "nope"\n')
        assert get_default_mode(path) == "conversation"
