"""Guard for the Wave 3 CLI-I/O helper dedup.

Two hand-repeated shapes in the writ/session package collapse to one helper each in the
new leaf module writ/session/cli_io.py:
  - `print(msg, file=sys.stderr)` + `sys.exit(2)`  (17 sites in cli_dispatch.py) -> _usage_exit(msg)
  - `json.dump(obj, sys.stdout[, indent=2])`       (7 approval_workflow + 3 metrics) -> _emit_json(obj, **kw)

RED today: cli_io does not exist (behavior tests fail on import) and the inline shapes
are still present (structural tests fail on their assertions).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SESSION = REPO / "writ" / "session"


class TestUsageExit:
    def test_usage_exit_prints_to_stderr_and_exits_2(self, capsys) -> None:
        from writ.session.cli_io import _usage_exit  # RED today: module absent

        with pytest.raises(SystemExit) as e:
            _usage_exit("Usage: boom")
        assert e.value.code == 2
        captured = capsys.readouterr()
        assert "Usage: boom" in captured.err
        assert captured.out == "", "usage messages go to stderr, not stdout"


class TestEmitJson:
    def test_emit_json_writes_object_to_stdout(self, capsys) -> None:
        from writ.session.cli_io import _emit_json  # RED today: module absent

        _emit_json({"a": 1, "b": [2, 3]})
        out = capsys.readouterr().out
        assert json.loads(out) == {"a": 1, "b": [2, 3]}

    def test_emit_json_passes_kwargs_through(self, capsys) -> None:
        from writ.session.cli_io import _emit_json

        _emit_json({"a": 1}, indent=2)
        out = capsys.readouterr().out
        assert "\n" in out, "indent=2 must pretty-print across multiple lines"
        assert json.loads(out) == {"a": 1}


class TestInlineShapesRemoved:
    def test_cli_dispatch_has_no_usage_exit_pairs(self) -> None:
        src = (SESSION / "cli_dispatch.py").read_text()
        assert "sys.exit(2)" not in src, "the 17 usage-exit pairs must route through _usage_exit"
        assert "_usage_exit(" in src, "cli_dispatch must use _usage_exit"

    def test_json_emitters_route_through_helper(self) -> None:
        for mod in ("approval_workflow.py", "metrics.py"):
            src = (SESSION / mod).read_text()
            assert "json.dump(" not in src, f"{mod} JSON output must route through _emit_json"
            assert "_emit_json(" in src, f"{mod} must use _emit_json"