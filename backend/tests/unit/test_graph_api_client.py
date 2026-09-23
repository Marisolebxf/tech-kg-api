"""``GraphAPIClient._unwrap`` 剥壳分支：错误响应不得伪装成空数据。"""

from __future__ import annotations

import httpx
import pytest

import infra.graph_api_client as graph_api_client
from infra.graph_api_client import GraphAPIClient, GraphAPIError
from service import business_access


def _response(status_code: int, payload: object) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload,
        request=httpx.Request("POST", "https://kg-internal/api/v1/graph-search/nodes/search"),
    )


def test_unwrap_returns_data_for_success_envelope() -> None:
    response = _response(200, {"code": 200, "success": True, "data": {"items": [1]}})

    assert GraphAPIClient._unwrap(response) == {"items": [1]}


def test_unwrap_raises_for_failed_envelope() -> None:
    response = _response(200, {"code": 500, "success": False, "msg": "search_nodes 失败"})

    with pytest.raises(GraphAPIError) as exc_info:
        GraphAPIClient._unwrap(response)

    assert "search_nodes" in str(exc_info.value)


def test_unwrap_raises_for_error_status_non_envelope_body() -> None:
    """鉴权 401 的 {"detail": ...} 不是图数据：按服务故障抛出，不许透传成空结果。"""
    response = _response(401, {"detail": "Not authenticated"})

    with pytest.raises(GraphAPIError) as exc_info:
        GraphAPIClient._unwrap(response)

    assert exc_info.value.status_code == 401
    assert "Not authenticated" in str(exc_info.value)


def test_unwrap_raises_for_gateway_error_status_with_dict_body() -> None:
    response = _response(502, {"message": "bad gateway"})

    with pytest.raises(GraphAPIError) as exc_info:
        GraphAPIClient._unwrap(response)

    assert exc_info.value.status_code == 502


def test_unwrap_passes_through_success_non_envelope_body() -> None:
    """成功状态的非 ApiResponse 结构（如 describe 端点直接返回 dict）保持透传。"""
    response = _response(200, {"columns": ["Field", "Type"]})

    assert GraphAPIClient._unwrap(response) == {"columns": ["Field", "Type"]}


def test_unwrap_raises_for_non_json_body() -> None:
    response = httpx.Response(
        502,
        text="<html>Bad Gateway</html>",
        request=httpx.Request("GET", "https://kg-internal/api/v1/graph-search/nodes"),
    )

    with pytest.raises(GraphAPIError):
        GraphAPIClient._unwrap(response)


async def test_graph_api_marks_internal_business_call(monkeypatch) -> None:
    """graph_api 的 ASGI transport 必须包 business_graph_app 打内部标记。

    九大业务名单账号的内层图查询靠该标记放行（enforce_business_access），
    漏包会把名单用户的业务自调用拦成 403（全景图/专家直接关系整页空）。
    """
    seen: dict = {}

    async def recorder_app(scope, receive, send):  # noqa: ANN001
        seen.update(scope)

    monkeypatch.setattr(graph_api_client, "_load_app", lambda: recorder_app)

    async with graph_api_client.graph_api() as client:
        transport_app = client._http._transport.app

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message) -> None:  # noqa: ANN001
        return None

    await transport_app({"type": "http", "path": "/api/v1/graph-search/nodes"}, receive, send)

    assert seen.get(business_access._INTERNAL_SCOPE_KEY) is business_access._INTERNAL_MARKER


async def test_graph_api_timeout_seconds_overrides_default(monkeypatch) -> None:
    """timeout_seconds 覆盖默认总预算：预算耗尽在 await 点抛 TimeoutError。"""

    import asyncio

    async def slow_app(scope, receive, send):  # noqa: ANN001
        await asyncio.sleep(0.2)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    monkeypatch.setattr(graph_api_client, "_load_app", lambda: slow_app)

    with pytest.raises(TimeoutError):
        async with graph_api_client.graph_api(timeout_seconds=0.05) as client:
            await client._get("/anything")
