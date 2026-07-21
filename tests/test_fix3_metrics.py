"""FIX-3: self-reporting metric bugs.

#5 -- /health silently reported rule_count:0 over a DB/index split (a FIX-2 stale-daemon
symptom). count_rules() is correct; FIX-3 adds a self-detecting `degraded` status so the
split (index warm, but Neo4j count 0) can never again read as a bland "healthy".

#4 -- the integrity staleness query referenced `last_seen`, a telemetry field never set on a
fresh corpus (0/280), causing a Neo4j UnknownPropertyKey warning + a useless all-rules "stale"
dump. The clause is dead (gated behind times_seen==0). FIX-3 drops it.
"""
from __future__ import annotations

import asyncio
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from tests.conftest import writ_server_source

SKILL = Path(__file__).resolve().parent.parent
CLI_PY = SKILL / "writ" / "cli.py"
VALIDATE_REPORT_PY = SKILL / "writ" / "graph" / "validate_report.py"


def _integrity_source() -> str:
    """integrity is a single file OR (Wave-2 split) a writ/graph/integrity/
    package; read whichever exists so this source-scan is layout-agnostic."""
    integ_dir = SKILL / "writ" / "graph" / "integrity"
    if integ_dir.is_dir():
        return "\n".join(p.read_text() for p in sorted(integ_dir.glob("*.py")))
    return (SKILL / "writ" / "graph" / "integrity.py").read_text()


def _health():
    try:
        from tests._daemon import _health_url

        with urllib.request.urlopen(_health_url(), timeout=2) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, OSError, ValueError):
        return None


class TestHealthStatusHelper:
    def test_degraded_when_warm_but_zero(self) -> None:
        from writ.server import _health_status
        assert _health_status(rule_count=0, index_warm=True) == "degraded"

    def test_healthy_when_warm_and_rules(self) -> None:
        from writ.server import _health_status
        assert _health_status(280, True) == "healthy"

    def test_healthy_when_cold(self) -> None:
        from writ.server import _health_status
        assert _health_status(0, False) == "healthy"
        assert _health_status(280, False) == "healthy"


class TestHealthLive:
    def test_loaded_daemon_reports_healthy_not_degraded(self) -> None:
        h = _health()
        if h is None:
            pytest.skip("test-port daemon unreachable")
        if h.get("rule_count", 0) == 0:
            pytest.skip("daemon reports 0 rules -> degraded by design; not the loaded case")
        assert h.get("status") == "healthy", f"loaded daemon must be healthy; got {h.get('status')}"

    def test_server_health_has_degraded_path(self) -> None:
        # Feature marker: /health must implement the degraded status (warm + 0 rules).
        assert "degraded" in writ_server_source(), \
            "server /health must implement a 'degraded' status for the DB/index split"


class TestStalenessQueryNoLastSeen:
    def test_detect_frequency_stale_drops_last_seen(self) -> None:
        src = _integrity_source()
        m = re.search(r"def detect_frequency_stale.*?(?=\n    async def |\n    def )", src, re.S)
        assert m, "detect_frequency_stale not found"
        assert "last_seen" not in m.group(0), \
            "detect_frequency_stale must not reference the never-populated last_seen (kills Neo4j warning)"

    def test_renderer_drops_last_seen(self) -> None:
        # The frequency-stale renderer moved from cli.py to
        # writ/graph/validate_report.py (Wave 2 Cycle 3 extraction); the
        # source-text guard follows it to its new home.
        src = VALIDATE_REPORT_PY.read_text()
        idx = src.find("Frequency stale")
        assert idx != -1, "Frequency-stale renderer not found"
        assert "last_seen" not in src[idx:idx + 400], \
            "the Frequency-stale renderer must not print the meaningless last_seen"


class TestStalenessLive:
    def test_returns_rule_ids_without_last_seen(self) -> None:
        try:
            from writ.config import get_neo4j_password, get_neo4j_uri, get_neo4j_user
            from writ.graph.db import Neo4jConnection
            from writ.graph.integrity import IntegrityChecker
        except Exception as e:  # pragma: no cover
            pytest.skip(f"imports unavailable: {e}")

        async def _run():
            db = Neo4jConnection(get_neo4j_uri(), get_neo4j_user(), get_neo4j_password())
            try:
                return await IntegrityChecker(db._driver, db._database).detect_frequency_stale()
            finally:
                await db.close()

        try:
            rows = asyncio.run(_run())
        except Exception as e:
            pytest.skip(f"Neo4j unavailable: {e}")
        assert isinstance(rows, list)
        for row in rows[:5]:
            assert "rule_id" in row
            assert "last_seen" not in row, "frequency-stale rows must not carry last_seen after FIX-3"
