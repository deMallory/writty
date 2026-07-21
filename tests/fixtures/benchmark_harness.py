"""Shared retrieval-benchmark mechanics (POL-2).

Single source of truth for the methodology-retrieval benchmark. Moved VERBATIM from
test_methodology_retrieval.py so the computed numbers are byte-identical -- INC-8..12 previously
copy-pasted the bundle_completeness loop into five test files, each re-encoding the corpus.

`rrf_fuse`, `retrieve`, `bundle_for`, and `benchmark_metrics` are duck-typed over the methodology
loader's index (`.search`), the embedding model (`.encode`/`.encode_batch`), a node_vectors dict,
and the adjacency map -- the same objects the session-scoped conftest fixtures provide.
"""
from __future__ import annotations

import time

import numpy as np

# Phase 0 release blockers (plan Section 5.3). Do NOT lower these thresholds.
BLOCKER_MRR = 0.78
BLOCKER_HIT_RATE = 0.90
BLOCKER_COMPLETENESS = 0.85
BLOCKER_P95_MS = 5.0

RRF_K = 60
BM25_LIMIT = 20
VECTOR_LIMIT = 20
BUNDLE_DEPTH = 1


def rrf_fuse(bm25_results: list[dict], vec_results: list[tuple[str, float]], top_n: int = 5) -> list[str]:
    """Reciprocal rank fusion of BM25 + vector rankings."""
    scores: dict[str, float] = {}
    for rank, r in enumerate(bm25_results):
        scores[r["rule_id"]] = scores.get(r["rule_id"], 0.0) + 1.0 / (RRF_K + rank + 1)
    for rank, (nid, _) in enumerate(vec_results):
        scores[nid] = scores.get(nid, 0.0) + 1.0 / (RRF_K + rank + 1)
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    return [nid for nid, _ in ranked[:top_n]]


def retrieve(
    query: str,
    keyword_index,
    embedding_model,
    node_vectors: dict[str, np.ndarray],
    top_k: int = 5,
) -> tuple[list[str], float, float]:
    """Run one query through a five-stage mini-pipeline.

    Returns (top_k ids, retrieval_latency_ms, encode_latency_ms). Retrieval latency excludes
    the ONNX encode step so it matches the blocker definition (Writ's published p95 measures
    the ranking pipeline, not the upstream embedding cost). Encode latency is reported
    separately so total user-facing latency is still visible.
    """
    t_enc = time.perf_counter()
    q_vec = np.asarray(embedding_model.encode(query), dtype=np.float32)
    encode_ms = (time.perf_counter() - t_enc) * 1000

    t_ret = time.perf_counter()
    bm25 = keyword_index.search(query, limit=BM25_LIMIT)
    vec_results = sorted(
        ((nid, float(np.dot(q_vec, v))) for nid, v in node_vectors.items()),
        key=lambda kv: -kv[1],
    )[:VECTOR_LIMIT]
    top = rrf_fuse(bm25, vec_results, top_n=top_k)
    retrieval_ms = (time.perf_counter() - t_ret) * 1000
    return top, retrieval_ms, encode_ms


def bundle_for(primary_id: str, adjacency: dict[str, list[tuple[str, str]]], max_depth: int = BUNDLE_DEPTH) -> set[str]:
    """Collect bundle member node IDs within max_depth hops of primary_id."""
    bundle = {primary_id}
    frontier = {primary_id}
    for _ in range(max_depth):
        nxt: set[str] = set()
        for nid in frontier:
            for tgt, _edge_type in adjacency.get(nid, []):
                if tgt not in bundle:
                    bundle.add(tgt)
                    nxt.add(tgt)
        frontier = nxt
    return bundle


def benchmark_metrics(
    ground_truth: dict,
    keyword_index,
    embedding_model,
    node_vectors: dict[str, np.ndarray],
    adjacency: dict[str, list[tuple[str, str]]],
) -> dict:
    """Run every ground-truth query once. Aggregate metrics + per-query detail."""
    per_query = []
    for q in ground_truth["queries"]:
        expected: list[str] = q["expected_node_ids"]
        top_k, retrieval_ms, encode_ms = retrieve(
            q["query"], keyword_index, embedding_model, node_vectors, top_k=5
        )
        rr = 0.0
        for rank, hit_id in enumerate(top_k):
            if hit_id in expected:
                rr = 1.0 / (rank + 1)
                break
        if top_k:
            bundle = bundle_for(top_k[0], adjacency)
            secondary = set(expected[1:])
            completeness = (len(secondary & bundle) / len(secondary)) if secondary else 1.0
        else:
            completeness = 0.0
        per_query.append({
            "id": q["id"],
            "query": q["query"],
            "expected_primary": expected[0] if expected else None,
            "expected_all": expected,
            "top_k": top_k,
            "rr": rr,
            "hit": rr > 0,
            "completeness": completeness,
            "retrieval_ms": retrieval_ms,
            "encode_ms": encode_ms,
        })
    n = len(per_query)
    retrieval_latencies = sorted(r["retrieval_ms"] for r in per_query)
    encode_latencies = sorted(r["encode_ms"] for r in per_query)
    return {
        "n_queries": n,
        "mrr_at_5": sum(r["rr"] for r in per_query) / n,
        "hit_rate": sum(1 for r in per_query if r["hit"]) / n,
        "bundle_completeness": sum(r["completeness"] for r in per_query) / n,
        "p95_retrieval_ms": retrieval_latencies[int(0.95 * n)] if n else 0.0,
        "mean_retrieval_ms": sum(retrieval_latencies) / n if n else 0.0,
        "p95_encode_ms": encode_latencies[int(0.95 * n)] if n else 0.0,
        "mean_encode_ms": sum(encode_latencies) / n if n else 0.0,
        "per_query": per_query,
    }


def bundle_completeness(
    ground_truth: dict,
    keyword_index,
    embedding_model,
    node_vectors: dict[str, np.ndarray],
    adjacency: dict[str, list[tuple[str, str]]],
) -> float:
    """The single bundle_completeness figure the INC absorption tests guard.

    Thin wrapper over benchmark_metrics so there is exactly one implementation of the loop.
    """
    return benchmark_metrics(
        ground_truth, keyword_index, embedding_model, node_vectors, adjacency
    )["bundle_completeness"]