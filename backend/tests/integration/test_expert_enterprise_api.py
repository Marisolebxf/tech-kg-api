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
        # find_nodes 是 service 的首个图调用；能执行即视为可用（空结果也算）
        client.find_nodes(["Scholar"], {"scholar_id": "__probe__"}, limit=1)
        return True
    except GraphRepoError:
        return False
    except Exception:
        return False


@pytest.mark.external
class TestExpertEnterpriseAPI:
    @pytest.mark.asyncio
    async def test_build_returns_shape(self):
        if not _techkg_usable():
            pytest.skip("techkg graph not usable (service/auth/schema unavailable)")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/kg-construction/expert-enterprise-relations/build",
                json={
                    "dataSource": "all",
                    "expertAId": "talent_001",
                    "relationType": "all",
                    "timeRange": None,
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert isinstance(data["enterprises"], list)
        assert "expert_id" in data
