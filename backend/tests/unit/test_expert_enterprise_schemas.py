from __future__ import annotations

from biz.schemas.expert_enterprise_relation import (
    EnterpriseItem,
    ExpertEnterpriseBuildRequest,
    ExpertEnterpriseBuildResponse,
    TimeRange,  # noqa: F401  kept to assert the symbol is exported
)


def test_request_defaults_and_parse():
    req = ExpertEnterpriseBuildRequest(expertAId="S1")
    assert req.dataSource == "all"
    assert req.relationType == "all"
    assert req.timeRange is None


def test_response_assemble():
    resp = ExpertEnterpriseBuildResponse(
        status="success",
        expert="张伟",
        expert_id="S1",
        title="",
        enterprises=[EnterpriseItem(enterprise_id="O1", name="清华大学", relation="任职")],
    )
    assert resp.enterprises[0].relation == "任职"
    assert resp.status == "success"
