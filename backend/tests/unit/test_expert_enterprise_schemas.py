from __future__ import annotations

from biz.schemas.expert_enterprise_relation import (
    BuiltRelation,
    ExpertEnterpriseBuildRequest,
    ExpertEnterpriseBuildResponse,
)


def test_request_parse():
    req = ExpertEnterpriseBuildRequest(
        scholarId="S001",
        enterpriseId="E001",
        relationTypes=["employment", "advisor", "rd_cooperation"],
    )
    assert req.scholarId == "S001"
    assert req.enterpriseId == "E001"
    assert req.relationTypes == ["employment", "advisor", "rd_cooperation"]


def test_request_defaults_empty_relation_types():
    req = ExpertEnterpriseBuildRequest(scholarId="S001", enterpriseId="E001")
    assert req.relationTypes == []


def test_response_assemble():
    resp = ExpertEnterpriseBuildResponse(
        status="success",
        scholarId="S001",
        enterpriseId="E001",
        scholarName="张三",
        enterpriseName="某企业",
        relations=[
            BuiltRelation(relationId="S001->E001@0", relationType="employment", effective=True),
            BuiltRelation(relationId="S001->E001@1", relationType="advisor", effective=True),
        ],
    )
    assert resp.status == "success"
    assert resp.scholarName == "张三"
    assert resp.enterpriseName == "某企业"
    assert resp.relations[0].relationType == "employment"
    assert resp.relations[1].effective is True
