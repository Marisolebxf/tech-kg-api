from fastapi.testclient import TestClient

from main import create_app


def test_app_factory_builds_isolated_apps_with_the_same_routes() -> None:
    first = create_app()
    second = create_app()

    assert first is not second
    assert {route.path for route in first.routes} == {route.path for route in second.routes}
    assert "/health" in {route.path for route in first.routes}
    paths = {route.path for route in first.routes}
    assert {
        "/api/v1/kg-construction/expert-indirect-relations/query",
        "/api/v1/kg-construction/expert-cooperation-achievements/query",
        "/api/v1/kg-construction/expert-colleague-relations/query",
        "/api/v1/kg-construction/expert-alumni-relations/query",
        "/api/v1/kg-construction/industry-chain-topn-event-relations/query",
        "/api/v1/kg-construction/industry-chain-panorama/query",
    } <= paths


def test_http_and_validation_errors_share_one_envelope() -> None:
    client = TestClient(create_app())

    missing = client.get("/api/v1/kg-construction/modules/not-a-module")
    assert missing.status_code == 404
    assert missing.json() == {
        "code": 404,
        "success": False,
        "data": None,
        "msg": "Module not found",
    }

    invalid = client.post("/api/v1/task-center/trigger", json={"domains": "paper"})
    assert invalid.status_code == 422
    body = invalid.json()
    assert body["code"] == 422
    assert body["success"] is False
    assert body["msg"] == "请求参数校验失败"
    assert body["data"][0]["loc"] == ["body", "domains"]
