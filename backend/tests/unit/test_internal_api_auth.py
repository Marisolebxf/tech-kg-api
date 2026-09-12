import pytest
from starlette.requests import Request

from biz.dependencies.internal_api import get_internal_api_auth_headers
from infra import graph_api_client as graph_api_client_module
from infra.graph_api_client import graph_api
from service.expert_indirect_relation_api import GraphQueryApiClient
from service.expert_paper_cooperation_api import GraphSearchApiClient


def _request(headers: list[tuple[bytes, bytes]]) -> Request:
    return Request({"type": "http", "headers": headers})


def test_internal_api_auth_forwards_only_credentials():
    request = _request(
        [
            (b"authorization", b"Bearer test-token"),
            (b"cookie", b"kg_session=test-session"),
            (b"x-forwarded-for", b"203.0.113.1"),
        ]
    )

    assert get_internal_api_auth_headers(request) == {
        "authorization": "Bearer test-token",
        "cookie": "kg_session=test-session",
    }


def test_internal_api_auth_omits_missing_credentials():
    assert get_internal_api_auth_headers(_request([])) == {}


@pytest.mark.asyncio
async def test_paper_graph_client_applies_forwarded_auth_headers():
    client = GraphSearchApiClient(
        "http://internal/api/v1",
        auth_headers={"cookie": "kg_session=test-session"},
    )
    try:
        assert client._client.headers["cookie"] == "kg_session=test-session"
    finally:
        await client._client.aclose()


@pytest.mark.asyncio
async def test_indirect_graph_client_applies_forwarded_auth_headers():
    client = GraphQueryApiClient(
        "http://internal/api/v1",
        auth_headers={"authorization": "Bearer test-token"},
    )
    try:
        assert client._client.headers["authorization"] == "Bearer test-token"
    finally:
        await client._client.aclose()


def _echo_asgi_app(captured: dict[str, str]):
    """回显请求头的最小 ASGI 应用，替代 main.app 验证凭证头确实发进了回环调用。"""

    async def app(scope, receive, send):  # noqa: ANN001, ANN202
        for k, v in scope.get("headers") or []:
            captured[k.decode("latin-1").lower()] = v.decode("latin-1")
        body = b'{"success": true, "data": {}}'
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": body})

    return app


@pytest.mark.asyncio
async def test_graph_api_factory_applies_forwarded_auth_headers(monkeypatch):
    captured: dict[str, str] = {}
    monkeypatch.setattr(graph_api_client_module, "_load_app", lambda: _echo_asgi_app(captured))
    async with graph_api(auth_headers={"cookie": "kg_session=test-session"}) as client:
        await client.get_stats()
    assert captured.get("cookie") == "kg_session=test-session"


@pytest.mark.asyncio
async def test_graph_api_factory_without_headers_sends_no_credentials(monkeypatch):
    captured: dict[str, str] = {}
    monkeypatch.setattr(graph_api_client_module, "_load_app", lambda: _echo_asgi_app(captured))
    async with graph_api() as client:
        await client.get_stats()
    assert "cookie" not in captured and "authorization" not in captured
