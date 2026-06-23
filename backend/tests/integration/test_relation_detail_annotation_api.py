from __future__ import annotations

import pytest


@pytest.mark.external
async def test_annotate_returns_422_for_bad_role(async_client):
    resp = await async_client.post(
        "/api/v1/kg-construction/relation-detail-annotations/annotate",
        json={"relationId": "S001->E001@0", "roleType": "ceo"},
    )
    assert resp.status_code == 422


@pytest.mark.external
async def test_describe_returns_module_info(async_client):
    resp = await async_client.get(
        "/api/v1/kg-construction/relation-detail-annotations"
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == "relation_detail_annotation"
