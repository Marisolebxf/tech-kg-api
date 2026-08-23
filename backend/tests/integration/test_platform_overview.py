import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from biz.handler.platform_overview import application
from biz.handler.platform_overview import router as platform_overview_router
from service.platform_overview import GraphStatsSnapshot, PlatformOverviewService


class _IntegrationStatsProvider:
    def get_stats(self) -> GraphStatsSnapshot:
        return GraphStatsSnapshot(
            total_nodes=128_000_000,
            total_edges=642_000_000,
            nodes={"Expert": 70, "Paper": 30},
            edges={"PUBLISH": 80, "WORKS_AT": 20},
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
    application.service = PlatformOverviewService(stats_provider=_IntegrationStatsProvider())
    response = await overview_client.get("/api/v1/platform/overview")

    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 200
    assert body["success"] is True
    assert body["msg"] == "success"

    data = body["data"]
    assert data["platformStatus"] == "图数据库连接正常"
    assert data["pendingBatchCount"] == 2
    assert len(data["updatedAt"]) == 5
    assert data["updatedAt"][2] == ":"
    assert [item["key"] for item in data["assetOverviewGroups"]] == [
        "entity",
        "relation",
        "property",
    ]
    assert len(data["assetChangeRows"]["entity"]) == 4
    assert len(data["latestChanges"]) == 5
    assert len(data["managementRisks"]) == 3
    assert sum(item["ratio"] for item in data["entityStructure"]) == 100
    assert sum(item["ratio"] for item in data["relationStructure"]) == 100
    assert data["dataMode"] == "partial"
    assert data["dataSources"]["graphAssets"] == "trsgraph-live"


async def test_platform_overview_atomic_endpoints_are_registered(
    overview_client: AsyncClient,
) -> None:
    application.service = PlatformOverviewService(stats_provider=_IntegrationStatsProvider())

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
