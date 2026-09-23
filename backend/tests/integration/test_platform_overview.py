import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from biz.handler.platform_overview import application
from biz.handler.platform_overview import router as platform_overview_router
from biz.schemas.platform_overview import AssetChangeRow
from service.platform_overview import (
    GraphStatsSnapshot,
    PlatformOverviewService,
    TodayChangesSnapshot,
)


class _IntegrationStatsProvider:
    def get_stats(self, space: str | None = None) -> GraphStatsSnapshot:
        return GraphStatsSnapshot(
            total_nodes=128_000_000,
            total_edges=642_000_000,
            nodes={"Expert": 70, "Paper": 30},
            edges={"PUBLISH": 80, "WORKS_AT": 20},
        )


class _IntegrationChangesProvider:
    """控制库今日增量替身：避免集成测试依赖真实 techkg_control 数据。"""

    def get_today_changes(self, space: str | None = None) -> TodayChangesSnapshot:
        return TodayChangesSnapshot(
            entity_added=5,
            relation_added=2,
            running_count=1,
            entity_rows=[
                AssetChangeRow(
                    type="审测挂件",
                    object="techkg_e2e_liz.review_widgets",
                    change="写图 5 条",
                    source="手动触发",
                    time="10:30:00",
                )
            ],
            relation_rows=[],
        )


@pytest.fixture
async def overview_client() -> AsyncClient:
    app = FastAPI()
    app.include_router(platform_overview_router, prefix="/api/v1")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def test_platform_overview_returns_frontend_contract(
    overview_client: AsyncClient,
) -> None:
    application.service = PlatformOverviewService(
        stats_provider=_IntegrationStatsProvider(),
        changes_provider=_IntegrationChangesProvider(),
    )
    response = await overview_client.get("/api/v1/platform/overview")

    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 200
    assert body["success"] is True
    assert body["msg"] == "success"

    data = body["data"]
    assert data["platformStatus"] == "图数据库连接正常"
    assert data["pendingBatchCount"] == 1
    assert len(data["updatedAt"]) == 5
    assert data["updatedAt"][2] == ":"
    assert [item["key"] for item in data["assetOverviewGroups"]] == [
        "entity",
        "relation",
        "property",
    ]
    # 今日新增来自工作流控制库替身：数值与明细行均为真实口径的返回形状
    assert data["assetOverviewGroups"][0]["added"] == "+5"
    assert data["assetOverviewGroups"][0]["addedLabel"] == "今日新增"
    assert data["assetOverviewGroups"][1]["added"] == "+2"
    assert len(data["assetChangeRows"]["entity"]) == 1
    assert data["assetChangeRows"]["entity"][0]["change"] == "写图 5 条"
    assert data["assetChangeRows"]["relation"] == []
    assert len(data["latestChanges"]) == 5
    assert len(data["managementRisks"]) == 3
    assert sum(item["ratio"] for item in data["entityStructure"]) == 100
    assert sum(item["ratio"] for item in data["relationStructure"]) == 100
    assert data["dataMode"] == "partial"
    assert data["dataSources"]["graphAssets"] == "trsgraph-live"
    assert data["dataSources"]["todayChanges"] == "workflow-control-live"


async def test_platform_overview_atomic_endpoints_are_registered(
    overview_client: AsyncClient,
) -> None:
    application.service = PlatformOverviewService(
        stats_provider=_IntegrationStatsProvider(),
        changes_provider=_IntegrationChangesProvider(),
    )

    assets = await overview_client.get("/api/v1/platform/overview/assets")
    changes = await overview_client.get(
        "/api/v1/platform/overview/changes", params={"assetType": "relation"}
    )
    activity = await overview_client.get("/api/v1/platform/overview/activity")
    risks = await overview_client.get("/api/v1/platform/overview/risks")
    structures = await overview_client.get("/api/v1/platform/overview/structures")

    assert assets.json()["data"]["items"][0]["total"] == "1.28 亿"
    assert changes.json()["data"]["assetType"] == "relation"
    assert len(activity.json()["data"]["items"]) == 5
    assert len(risks.json()["data"]["items"]) == 3
    assert structures.json()["data"]["dataSource"] == "trsgraph-live"
