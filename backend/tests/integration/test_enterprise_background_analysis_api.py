from __future__ import annotations

import pytest


@pytest.mark.external
async def test_analyze_returns_422_for_bad_dimension(async_client):
    resp = await async_client.post(
        "/api/v1/kg-construction/enterprise-background-analyses/analyze",
        json={"enterpriseId": "E001", "analysisDimensions": ["bogus"], "patentCPC": []},
    )
    assert resp.status_code == 422


@pytest.mark.external
async def test_describe_returns_module_info(async_client):
    resp = await async_client.get("/api/v1/kg-construction/enterprise-background-analyses")
    assert resp.status_code == 200
    assert resp.json()["code"] == "enterprise_background_analysis"
