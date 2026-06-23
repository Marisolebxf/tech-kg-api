from __future__ import annotations

import pytest


@pytest.mark.external
async def test_build_returns_422_for_bad_relation_type(async_client):
    resp = await async_client.post(
        "/api/v1/kg-construction/expert-enterprise-relations/build",
        json={"scholarId": "S001", "enterpriseId": "E001", "relationTypes": ["bogus"]},
    )
    assert resp.status_code == 422


@pytest.mark.external
async def test_describe_returns_module_info(async_client):
    resp = await async_client.get("/api/v1/kg-construction/expert-enterprise-relations")
    assert resp.status_code == 200
    assert resp.json()["code"] == "expert_enterprise_relation"
