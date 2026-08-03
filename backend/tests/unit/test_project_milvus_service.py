"""Unit tests for Project Milvus text helpers and alignment decisions."""

from __future__ import annotations

from infra.milvus import MilvusSearchHit
from service.project_milvus import (
    AlignmentHit,
    compose_project_text,
    decide,
    decide_person,
    score_person_hit,
    sparse_to_dict,
)


def test_compose_project_text_skips_empty_parts() -> None:
    text = compose_project_text(
        {
            "title": "量子计算基础研究",
            "project_number": "P-001",
            "funded_institution": "中国科学院",
            "project_host": "",
            "discipline": "物理学",
            "keywords": "量子；计算",
            "abstract": "摘要内容",
            "final_report_abstract": "",
        }
    )
    assert "量子计算基础研究" in text
    assert "P-001" in text
    assert "资助机构：中国科学院" in text
    assert "负责人：" not in text
    assert "学科：物理学" in text
    assert "关键词：量子；计算" in text
    assert "摘要：摘要内容" in text
    assert "结题摘要：" not in text


def test_sparse_to_dict_from_mapping() -> None:
    assert sparse_to_dict({1: 0.5, 2: 0.0, 3: 1.2}) == {1: 0.5, 3: 1.2}


def test_decide_accepts_clear_top1() -> None:
    decision = decide(
        [
            AlignmentHit("org_a", 0.95, {}),
            AlignmentHit("org_b", 0.70, {}),
        ],
        threshold=0.88,
        margin=0.08,
    )
    assert decision.status == "matched"
    assert decision.vid == "org_a"
    assert decision.margin >= 0.08


def test_decide_rejects_small_margin() -> None:
    decision = decide(
        [
            AlignmentHit("org_a", 0.95, {}),
            AlignmentHit("org_b", 0.90, {}),
        ],
        threshold=0.88,
        margin=0.08,
    )
    assert decision.status == "rejected"
    assert decision.vid is None


def test_decide_person_requires_name_score() -> None:
    hits = [
        AlignmentHit("person_1", 0.99, {"name_score": 0.5}),
        AlignmentHit("person_2", 0.80, {"name_score": 0.4}),
    ]
    decision = decide_person(hits, threshold=0.88, margin=0.08, name_min=0.92)
    assert decision.status == "rejected"
    assert decision.evidence == "name_score_below_min"


def test_score_person_hit_boosts_institution_context() -> None:
    hit = MilvusSearchHit(
        vid="person_x",
        score=0.7,
        fields={
            "canonical_name": "张三",
            "aliases": "",
            "search_text": "张三 中国科学院计算技术研究所 计算机",
        },
    )
    scored = score_person_hit(
        query_name="张三",
        institution="中国科学院计算技术研究所",
        discipline="计算机",
        hit=hit,
    )
    assert scored.fields["name_score"] == 1.0
    assert scored.score >= 0.95
