from __future__ import annotations

import pytest

from biz.handler import expert_alumni_relation as handler


@pytest.mark.asyncio
async def test_describe_alumni_relation(async_client):
    resp = await async_client.get("/api/v1/kg-construction/expert-alumni-relations")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == "expert_alumni_relation"
    assert body["status"] == "ready"


@pytest.mark.asyncio
async def test_query_alumni_relation_success(async_client, monkeypatch):
    monkeypatch.setattr(
        handler.application,
        "query",
        lambda **kwargs: {
            "expert": {"id": "S1", "name": "甲", "educations": []},
            "mode": "pair",
            "total": 1,
            "items": [
                {
                    "alumniId": "S2",
                    "name": "乙",
                    "sharedInstitutions": ["北京大学"],
                    "dimensions": ["同校"],
                    "educations": [],
                    "interactions": {
                        "coauthorEdge": False,
                        "paperCount": 0,
                        "patentCount": 0,
                        "projectCount": 0,
                        "summary": "共同论文 0 篇、专利 0、项目 0",
                    },
                }
            ],
            "dimensionsCatalog": ["同校"],
            "sourceMeta": {"space": "dev", "graph": "trs-graph", "truncated": False},
        },
    )
    resp = await async_client.post(
        "/api/v1/kg-construction/expert-alumni-relations/query",
        json={"expertId": "S1", "targetExpertId": "S2"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["dimensions"] == ["同校"]


@pytest.mark.asyncio
async def test_query_alumni_relation_not_found(async_client, monkeypatch):
    def _raise(**kwargs):
        raise KeyError("未找到专家: S404")

    monkeypatch.setattr(handler.application, "query", _raise)
    resp = await async_client.post(
        "/api/v1/kg-construction/expert-alumni-relations/query",
        json={"expertId": "S404"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 404
    assert body["success"] is False
    assert body["data"] is None
    assert body["msg"] == "未找到专家: S404"


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["expertId", "targetExpertId"])
@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("X" * 65, "64"),
        ("person_1!@#￥%&", "异常字符"),
        ("person 1", "空格"),
    ],
)
async def test_query_alumni_relation_rejects_invalid_expert_ids(
    async_client, field, value, message
):
    payload = {"expertId": "S1", "targetExpertId": "S2", field: value}
    resp = await async_client.post(
        "/api/v1/kg-construction/expert-alumni-relations/query", json=payload
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 422
    assert any(message in error["msg"] for error in body["data"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("value", "message"),
    [("学" * 101, "100"), ("清华大学!@#￥%&", "异常字符")],
)
async def test_query_alumni_relation_rejects_invalid_school(async_client, value, message):
    resp = await async_client.post(
        "/api/v1/kg-construction/expert-alumni-relations/query",
        json={"expertId": "S1", "school": value},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 422
    assert any(message in error["msg"] for error in body["data"])


@pytest.mark.asyncio
async def test_legacy_alumni_routes(async_client, monkeypatch):
    resp = await async_client.get("/api/v1/kg-service/expert-alumni-relation")
    assert resp.status_code == 200
    assert resp.json()["code"] == "expert_alumni_relation"

    monkeypatch.setattr(
        handler.application,
        "query",
        lambda **kwargs: {
            "expert": {"id": "S1", "name": "甲", "educations": []},
            "mode": "pair",
            "total": 0,
            "items": [],
            "dimensionsCatalog": [],
            "sourceMeta": {"space": "dev", "graph": "trs-graph", "truncated": False},
        },
    )
    resp = await async_client.post(
        "/api/v1/kg-service/expert-alumni-relation",
        json={"expertId": "S1", "targetExpertId": "S2"},
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 200
