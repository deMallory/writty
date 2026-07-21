"""Guard for the Wave 3 read_jsonl() dedup.

Five functions in writ/analysis/ hand-repeated the same "open a JSONL file, strip, skip
blank, json.loads, skip malformed" loop. The dedup extracts it into one generator
writ/analysis/jsonl.read_jsonl(path, *, errors=None) and rewrites each caller to iterate it.

read_jsonl tolerates ONLY per-line json errors; open-time OSError (missing/dir/permission)
PROPAGATES, so each caller keeps its OWN prior missing/error policy: friction guards with
path.exists(); token_audit._read_friction wraps in try/except OSError; the required-transcript
readers (parse_turns/_detect_cc_version) let it raise so a bad path fails LOUD as before.

RED today: writ.analysis.jsonl does not exist (behavior tests fail on import) and the three
modules still contain inline `json.loads(line)` loops (structural tests fail on assertion).
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
ANALYSIS = REPO / "writ" / "analysis"


class TestReadJsonlBehavior:
    def test_yields_parsed_objects_and_skips_blank_and_malformed(self, tmp_path) -> None:
        from writ.analysis.jsonl import read_jsonl  # RED today: module absent

        p = tmp_path / "log.jsonl"
        p.write_text('{"a": 1}\n\n   \n{bad json\n{"b": 2}\n')
        assert list(read_jsonl(p)) == [{"a": 1}, {"b": 2}]

    def test_missing_file_raises(self, tmp_path) -> None:
        # read_jsonl does NOT decide the missing policy; it propagates so callers that must
        # fail loud (required transcript) do, and callers that tolerate missing guard themselves.
        from writ.analysis.jsonl import read_jsonl

        with pytest.raises(FileNotFoundError):
            list(read_jsonl(tmp_path / "does-not-exist.jsonl"))

    def test_directory_path_raises(self, tmp_path) -> None:
        from writ.analysis.jsonl import read_jsonl

        with pytest.raises(OSError):
            list(read_jsonl(tmp_path))

    def test_errors_ignore_yields_valid_object(self, tmp_path) -> None:
        from writ.analysis.jsonl import read_jsonl

        p = tmp_path / "bytes.jsonl"
        p.write_bytes(b"\xff\xfe garbage\n" + b'{"ok": 1}\n')
        assert list(read_jsonl(p, errors="ignore")) == [{"ok": 1}]


class TestCallerMissingPolicyPreserved:
    """Each caller keeps its exact pre-dedup missing/error behavior."""

    def test_friction_missing_returns_empty(self, tmp_path) -> None:
        from writ.analysis.friction import _read_single_file

        assert _read_single_file(tmp_path / "nope.jsonl") == []

    def test_friction_directory_fails_loud(self, tmp_path) -> None:
        # a --log path that is a directory raised (uncaught) before the dedup; it must still
        # fail loud rather than silently report "0 events".
        from writ.analysis.friction import _read_single_file

        with pytest.raises(OSError):
            _read_single_file(tmp_path)

    def test_read_friction_tolerates_missing_and_none(self, tmp_path) -> None:
        from writ.analysis.token_audit import _read_friction

        assert _read_friction(None) == []
        assert _read_friction(str(tmp_path / "nope.jsonl")) == []

    def test_scorecard_on_missing_transcript_fails_loud_as_io_error(self, tmp_path) -> None:
        # The required transcript is not optional: a missing/typo path must surface as an IO
        # error (cli maps it to exit 1 "cannot read transcript"), NOT the schema canary.
        from writ.analysis.token_audit import scorecard

        with pytest.raises(OSError):
            scorecard(str(tmp_path / "no-such-transcript.jsonl"), None, "claude-opus-4-8")


class TestCallersUseReadJsonl:
    def test_friction_reader_uses_read_jsonl(self) -> None:
        src = (ANALYSIS / "friction.py").read_text()
        assert "read_jsonl" in src, "friction.py must use read_jsonl"
        assert "json.loads(line)" not in src, "the inline skip-malformed loop must be gone"

    def test_token_audit_and_efficacy_use_read_jsonl(self) -> None:
        for mod in ("token_audit.py", "efficacy_ab.py"):
            src = (ANALYSIS / mod).read_text()
            assert "read_jsonl" in src, f"{mod} must use read_jsonl"
            assert "json.loads(line)" not in src, f"{mod} inline skip-malformed loop must be gone"
