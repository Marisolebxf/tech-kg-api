"""Shared confidence scoring helpers for expert relationship modules."""

from __future__ import annotations

from typing import Any

EDGE_DEFAULT_CONFIDENCE = {
    "AUTHORED_BY": 0.86,
    "INVENTED_BY": 0.88,
    "LEADS": 0.90,
    "HAS_PARTICIPANT": 0.86,
}
EXACT_MATCH_METHODS = {
    "exact",
    "id_exact",
    "name_exact",
    "source_id_exact",
    "doi_registry_exact",
}


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)


def normalize_confidence(value: Any) -> float | None:
    """Normalize decimal/percentage confidence into the inclusive 0..1 range."""
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if 1 < numeric <= 100:
        numeric /= 100
    if not 0 <= numeric <= 1:
        return None
    return round(numeric, 4)


def confidence_result(
    confidence: float,
    *,
    source: str,
    rule: str,
    original_edge_type: str | None = None,
    score_breakdown: dict[str, float] | None = None,
) -> dict[str, Any]:
    basis: dict[str, Any] = {
        "rule": rule,
        "scoreBreakdown": {key: round(value, 4) for key, value in (score_breakdown or {}).items()},
    }
    if original_edge_type:
        basis["originalEdgeType"] = original_edge_type
    return {
        "confidence": round(max(0.0, min(confidence, 1.0)), 4),
        "confidenceSource": source,
        "confidenceBasis": basis,
    }


def edge_confidence(edge: Any, edge_type: str | None = None) -> dict[str, Any]:
    """Prefer an original edge score and derive an explainable fallback otherwise."""
    properties = getattr(edge, "properties", None) or {}
    resolved_type = str(edge_type or getattr(edge, "type", "") or "")
    original = normalize_confidence(properties.get("confidence"))
    if original is not None:
        return confidence_result(
            original,
            source="original",
            rule="original-edge-confidence",
            original_edge_type=resolved_type,
            score_breakdown={"originalConfidence": original},
        )

    fallback = EDGE_DEFAULT_CONFIDENCE.get(resolved_type, 0.75)
    match_method = str(properties.get("match_method") or "").strip().lower()
    if _has_value(properties.get("source_record_id")) or match_method in EXACT_MATCH_METHODS:
        score = 0.95
        rule = "exact-edge-evidence-fallback"
    elif _has_value(properties.get("match_evidence")):
        score = max(fallback, 0.90)
        rule = "matched-edge-evidence-fallback"
    else:
        score = fallback
        rule = "edge-type-fallback"
    return confidence_result(
        score,
        source="derived",
        rule=rule,
        original_edge_type=resolved_type,
        score_breakdown={"typeFallback": score},
    )


def expert_entity_confidence(properties: dict[str, Any], name: str) -> dict[str, Any]:
    original = normalize_confidence(properties.get("confidence"))
    if original is not None:
        return confidence_result(
            original,
            source="original",
            rule="original-entity-confidence",
            score_breakdown={"originalConfidence": original},
        )

    breakdown = {
        "base": 0.50,
        "name": 0.20 if _has_value(name) else 0.0,
        "sourceRecord": 0.15 if _has_value(properties.get("source_record_id")) else 0.0,
        "sourceTable": 0.10 if _has_value(properties.get("source_table")) else 0.0,
        "organization": 0.05 if _has_value(properties.get("scholar_org")) else 0.0,
    }
    return confidence_result(
        min(0.98, sum(breakdown.values())),
        source="derived",
        rule="expert-entity-completeness-v1",
        score_breakdown=breakdown,
    )


def achievement_entity_confidence(
    kind: str,
    properties: dict[str, Any],
    *,
    title: str,
    time_value: str | None,
    fields: list[str],
    vid: str,
) -> dict[str, Any]:
    original = normalize_confidence(properties.get("confidence"))
    if original is not None:
        return confidence_result(
            original,
            source="original",
            rule="original-entity-confidence",
            score_breakdown={"originalConfidence": original},
        )

    has_title = _has_value(title) and title != vid
    has_source = any(
        _has_value(properties.get(key))
        for key in ("source", "source_table", "db_source", "source_system")
    )
    if kind == "paper":
        breakdown = {
            "title": 0.35 if has_title else 0.0,
            "time": 0.20 if _has_value(time_value) else 0.0,
            "identifier": 0.20
            if any(_has_value(properties.get(key)) for key in ("doi", "paper_id"))
            else 0.0,
            "source": 0.15 if has_source else 0.0,
            "fields": 0.10 if fields else 0.0,
        }
    elif kind == "patent":
        breakdown = {
            "title": 0.30 if has_title else 0.0,
            "identifier": 0.25
            if any(
                _has_value(properties.get(key))
                for key in ("publication_number", "patent_id", "application_number")
            )
            else 0.0,
            "time": 0.20 if _has_value(time_value) else 0.0,
            "source": 0.15 if has_source else 0.0,
            "fields": 0.10 if fields else 0.0,
        }
    else:
        project_fields = (
            "title",
            "abstract",
            "funded_amount",
            "discipline",
            "approval_year",
            "fund_category",
        )
        filled = sum(1 for key in project_fields if _has_value(properties.get(key)))
        score = max(0.30, filled / len(project_fields))
        if not _has_value(properties.get("title")):
            score = min(score, 0.60)
        return confidence_result(
            min(0.98, score),
            source="derived",
            rule="project-entity-completeness-v1",
            score_breakdown={"coreFieldCompleteness": score},
        )

    score = max(0.30, sum(breakdown.values()))
    if not has_title:
        score = min(score, 0.60)
    return confidence_result(
        min(0.98, score),
        source="derived",
        rule=f"{kind}-entity-completeness-v1",
        score_breakdown=breakdown,
    )
