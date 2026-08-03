import math

from fastapi.testclient import TestClient

from script.m3e_embedding_service import create_app


class Vector(list):
    def tolist(self):
        return list(self)


class FakeModel:
    def get_sentence_embedding_dimension(self):
        return 512

    def encode(self, texts, **kwargs):
        assert kwargs["normalize_embeddings"] is True
        return [Vector([1.0] + [0.0] * 511) for _ in texts]


def fake_factory(model_name, device):
    assert model_name == "moka-ai/m3e-small"
    assert device == "cpu"
    return FakeModel()


def test_openai_compatible_embedding_endpoint(monkeypatch):
    monkeypatch.delenv("M3E_API_KEY", raising=False)
    app = create_app(fake_factory)
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.json()["status"] == "ok"

        response = client.post(
            "/v1/embeddings",
            json={
                "model": "moka-ai/m3e-small",
                "input": ["中文专利", "English patent"],
                "dimensions": 512,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["object"] == "list"
    assert len(payload["data"]) == 2
    assert len(payload["data"][0]["embedding"]) == 512
    assert math.isclose(payload["data"][0]["embedding"][0], 1.0)


def test_embedding_endpoint_rejects_wrong_dimension():
    app = create_app(fake_factory)
    with TestClient(app) as client:
        response = client.post(
            "/v1/embeddings",
            json={"model": "moka-ai/m3e-small", "input": "专利", "dimensions": 768},
        )
    assert response.status_code == 400


def test_embedding_endpoint_supports_bearer_auth(monkeypatch):
    monkeypatch.setenv("M3E_API_KEY", "secret")
    app = create_app(fake_factory)
    with TestClient(app) as client:
        denied = client.post("/v1/embeddings", json={"input": "专利"})
        allowed = client.post(
            "/v1/embeddings",
            headers={"Authorization": "Bearer secret"},
            json={"input": "专利"},
        )
    assert denied.status_code == 401
    assert allowed.status_code == 200
