"""Audit #7: `writ validate` must fail (exit 1) on methodology orphans.

run_all_checks computed exit_code from only :Rule orphans (the `orphans` key). A
disconnected methodology node (Skill/Playbook/SubagentRole/...) -- exactly the orphan
class that upsert-only ingest leaves behind when a node is renamed or deleted -- showed
up in `orphans_all_labels` but never affected the exit code, so CI/validate read clean.

Pure unit test: mock every detector so no Neo4j is needed; assert that a non-empty
orphans_all_labels flips exit_code to 1, and that an all-clean run stays 0.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from writ.graph.integrity import IntegrityChecker


def _checker_with_findings(*, orphans_all_labels, counts):
    """Build a checker whose every detector is stubbed empty except the all-labels
    orphan scan, which returns the supplied (list, counts)."""
    checker = IntegrityChecker(None, None)  # driver unused: all detectors patched
    patches = {
        "detect_conflicts": AsyncMock(return_value=[]),
        "detect_orphans": AsyncMock(return_value=[]),
        "detect_stale": AsyncMock(return_value=[]),
        "detect_redundant": AsyncMock(return_value=[]),
        "check_unreviewed_count": AsyncMock(return_value=None),
        "detect_frequency_stale": AsyncMock(return_value=[]),
        "detect_graduation_flags": AsyncMock(return_value=[]),
        "detect_dangling_dispatched_roles": AsyncMock(return_value=[]),
        "detect_orphans_all_labels": AsyncMock(return_value=(orphans_all_labels, counts)),
    }
    return checker, patches


async def _run(checker, patches):
    cms = [patch.object(checker, name, mock) for name, mock in patches.items()]
    for cm in cms:
        cm.start()
    try:
        return await checker.run_all_checks(skip_redundancy=True)
    finally:
        for cm in cms:
            cm.stop()


@pytest.mark.asyncio
async def test_methodology_orphan_flips_exit_code() -> None:
    checker, patches = _checker_with_findings(
        orphans_all_labels=[{"type": "Skill", "id": "SKL-ORPHAN-001"}],
        counts={"Skill": 1},
    )
    findings = await _run(checker, patches)
    assert findings["exit_code"] == 1, (
        "a disconnected methodology node must fail `writ validate`"
    )


@pytest.mark.asyncio
async def test_all_clean_stays_exit_0() -> None:
    checker, patches = _checker_with_findings(orphans_all_labels=[], counts={})
    findings = await _run(checker, patches)
    assert findings["exit_code"] == 0
