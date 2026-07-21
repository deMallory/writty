"""RED-phase test skeleton for the systemd rotate-timer install (P2).

Covers `scripts/systemd/writ-logs-rotate.service`, `.timer`, and the
`scripts/install-server-service.sh` wiring that installs/enables them
alongside `writ-server.service`, fail-open when systemd is unavailable.

These are SOURCE-INSPECTION tests only (read_text + substring/regex checks).
`scripts/install-server-service.sh` is deliberately never executed here: it
calls `systemctl --user enable --now writ-server.service` against the REAL
live systemd user session on this machine (per MEMORY.md, writ-server already
runs as a systemd user service), so invoking it -- even "for a test" -- risks
disrupting the actual running daemon. Static content checks are the safe,
correct tool for verifying this file (mirrors the non-executing half of
tests/test_bootstrap.py's TestBootstrapSections).

RED PHASE: `scripts/systemd/` does not exist at all yet, and
`install-server-service.sh` has no rotate-timer wiring. File-presence checks
fail first; content checks that follow are pinned against a plan-approved
shape.

Run ONLY this file (never bare pytest -- that wipes the shared graph):
  .venv/bin/python -m pytest tests/test_logs_rotate_install.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
SYSTEMD_DIR = SCRIPTS_DIR / "systemd"
SERVICE_UNIT = SYSTEMD_DIR / "writ-logs-rotate.service"
TIMER_UNIT = SYSTEMD_DIR / "writ-logs-rotate.timer"
INSTALLER = SCRIPTS_DIR / "install-server-service.sh"


# ===========================================================================
# File presence
# ===========================================================================


class TestFilePresence:
    def test_service_unit_file_exists(self) -> None:
        assert SERVICE_UNIT.exists(), (
            f"{SERVICE_UNIT} must exist (scripts/systemd/writ-logs-rotate.service)"
        )

    def test_timer_unit_file_exists(self) -> None:
        assert TIMER_UNIT.exists(), (
            f"{TIMER_UNIT} must exist (scripts/systemd/writ-logs-rotate.timer)"
        )

    def test_installer_script_exists(self) -> None:
        assert INSTALLER.exists(), f"{INSTALLER} must already exist (modified, not created)"


# ===========================================================================
# writ-logs-rotate.service content
# ===========================================================================


class TestServiceUnitContent:
    @pytest.fixture
    def content(self) -> str:
        assert SERVICE_UNIT.exists(), f"{SERVICE_UNIT} does not exist yet"
        return SERVICE_UNIT.read_text()

    def test_service_declares_service_section(self, content: str) -> None:
        assert "[Service]" in content

    def test_service_is_type_oneshot(self, content: str) -> None:
        assert re.search(r"Type\s*=\s*oneshot", content), (
            f"writ-logs-rotate.service must declare Type=oneshot; got:\n{content}"
        )

    def test_service_execstart_uses_the_writ_bin_placeholder(self, content: str) -> None:
        assert "__WRIT_BIN__" in content, (
            "the ExecStart must carry the __WRIT_BIN__ placeholder substituted "
            "at install time"
        )

    def test_service_execstart_runs_logs_rotate_subcommand(self, content: str) -> None:
        assert re.search(r"ExecStart\s*=\s*__WRIT_BIN__\s+logs\s+rotate\s*$", content, re.M), (
            f"ExecStart must run `__WRIT_BIN__ logs rotate`; got:\n{content}"
        )


# ===========================================================================
# writ-logs-rotate.timer content
# ===========================================================================


class TestTimerUnitContent:
    @pytest.fixture
    def content(self) -> str:
        assert TIMER_UNIT.exists(), f"{TIMER_UNIT} does not exist yet"
        return TIMER_UNIT.read_text()

    @staticmethod
    def _section(content: str, name: str) -> str:
        """Return the body text of a `[name]` INI-style section (systemd unit
        files are ini-shaped), from its header to the next `[`-header or EOF."""
        match = re.search(
            rf"^\[{re.escape(name)}\]\s*$(.*?)(?=^\[|\Z)",
            content,
            re.M | re.S,
        )
        assert match, f"[{name}] section not found in unit content:\n{content}"
        return match.group(1)

    def test_timer_declares_timer_section(self, content: str) -> None:
        assert "[Timer]" in content

    def test_timer_runs_daily(self, content: str) -> None:
        timer_section = self._section(content, "Timer")
        assert re.search(r"OnCalendar\s*=\s*daily", timer_section), (
            f"[Timer] must declare OnCalendar=daily; got:\n{timer_section}"
        )

    def test_timer_is_persistent(self, content: str) -> None:
        timer_section = self._section(content, "Timer")
        assert re.search(r"Persistent\s*=\s*true", timer_section), (
            f"[Timer] must declare Persistent=true (catch a missed run after "
            f"downtime); got:\n{timer_section}"
        )

    def test_timer_wanted_by_timers_target(self, content: str) -> None:
        install_section = self._section(content, "Install")
        assert re.search(r"WantedBy\s*=\s*timers\.target", install_section), (
            f"[Install] must declare WantedBy=timers.target; got:\n{install_section}"
        )


# ===========================================================================
# scripts/install-server-service.sh wiring
# ===========================================================================


class TestInstallerWiring:
    @pytest.fixture
    def content(self) -> str:
        return INSTALLER.read_text()

    def test_installer_references_both_rotate_unit_filenames(self, content: str) -> None:
        assert "writ-logs-rotate.service" in content, (
            "installer must reference writ-logs-rotate.service (to copy it into "
            "$HOME/.config/systemd/user)"
        )
        assert "writ-logs-rotate.timer" in content, (
            "installer must reference writ-logs-rotate.timer (to copy it into "
            "$HOME/.config/systemd/user)"
        )

    def test_installer_guards_the_rotate_install_with_systemctl_presence_check(
        self, content: str,
    ) -> None:
        assert "command -v systemctl" in content, (
            "the rotate-timer install step must be guarded by `command -v systemctl` "
            "so it fail-opens when systemd is unavailable"
        )

    def test_installer_substitutes_writ_bin_placeholder_with_venv_writ(
        self, content: str,
    ) -> None:
        assert "__WRIT_BIN__" in content, (
            "installer must reference the __WRIT_BIN__ placeholder to substitute"
        )
        assert "sed" in content, (
            "installer must use sed (or equivalent) to substitute __WRIT_BIN__"
        )
        assert "$VENV_WRIT" in content, (
            "installer must substitute the placeholder with the already-resolved "
            "$VENV_WRIT path (single source of the venv writ binary)"
        )

    def test_installer_reloads_and_enables_the_rotate_timer(self, content: str) -> None:
        assert re.search(r"daemon-reload", content), (
            "installer must run `systemctl --user daemon-reload` after writing units"
        )
        assert re.search(r"enable\s+--now\s+writ-logs-rotate\.timer", content), (
            "installer must run `systemctl --user enable --now writ-logs-rotate.timer`"
        )

    def test_installer_still_installs_and_enables_writ_server_service(
        self, content: str,
    ) -> None:
        """Regression guard: the new rotate wiring must be ADDITIVE -- the
        pre-existing writ-server.service install/enable step must remain."""
        assert "writ-server.service" in content
        assert re.search(r"enable\s+--now\s+writ-server\.service", content)


# ===========================================================================
# Fail-open behavior when systemd is unavailable
# ===========================================================================


class TestInstallerFailOpen:
    @pytest.fixture
    def content(self) -> str:
        return INSTALLER.read_text()

    def test_installer_prints_a_skip_note_when_systemctl_is_absent(
        self, content: str,
    ) -> None:
        lowered = content.lower()
        assert any(
            phrase in lowered
            for phrase in (
                "systemctl not found",
                "skip",
                "systemd not available",
                "no systemd",
                "systemctl unavailable",
            )
        ), (
            "install-server-service.sh must print a human-readable skip note "
            "(not silently fail) when systemctl is unavailable for the "
            "rotate-timer install step"
        )

    def test_installer_rotate_block_does_not_abort_the_whole_install_on_failure(
        self, content: str,
    ) -> None:
        """The whole script runs under `set -euo pipefail`. A mid-block error
        in the rotate-timer install step (missing loginctl, a failed sed, an
        absent unit dir, etc.) must not propagate and abort the already-working
        writ-server.service install -- some fail-soft idiom must guard it."""
        idx = content.find("command -v systemctl")
        assert idx != -1, "systemctl presence guard not found"
        window = content[idx : idx + 3000]
        assert (
            "|| true" in window or "|| echo" in window or "2>/dev/null" in window
        ), (
            "the rotate-timer install block must fail-soft (e.g. `|| true`) so a "
            "mid-block error under `set -euo pipefail` does not abort the whole "
            "writ-server install; searched near the systemctl guard:\n"
            f"{window}"
        )

    def test_installer_still_uses_strict_mode(self, content: str) -> None:
        """The pre-existing strict-mode header must be untouched by the P2 change."""
        assert "set -euo pipefail" in content
