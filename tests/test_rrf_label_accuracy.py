"""Audit #8: the ranking stage is mislabeled "RRF".

normalize_ranks is plain reciprocal rank (1/(rank+1)) followed by weighted linear
fusion in compute_score -- NOT classical Reciprocal Rank Fusion (which uses 1/(k+rank)
with k~60). normalize_ranks' own docstring is honest about this, but ranking.py's module
docstring, pipeline.py's stage comment, and authoring.py all called it "RRF".

Guard: those code files must not use the bare acronym "RRF", and any "Reciprocal Rank
Fusion" mention must be a disclaimer (the line also says "not"), never a bare claim.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FILES = [
    REPO / "writ" / "retrieval" / "ranking.py",
    REPO / "writ" / "retrieval" / "pipeline.py",
    REPO / "writ" / "authoring.py",
]


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_no_bare_rrf_acronym(path: Path) -> None:
    src = path.read_text()
    assert "RRF" not in src, (
        f"{path.name} uses the bare acronym 'RRF' for a non-RRF algorithm "
        "(plain reciprocal rank + weighted linear fusion)"
    )


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_reciprocal_rank_fusion_only_as_disclaimer(path: Path) -> None:
    # Whitespace-collapsed so a disclaimer that wraps across lines ("...not\n
    # classical Reciprocal Rank Fusion...") is still recognized.
    flat = re.sub(r"\s+", " ", path.read_text())
    for m in re.finditer(r"reciprocal rank fusion", flat, re.IGNORECASE):
        window = flat[max(0, m.start() - 40):m.start()].lower()
        assert "not" in window, (
            f"{path.name} claims 'Reciprocal Rank Fusion' without a disclaimer; the "
            f"algorithm is reciprocal rank + weighted linear fusion. Context: "
            f"...{flat[max(0, m.start() - 40):m.end() + 10]}..."
        )
