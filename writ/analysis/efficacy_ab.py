"""P0.5: writ efficacy-ab -- the NUMERATOR harness (WRIT-TOKEN-BLUEPRINT.md).

Runs real agentic Claude Code sessions (claude -p --output-format json) under two variants,
scores TOTAL cost via token_audit.scorecard() + a defect-caught signal (mechanical gate-fired
FIRST, LLM-judge fallback). The cost half is reused, not re-implemented. Spawning real sessions
is gated behind the CLI --live flag; this module's pure functions are unit-tested with canned data.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
from collections import defaultdict

from writ.analysis.jsonl import read_jsonl


class EfficacyError(Exception):
    """Harness failure (run/locate/judge). CLI maps it to exit 3."""


def load_suite(suite_dir: str) -> list[dict]:
    """Read each suite_dir/*/task.json, attach task['dir'] = its dir, return the task list."""
    tasks = []
    for manifest in sorted(glob.glob(os.path.join(suite_dir, "*", "task.json"))):
        with open(manifest) as fh:
            t = json.load(fh)
        t["dir"] = os.path.dirname(manifest)
        tasks.append(t)
    if not tasks:
        raise EfficacyError(f"no tasks found under {suite_dir!r}")
    return tasks


def locate_transcript(session_id: str) -> str:
    """Glob the transcript by session_id across ALL project slugs. Never reconstruct the slug
    (the dotted-home/.claude path produces a fragile double-hyphen slug). session_id is a UUID,
    so exactly one match is expected; 0 or >1 fails loud."""
    home = os.path.expanduser("~")
    matches = glob.glob(os.path.join(home, ".claude", "projects", "*", f"{session_id}.jsonl"))
    if len(matches) != 1:
        raise EfficacyError(
            f"expected exactly 1 transcript for session {session_id!r}, found {len(matches)}")
    return matches[0]


def run_task(task: dict, variant: dict, workdir: str, timeout: int = 900) -> dict:
    """Copy the frozen task repo into workdir, run headless claude under the variant's env/settings,
    return the parsed result JSON essentials. SPAWNS real claude (Phase-2 only)."""
    run_repo = os.path.join(workdir, "repo")
    shutil.copytree(os.path.join(task["dir"], "repo"), run_repo)
    # Seed a baseline commit on the throwaway copy so make_judge can `git diff` the agent's edits.
    # The committed suite seed is plain files (no nested .git); the run-time copy is the git repo.
    subprocess.run(["git", "init", "-q"], cwd=run_repo, check=False)
    subprocess.run(["git", "add", "-A"], cwd=run_repo, check=False)
    subprocess.run(["git", "-c", "user.email=ab@writ", "-c", "user.name=writ-ab",
                    "commit", "-q", "-m", "seed"], cwd=run_repo, check=False)
    with open(os.path.join(task["dir"], task.get("prompt_file", "prompt.md"))) as fh:
        prompt = fh.read()
    env = dict(os.environ)
    env.update(variant.get("env", {}))
    cmd = ["claude", "-p", "--output-format", "json", "--dangerously-skip-permissions"]
    if variant.get("settings_file"):
        cmd += ["--settings", variant["settings_file"]]
    cmd += [prompt]
    proc = subprocess.run(cmd, cwd=run_repo, env=env, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise EfficacyError(f"claude run failed (exit {proc.returncode}): {proc.stderr[:500]}")
    result = json.loads(proc.stdout)
    sid = result.get("session_id")
    if not sid:
        raise EfficacyError("result JSON missing session_id")
    return {"session_id": sid, "result_usd": result.get("total_cost_usd"), "run_repo": run_repo}


def defect_caught(task: dict, run_repo: str, transcript_path: str,
                  friction_path: str | None, judge_fn=None) -> dict:
    """Numerator scorer for a DEFECT task. Mechanical gate-fired signal FIRST (a gate denial naming
    the catching rule is binary, interpretation-free), LLM-judge fallback only for ambiguity. The
    deciding signal is labeled so a human can audit which one decided."""
    rule_id = task.get("catching_rule_id")
    if friction_path and rule_id and os.path.exists(friction_path):
        for e in read_jsonl(friction_path):
            if e.get("event") in ("gate_denial", "write_blocked", "pre_write_deny") \
               and rule_id in json.dumps(e):
                return {"caught": True, "signal": "gate", "detail": e.get("event")}
    if judge_fn is None:
        return {"caught": False, "signal": "none", "detail": "no gate denial; no judge supplied"}
    verdict = judge_fn(task, run_repo, transcript_path)
    return {"caught": bool(verdict.get("caught")), "signal": "judge",
            "detail": verdict.get("reason", "")}


def score_run(task: dict, run_result: dict, variant_name: str,
              friction_path: str | None, judge_fn=None, model: str = "claude-opus-4-8") -> dict:
    """Score one run: TOTAL cost via the reused scorecard() + defect/clean outcome."""
    from writ.analysis import token_audit
    tpath = locate_transcript(run_result["session_id"])
    card = token_audit.scorecard(tpath, friction_path, model)
    out = {"task_id": task["task_id"], "arm": task["arm"], "variant": variant_name,
           "total_cost": card["measured"]["total_cost"], "total_usd": card["measured"]["total_usd"],
           "result_usd": run_result.get("result_usd"), "transcript": tpath}
    if task["arm"] == "defect":
        out["defect"] = defect_caught(task, run_result.get("run_repo", ""), tpath,
                                      friction_path, judge_fn)
    else:  # clean arm: no planted defect -> cost-of-presence; a gate firing here is a FALSE positive
        spurious = bool(friction_path and os.path.exists(friction_path)
                        and any('"event": "gate_denial"' in ln for ln in open(friction_path)))
        out["defect"] = {"caught": None, "signal": "clean-arm",
                         "detail": "spurious_gate" if spurious else "clean"}
    return out


def compare_arms(scored_runs: list[dict], reps_floor: int = 5) -> dict:
    """Aggregate per (arm, variant): mean total cost + defect-caught rate. Emits a verdict SCAFFOLD
    that REFUSES a lever pass/fail until n >= reps_floor (non-determinism guard). A lever passes only
    if cost DROPS and defect-caught HOLDS."""
    groups: dict = defaultdict(list)
    for r in scored_runs:
        groups[(r["arm"], r["variant"])].append(r)
    summary = {}
    for (arm, variant), runs in groups.items():
        n = len(runs)
        caught = [x["defect"]["caught"] for x in runs if x["defect"]["caught"] is not None]
        summary[f"{arm}/{variant}"] = {
            "n": n,
            "mean_total_cost": sum(x["total_cost"] for x in runs) / n,
            "defect_caught_rate": (sum(1 for c in caught if c) / len(caught)) if caught else None,
        }
    return {"summary": summary, "verdict": _verdict(summary, reps_floor)}


def _verdict(summary: dict, reps_floor: int) -> dict:
    """Defect-arm verdict: compare the two variants. Guard insufficient_n loudly."""
    defect = {k: v for k, v in summary.items() if k.startswith("defect/")}
    if len(defect) < 2:
        return {"status": "incomplete", "reason": "need two variants on the defect arm"}
    if any(v["n"] < reps_floor for v in defect.values()):
        return {"status": "insufficient_n", "reason": f"reps < floor={reps_floor}; single draw"}
    (na, a), (nb, b) = sorted(defect.items())
    cost_down = b["mean_total_cost"] < a["mean_total_cost"]
    caught_held = (b["defect_caught_rate"] or 0) >= (a["defect_caught_rate"] or 0)
    return {"status": "ok", "pass": bool(cost_down and caught_held),
            "cost_down": cost_down, "caught_held": caught_held}


def make_judge(model: str = "claude-opus-4-8"):
    """Build an LLM-judge fn: a single temperature-0 strict-JSON `claude -p` over the final repo
    diff, classifying whether the planted defect was caught. Reuses llm.py prompt discipline.
    SPAWNS claude (Phase-2 spend). Returns a fn(task, run_repo, transcript)->{caught, reason}."""
    def judge(task: dict, run_repo: str, transcript_path: str) -> dict:
        diff = subprocess.run(["git", "-C", run_repo, "diff"], capture_output=True, text=True).stdout
        prompt = (
            "You are a strict code-defect judge. The repo had this planted defect: "
            f"{task.get('defect_signature','(unspecified)')} (rule {task.get('catching_rule_id')}).\n"
            "Below is the agent's final git diff. Reply ONLY strict JSON "
            '{"caught": true|false, "reason": "<one line>"}. '
            "caught=true iff the agent removed/fixed/flagged the defect; false if it persists.\n\n"
            f"DIFF:\n{diff[:8000]}")
        proc = subprocess.run(["claude", "-p", "--output-format", "json", prompt],
                              capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            raise EfficacyError(f"judge failed: {proc.stderr[:300]}")
        text = json.loads(proc.stdout).get("result", "")
        start, end = text.find("{"), text.rfind("}")
        return json.loads(text[start:end + 1])
    return judge


def render_text(report: dict) -> str:
    lines = ["EFFICACY A/B (numerator) -- per (arm/variant):"]
    for k, v in report["summary"].items():
        rate = "n/a" if v["defect_caught_rate"] is None else f"{v['defect_caught_rate']:.2f}"
        lines.append(f"  {k:24s} n={v['n']} mean_cost={v['mean_total_cost']:>12,.0f} "
                     f"defect_caught={rate}")
    lines.append(f"VERDICT: {report['verdict']}")
    return "\n".join(lines)
