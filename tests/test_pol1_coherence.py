"""POL-1: remove dead Phase A-D workflow remnants (Wave 4 coherence cleanup).

The Phase A-D / plan-guardian workflow was deleted 2026-05-10, but two remnants survived, both
citing the deleted ENF-GATE-FINAL rule:
  - writ/server.py had a live deny gate ("COMPLETE" path -> [ENF-GATE-FINAL]);
  - bible/playbooks/ held two vestigial prose playbooks citing ENF-GATE-FINAL + 4 other deleted
    rules, read by nothing and superseded by the methodology PBK-* nodes.

Pure filesystem/source assertions (always run; no daemon). RED before the cleanup (server has the
string; playbooks exist), GREEN after.

W2 (server package split, branch refactor/w2-server-split): the server-source assertions read via
writ_server_source() (tests/conftest.py), which is layout-agnostic -- it scans every *.py under
writ/server/ if that directory exists (post-split), else the single writ/server.py file
(pre-split). This keeps the content guarantee ("no dead deny gate, no deleted rule ids") correct
regardless of which file(s) the content physically lives in.
"""
from __future__ import annotations

from pathlib import Path

from tests.conftest import writ_server_source

WRIT_ROOT = Path(__file__).resolve().parent.parent
BIBLE = WRIT_ROOT / "bible"
PLAYBOOKS_DIR = BIBLE / "playbooks"

# Rule ids that belonged to the deleted Phase A-D / plan-guardian workflow.
DELETED_WORKFLOW_RULE_IDS = [
    "ENF-GATE-FINAL",
    "SEC-UNI-001",
    "SEC-UNI-002",
    "ENF-POST-008",
    "ENF-SYS-001",
]


class TestServerDeadDenyRemoved:
    def test_server_does_not_cite_enf_gate_final(self) -> None:
        src = writ_server_source()
        assert "ENF-GATE-FINAL" not in src, (
            "writ.server still cites the deleted ENF-GATE-FINAL rule at runtime"
        )

    def test_server_has_no_complete_path_deny(self) -> None:
        src = writ_server_source()
        assert '"COMPLETE" in file_path' not in src, (
            "writ.server still has the dead Final-gate (COMPLETE-path) deny block"
        )


class TestVestigialPlaybooksRemoved:
    def test_playbooks_dir_gone(self) -> None:
        # The dir may be removed entirely, or simply hold no markdown.
        leftover = list(PLAYBOOKS_DIR.glob("*.md")) if PLAYBOOKS_DIR.exists() else []
        assert not leftover, (
            f"bible/playbooks/ still holds vestigial files: {[p.name for p in leftover]}"
        )


class TestCorpusCleanOfDeletedRuleIds:
    def test_no_deleted_rule_ids_under_bible(self) -> None:
        offenders: list[str] = []
        for md in BIBLE.rglob("*.md"):
            text = md.read_text(encoding="utf-8")
            for rid in DELETED_WORKFLOW_RULE_IDS:
                if rid in text:
                    offenders.append(f"{md.relative_to(WRIT_ROOT)} -> {rid}")
        assert not offenders, (
            "deleted-workflow rule ids still referenced under bible/:\n  " + "\n  ".join(offenders)
        )

    def test_no_deleted_rule_ids_in_server(self) -> None:
        src = writ_server_source()
        present = [rid for rid in DELETED_WORKFLOW_RULE_IDS if rid in src]
        assert not present, f"writ.server still references deleted rule ids: {present}"
