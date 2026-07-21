"""always-on bundle: extend endpoint to surface methodology nodes.

The /always-on endpoint historically queried only Rule (where
always_on=true) and ALL ForbiddenResponse nodes. After Phase 6
methodology absorption, Skill/Playbook nodes can carry meaningful
always_on=true semantics (skills the agent should keep in mind
every turn). This test pins:

1. Skill nodes with always_on=true appear in /always-on?mode=work.
2. Playbook nodes with always_on=true appear in /always-on?mode=work.
3. Untagged Skill/Playbook nodes (always_on=false or unset) do NOT
   appear -- only the tagged ones surface.
4. The mode-scoping rule (process-domain excluded outside work mode)
   continues to apply to the new types.

These tests run against the LIVE server so the endpoint reload
after restart is verified end-to-end. They skip cleanly if the
server is not reachable.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from tests._daemon import _port


SERVER = f"http://localhost:{_port()}"


def _get_always_on(mode: str | None = "work") -> dict:
    url = f"{SERVER}/always-on"
    if mode is not None:
        url += f"?mode={mode}"
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, OSError) as e:
        pytest.skip(f"Writ server unreachable: {e}")


class TestAlwaysOnSkillPlaybookSurfaced:
    """1.7 CUTOVER (D1): /always-on is now RULES + ForbiddenResponse ONLY.
    Methodology (Skill/Playbook/Technique) moved entirely to CHANNEL 2
    (/methodology-companion), so it must NOT appear in /always-on anymore."""

    def test_no_methodology_in_always_on_after_cutover(self) -> None:
        data = _get_always_on("work")
        ids = [r["rule_id"] for r in data.get("rules", [])]
        methodology = [
            i for i in ids
            if i.startswith("SKL-") or i.startswith("PBK-") or i.startswith("TEC-")
        ]
        assert not methodology, (
            f"methodology leaked into /always-on after the 1.7 cutover "
            f"(it belongs to /methodology-companion): {methodology}"
        )

    def test_always_on_includes_existing_rule_and_frb_nodes(self) -> None:
        """Don't regress the existing Rule + ForbiddenResponse path."""
        data = _get_always_on("work")
        ids = [r["rule_id"] for r in data.get("rules", [])]
        assert any(i.startswith("ENF-") for i in ids), (
            f"ENF- rules missing from always-on: {ids}"
        )
        assert any(i.startswith("FRB-") for i in ids), (
            f"FRB- nodes missing from always-on: {ids}"
        )

    def test_total_tokens_under_cap(self) -> None:
        data = _get_always_on("work")
        cap = data.get("cap", 5000)
        total = data.get("total_tokens", 0)
        assert total < cap, (
            f"always-on bundle blew the cap: total_tokens={total} cap={cap}"
        )


class TestAlwaysOnModeScoping:
    """The mode filter on /always-on excludes process-domain rules
    when mode != work. New Skill/Playbook nodes whose domain is
    process must be excluded the same way."""

    def test_process_domain_skills_excluded_in_conversation_mode(
        self,
    ) -> None:
        data = _get_always_on("conversation")
        ids = [r["rule_id"] for r in data.get("rules", [])]
        # SKL-PROC-* are process-domain; should be filtered out in
        # conversation mode (agent is not generating code).
        proc_skills = [i for i in ids if i.startswith("SKL-PROC-")]
        assert not proc_skills, (
            f"process-domain SKL- nodes leaked into conversation mode: "
            f"{proc_skills}"
        )


# Increment 1: debug mode must receive process-domain always-on doctrine.
# The /always-on filter (server.py:1108-1112) strips ALL domain==process nodes
# in non-work modes, which silently drops ENF-PROC-DEBUG-001 (always_on=true,
# domain=process) in debug mode -- the one mode it is authored for. The fix
# narrows the strip to {conversation, review, universal} via
# _ALWAYS_ON_PROCESS_MODES = {"work", "debug"}.
#
# Empirical baseline at skeleton-authoring time (live server):
#   work=11 rules (ENF-PROC-DEBUG-001 present), debug=3 (absent),
#   conversation=3 (absent), review=3 (absent).
# Expected post-fix: debug includes ENF-PROC-DEBUG-001; conversation/review
# remain unchanged (still exclude process-domain).
DEBUG_DOCTRINE_RULE_ID = "ENF-PROC-DEBUG-001"


class TestDebugModeProcessDomainInclusion:
    """Increment 1 contract: process-domain always-on rules reach debug mode,
    while conversation/review remain blast-radius-pinned to the old behavior."""

    def test_process_domain_rule_included_in_debug_mode(self) -> None:
        """RED before the fix, GREEN after: the debug doctrine surfaces in debug."""
        data = _get_always_on("debug")
        ids = [r["rule_id"] for r in data.get("rules", [])]
        assert DEBUG_DOCTRINE_RULE_ID in ids, (
            f"{DEBUG_DOCTRINE_RULE_ID} (always_on=true, domain=process) must "
            f"appear in debug-mode always-on bundle after the filter fix; "
            f"got rule_ids: {ids}"
        )

    def test_process_domain_included_in_work_mode_unchanged(self) -> None:
        """Baseline that must stay GREEN: work mode keeps process-domain rules."""
        data = _get_always_on("work")
        ids = [r["rule_id"] for r in data.get("rules", [])]
        assert DEBUG_DOCTRINE_RULE_ID in ids, (
            f"{DEBUG_DOCTRINE_RULE_ID} must remain in work-mode always-on "
            f"(work was never filtered); got rule_ids: {ids}"
        )

    def test_process_domain_still_excluded_in_review_mode(self) -> None:
        """Blast-radius pin: review must STILL exclude process-domain nodes.

        The fix adds only 'debug' to _ALWAYS_ON_PROCESS_MODES, never 'review'.
        """
        data = _get_always_on("review")
        ids = [r["rule_id"] for r in data.get("rules", [])]
        assert DEBUG_DOCTRINE_RULE_ID not in ids, (
            f"{DEBUG_DOCTRINE_RULE_ID} leaked into review mode -- the filter "
            f"fix must be scoped to debug only; got rule_ids: {ids}"
        )
        proc_skills = [i for i in ids if i.startswith("SKL-PROC-")]
        assert not proc_skills, (
            f"process-domain SKL- nodes leaked into review mode: {proc_skills}"
        )

    def test_process_domain_still_excluded_in_conversation_mode(self) -> None:
        """Blast-radius pin: conversation must STILL exclude process-domain."""
        data = _get_always_on("conversation")
        ids = [r["rule_id"] for r in data.get("rules", [])]
        assert DEBUG_DOCTRINE_RULE_ID not in ids, (
            f"{DEBUG_DOCTRINE_RULE_ID} leaked into conversation mode; "
            f"got rule_ids: {ids}"
        )
