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
        raise KeyError("专家不存在: S404")

    monkeypatch.setattr(handler.application, "query", _raise)
    resp = await async_client.post(
        "/api/v1/kg-construction/expert-alumni-relations/query",
        json={"expertId": "S404"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 404
    assert body["success"] is False
