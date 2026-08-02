"""专利关系补齐使用的 Milvus 混合召回与置信度裁决。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pymilvus import AnnSearchRequest, RRFRanker


@dataclass(frozen=True)
class Match:
    graph_vid: str
    score: float
    metadata: dict[str, Any]


def hybrid_search(
    client: Any, collection: str, dense: list[float], sparse: dict[int, float], limit: int = 5
) -> list[Match]:
    requests = [
        AnnSearchRequest(
            [dense], "dense_vector", {"metric_type": "COSINE", "params": {"ef": 128}}, limit=limit
        ),
        AnnSearchRequest(
            [sparse], "sparse_vector", {"metric_type": "IP", "params": {}}, limit=limit
        ),
    ]
    output_fields = [
        "vid",
        "entity_type",
        "patent_id",
        "publication_number",
        "application_number",
        "granted_number",
        "simple_family_number",
        "country_code",
        "source_table",
    ]
    rows = client.hybrid_search(
        collection, requests, RRFRanker(60), limit=limit, output_fields=output_fields
    )[0]
    result = []
    for hit in rows:
        entity = dict(hit.get("entity") or {})
        graph_vid = str(entity.get("vid") or hit.get("id") or "")
        if not graph_vid:
            continue
        result.append(Match(graph_vid, float(hit["distance"]), entity))
    return result


def decide(candidates: list[Match], threshold: float = 0.75, margin: float = 0.08) -> Match | None:
    if not candidates or candidates[0].score < threshold:
        return None
    if len(candidates) > 1 and candidates[0].score - candidates[1].score < margin:
        return None
    return candidates[0]
