"""Abstraction node generation from rule clusters.

Per ARCH-SSOT-001: Abstraction nodes stored in Neo4j are the canonical source.
Per INV-SUMMARY: summary = statement of rule nearest to cluster centroid.
No LLM dependency. Deterministic and offline.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from writ.compression.clusters import ClusterResult
    from writ.graph.db import Neo4jConnection

# Per ARCH-CONST-001
ABSTRACTION_ID_PREFIX = "ABS"
APPROX_TOKENS_PER_CHAR = 0.25  # conservative estimate for English text

# Repo root derived the same way writ/server.py locates bible/
# (Path(__file__).resolve().parent.parent / "bible"); this module lives one
# level deeper (writ/compression/), so the repo root is parent.parent.parent.
DEFAULT_ABSTRACTIONS_ARTIFACT: Path = (
    Path(__file__).resolve().parent.parent.parent / "bible" / "abstractions.json"
)


async def run_compression(
    db: Neo4jConnection,
    project: str = "writ",
    artifact_path: Path | None = None,
) -> dict:
    """Regenerate the Abstraction layer for `project` from its non-mandatory rules.

    Reusable pipeline shared by `writ compress` and `writ import-markdown
    --compress`: embeds each non-mandatory rule's `trigger statement`, runs the
    HDBSCAN/k-means comparison, generates abstractions from the chosen result,
    and writes them to the graph (replacing the project's existing abstractions).

    The `sentence_transformers` import is lazy and lives INSIDE this helper so
    that importing this module never requires the dep. Production installs
    deliberately exclude it (pyproject [fallback] extras); callers that want a
    graceful degradation should catch ImportError.

    In addition to writing the abstractions to the graph, this also writes a
    cached JSON artifact (Approach A: durable abstraction persistence) so the
    dep-free materialization path can reproduce the graph layer on a later
    ingest without re-clustering. When `artifact_path` is None it defaults to
    DEFAULT_ABSTRACTIONS_ARTIFACT (bible/abstractions.json at the repo root).

    Returns {abstractions, ungrouped, avg_ratio, chosen}.
    """
    import numpy as np
    from sentence_transformers import SentenceTransformer

    from writ.compression.clusters import evaluate_both

    all_rules = await db.get_all_rules(project=project)
    domain_rules = [r for r in all_rules if not r.get("mandatory", False)]
    if not domain_rules:
        return {"abstractions": [], "ungrouped": [], "avg_ratio": 0.0, "chosen": None}

    model = SentenceTransformer("all-MiniLM-L6-v2")
    texts = [f"{r.get('trigger', '')} {r.get('statement', '')}" for r in domain_rules]
    embeddings = np.array(model.encode(texts), dtype=np.float32)

    comparison = evaluate_both([r["rule_id"] for r in domain_rules], embeddings)
    chosen_result = (
        comparison.hdbscan if comparison.chosen == "hdbscan" else comparison.kmeans
    )

    abstractions = generate_abstractions(chosen_result, domain_rules)
    await write_abstractions_to_graph(db, abstractions, project=project)

    write_abstractions_artifact(abstractions, project=project, artifact_path=artifact_path)

    avg_ratio = 0.0
    if abstractions:
        avg_ratio = sum(a["compression_ratio"] for a in abstractions) / len(abstractions)

    return {
        "abstractions": abstractions,
        "ungrouped": chosen_result.ungrouped,
        "avg_ratio": avg_ratio,
        "chosen": comparison.chosen,
    }


def write_abstractions_artifact(
    abstractions: list[dict],
    project: str = "writ",
    artifact_path: Path | None = None,
) -> Path:
    """Write the cached abstractions JSON artifact (deterministic ordering).

    Schema: {"project", "abstractions": [{abstraction_id, summary, rule_ids,
    compression_ratio}, ...]}. Abstractions are sorted by abstraction_id and
    each rule_ids list is sorted so the committed file is stable across runs.
    Returns the path written. Dep-free (no clustering/sentence_transformers).
    """
    if artifact_path is None:
        artifact_path = DEFAULT_ABSTRACTIONS_ARTIFACT

    payload = {
        "project": project,
        "abstractions": [
            {
                "abstraction_id": a["abstraction_id"],
                "summary": a["summary"],
                "rule_ids": sorted(a["rule_ids"]),
                "compression_ratio": a["compression_ratio"],
            }
            for a in sorted(abstractions, key=lambda x: x["abstraction_id"])
        ],
    }
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    return artifact_path


async def _persist_abstraction_layer(
    db: Neo4jConnection,
    entries: list[tuple[dict, list[str]]],
    project: str,
) -> int:
    """Delete this project's abstractions, then MERGE each (node_data, rule_ids)
    entry: one create_abstraction plus one create_abstracts_edge per rule_id.

    Shared by materialize_abstractions_from_artifact and write_abstractions_to_graph,
    which build node_data DIFFERENTLY (the artifact path has no domain and uses .get
    defaults; the recompute path is strict and carries domain). Returns the count
    persisted. Import-light (db calls only) so the artifact path stays dep-free.
    """
    await db.delete_abstractions(project=project)
    for node_data, rule_ids in entries:
        await db.create_abstraction(node_data)
        for rid in rule_ids:
            await db.create_abstracts_edge(node_data["abstraction_id"], rid, project=project)
    return len(entries)


async def materialize_abstractions_from_artifact(
    artifact_path: Path,
    db: Neo4jConnection,
    project: str = "writ",
) -> int:
    """Recreate Abstraction nodes + ABSTRACTS edges from the cached artifact.

    Dep-free: reads the JSON artifact and writes the graph layer WITHOUT
    importing sentence_transformers/numpy or running any clustering. This is the
    default ingest reproduce path -- a rebuild restores the abstraction view
    from the committed file rather than recomputing it. If the artifact file is
    absent, returns 0 (no-op). Returns the number of Abstraction nodes created.

    The Abstraction node and ABSTRACTS edge shapes mirror
    write_abstractions_to_graph (create_abstraction node_data dict + project
    threading from the M.2 work). The artifact has no `domain` field, so the
    node's domain is left unset on this dep-free path.
    """
    if not artifact_path.exists():
        return 0

    data = json.loads(artifact_path.read_text(encoding="utf-8"))
    # The caller's `project` is authoritative for every graph write (delete +
    # create). Refuse to act on an artifact that declares a DIFFERENT project --
    # otherwise a mismatched/tampered file would delete another project's
    # abstractions. Fail loud rather than cross-project clobber.
    artifact_project = data.get("project")
    if artifact_project is not None and artifact_project != project:
        raise ValueError(
            f"abstractions artifact declares project={artifact_project!r} but "
            f"materialization was requested for project={project!r}; refusing a "
            f"cross-project delete/create"
        )
    abstractions = data.get("abstractions", [])

    entries: list[tuple[dict, list[str]]] = []
    for abst in abstractions:
        rule_ids = abst.get("rule_ids", [])
        node_data = {
            "abstraction_id": abst["abstraction_id"],
            "summary": abst.get("summary", ""),
            "compression_ratio": abst.get("compression_ratio"),
            "rule_count": len(rule_ids),
            "project": project,
        }
        entries.append((node_data, rule_ids))
    return await _persist_abstraction_layer(db, entries, project)


def generate_abstractions(
    cluster_result: ClusterResult,
    rules: list[dict],
) -> list[dict]:
    """Generate Abstraction dicts from cluster result.

    Each abstraction has: abstraction_id, summary, rule_ids, domain, compression_ratio.
    Summary is the statement of the rule nearest to the cluster centroid (INV-SUMMARY).
    """
    rid_to_rule = {r["rule_id"]: r for r in rules}
    rule_ids_list = [r["rule_id"] for r in rules]
    abstractions: list[dict] = []

    for cid, member_ids in sorted(cluster_result.clusters.items()):
        centroid_idx = cluster_result.centroid_indices.get(cid)
        if centroid_idx is None or centroid_idx >= len(rule_ids_list):
            continue

        centroid_rule_id = rule_ids_list[centroid_idx]
        centroid_rule = rid_to_rule.get(centroid_rule_id, {})
        summary = centroid_rule.get("statement", "")

        domain = _derive_domain(member_ids, rid_to_rule)
        compression_ratio = _compute_compression_ratio(member_ids, rid_to_rule, summary)
        abs_id = f"{ABSTRACTION_ID_PREFIX}-{domain.upper().replace(' ', '-')}-{cid:03d}"

        abstractions.append({
            "abstraction_id": abs_id,
            "summary": summary,
            "rule_ids": sorted(member_ids),
            "domain": domain,
            "compression_ratio": round(compression_ratio, 2),
        })

    return abstractions


async def write_abstractions_to_graph(
    db: Neo4jConnection,
    abstractions: list[dict],
    project: str = "writ",
) -> int:
    """Write Abstraction nodes and ABSTRACTS edges to Neo4j, scoped to `project`.

    Deletes this project's existing abstractions first for clean recompression
    (INV-IDEMPOTENT) without touching another project's. The Abstraction nodes and
    ABSTRACTS edges carry `project` so they stay project-isolated (M.2). Returns count
    of abstractions written.
    """
    entries = [
        (
            {
                "abstraction_id": abst["abstraction_id"],
                "summary": abst["summary"],
                "domain": abst["domain"],
                "compression_ratio": abst["compression_ratio"],
                "rule_count": len(abst["rule_ids"]),
                "project": project,
            },
            abst["rule_ids"],
        )
        for abst in abstractions
    ]
    return await _persist_abstraction_layer(db, entries, project)


def _derive_domain(member_ids: list[str], rid_to_rule: dict[str, dict]) -> str:
    """Most common domain among cluster members."""
    domains = [rid_to_rule.get(rid, {}).get("domain", "Unknown") for rid in member_ids]
    if not domains:
        return "Unknown"
    counter = Counter(domains)
    return counter.most_common(1)[0][0]


def _compute_compression_ratio(
    member_ids: list[str],
    rid_to_rule: dict[str, dict],
    summary: str,
) -> float:
    """Ratio of total member text tokens to summary tokens."""
    member_tokens = 0
    for rid in member_ids:
        rule = rid_to_rule.get(rid, {})
        text = f"{rule.get('statement', '')} {rule.get('trigger', '')}"
        member_tokens += len(text) * APPROX_TOKENS_PER_CHAR

    summary_tokens = max(len(summary) * APPROX_TOKENS_PER_CHAR, 1)
    return member_tokens / summary_tokens
