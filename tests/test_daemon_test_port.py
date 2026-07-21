"""F4b/option C: the suite runs its own daemon on a dedicated port.

A single mutable daemon shared between the test suite and the interactive session
was the root of a bug class (cache-desync "fails en masse", the F4 friction bleed,
the realign/restore machinery). The suite now forces WRIT_PORT to a dedicated test
port at conftest import and owns that daemon's lifecycle (start_test_daemon /
stop_test_daemon), so the interactive 8765 daemon is structurally never touched.
"""
from __future__ import annotations

import os


def test_suite_forces_dedicated_port() -> None:
    from tests.conftest import TEST_DAEMON_PORT

    assert TEST_DAEMON_PORT != "8765", "the test daemon must not share the interactive port"
    assert os.environ.get("WRIT_PORT") == TEST_DAEMON_PORT, (
        "conftest must force WRIT_PORT to the dedicated test port at import, so every "
        "port resolution (daemon, hooks, _writ_session) targets the test daemon"
    )


def test_port_resolution_is_live() -> None:
    """tests._daemon._port() must read WRIT_PORT live (not freeze it at import), so the
    dedicated port set in conftest is honored regardless of import order."""
    from tests import _daemon

    prev = os.environ.get("WRIT_PORT")
    try:
        os.environ["WRIT_PORT"] = "8123"
        assert _daemon._port() == "8123"
        assert _daemon._health_url() == "http://localhost:8123/health"
    finally:
        if prev is None:
            os.environ.pop("WRIT_PORT", None)
        else:
            os.environ["WRIT_PORT"] = prev
