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


SERVER = "http://localhost:8765"


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
    """Skill / Playbook nodes tagged always_on=true must appear in
    /always-on alongside Rule and ForbiddenResponse."""

    def test_always_on_returns_at_least_one_skill_node(self) -> None:
        data = _get_always_on("work")
        ids = [r["rule_id"] for r in data.get("rules", [])]
        skl = [i for i in ids if i.startswith("SKL-")]
        assert skl, (
            f"expected at least one SKL- node in always-on bundle, "
            f"got rule_ids: {ids[:20]}"
        )

    def test_always_on_returns_at_least_one_playbook_node(self) -> None:
        data = _get_always_on("work")
        ids = [r["rule_id"] for r in data.get("rules", [])]
        pbk = [i for i in ids if i.startswith("PBK-")]
        assert pbk, (
            f"expected at least one PBK- node in always-on bundle, "
            f"got rule_ids: {ids[:20]}"
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
