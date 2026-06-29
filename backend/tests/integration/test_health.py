import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(async_client: AsyncClient) -> None:
    response = await async_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_list_kg_construction_modules(async_client: AsyncClient) -> None:
    response = await async_client.get("/api/v1/kg-construction/modules")

    assert response.status_code == 200
    assert len(response.json()["items"]) == 11
