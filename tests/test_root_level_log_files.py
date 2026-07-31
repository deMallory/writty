"""Coverage-audit D3: the two root-level log files are unmanaged BY DECISION.

`var/logs/calibration.jsonl` sits outside any project dir and outside the stream
taxonomy, which the audit filed as "unrouted". Routing it would be wrong: it holds global
analyzer-calibration data, not per-project workflow events, so it is not a stream. Adding
rotation would also be pointless, because the writer is self-bounding.

That answer is only defensible while the bound holds, so this pins both halves:

  1. The sweep skips root-level files (shared with `_fallback.jsonl`, the durable safety
     net -- rotating the thing that catches failed writes would be self-defeating).
  2. Writes STOP at CALIBRATION_THRESHOLD, so the file cannot grow without limit.

If someone later makes log_calibration unconditional, part 2 fails here and the
"no rotation needed" conclusion has to be revisited rather than silently inherited.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

WRIT_ROOT = Path(__file__).resolve().parent.parent
ROOT_LEVEL_FILES = ("_fallback.jsonl", "calibration.jsonl")


class TestSweepSkipsRootLevelFiles:
    def test_neither_is_a_known_stream(self):
        from writ.session.log_rotation import RETENTION_DAYS

        for name in ROOT_LEVEL_FILES:
            stem = name[: -len(".jsonl")]
            assert stem not in RETENTION_DAYS, (
                f"{name} became a stream; it is per-root, not per-project"
            )

    @pytest.mark.parametrize("name", ROOT_LEVEL_FILES)
    def test_a_root_level_file_is_not_collected_as_live(self, tmp_path, name):
        """The real _collect, on a tree holding both a root file and a project stream."""
        from writ.session.log_rotation import _collect

        (tmp_path / name).write_text('{"event": "x"}\n')
        proj = tmp_path / "github.com" / "org" / "repo"
        proj.mkdir(parents=True)
        (proj / "audit.jsonl").write_text('{"event": "y"}\n')

        live, arc_jsonl, arc_gz = _collect(tmp_path)
        live_names = {p.name for p in live}
        assert "audit.jsonl" in live_names, "a project stream must still be collected"
        assert name not in live_names, f"{name} must not be treated as a live stream"
        assert all(name != p.name for p in arc_jsonl + arc_gz), (
            f"{name} must not be mistaken for an archive generation either"
        )

    def test_a_full_sweep_leaves_the_root_files_alone(self, tmp_path, monkeypatch):
        """End to end through the real entry point, not just the collector.

        rotate_logs resolves the root itself via log_root(), so the tree is pointed at
        with WRIT_LOG_ROOT; scratch_dir is redirected so the run cannot touch /tmp.
        """
        from writ.session.log_rotation import rotate_logs

        monkeypatch.setenv("WRIT_LOG_ROOT", str(tmp_path))
        scratch = tmp_path / "scratch"
        scratch.mkdir()

        before = {}
        for name in ROOT_LEVEL_FILES:
            p = tmp_path / name
            p.write_text('{"event": "keep me"}\n' * 50)
            before[name] = p.read_bytes()
        # A real project stream alongside them, so the sweep has actual work to do and
        # the assertion is not vacuously true on an empty tree.
        proj = tmp_path / "github.com" / "org" / "repo"
        proj.mkdir(parents=True)
        (proj / "audit.jsonl").write_text('{"event": "rotate me"}\n' * 50)

        summary = rotate_logs(scratch_dir=scratch)
        assert isinstance(summary, dict)

        for name in ROOT_LEVEL_FILES:
            p = tmp_path / name
            assert p.is_file(), f"the sweep removed {name}"
            assert p.read_bytes() == before[name], f"the sweep rewrote {name}"
            assert not (tmp_path / "archive" / name).exists()


class TestCalibrationWritesAreBounded:
    def test_get_mode_flips_to_production_at_the_threshold(self, tmp_path):
        from writ.analysis.instrumentation import CALIBRATION_THRESHOLD, Instrumentation

        log = tmp_path / "calibration.jsonl"
        log.write_text('{"n": 1}\n' * (CALIBRATION_THRESHOLD - 1))
        assert Instrumentation(log_path=log).get_mode() == "calibration"

        log.write_text('{"n": 1}\n' * CALIBRATION_THRESHOLD)
        assert Instrumentation(log_path=log).get_mode() == "production", (
            "past the threshold the analyzer must stop writing, which is what bounds the file"
        )

    def test_the_only_caller_is_gated_on_that_mode(self):
        """A source check, because the bound lives in the CALLER, not in the writer.

        log_calibration itself will append whenever called; what limits the file is that
        analyzer.py calls it only under `if mode == "calibration"`. An unconditional call
        added later would remove the bound while every unit test still passed.
        """
        analyzer = (WRIT_ROOT / "writ" / "analysis" / "analyzer.py").read_text()
        calls = [
            (i, ln) for i, ln in enumerate(analyzer.splitlines(), 1)
            if "log_calibration(" in ln
        ]
        assert len(calls) == 1, f"expected exactly one call site; found {calls}"
        lineno = calls[0][0]
        preceding = "\n".join(analyzer.splitlines()[max(0, lineno - 15):lineno])
        assert re.search(r'if\s+mode\s*==\s*["\']calibration["\']', preceding), (
            "the log_calibration call is no longer behind the calibration-mode check, so "
            "calibration.jsonl is no longer bounded and D3's 'no rotation needed' "
            "conclusion needs revisiting"
        )

    def test_no_other_module_calls_it(self):
        hits = []
        for path in (WRIT_ROOT / "writ").rglob("*.py"):
            for i, ln in enumerate(path.read_text().splitlines(), 1):
                if "log_calibration(" in ln and "def log_calibration" not in ln:
                    hits.append(f"{path.relative_to(WRIT_ROOT)}:{i}")
        assert hits == ["writ/analysis/analyzer.py:78"] or len(hits) == 1, (
            f"a second caller would need its own bound: {hits}"
        )
