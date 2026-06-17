from __future__ import annotations

from biz.schemas.expert_enterprise_relation import (
    ExpertEnterpriseBuildRequest,
    ExpertEnterpriseBuildResponse,
    RelationItem,
)


def test_request_parse():
    req = ExpertEnterpriseBuildRequest(
        scholarId="S001", enterpriseId="E001", relationType="任职"
    )
    assert req.scholarId == "S001"
    assert req.enterpriseId == "E001"
    assert req.relationType == "任职"


def test_response_assemble():
    resp = ExpertEnterpriseBuildResponse(
        status="success",
        scholarId="S001",
        scholarName="张三",
        builtRelationId="S001->E001@0",
        relationType="任职",
        effective=True,
        relations=[
            RelationItem(
                relationId="S001->ENT001@0",
                enterpriseId="ENT001",
                enterpriseName="华智科技",
                relationType="任职",
            ),
        ],
    )
    assert resp.status == "success"
    assert resp.scholarName == "张三"
    assert resp.builtRelationId == "S001->E001@0"
    assert resp.effective is True
    assert resp.relations[0].enterpriseName == "华智科技"
    assert resp.relations[0].relationType == "任职"
