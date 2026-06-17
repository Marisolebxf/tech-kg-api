"""专家-企业关系构建 API 集成测试（@external，需真实后端 + techkg 图）。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.mark.external
class TestExpertEnterpriseAPI:
    @pytest.mark.asyncio
    async def test_build_returns_shape(self):
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
