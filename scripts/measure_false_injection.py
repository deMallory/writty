"""Offline false-injection diagnostic (KG #85). No API, read-only, no graph writes.

Measures whether the retriever can tell when NO rule is relevant, using the
negatives in tests/fixtures/ground_truth_negatives.json vs the real gold set in
tests/fixtures/ground_truth_queries.json.

Finding (2026-07-17): the pipeline's NORMALIZED top-1 score does NOT separate
off-domain negatives from real queries (rank-relative, so the top result is
always confident) -> ~100% false injection, un-gateable by that score. The RAW
vector cosine (relevance-absolute) DOES separate them, so a CRAG abstention gate
(S4) is feasible but must gate on raw cosine, not the normalized score. This
script prints both distributions + a threshold sweep so the operating point is
reproducible. It is a diagnostic, not a pass/fail gate (the abstain threshold is
an S4 product decision).

Run: PYTHONHASHSEED=0 .venv/bin/python scripts/measure_false_injection.py
"""
import asyncio
import json
import statistics
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from writ.config import get_neo4j_uri, get_neo4j_user, get_neo4j_password
from writ.graph.db import Neo4jConnection
from writ.retrieval.pipeline import build_pipeline

_ROOT = Path(__file__).resolve().parent.parent
GOLD = json.loads((_ROOT / "tests/fixtures/ground_truth_queries.json").read_text())["queries"]
NEG = json.loads((_ROOT / "tests/fixtures/ground_truth_negatives.json").read_text())["negatives"]


def _summary(xs: list[float]) -> str:
    xs = sorted(xs)
    n = len(xs)
    return (f"min={xs[0]:.3f} p10={xs[max(0, int(0.1 * n))]:.3f} "
            f"med={statistics.median(xs):.3f} p90={xs[int(0.9 * n)]:.3f} max={xs[-1]:.3f}")


def _norm_top1(pipe, q: str) -> float:
    rules = pipe.query(q)["rules"]
    return rules[0]["score"] if rules else 0.0


def _raw_cosine_top1(pipe, q: str) -> float:
    vec = np.asarray(pipe._model.encode(q), dtype=np.float32)
    res = pipe._vector.search(vec.tolist(), 5)
    return res[0].score if res else 0.0  # score = 1 - cosine_distance = raw cosine sim


async def main() -> None:
    db = Neo4jConnection(get_neo4j_uri(), get_neo4j_user(), get_neo4j_password())
    try:
        pipe = await build_pipeline(db)
        pos_q = [q["query"] for q in GOLD]
        neg_q = [n["query"] for n in NEG]

        for label, scorer in (("NORMALIZED top-1 score", _norm_top1),
                              ("RAW top-1 vector cosine", _raw_cosine_top1)):
            pos = [scorer(pipe, q) for q in pos_q]
            neg = [scorer(pipe, q) for q in neg_q]
            print(f"\n=== {label} ===")
            print(f"  POSITIVE (n={len(pos)}): {_summary(pos)}")
            print(f"  NEGATIVE (n={len(neg)}): {_summary(neg)}")
            print(f"  {'threshold':>10}{'false_inj(neg>=T)':>19}{'pos_retain(pos>=T)':>20}")
            lo, hi = min(neg + pos), max(neg + pos)
            for i in range(9):
                T = lo + (hi - lo) * i / 8.0
                fi = sum(1 for s in neg if s >= T) / len(neg)
                pr = sum(1 for s in pos if s >= T) / len(pos)
                print(f"  {T:>10.3f}{fi:>19.2f}{pr:>20.2f}")
    finally:
        await db.close()


asyncio.run(main())
