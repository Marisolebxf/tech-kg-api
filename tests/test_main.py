from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def _assert_ok(response, path: str = "") -> None:
    assert response.status_code == 200, (
        f"{path} expected 200, got {response.status_code}: {response.text}"
    )


def test_hello():
    response = client.get("/hello")
    _assert_ok(response, "GET /hello")
    assert response.json() == {"message": "Hello, Tech KG!"}


def test_api_root():
    response = client.get("/api")
    _assert_ok(response, "GET /api")
    assert response.json()["message"] == "API is running"


def test_entity_alignment_default():
    response = client.post("/api/v1/entity/alignment", json={})
    _assert_ok(response, "POST /api/v1/entity/alignment")
    data = response.json()
    assert data["count_a"] == 7
    assert data["aligned_count"] >= 1
    assert len(data["details"]) == 7


def test_entity_disambiguation_default():
    response = client.post(
        "/api/v1/entity/disambiguation",
        json={
            "text": "苹果今天在发布会上推出了新款iPhone 16。",
            "mention": "苹果",
        },
    )
    _assert_ok(response, "POST /api/v1/entity/disambiguation")
    data = response.json()
    assert data["is_nil"] is False, data
    assert data["linked_entity_id"] == "KB001", data


def test_entity_alignment_empty_lists_use_defaults():
    response = client.post(
        "/api/v1/entity/alignment",
        json={"kg_a": [], "kg_b": []},
    )
    _assert_ok(response, "POST alignment empty lists")
    data = response.json()
    assert data["count_a"] == 7
    assert data["count_b"] == 8


def test_entity_disambiguation_empty_kb_uses_default():
    response = client.post(
        "/api/v1/entity/disambiguation",
        json={
            "text": "苹果今天在发布会上推出了新款iPhone 16。",
            "mention": "苹果",
            "kb": [],
        },
    )
    _assert_ok(response, "POST disambiguation kb=[]")
    data = response.json()
    assert data["is_nil"] is False, data
    assert data["linked_entity_id"] == "KB001", data
