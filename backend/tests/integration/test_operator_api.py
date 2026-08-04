from __future__ import annotations

import pytest

from application.operator import OperatorApplication
from biz.handler.operator import get_operator_application
from main import app
from service.operator_registry import OperatorRegistry


@pytest.fixture
def operator_registry(tmp_path):
    registry = OperatorRegistry(tmp_path)
    app.dependency_overrides[get_operator_application] = lambda: OperatorApplication(registry)
    yield registry
    app.dependency_overrides.pop(get_operator_application, None)


async def test_operator_crud_invoke_and_hot_update(async_client, operator_registry):
    create_response = await async_client.post(
        "/api/v1/operators",
        json={
            "name": "user.api_score",
            "version": "1.0.0",
            "kind": "data_processing",
            "description": "API 测试算子",
            "source": (
                "def operator(data, ctx):\n"
                "    return [{**x, 'score': len(x['name']) * 10} for x in data]\n"
            ),
        },
    )
    assert create_response.status_code == 201
    assert create_response.json()["version"] == "1.0.0"

    invoke_response = await async_client.post(
        "/api/v1/operators/user.api_score/invoke",
        json={"data": [{"name": "foo"}], "ctx": {}},
    )
    assert invoke_response.status_code == 200
    assert invoke_response.json()["data"] == [{"name": "foo", "score": 30}]

    update_response = await async_client.put(
        "/api/v1/operators/user.api_score",
        json={
            "version": "2.0.0",
            "kind": "data_processing",
            "source": (
                "def operator(data, ctx):\n"
                "    return [{**x, 'score': len(x['name']) * 100} for x in data]\n"
            ),
        },
    )
    assert update_response.status_code == 200

    invoke_response = await async_client.post(
        "/api/v1/operators/user.api_score/invoke",
        json={"data": [{"name": "foo"}], "ctx": {}},
    )
    assert invoke_response.json()["data"] == [{"name": "foo", "score": 300}]

    list_response = await async_client.get("/api/v1/operators", params={"kind": "data_processing"})
    names = {item["name"] for item in list_response.json()["items"]}
    assert {"builtin.data_normalize", "user.api_score"}.issubset(names)

    delete_response = await async_client.delete("/api/v1/operators/user.api_score")
    assert delete_response.status_code == 204
    assert (await async_client.get("/api/v1/operators/user.api_score")).status_code == 404


async def test_upload_validation_and_reserved_name(async_client, operator_registry):
    invalid_response = await async_client.post(
        "/api/v1/operators",
        json={
            "name": "user.invalid",
            "version": "1.0.0",
            "kind": "data_processing",
            "source": "value = 1\n",
        },
    )
    assert invalid_response.status_code == 422
    assert "operator" in invalid_response.json()["msg"]

    reserved_response = await async_client.post(
        "/api/v1/operators",
        json={
            "name": "builtin.data_normalize",
            "version": "2.0.0",
            "kind": "data_processing",
            "source": "def operator(data, ctx):\n    return data\n",
        },
    )
    assert reserved_response.status_code == 409


async def test_internal_reload_endpoint(async_client, operator_registry, monkeypatch):
    monkeypatch.setenv("OPERATOR_RELOAD_TOKEN", "secret")
    assert (await async_client.post("/internal/operators/reload")).status_code == 401

    response = await async_client.post(
        "/internal/operators/reload", headers={"X-Operator-Reload-Token": "secret"}
    )
    assert response.status_code == 200
    assert response.json() == {"loaded": [], "count": 0}


async def test_internal_reload_can_install_operator_snapshot(
    async_client, operator_registry, monkeypatch
):
    monkeypatch.setenv("OPERATOR_RELOAD_TOKEN", "secret")
    response = await async_client.post(
        "/internal/operators/reload",
        headers={"X-Operator-Reload-Token": "secret"},
        json={
            "operators": [
                {
                    "manifest": {
                        "name": "user.remote",
                        "version": "1.0.0",
                        "kind": "data_processing",
                        "description": "远程同步",
                        "builtin": False,
                        "updated_at": "2026-07-29T00:00:00+00:00",
                    },
                    "source": "def operator(data, ctx):\n    return [{**x, 'remote': True} for x in data]\n",
                }
            ],
            "replace": True,
        },
    )

    assert response.status_code == 200
    invoke_response = await async_client.post(
        "/api/v1/operators/user.remote/invoke", json={"data": [{"id": 1}], "ctx": {}}
    )
    assert invoke_response.json()["data"] == [{"id": 1, "remote": True}]
