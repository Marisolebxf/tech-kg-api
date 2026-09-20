from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from biz.dependencies.auth import require_platform_actor
from biz.handler import project_relation as handler
from service.platform_access import PlatformActor


@dataclass
class _Result:
    records: list[dict[str, Any]]


class _Graph:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def execute_read(self, query: str, params: dict[str, Any] | None = None) -> _Result:
        if self.fail:
            raise RuntimeError("http://internal:9999 secret-api-key nGQL")
        return _Result([])


@pytest.fixture
async def project_relation_client() -> AsyncClient:
    app = FastAPI()
    app.include_router(handler.router, prefix="/api/v1")
    app.dependency_overrides[require_platform_actor] = lambda: PlatformActor(
        user_id="test-user",
        username="tester",
        display_name="Tester",
        email="tester@example.com",
        is_admin=False,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def test_route_is_registered_and_empty_data_succeeds(
    project_relation_client, monkeypatch
) -> None:
    monkeypatch.setattr(handler, "get_trs_graph_client", lambda: _Graph())
    response = await project_relation_client.post(
        "/api/v1/kg-service/project-relations/query", json={"pageSize": 10}
    )
    assert response.status_code == 200
    assert response.json()["data"] == {
        "items": [],
        "pageSize": 10,
        "nextCursor": "",
        "hasMore": False,
    }


async def test_validation_errors_use_http_422(project_relation_client) -> None:
    for payload in (
        {"relationTypes": ["DROP_SPACE"]},
        {"pageSize": 201},
    ):
        response = await project_relation_client.post(
            "/api/v1/kg-service/project-relations/query", json=payload
        )
        assert response.status_code == 422


async def test_invalid_cursor_uses_http_400(project_relation_client, monkeypatch) -> None:
    monkeypatch.setattr(handler, "get_trs_graph_client", lambda: _Graph())
    response = await project_relation_client.post(
        "/api/v1/kg-service/project-relations/query", json={"cursor": "bad"}
    )
    assert response.status_code == 400


async def test_graph_failure_uses_safe_http_502(project_relation_client, monkeypatch) -> None:
    monkeypatch.setattr(handler, "get_trs_graph_client", lambda: _Graph(fail=True))
    response = await project_relation_client.post(
        "/api/v1/kg-service/project-relations/query", json={}
    )
    assert response.status_code == 502
    body = response.text
    assert "internal:9999" not in body
    assert "secret-api-key" not in body
    assert "nGQL" not in body
