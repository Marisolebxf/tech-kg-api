from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_expert_colleague_route_is_registered_and_wraps_result(async_client) -> None:
    data = {
        "expert": {"id": "person_a", "name": "张明远"},
        "colleagues": [],
        "total": 0,
        "summary": {},
        "graph": {"nodes": [], "edges": []},
        "apiCalls": [],
    }
    with patch(
        "biz.handler.expert_colleague_relation.application.query",
        new=AsyncMock(return_value=data),
    ):
        response = await async_client.post(
            "/api/v1/kg-service/expert-colleague-relation",
            json={"expert_a_id": "person_a", "expert_b_id": "person_b"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["expert"]["id"] == "person_a"


@pytest.mark.asyncio
async def test_expert_colleague_request_requires_both_expert_ids(async_client) -> None:
    response = await async_client.post(
        "/api/v1/kg-service/expert-colleague-relation",
        json={"expert_a_id": "person_a"},
    )

    assert response.status_code == 200
    assert response.json()["code"] == 422
