import asyncio
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from biz.schemas.expert_alumni_relation import AlumniRelationQueryRequest


@pytest.mark.parametrize("field", ["expertId", "targetExpertId"])
@pytest.mark.parametrize("empty", [None, "", "   "])
def test_alumni_requires_both_nonempty_expert_ids(field, empty):
    payload = {"expertId": "person_9F9A0001", "targetExpertId": "person_9F9A0004"}
    payload[field] = empty

    with pytest.raises(ValidationError) as error:
        AlumniRelationQueryRequest.model_validate(payload)

    assert any(item["loc"] == (field,) for item in error.value.errors())


@pytest.mark.parametrize("field", ["expertId", "targetExpertId"])
def test_alumni_rejects_missing_expert_id(field):
    payload = {"expertId": "person_9F9A0001", "targetExpertId": "person_9F9A0004"}
    del payload[field]

    with pytest.raises(ValidationError) as error:
        AlumniRelationQueryRequest.model_validate(payload)

    assert any(item["loc"] == (field,) for item in error.value.errors())


def test_alumni_openapi_lists_both_expert_ids_as_required():
    assert set(AlumniRelationQueryRequest.model_json_schema()["required"]) == {
        "expertId",
        "targetExpertId",
    }


def test_alumni_accepts_pair_without_optional_filters():
    payload = {"expertId": "person_9F9A0001", "targetExpertId": "person_9F9A0004"}
    request = AlumniRelationQueryRequest.model_validate(payload)

    assert request.expertId == payload["expertId"]
    assert request.targetExpertId == payload["targetExpertId"]
    assert request.limit == 20


def test_alumni_route_rejects_missing_target_before_querying(monkeypatch):
    from biz.handler import expert_alumni_relation as handler

    query = Mock(return_value={})
    monkeypatch.setattr(handler.application, "query", query)
    app = FastAPI()
    app.include_router(handler.router, prefix="/api/v1")

    async def request():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.post(
                "/api/v1/kg-construction/expert-alumni-relations/query",
                json={"expertId": "person_9F9A0001"},
            )

    response = asyncio.run(request())

    assert response.status_code == 422
    assert any(item["loc"] == ["body", "targetExpertId"] for item in response.json()["detail"])
    query.assert_not_called()


def test_alumni_route_accepts_both_required_experts(monkeypatch):
    from biz.handler import expert_alumni_relation as handler

    query = Mock(return_value={"mode": "pair", "total": 0, "items": []})
    monkeypatch.setattr(handler.application, "query", query)
    app = FastAPI()
    app.include_router(handler.router, prefix="/api/v1")

    async def request():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.post(
                "/api/v1/kg-construction/expert-alumni-relations/query",
                json={"expertId": "person_9F9A0001", "targetExpertId": "person_9F9A0004"},
            )

    response = asyncio.run(request())

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert query.call_args.kwargs["target_expert_id"] == "person_9F9A0004"
