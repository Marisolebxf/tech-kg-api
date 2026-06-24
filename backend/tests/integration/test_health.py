from fastapi.testclient import TestClient


def test_health_check(async_client: TestClient) -> None:
    response = async_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_kg_construction_modules(async_client: TestClient) -> None:
    response = async_client.get("/api/v1/kg-construction/modules")

    assert response.status_code == 200
    assert len(response.json()["items"]) == 11
