import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from biz.handler.platform_overview import application
from biz.handler.platform_overview import router as platform_overview_router
from biz.schemas.platform_overview import AssetChangeRow
from service.platform_overview import (
    DayChangesSnapshot,
    GraphStatsSnapshot,
    PlatformOverviewService,
)


class _IntegrationStatsProvider:
    def get_stats(self, space: str | None = None) -> GraphStatsSnapshot:
        # 资产卡中心用去重口径（total_nodes/total_edges）：替身数字自洽，
        # Σnodes=1.28 亿、Σedges=6.42 亿与 total_nodes/total_edges 相等
        # （单标签图场景；多标签顶点场景见单测 test_overview_total_is_deduped）。
        return GraphStatsSnapshot(
            total_nodes=128_000_000,
            total_edges=642_000_000,
            nodes={"Expert": 70_000_000, "Paper": 58_000_000},
            edges={"PUBLISH": 380_000_000, "WORKS_AT": 262_000_000},
        )


class _IntegrationChangesProvider:
    """控制库昨日增量替身：避免集成测试依赖真实 techkg_control 数据。"""

    def get_day_changes(self, space: str | None = None) -> DayChangesSnapshot:
        return DayChangesSnapshot(
            entity_added=5,
            relation_added=2,
            running_count=1,
            entity_rows=[
                AssetChangeRow(
                    type="审测挂件",
                    object="审测挂件 · 5 条",
                    change="新增 review-widget-64d0d5",
                    source="techkg_e2e_liz.review_widgets",
                    time="09-22 10:30:00",
                )
            ],
            relation_rows=[],
        )

    def running_count(self, space: str | None = None) -> int:
        return 1


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
    # 资产卡只有实体/关系两类（属性值占位卡随演示数据清理一并删除）
    assert [item["key"] for item in data["assetOverviewGroups"]] == ["entity", "relation"]
    # 昨日新增来自工作流控制库替身：数值与明细行均为真实口径的返回形状
    assert data["assetOverviewGroups"][0]["added"] == "+5"
    assert data["assetOverviewGroups"][0]["addedLabel"] == "昨日新增"
    assert data["assetOverviewGroups"][1]["added"] == "+2"
    assert len(data["assetChangeRows"]["entity"]) == 1
    assert data["assetChangeRows"]["entity"][0]["change"] == "新增 review-widget-64d0d5"
    assert data["assetChangeRows"]["relation"] == []
    assert set(data["assetChangeRows"]) == {"entity", "relation"}
    # 纯演示字段已删：响应里不再有最新动态/管理风险/环形图中心数
    assert "latestChanges" not in data
    assert "managementRisks" not in data
    assert "entityStructureTotal" not in data
    assert "relationStructureTotal" not in data
    assert sum(item["ratio"] for item in data["entityStructure"]) == 100
    assert sum(item["ratio"] for item in data["relationStructure"]) == 100
    assert data["dataMode"] == "partial"
    assert data["dataSources"]["graphAssets"] == "trsgraph-live"
    assert data["dataSources"]["dayChanges"] == "workflow-control-live"


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
    structures = await overview_client.get("/api/v1/platform/overview/structures")

    assert assets.json()["data"]["items"][0]["total"] == "1.28 亿"
    assert changes.json()["data"]["assetType"] == "relation"
    assert changes.json()["data"]["dataSource"] == "workflow-control-live"
    assert structures.json()["data"]["dataSource"] == "trsgraph-live"


async def test_platform_overview_demo_endpoints_are_removed(
    overview_client: AsyncClient,
) -> None:
    """纯演示数据的 /activity、/risks 端点已删：不再对外提供演示内容。"""
    activity = await overview_client.get("/api/v1/platform/overview/activity")
    risks = await overview_client.get("/api/v1/platform/overview/risks")

    assert activity.status_code == 404
    assert risks.status_code == 404
