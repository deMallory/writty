"""POL-6h: cmd_metrics -> writ/session/metrics.py (the final facade extraction).

metrics.py is a pure leaf: stdlib-only, no writ.session import. After this the facade has zero
inline command defs. RED until the move lands.

Per TEST-TDD-001: skeletons approved before implementation.
"""

from __future__ import annotations

import contextlib
import importlib
import importlib.util
import io
import json
import os
import sys

import pytest

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
FACADE_PATH = os.path.join(SKILL_ROOT, "bin", "lib", "writ-session.py")
METRICS_PATH = os.path.join(SKILL_ROOT, "writ", "session", "metrics.py")


def _load_facade():
    spec = importlib.util.spec_from_file_location("writ_session_pol6h", FACADE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _imp(name):
    if SKILL_ROOT not in sys.path:
        sys.path.insert(0, SKILL_ROOT)
    return importlib.import_module(name)


def _import_lines(path):
    with open(path) as f:
        return "\n".join(
            l for l in f.read().splitlines() if l.strip().startswith(("import ", "from "))
        )


def _write_log(tmp_path, lines):
    p = tmp_path / "workflow-friction.log"
    p.write_text("\n".join(json.dumps(e) if isinstance(e, dict) else e for e in lines) + "\n")
    return p


class TestMetricsModule:
    def test_module_exists(self):
        assert os.path.isfile(METRICS_PATH)

    def test_imports(self):
        assert _imp("writ.session.metrics") is not None

    def test_acyclic_only_lower_layer_import(self):
        imports = _import_lines(METRICS_PATH)
        assert "writ_session" not in imports and "writ-session" not in imports
        # metrics' only package dependency is mode_engine.VALID_MODES (a lower layer).
        assert "from writ.session.mode_engine import" in imports
        assert "VALID_MODES" in imports
        with open(METRICS_PATH) as f:
            assert "spec_from_file_location" not in f.read()


class TestMetricsBehavior:
    def test_report_counts_sessions_and_events(self, tmp_path):
        f = _load_facade()
        log = _write_log(tmp_path, [
            {"session": "s1", "event": "phase_transition_time", "elapsed_seconds": 5},
            {"session": "s1", "event": "phase_advance"},
            {"session": "s2", "event": "gate_denied_then_approved"},
        ])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            f.cmd_metrics(str(log))
        report = json.loads(buf.getvalue().strip())
        assert report["total_sessions"] == 2
        assert report["total_events"] == 3
        assert "clean_run_rate" in report

    def test_missing_log_errors_and_exits(self, tmp_path, capsys):
        f = _load_facade()
        missing = tmp_path / "nope.log"
        with pytest.raises(SystemExit):
            f.cmd_metrics(str(missing))
        assert "error" in capsys.readouterr().out.lower()

    def test_empty_log_errors_and_exits(self, tmp_path, capsys):
        f = _load_facade()
        log = _write_log(tmp_path, ["# just a comment", ""])
        with pytest.raises(SystemExit):
            f.cmd_metrics(str(log))
        assert "error" in capsys.readouterr().out.lower()


class TestSourceShape:
    def test_facade_no_inline_def(self):
        with open(FACADE_PATH) as f:
            assert "def cmd_metrics(" not in f.read()

    def test_facade_reimports_metrics(self):
        with open(FACADE_PATH) as f:
            assert "from writ.session.metrics import" in f.read()

    def test_module_defines_cmd_metrics(self):
        with open(METRICS_PATH) as f:
            assert "def cmd_metrics(" in f.read()

    def test_facade_has_no_remaining_command_defs(self):
        # POL-6 end state: the facade defines only main() (no cmd_* / _helper defs left).
        with open(FACADE_PATH) as f:
            defs = [l for l in f.read().splitlines() if l.startswith("def ")]
        assert defs == ["def main() -> None:"], f"unexpected facade defs: {defs}"
