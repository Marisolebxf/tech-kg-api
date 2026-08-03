from httpx import AsyncClient


async def test_platform_overview_returns_frontend_demo_data(
    async_client: AsyncClient,
) -> None:
    response = await async_client.get("/api/v1/platform/overview")

    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 200
    assert body["success"] is True
    assert body["msg"] == "success"

    data = body["data"]
    assert data["platformStatus"] == "平台服务正常"
    assert data["pendingBatchCount"] == 2
    assert data["updatedAt"] == "10:30"
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
