from __future__ import annotations

from biz.schemas.relation_detail_annotation import RelationDetailAnnotationRequest


def test_request_accepts_valid_role():
    req = RelationDetailAnnotationRequest(
        relationId="S001->E001@0",
        roleType="chief_scientist",
        techField="人工智能",
        period={"start": "2021-01-01", "end": "2024-12-31"},
    )
    assert req.roleType == "chief_scientist"
    assert req.period.start == "2021-01-01"


def test_request_accepts_free_text_role():
    # 角色不再限定码表，接受任意职位文本（如挖掘抽取的 博士后/研究员/副教授 等）
    req = RelationDetailAnnotationRequest(relationId="S001->E001@0", roleType="博士后")
    assert req.roleType == "博士后"
