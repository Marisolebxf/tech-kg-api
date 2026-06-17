"""专家-企业关系构建 API 集成测试（@external，需真实后端 + techkg 图可查）。

仅当 techkg 图可达且可查询时运行；否则自动 skip。
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from infra.graph_db import get_techkg_client
from infra.graph_db.exceptions import GraphRepoError
from main import app


def _techkg_usable() -> bool:
    """探测 techkg 图是否可达且可查询（含鉴权）。"""
    try:
        client = get_techkg_client()
        # get_node 是 service 的首个图调用；能执行即视为可用
        client.get_node("__probe__")
        return True
    except GraphRepoError:
        return False
    except Exception:
        return False


@pytest.mark.external
class TestExpertEnterpriseAPI:
    @pytest.mark.asyncio
    async def test_build_constructs_relations(self):
        if not _techkg_usable():
            pytest.skip("techkg graph not usable (service/auth/schema unavailable)")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/kg-construction/expert-enterprise-relations/build",
                json={
                    "scholarId": "E10001",
                    "enterpriseId": "ENT001",
                    "relationTypes": ["employment", "advisor", "rd_cooperation"],
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["scholarId"] == "E10001"
        assert data["enterpriseId"] == "ENT001"
        assert isinstance(data["relations"], list)
        assert len(data["relations"]) == 3
        assert all(r["effective"] for r in data["relations"])
