from __future__ import annotations

from types import SimpleNamespace

from service.confidence_scoring import (
    achievement_entity_confidence,
    edge_confidence,
    expert_entity_confidence,
    normalize_confidence,
)


def _edge(edge_type: str, properties: dict | None = None):
    return SimpleNamespace(type=edge_type, properties=properties or {})


def test_normalize_confidence_accepts_decimal_and_percentage():
    assert normalize_confidence(0.93) == 0.93
    assert normalize_confidence(93) == 0.93
    assert normalize_confidence("85") == 0.85
    assert normalize_confidence(-1) is None
    assert normalize_confidence(101) is None
    assert normalize_confidence("bad") is None


def test_edge_confidence_prefers_original_then_uses_evidence_fallbacks():
    original = edge_confidence(_edge("AUTHORED_BY", {"confidence": 92}))
    assert original["confidence"] == 0.92
    assert original["confidenceSource"] == "original"

    exact = edge_confidence(_edge("INVENTED_BY", {"source_record_id": "r1"}))
    assert exact["confidence"] == 0.95
    assert exact["confidenceSource"] == "derived"

    default = edge_confidence(_edge("HAS_PARTICIPANT"))
    assert default["confidence"] == 0.86
    assert default["confidenceBasis"]["originalEdgeType"] == "HAS_PARTICIPANT"


def test_entity_confidence_is_original_first_and_never_empty():
    expert = expert_entity_confidence({"confidence": 1.0}, "甲")
    assert expert["confidence"] == 1.0
    assert expert["confidenceSource"] == "original"

    paper = achievement_entity_confidence(
        "paper",
        {"title_zh": "论文", "doi": "10.1/x", "publication_year": 2024},
        title="论文",
        time_value="2024",
        fields=[],
        vid="P1",
    )
    assert 0.3 <= paper["confidence"] <= 0.98
    assert paper["confidenceSource"] == "derived"

    empty_project = achievement_entity_confidence(
        "project", {}, title="PR1", time_value=None, fields=[], vid="PR1"
    )
    assert empty_project["confidence"] == 0.3
