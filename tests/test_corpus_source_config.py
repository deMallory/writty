"""get_corpus_dir and the CLI source-dir resolution for the corpus source (MTY-53).

Layering for the corpus source: env beats file beats built-in, mirroring
get_default_mode. With [source] corpus_dir set, `writ import-markdown`,
`writ export` and the promote write path default to Mistty's corpus instead of
bible/; the path arguments still override. Unset, every default stays bible/.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from writ.cli import DEFAULT_BIBLE_DIR, resolve_source_dir
from writ.config import get_corpus_dir


def _write_config(tmp_path, body: str) -> str:
    p = tmp_path / "writ.toml"
    p.write_text(textwrap.dedent(body))
    return str(p)


class TestGetCorpusDir:
    def test_no_env_and_no_config_section_yields_none(self, tmp_path, monkeypatch):
        monkeypatch.delenv("WRIT_CORPUS_DIR", raising=False)
        path = _write_config(tmp_path, "[service]\nport = 8765\n")
        assert get_corpus_dir(path) is None

    def test_a_configured_corpus_dir_is_returned_as_a_path(self, tmp_path, monkeypatch):
        monkeypatch.delenv("WRIT_CORPUS_DIR", raising=False)
        path = _write_config(
            tmp_path,
            '[source]\ncorpus_dir = "/repos/mistty/vibe/core/governance/corpus"\n',
        )
        assert get_corpus_dir(path) == Path("/repos/mistty/vibe/core/governance/corpus")

    def test_env_beats_the_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CORPUS_DIR", "/from/env/corpus")
        path = _write_config(tmp_path, '[source]\ncorpus_dir = "/from/file/corpus"\n')
        assert get_corpus_dir(path) == Path("/from/env/corpus")

    def test_an_empty_config_value_is_ignored(self, tmp_path, monkeypatch):
        monkeypatch.delenv("WRIT_CORPUS_DIR", raising=False)
        path = _write_config(tmp_path, '[source]\ncorpus_dir = ""\n')
        assert get_corpus_dir(path) is None

    def test_an_empty_env_value_is_ignored_in_favor_of_the_file(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("WRIT_CORPUS_DIR", "")
        path = _write_config(tmp_path, '[source]\ncorpus_dir = "/from/file/corpus"\n')
        assert get_corpus_dir(path) == Path("/from/file/corpus")


class TestResolveSourceDir:
    def test_without_config_the_default_is_bible(self, tmp_path, monkeypatch):
        monkeypatch.delenv("WRIT_CORPUS_DIR", raising=False)
        path = _write_config(tmp_path, "[service]\nport = 8765\n")
        assert resolve_source_dir(config_path=path) == Path(DEFAULT_BIBLE_DIR)

    def test_with_a_configured_corpus_dir_it_becomes_the_default(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.delenv("WRIT_CORPUS_DIR", raising=False)
        path = _write_config(
            tmp_path,
            '[source]\ncorpus_dir = "/repos/mistty/vibe/core/governance/corpus"\n',
        )
        assert resolve_source_dir(config_path=path) == Path(
            "/repos/mistty/vibe/core/governance/corpus"
        )

    def test_an_explicit_argument_beats_env_and_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CORPUS_DIR", "/from/env/corpus")
        path = _write_config(tmp_path, '[source]\ncorpus_dir = "/from/file/corpus"\n')
        assert resolve_source_dir(
            argument=Path("/explicit/dir"), config_path=path
        ) == Path("/explicit/dir")

    def test_an_env_corpus_dir_beats_the_file_default(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CORPUS_DIR", "/from/env/corpus")
        path = _write_config(tmp_path, "[service]\nport = 8765\n")
        assert resolve_source_dir(config_path=path) == Path("/from/env/corpus")
