"""Default-mode fallback: a prompt that classifies as neither work nor investigate
defaults an unset session to the configured mode (conversation), without ever
touching a session that already has a mode and without feeding the re-route arm.

Harness copied from test_mode_autoroute.py TestHookAutoRouteBehavior: run the real
UserPromptSubmit hook (hooks/scripts/writ-rag-inject.sh) with a dead daemon port so
every read is the file-direct fallback, then assert the session cache's mode via
bin/lib/writ-session.py `mode get`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

HOOK = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), os.pardir, "hooks", "scripts", "writ-rag-inject.sh"
    )
)
HELPER = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, "bin", "lib", "writ-session.py")
)

# Classifies as neither work nor investigate (it is a greeting), so the classifier
# returns nothing and the default-mode fallback is the only thing that can act.
NEUTRAL_PROMPT = "hello, i'm checking out our new UI, looks super good"


class TestHookDefaultMode:
    def _run(
        self,
        tmp_path,
        prompt,
        seed_mode=None,
        sid="defaultmode-e2e",
        stdin_extra=None,
        default_mode_env=None,
    ):
        env = os.environ.copy()
        env["WRIT_CACHE_DIR"] = str(tmp_path)
        env["WRIT_PORT"] = (
            "59997"  # dead port -> curl fails fast -> file-direct fallback
        )
        env["WRIT_HOST"] = "localhost"
        env["WRIT_FRICTION_LOG"] = str(tmp_path / "friction.log")
        env["WRIT_NO_AUTOSTART"] = (
            "1"  # do not let the hook spawn a daemon on the dead port
        )
        # The env layer is under test only when the caller names a value; otherwise
        # the file/built-in default is what runs.
        if default_mode_env is None:
            env.pop("WRIT_DEFAULT_MODE", None)
        else:
            env["WRIT_DEFAULT_MODE"] = default_mode_env
        # cwd must stay inside tmp_path: `mode set` stamps cache["project_root"] from
        # the process cwd, and clearing gate state deletes <project_root>/.claude/gates/
        # *.approved, so inheriting pytest's cwd deleted the REAL repo's approval files.
        sandbox = tmp_path / "sandbox"
        (sandbox / ".claude" / "gates").mkdir(parents=True, exist_ok=True)
        (sandbox / ".git").mkdir(exist_ok=True)
        if seed_mode:
            subprocess.run(
                [sys.executable, HELPER, "mode", "set", seed_mode, sid],
                env=env,
                check=True,
                capture_output=True,
                text=True,
                cwd=str(sandbox),
            )
        payload = {"session_id": sid, "prompt": prompt}
        if stdin_extra:
            payload.update(stdin_extra)
        r = subprocess.run(
            ["bash", HOOK],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
            cwd=str(sandbox),
            check=False,
        )
        mode = subprocess.run(
            [sys.executable, HELPER, "mode", "get", sid],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        return r, mode

    def test_neutral_prompt_defaults_an_unset_session_to_conversation(self, tmp_path):
        r, mode = self._run(tmp_path, NEUTRAL_PROMPT)
        assert r.returncode == 0, r.stderr
        assert mode == "conversation", (
            f"expected the default conversation, got {mode!r}"
        )
        assert "configured default" in r.stdout

    def test_the_mode_directive_banner_is_replaced_by_the_default(self, tmp_path):
        r, mode = self._run(tmp_path, NEUTRAL_PROMPT)
        assert r.returncode == 0, r.stderr
        assert mode == "conversation"
        assert "[Writ: set mode before proceeding]" not in r.stdout

    def test_explicitly_set_mode_is_never_overridden(self, tmp_path):
        r, mode = self._run(tmp_path, NEUTRAL_PROMPT, seed_mode="work")
        assert r.returncode == 0, r.stderr
        assert mode == "work", (
            f"a hand-set work mode must survive a neutral prompt, got {mode!r}"
        )
        assert "configured default" not in r.stdout

    def test_a_later_work_prompt_reroutes_a_defaulted_session(self, tmp_path):
        r1, mode1 = self._run(tmp_path, NEUTRAL_PROMPT)
        assert r1.returncode == 0, r1.stderr
        assert mode1 == "conversation"
        r2, mode2 = self._run(
            tmp_path, "implement the export endpoint from the approved plan"
        )
        assert r2.returncode == 0, r2.stderr
        assert mode2 == "work", (
            f"a defaulted session must still re-route to work, got {mode2!r}"
        )

    def test_a_neutral_prompt_does_not_demote_an_auto_investigate_session(
        self, tmp_path
    ):
        r1, mode1 = self._run(tmp_path, "audit the codebase for security issues")
        assert r1.returncode == 0, r1.stderr
        assert mode1 == "investigate"
        r2, mode2 = self._run(tmp_path, NEUTRAL_PROMPT)
        assert r2.returncode == 0, r2.stderr
        assert mode2 == "investigate", "the default must not flow into the re-route arm"

    def test_a_subagent_prompt_never_gets_the_default(self, tmp_path):
        r, mode = self._run(
            tmp_path,
            NEUTRAL_PROMPT,
            sid="defaultmode-subagent",
            stdin_extra={"agent_id": "subagent-1"},
        )
        assert r.returncode == 0, r.stderr
        assert mode == "", (
            "a subagent inherits its parent's mode; the default must not apply"
        )

    def test_env_override_selects_the_default_end_to_end(self, tmp_path):
        r, mode = self._run(tmp_path, NEUTRAL_PROMPT, default_mode_env="review")
        assert r.returncode == 0, r.stderr
        assert mode == "review", (
            f"WRIT_DEFAULT_MODE=review must default the session, got {mode!r}"
        )

    def test_a_second_neutral_prompt_on_a_defaulted_session_is_a_noop(self, tmp_path):
        _, mode1 = self._run(tmp_path, NEUTRAL_PROMPT)
        assert mode1 == "conversation"
        r2, mode2 = self._run(tmp_path, NEUTRAL_PROMPT)
        assert r2.returncode == 0, r2.stderr
        assert mode2 == "conversation", (
            f"the fallback must be idempotent, got {mode2!r}"
        )
        assert "configured default" not in r2.stdout
