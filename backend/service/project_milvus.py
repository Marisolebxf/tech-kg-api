"""Project-domain Milvus: text composition, schema, hybrid search, alignment decisions."""

from __future__ import annotations

import os
from dataclasses import dataclass
from math import isclose
from typing import Any

from rapidfuzz import fuzz

from infra.milvus import MilvusSearchHit
from service.organization_entity_alignment import normalize_alignment_text

COLLECTION_NAME = os.environ.get("PROJECT_MILVUS_COLLECTION", "project")
DENSE_DIM = 512
DENSE_MODEL_NAME = os.environ.get("PROJECT_DENSE_MODEL", "moka-ai/m3e-small")
RRF_K = 60

ABSTRACT_MAX_CHARS = 800
DENSE_TEXT_MAX_CHARS = 4000
STORED_TEXT_MAX_CHARS = 12000


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().replace("\n", " ").replace("\r", " ")


def sparse_to_dict(row: Any) -> dict[int, float]:
    """Convert a scipy CSR / COO sparse row to ``{col: value}`` for pymilvus upsert."""
    if isinstance(row, dict):
        return {
            int(k): float(v)
            for k, v in row.items()
            if not isclose(float(v), 0.0, abs_tol=1e-12)
        }
    if hasattr(row, "tocoo"):
        coo = row.tocoo()
        return {
            int(k): float(v)
            for k, v in zip(coo.col, coo.data, strict=False)
            if not isclose(float(v), 0.0, abs_tol=1e-12)
        }
    raise TypeError(f"unsupported sparse vector type: {type(row)!r}")


def compose_project_text(props: dict[str, Any], *, abstract_max: int = ABSTRACT_MAX_CHARS) -> str:
    """Compose BM25 / dense corpus text from Project props (+ optional MySQL enrichment)."""
    title = clean_text(props.get("title"))
    number = clean_text(props.get("project_number"))
    institution = clean_text(props.get("funded_institution"))
    host = clean_text(props.get("project_host"))
    discipline = clean_text(props.get("discipline"))
    keywords = clean_text(props.get("keywords"))
    abstract = clean_text(props.get("abstract"))[:abstract_max]
    final_abs = clean_text(props.get("final_report_abstract"))[:abstract_max]
    parts = [
        title,
        number,
        f"资助机构：{institution}" if institution else "",
        f"负责人：{host}" if host else "",
        f"学科：{discipline}" if discipline else "",
        f"关键词：{keywords}" if keywords else "",
        f"摘要：{abstract}" if abstract else "",
        f"结题摘要：{final_abs}" if final_abs else "",
    ]
    return "｜".join(part for part in parts if part)


def truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


DEFAULT_ORG_THRESHOLD = float(os.environ.get("PROJECT_ALIGN_ORG_THRESHOLD", "0.88"))
DEFAULT_ORG_MARGIN = float(os.environ.get("PROJECT_ALIGN_ORG_MARGIN", "0.08"))
DEFAULT_PERSON_THRESHOLD = float(os.environ.get("PROJECT_ALIGN_PERSON_THRESHOLD", "0.88"))
DEFAULT_PERSON_MARGIN = float(os.environ.get("PROJECT_ALIGN_PERSON_MARGIN", "0.08"))
DEFAULT_PERSON_NAME_MIN = float(os.environ.get("PROJECT_ALIGN_PERSON_NAME_MIN", "0.92"))
DEFAULT_TOP_K = int(os.environ.get("PROJECT_ALIGN_TOPK", "20"))


@dataclass(frozen=True)
class AlignmentHit:
    vid: str
    score: float
    fields: dict[str, Any]


@dataclass(frozen=True)
class AlignmentDecision:
    status: str  # matched | rejected | ambiguous
    vid: str | None
    score: float
    margin: float
    method: str
    evidence: str = ""


def decide(
    hits: list[AlignmentHit] | list[MilvusSearchHit],
    *,
    threshold: float,
    margin: float,
) -> AlignmentDecision:
    """Accept top-1 only when score and gap to top-2 both clear thresholds."""
    if not hits:
        return AlignmentDecision("rejected", None, 0.0, 0.0, "empty", "no_candidates")
    ranked: list[tuple[str, float, dict[str, Any]]] = []
    for hit in hits:
        if isinstance(hit, AlignmentHit):
            ranked.append((hit.vid, hit.score, hit.fields))
        else:
            ranked.append((hit.vid, float(hit.score), dict(hit.fields)))
    ranked.sort(key=lambda item: (-item[1], item[0]))
    best_vid, best_score, _fields = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    gap = best_score - second
    if best_score >= threshold and gap >= margin:
        return AlignmentDecision(
            "matched",
            best_vid,
            best_score,
            gap,
            "milvus_hybrid",
            f"score={best_score:.4f};margin={gap:.4f}",
        )
    return AlignmentDecision(
        "rejected",
        None,
        best_score,
        gap,
        "milvus_hybrid",
        f"below_threshold score={best_score:.4f};margin={gap:.4f}",
    )


def score_person_hit(
    *,
    query_name: str,
    institution: str,
    discipline: str,
    hit: MilvusSearchHit,
) -> AlignmentHit:
    """Combine retrieval score with RapidFuzz name and light context boosts."""
    fields = dict(hit.fields)
    names = [
        fields.get("canonical_name"),
        *(
            part.strip()
            for part in str(fields.get("aliases") or "").replace("|", ";").split(";")
            if part.strip()
        ),
    ]
    name_score = max(
        (
            fuzz.WRatio(normalize_alignment_text(query_name), normalize_alignment_text(name))
            / 100.0
            for name in names
            if name
        ),
        default=0.0,
    )
    retrieval = max(0.0, min(float(hit.score), 1.0))
    score = 0.65 * name_score + 0.25 * retrieval
    search_text = normalize_alignment_text(fields.get("search_text") or "")
    if institution and normalize_alignment_text(institution) in search_text:
        score = min(1.0, score + 0.08)
    if discipline and normalize_alignment_text(discipline) in search_text:
        score = min(1.0, score + 0.02)
    if isclose(name_score, 1.0):
        score = max(score, 0.95)
    return AlignmentHit(vid=hit.vid, score=score, fields={**fields, "name_score": name_score})


def decide_person(
    hits: list[AlignmentHit],
    *,
    threshold: float = DEFAULT_PERSON_THRESHOLD,
    margin: float = DEFAULT_PERSON_MARGIN,
    name_min: float = DEFAULT_PERSON_NAME_MIN,
) -> AlignmentDecision:
    """Person decisions require a high name similarity in addition to hybrid scores."""
    eligible = [hit for hit in hits if float(hit.fields.get("name_score") or 0.0) >= name_min]
    if not eligible:
        return AlignmentDecision(
            "rejected",
            None,
            hits[0].score if hits else 0.0,
            0.0,
            "milvus_hybrid",
            "name_score_below_min",
        )
    return decide(eligible, threshold=threshold, margin=margin)


def build_project_schema(client: Any):
    from pymilvus import DataType  # type: ignore

    schema = client.create_schema(auto_id=False, enable_dynamic_field=True)
    schema.add_field("vid", DataType.VARCHAR, is_primary=True, max_length=128)
    schema.add_field("project_number", DataType.VARCHAR, max_length=128)
    schema.add_field("title", DataType.VARCHAR, max_length=1024)
    schema.add_field("source", DataType.VARCHAR, max_length=64)
    schema.add_field("source_table", DataType.VARCHAR, max_length=128)
    schema.add_field("source_record_id", DataType.VARCHAR, max_length=128)
    schema.add_field("approval_year", DataType.VARCHAR, max_length=32)
    schema.add_field("text", DataType.VARCHAR, max_length=65535)
    schema.add_field("dense_vec", DataType.FLOAT_VECTOR, dim=DENSE_DIM)
    schema.add_field("sparse_vec", DataType.SPARSE_FLOAT_VECTOR)
    return schema


def build_project_index_params(client: Any):
    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="dense_vec",
        index_type="HNSW",
        metric_type="COSINE",
        params={"M": 16, "efConstruction": 200},
    )
    index_params.add_index(
        field_name="sparse_vec",
        index_type="SPARSE_INVERTED_INDEX",
        metric_type="IP",
        params={"drop_ratio_build": 0.0},
    )
    return index_params


def hybrid_search_project(
    client: Any,
    *,
    dense_query: list[float],
    sparse_query: Any,
    top_k: int = 5,
    collection: str = COLLECTION_NAME,
) -> list[AlignmentHit]:
    from pymilvus import AnnSearchRequest, RRFRanker  # type: ignore

    dense_req = AnnSearchRequest(
        data=[dense_query],
        anns_field="dense_vec",
        param={"metric_type": "COSINE", "params": {"ef": 128}},
        limit=top_k,
    )
    sparse_req = AnnSearchRequest(
        data=[sparse_query],
        anns_field="sparse_vec",
        param={"metric_type": "IP", "params": {"drop_ratio_search": 0.2}},
        limit=top_k,
    )
    resp = client.hybrid_search(
        collection_name=collection,
        reqs=[dense_req, sparse_req],
        ranker=RRFRanker(k=RRF_K),
        limit=top_k,
        output_fields=["vid", "project_number", "title", "source_record_id"],
    )
    out: list[AlignmentHit] = []
    if not resp or not resp[0]:
        return out
    for hit in resp[0]:
        entity = getattr(hit, "entity", None) or {}

        def _get(entity_ref: Any, key: str, default: Any = None) -> Any:
            if hasattr(entity_ref, "get"):
                return entity_ref.get(key, default)
            return getattr(entity_ref, key, default)

        vid = str(_get(entity, "vid") or getattr(hit, "id", "") or "")
        if not vid:
            continue
        out.append(
            AlignmentHit(
                vid=vid,
                score=float(getattr(hit, "score", 0.0) or 0.0),
                fields={
                    "project_number": _get(entity, "project_number"),
                    "title": _get(entity, "title"),
                    "source_record_id": _get(entity, "source_record_id"),
                },
            )
        )
    return out


__all__ = [
    "ABSTRACT_MAX_CHARS",
    "COLLECTION_NAME",
    "DENSE_DIM",
    "DENSE_MODEL_NAME",
    "DENSE_TEXT_MAX_CHARS",
    "DEFAULT_ORG_MARGIN",
    "DEFAULT_ORG_THRESHOLD",
    "DEFAULT_PERSON_MARGIN",
    "DEFAULT_PERSON_NAME_MIN",
    "DEFAULT_PERSON_THRESHOLD",
    "DEFAULT_TOP_K",
    "RRF_K",
    "STORED_TEXT_MAX_CHARS",
    "AlignmentDecision",
    "AlignmentHit",
    "build_project_index_params",
    "build_project_schema",
    "clean_text",
    "compose_project_text",
    "decide",
    "decide_person",
    "hybrid_search_project",
    "score_person_hit",
    "sparse_to_dict",
    "truncate_text",
]
