"""P0.5: `writ efficacy-ab` -- numerator harness (WRIT-TOKEN-BLUEPRINT.md).

Pure unit tests (no subprocess to claude, no Neo4j, no daemon). RED until
writ/analysis/efficacy_ab.py + writ/analysis/variants.py + the CLI command exist.

Contracts tested:
  TestLoadSuite           -- load_suite(dir) happy path + empty-dir EfficacyError
  TestLocateTranscript    -- glob-by-UUID, dotted-home slug; 0-match + dupe raise EfficacyError
  TestScoreRun            -- cost half reused from token_audit.scorecard(), not re-derived
  TestDefectCaught        -- gate signal > judge fallback > none fallback
  TestCleanArm            -- clean-arm sentinel + spurious_gate detection
  TestCompareArms         -- incomplete / insufficient_n / ok+pass verdict scaffold
  TestVariants            -- materialize_variant writ-off/writ-on/unknown
  TestCli                 -- dry-run: exit 0, "DRY RUN" in output, no claude spawn
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

import pytest

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


# ---------------------------------------------------------------------------
# Lazy module loaders (same pattern as test_token_audit.py)
# ---------------------------------------------------------------------------

def _ab():
    if SKILL_ROOT not in sys.path:
        sys.path.insert(0, SKILL_ROOT)
    return importlib.import_module("writ.analysis.efficacy_ab")


def _variants():
    if SKILL_ROOT not in sys.path:
        sys.path.insert(0, SKILL_ROOT)
    return importlib.import_module("writ.analysis.variants")


# ---------------------------------------------------------------------------
# Local transcript helpers (replicated from test_token_audit.py -- no import)
# ---------------------------------------------------------------------------

def _usage(inp=100, out=10, read=1000, write=200, c5=None, c1=None):
    """A well-formed CC assistant-turn usage dict."""
    u = {
        "input_tokens": inp,
        "output_tokens": out,
        "cache_read_input_tokens": read,
        "cache_creation_input_tokens": write,
    }
    if c5 is not None or c1 is not None:
        u["cache_creation"] = {"ephemeral_5m_input_tokens": c5 or 0,
                               "ephemeral_1h_input_tokens": c1 or 0}
    return u


def _write_transcript(path: Path, usages: list[dict], model="claude-opus-4-8") -> Path:
    """Write a minimal CC transcript jsonl: assistant turns carrying message.usage."""
    with open(path, "w") as f:
        for u in usages:
            f.write(json.dumps({"type": "assistant",
                                "message": {"model": model, "usage": u}}) + "\n")
    return path


# ---------------------------------------------------------------------------
# TestLoadSuite
# ---------------------------------------------------------------------------

class TestLoadSuite:
    def test_returns_tasks_with_dir_attached(self, tmp_path: Path):
        ab = _ab()
        for name in ("task_a", "task_b"):
            d = tmp_path / name
            d.mkdir()
            (d / "task.json").write_text(json.dumps({"task_id": name, "arm": "defect"}))
        tasks = ab.load_suite(str(tmp_path))
        assert len(tasks) == 2
        task_ids = {t["task_id"] for t in tasks}
        assert task_ids == {"task_a", "task_b"}

    def test_each_task_has_dir_set(self, tmp_path: Path):
        ab = _ab()
        d = tmp_path / "task_x"
        d.mkdir()
        (d / "task.json").write_text(json.dumps({"task_id": "task_x", "arm": "clean"}))
        tasks = ab.load_suite(str(tmp_path))
        assert len(tasks) == 1
        assert tasks[0]["dir"] == str(d)

    def test_dir_field_points_to_manifest_parent(self, tmp_path: Path):
        ab = _ab()
        d = tmp_path / "some_task"
        d.mkdir()
        manifest = d / "task.json"
        manifest.write_text(json.dumps({"task_id": "some_task", "arm": "defect"}))
        tasks = ab.load_suite(str(tmp_path))
        assert tasks[0]["dir"] == str(d)
        assert os.path.exists(os.path.join(tasks[0]["dir"], "task.json"))

    def test_empty_suite_dir_raises_efficacy_error(self, tmp_path: Path):
        ab = _ab()
        with pytest.raises(ab.EfficacyError) as e:
            ab.load_suite(str(tmp_path))
        assert str(tmp_path) in str(e.value)

    def test_tasks_sorted_deterministically(self, tmp_path: Path):
        ab = _ab()
        for name in ("zzz_last", "aaa_first"):
            d = tmp_path / name
            d.mkdir()
            (d / "task.json").write_text(json.dumps({"task_id": name, "arm": "defect"}))
        tasks = ab.load_suite(str(tmp_path))
        assert tasks[0]["task_id"] == "aaa_first"
        assert tasks[1]["task_id"] == "zzz_last"


# ---------------------------------------------------------------------------
# TestLocateTranscript
# ---------------------------------------------------------------------------

class TestLocateTranscript:
    def test_finds_transcript_by_uuid(self, tmp_path: Path, monkeypatch):
        ab = _ab()
        # Simulate ~/ -> tmp_path via monkeypatching os.path.expanduser
        slug = "-home-user--claude-skills-writ"
        projects_dir = tmp_path / ".claude" / "projects" / slug
        projects_dir.mkdir(parents=True)
        uuid = "aaaabbbb-cccc-dddd-eeee-ffffffffffff"
        transcript = projects_dir / f"{uuid}.jsonl"
        transcript.write_text("{}\n")

        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(os.path, "expanduser",
                            lambda p: str(tmp_path) if p == "~" else os.path.expanduser(p))

        result = ab.locate_transcript(uuid)
        assert result == str(transcript)

    def test_missing_uuid_raises_efficacy_error(self, tmp_path: Path, monkeypatch):
        ab = _ab()
        slug = "-home-user--claude-skills-writ"
        projects_dir = tmp_path / ".claude" / "projects" / slug
        projects_dir.mkdir(parents=True)
        # No .jsonl file created

        monkeypatch.setattr(os.path, "expanduser",
                            lambda p: str(tmp_path) if p == "~" else os.path.expanduser(p))

        with pytest.raises(ab.EfficacyError) as e:
            ab.locate_transcript("00000000-0000-0000-0000-000000000000")
        assert "0" in str(e.value) or "found" in str(e.value)

    def test_duplicate_uuid_across_slugs_raises_efficacy_error(self, tmp_path: Path, monkeypatch):
        ab = _ab()
        uuid = "ddddeeee-ffff-0000-1111-222233334444"
        for slug in ("slug-one", "slug-two"):
            d = tmp_path / ".claude" / "projects" / slug
            d.mkdir(parents=True)
            (d / f"{uuid}.jsonl").write_text("{}\n")

        monkeypatch.setattr(os.path, "expanduser",
                            lambda p: str(tmp_path) if p == "~" else os.path.expanduser(p))

        with pytest.raises(ab.EfficacyError) as e:
            ab.locate_transcript(uuid)
        assert "2" in str(e.value) or "found" in str(e.value)

    def test_dotted_home_double_hyphen_slug_is_found(self, tmp_path: Path, monkeypatch):
        """The canonical CC slug has double-hyphens where the path had slashes after the home
        prefix. locate_transcript globs by UUID so the slug shape is irrelevant -- but this
        test pins the known slug format to catch any regression."""
        ab = _ab()
        # Real slug from CC for ~/.claude/skills/writ
        slug = "-home-user--claude-skills-writ"
        d = tmp_path / ".claude" / "projects" / slug
        d.mkdir(parents=True)
        uuid = "12345678-1234-1234-1234-123456789abc"
        (d / f"{uuid}.jsonl").write_text("{}\n")

        monkeypatch.setattr(os.path, "expanduser",
                            lambda p: str(tmp_path) if p == "~" else os.path.expanduser(p))

        assert ab.locate_transcript(uuid).endswith(f"{uuid}.jsonl")


# ---------------------------------------------------------------------------
# TestScoreRun
# ---------------------------------------------------------------------------

class TestScoreRun:
    def test_total_cost_matches_token_audit_scorecard(self, tmp_path: Path, monkeypatch):
        """The cost half must be REUSED from token_audit.scorecard(), not re-derived."""
        ab = _ab()
        if SKILL_ROOT not in sys.path:
            sys.path.insert(0, SKILL_ROOT)
        token_audit = importlib.import_module("writ.analysis.token_audit")

        usages = [_usage(inp=200, out=20, read=2000, write=300),
                  _usage(inp=150, out=15, read=1500, write=250)]
        tpath = _write_transcript(tmp_path / "transcript.jsonl", usages)

        # Monkeypatch locate_transcript to return our canned path
        monkeypatch.setattr(ab, "locate_transcript", lambda sid: str(tpath))

        task = {"task_id": "t1", "arm": "defect", "catching_rule_id": "R-001"}
        run_result = {"session_id": "fake-uuid", "run_repo": str(tmp_path)}

        out = ab.score_run(task=task, run_result=run_result, variant_name="writ-on",
                           friction_path=None, judge_fn=None, model="claude-opus-4-8")

        expected_cost = token_audit.scorecard(str(tpath), None, "claude-opus-4-8")["measured"]["total_cost"]
        assert out["total_cost"] == pytest.approx(expected_cost)

    def test_score_run_includes_required_fields(self, tmp_path: Path, monkeypatch):
        ab = _ab()
        tpath = _write_transcript(tmp_path / "t.jsonl", [_usage()])
        monkeypatch.setattr(ab, "locate_transcript", lambda sid: str(tpath))

        task = {"task_id": "t2", "arm": "defect", "catching_rule_id": "R-002"}
        run_result = {"session_id": "fake-uuid-2", "run_repo": str(tmp_path)}
        out = ab.score_run(task=task, run_result=run_result, variant_name="writ-off",
                           friction_path=None, judge_fn=None, model="claude-opus-4-8")

        for field in ("task_id", "arm", "variant", "total_cost", "total_usd", "transcript", "defect"):
            assert field in out, f"missing field: {field}"

    def test_score_run_propagates_variant_name(self, tmp_path: Path, monkeypatch):
        ab = _ab()
        tpath = _write_transcript(tmp_path / "t.jsonl", [_usage()])
        monkeypatch.setattr(ab, "locate_transcript", lambda sid: str(tpath))

        task = {"task_id": "t3", "arm": "defect", "catching_rule_id": "R-003"}
        run_result = {"session_id": "fake-uuid-3", "run_repo": str(tmp_path)}
        out = ab.score_run(task=task, run_result=run_result, variant_name="custom-variant",
                           friction_path=None, judge_fn=None, model="claude-opus-4-8")

        assert out["variant"] == "custom-variant"


# ---------------------------------------------------------------------------
# TestDefectCaught
# ---------------------------------------------------------------------------

class TestDefectCaught:
    def _friction_with_gate_denial(self, path: Path, rule_id: str) -> str:
        fpath = path / "friction.log"
        event = {"event": "gate_denial", "rule_id": rule_id, "detail": "blocked"}
        fpath.write_text(json.dumps(event) + "\n")
        return str(fpath)

    def test_gate_denial_naming_rule_returns_caught_gate_signal(self, tmp_path: Path):
        ab = _ab()
        task = {"task_id": "t", "arm": "defect", "catching_rule_id": "R-GATE"}
        friction_path = self._friction_with_gate_denial(tmp_path, "R-GATE")
        result = ab.defect_caught(task, str(tmp_path), "fake_transcript.jsonl",
                                  friction_path, judge_fn=None)
        assert result["caught"] is True
        assert result["signal"] == "gate"

    def test_no_gate_with_stub_judge_returns_caught_judge_signal(self, tmp_path: Path):
        ab = _ab()
        task = {"task_id": "t", "arm": "defect", "catching_rule_id": "R-JUDGE"}
        # friction log exists but has no gate_denial for this rule
        fpath = tmp_path / "friction.log"
        fpath.write_text(json.dumps({"event": "rag_query", "tokens_injected": 100}) + "\n")

        def stub_judge(task, run_repo, transcript_path):
            return {"caught": True, "reason": "defect fixed in diff"}

        result = ab.defect_caught(task, str(tmp_path), "fake_transcript.jsonl",
                                  str(fpath), judge_fn=stub_judge)
        assert result["caught"] is True
        assert result["signal"] == "judge"

    def test_no_gate_no_judge_returns_not_caught_none_signal(self, tmp_path: Path):
        ab = _ab()
        task = {"task_id": "t", "arm": "defect", "catching_rule_id": "R-NONE"}
        result = ab.defect_caught(task, str(tmp_path), "fake_transcript.jsonl",
                                  friction_path=None, judge_fn=None)
        assert result["caught"] is False
        assert result["signal"] == "none"

    def test_gate_denial_unrelated_rule_falls_through_to_judge(self, tmp_path: Path):
        ab = _ab()
        task = {"task_id": "t", "arm": "defect", "catching_rule_id": "R-WANTED"}
        fpath = tmp_path / "friction.log"
        # Gate fired for a DIFFERENT rule
        fpath.write_text(json.dumps({"event": "gate_denial", "rule_id": "R-OTHER"}) + "\n")

        def stub_judge(task, run_repo, transcript_path):
            return {"caught": False, "reason": "defect still present"}

        result = ab.defect_caught(task, str(tmp_path), "fake_transcript.jsonl",
                                  str(fpath), judge_fn=stub_judge)
        # Gate fired but not for R-WANTED; falls through to judge
        assert result["signal"] in ("judge", "none")

    def test_judge_caught_false_propagates_correctly(self, tmp_path: Path):
        ab = _ab()
        task = {"task_id": "t", "arm": "defect", "catching_rule_id": "R-X"}

        def stub_judge_negative(task, run_repo, transcript_path):
            return {"caught": False, "reason": "still broken"}

        result = ab.defect_caught(task, str(tmp_path), "fake_transcript.jsonl",
                                  friction_path=None, judge_fn=stub_judge_negative)
        assert result["caught"] is False
        assert result["signal"] == "judge"


# ---------------------------------------------------------------------------
# TestCleanArm
# ---------------------------------------------------------------------------

class TestCleanArm:
    def test_clean_arm_defect_caught_is_none(self, tmp_path: Path, monkeypatch):
        ab = _ab()
        tpath = _write_transcript(tmp_path / "t.jsonl", [_usage()])
        monkeypatch.setattr(ab, "locate_transcript", lambda sid: str(tpath))

        task = {"task_id": "clean_t", "arm": "clean"}
        run_result = {"session_id": "fake-uuid-clean", "run_repo": str(tmp_path)}
        out = ab.score_run(task=task, run_result=run_result, variant_name="writ-on",
                           friction_path=None, judge_fn=None, model="claude-opus-4-8")

        assert out["defect"]["caught"] is None
        assert out["defect"]["signal"] == "clean-arm"

    def test_clean_arm_no_spurious_gate_reports_clean(self, tmp_path: Path, monkeypatch):
        ab = _ab()
        tpath = _write_transcript(tmp_path / "t.jsonl", [_usage()])
        monkeypatch.setattr(ab, "locate_transcript", lambda sid: str(tpath))

        # Friction log with no gate_denial event
        fpath = tmp_path / "friction.log"
        fpath.write_text(json.dumps({"event": "rag_query", "tokens_injected": 50}) + "\n")

        task = {"task_id": "clean_t", "arm": "clean"}
        run_result = {"session_id": "fake-uuid-clean2", "run_repo": str(tmp_path)}
        out = ab.score_run(task=task, run_result=run_result, variant_name="writ-on",
                           friction_path=str(fpath), judge_fn=None, model="claude-opus-4-8")

        assert out["defect"]["detail"] == "clean"

    def test_clean_arm_spurious_gate_denial_sets_spurious_gate_detail(self, tmp_path: Path, monkeypatch):
        ab = _ab()
        tpath = _write_transcript(tmp_path / "t.jsonl", [_usage()])
        monkeypatch.setattr(ab, "locate_transcript", lambda sid: str(tpath))

        # A gate_denial fired on a clean arm = false positive = spurious_gate
        fpath = tmp_path / "friction.log"
        fpath.write_text(json.dumps({"event": "gate_denial", "rule_id": "R-SPURIOUS"}) + "\n")

        task = {"task_id": "clean_t", "arm": "clean"}
        run_result = {"session_id": "fake-uuid-clean3", "run_repo": str(tmp_path)}
        out = ab.score_run(task=task, run_result=run_result, variant_name="writ-on",
                           friction_path=str(fpath), judge_fn=None, model="claude-opus-4-8")

        assert out["defect"]["caught"] is None
        assert out["defect"]["signal"] == "clean-arm"
        assert out["defect"]["detail"] == "spurious_gate"


# ---------------------------------------------------------------------------
# TestCompareArms
# ---------------------------------------------------------------------------

class TestCompareArms:
    def _make_run(self, arm, variant, total_cost, caught=None):
        return {
            "task_id": "t",
            "arm": arm,
            "variant": variant,
            "total_cost": total_cost,
            "total_usd": total_cost / 1_000_000,
            "defect": {"caught": caught, "signal": "gate" if caught else "none", "detail": ""},
        }

    def test_single_variant_on_defect_arm_returns_incomplete(self):
        ab = _ab()
        runs = [self._make_run("defect", "writ-on", 500.0, caught=True)]
        report = ab.compare_arms(runs, reps_floor=5)
        assert report["verdict"]["status"] == "incomplete"

    def test_insufficient_n_below_reps_floor(self):
        ab = _ab()
        # Two variants but n=1 each, floor=5
        runs = [
            self._make_run("defect", "writ-on", 600.0, caught=True),
            self._make_run("defect", "writ-off", 800.0, caught=False),
        ]
        report = ab.compare_arms(runs, reps_floor=5)
        assert report["verdict"]["status"] == "insufficient_n"

    def test_ok_verdict_when_n_meets_floor_cost_down_caught_held(self):
        ab = _ab()
        reps_floor = 2
        # variant-a (writ-off): higher cost, lower caught rate
        # variant-b (writ-on): lower cost, same or higher caught rate
        # sorted by key => "defect/writ-off" < "defect/writ-on" alphabetically
        # _verdict sorts by key: a=writ-off (higher cost), b=writ-on (lower cost)
        runs = []
        for _ in range(reps_floor):
            runs.append(self._make_run("defect", "writ-off", 900.0, caught=False))
            runs.append(self._make_run("defect", "writ-on", 400.0, caught=True))
        report = ab.compare_arms(runs, reps_floor=reps_floor)
        assert report["verdict"]["status"] == "ok"
        assert report["verdict"]["pass"] is True

    def test_ok_verdict_pass_false_when_cost_not_down(self):
        ab = _ab()
        reps_floor = 2
        # writ-on costs MORE than writ-off -> pass=False
        runs = []
        for _ in range(reps_floor):
            runs.append(self._make_run("defect", "writ-off", 400.0, caught=True))
            runs.append(self._make_run("defect", "writ-on", 900.0, caught=True))
        report = ab.compare_arms(runs, reps_floor=reps_floor)
        assert report["verdict"]["status"] == "ok"
        assert report["verdict"]["pass"] is False

    def test_summary_keys_include_arm_variant_pairs(self):
        ab = _ab()
        runs = [
            self._make_run("defect", "writ-on", 500.0, caught=True),
            self._make_run("clean", "writ-on", 300.0, caught=None),
        ]
        report = ab.compare_arms(runs, reps_floor=5)
        assert "defect/writ-on" in report["summary"]
        assert "clean/writ-on" in report["summary"]

    def test_summary_mean_total_cost_computed_correctly(self):
        ab = _ab()
        runs = [
            self._make_run("defect", "writ-on", 400.0, caught=True),
            self._make_run("defect", "writ-on", 600.0, caught=True),
        ]
        report = ab.compare_arms(runs, reps_floor=5)
        assert report["summary"]["defect/writ-on"]["mean_total_cost"] == pytest.approx(500.0)


# ---------------------------------------------------------------------------
# TestVariants
# ---------------------------------------------------------------------------

class TestVariants:
    def test_writ_off_writes_no_hooks_settings_file(self, tmp_path: Path):
        V = _variants()
        profile = V.materialize_variant("writ-off", str(tmp_path))
        assert profile["settings_file"] is not None
        assert os.path.exists(profile["settings_file"])
        with open(profile["settings_file"]) as f:
            data = json.load(f)
        assert data["disableAllHooks"] is True

    def test_writ_off_sets_no_autostart_env(self, tmp_path: Path):
        V = _variants()
        profile = V.materialize_variant("writ-off", str(tmp_path))
        assert profile["env"]["WRIT_NO_AUTOSTART"] == "1"

    def test_writ_off_sets_isolated_cache_dir_and_friction_log(self, tmp_path: Path):
        V = _variants()
        profile = V.materialize_variant("writ-off", str(tmp_path))
        assert "WRIT_CACHE_DIR" in profile["env"]
        assert "WRIT_FRICTION_LOG" in profile["env"]
        # Both must be under tmp_path
        assert profile["env"]["WRIT_CACHE_DIR"].startswith(str(tmp_path))
        assert profile["env"]["WRIT_FRICTION_LOG"].startswith(str(tmp_path))

    def test_writ_on_settings_file_is_none(self, tmp_path: Path):
        V = _variants()
        profile = V.materialize_variant("writ-on", str(tmp_path))
        assert profile["settings_file"] is None

    def test_writ_on_still_sets_cache_dir_and_friction_log(self, tmp_path: Path):
        V = _variants()
        profile = V.materialize_variant("writ-on", str(tmp_path))
        assert "WRIT_CACHE_DIR" in profile["env"]
        assert "WRIT_FRICTION_LOG" in profile["env"]

    def test_unknown_variant_raises_key_error(self, tmp_path: Path):
        V = _variants()
        with pytest.raises(KeyError):
            V.materialize_variant("nonexistent-variant", str(tmp_path))

    def test_writ_off_cache_dir_is_created_on_disk(self, tmp_path: Path):
        V = _variants()
        profile = V.materialize_variant("writ-off", str(tmp_path))
        assert os.path.isdir(profile["env"]["WRIT_CACHE_DIR"])

    def test_two_calls_with_same_name_produce_consistent_paths(self, tmp_path: Path):
        V = _variants()
        p1 = V.materialize_variant("writ-on", str(tmp_path))
        p2 = V.materialize_variant("writ-on", str(tmp_path))
        assert p1["env"]["WRIT_CACHE_DIR"] == p2["env"]["WRIT_CACHE_DIR"]


# ---------------------------------------------------------------------------
# TestCli
# ---------------------------------------------------------------------------

class TestCli:
    def _make_suite(self, tmp_path: Path) -> Path:
        """Build a minimal 1-task suite dir for the CLI to load."""
        suite = tmp_path / "suite"
        suite.mkdir()
        task_dir = suite / "task_one"
        task_dir.mkdir()
        (task_dir / "task.json").write_text(
            json.dumps({"task_id": "task_one", "arm": "defect", "catching_rule_id": "R-CLI"})
        )
        return suite

    def test_dry_run_exits_0(self, tmp_path: Path):
        from typer.testing import CliRunner
        if SKILL_ROOT not in sys.path:
            sys.path.insert(0, SKILL_ROOT)
        from writ.cli import app

        suite = self._make_suite(tmp_path)
        result = CliRunner().invoke(app, ["efficacy-ab", str(suite)])
        assert result.exit_code == 0

    def test_dry_run_output_contains_dry_run_marker(self, tmp_path: Path):
        from typer.testing import CliRunner
        if SKILL_ROOT not in sys.path:
            sys.path.insert(0, SKILL_ROOT)
        from writ.cli import app

        suite = self._make_suite(tmp_path)
        result = CliRunner().invoke(app, ["efficacy-ab", str(suite)])
        assert "DRY RUN" in result.output

    def test_dry_run_output_mentions_run_count(self, tmp_path: Path):
        """1 task x 2 variants x 1 rep = 2 runs printed in the plan."""
        from typer.testing import CliRunner
        if SKILL_ROOT not in sys.path:
            sys.path.insert(0, SKILL_ROOT)
        from writ.cli import app

        suite = self._make_suite(tmp_path)
        result = CliRunner().invoke(app, ["efficacy-ab", str(suite)])
        assert "2 runs" in result.output

    def test_dry_run_does_not_spawn_claude(self, tmp_path: Path, monkeypatch):
        """The dry-run path must return before run_task(); verify no subprocess.run to claude."""
        import subprocess as _subprocess
        from typer.testing import CliRunner
        if SKILL_ROOT not in sys.path:
            sys.path.insert(0, SKILL_ROOT)
        from writ.cli import app

        spawn_calls = []

        real_run = _subprocess.run
        def guarded_run(cmd, *args, **kwargs):
            if isinstance(cmd, list) and cmd and cmd[0] == "claude":
                spawn_calls.append(cmd)
                raise AssertionError("claude was spawned during dry-run -- must not happen")
            return real_run(cmd, *args, **kwargs)

        monkeypatch.setattr(_subprocess, "run", guarded_run)

        suite = self._make_suite(tmp_path)
        result = CliRunner().invoke(app, ["efficacy-ab", str(suite)])
        assert result.exit_code == 0
        assert len(spawn_calls) == 0

    def test_empty_suite_dir_exits_nonzero(self, tmp_path: Path):
        """An empty suite dir raises EfficacyError -> CLI should exit with non-zero code."""
        from typer.testing import CliRunner
        if SKILL_ROOT not in sys.path:
            sys.path.insert(0, SKILL_ROOT)
        from writ.cli import app

        empty_suite = tmp_path / "empty"
        empty_suite.mkdir()
        result = CliRunner().invoke(app, ["efficacy-ab", str(empty_suite)])
        assert result.exit_code != 0
