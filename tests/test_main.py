from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_hello():
    response = client.get("/hello")
    assert response.status_code == 200
    assert response.json() == {"message": "Hello, Tech KG!"}


def test_api_root():
    response = client.get("/api")
    assert response.status_code == 200
    assert response.json()["message"] == "API is running"
