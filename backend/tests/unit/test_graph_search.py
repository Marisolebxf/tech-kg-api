"""图谱搜索 API 基础测试。

本文件只测试路由注册和请求参数校验，不连接真实 TRSGraph。
项目会将 FastAPI 参数校验异常统一包装为：
HTTP 422 + 业务 code 422 + success false。
"""

from typing import Any

from fastapi.testclient import TestClient
from httpx import Response

from main import app

client = TestClient(app)

BASE_URL = "/api/v1/graph-search"
NODE_ID = "007Rb117"


def assert_validation_error(
    response: Response,
    field_name: str,
) -> None:
    """断言请求被项目统一的参数校验处理器拒绝。

    Args:
        response: TestClient 返回的响应。
        field_name: 预期发生错误的查询参数名称。
    """

    assert response.status_code == 422

    body: dict[str, Any] = response.json()

    assert body["code"] == 422
    assert body["success"] is False
    assert body["msg"] == "请求参数校验失败"

    errors = body["data"]

    assert isinstance(errors, list)
    assert errors

    first_error = errors[0]

    assert first_error["loc"] == ["query", field_name]
    assert "msg" in first_error
    assert "type" in first_error


def test_graph_search_routes_registered() -> None:
    """检查全部图谱搜索路由是否已注册到 OpenAPI。"""

    response = client.get("/openapi.json")

    assert response.status_code == 200

    body = response.json()
    paths = body["paths"]

    expected_paths = [
        f"{BASE_URL}/nodes/{{node_id}}",
        f"{BASE_URL}/nodes",
        f"{BASE_URL}/nodes/search",
        f"{BASE_URL}/subgraph/{{node_id}}",
        f"{BASE_URL}/node/{{node_id}}/edges",
        f"{BASE_URL}/node/{{node_id}}/neighbours",
        f"{BASE_URL}/shortest-path",
        f"{BASE_URL}/spaces",
        f"{BASE_URL}/stats",
    ]

    for path in expected_paths:
        assert path in paths, f"图谱搜索路由未注册：{path}"


def test_subgraph_rejects_depth_above_maximum() -> None:
    """子图查询的 depth 最大值应为 3。"""

    response = client.get(
        f"{BASE_URL}/subgraph/{NODE_ID}",
        params={
            "depth": 4,
            "limit": 50,
            "direction": "both",
        },
    )

    assert_validation_error(response, "depth")

    body = response.json()
    error = body["data"][0]

    assert error["type"] == "less_than_equal"


def test_subgraph_rejects_limit_above_maximum() -> None:
    """子图查询的 limit 最大值应为 200。"""

    response = client.get(
        f"{BASE_URL}/subgraph/{NODE_ID}",
        params={
            "depth": 3,
            "limit": 201,
            "direction": "both",
        },
    )

    assert_validation_error(response, "limit")

    body = response.json()
    error = body["data"][0]

    assert error["type"] == "less_than_equal"


def test_subgraph_rejects_invalid_direction() -> None:
    """子图接口的 direction 只能是 out、in 或 both。"""

    response = client.get(
        f"{BASE_URL}/subgraph/{NODE_ID}",
        params={
            "depth": 3,
            "limit": 50,
            "direction": "abc",
        },
    )

    assert_validation_error(response, "direction")

    body = response.json()
    error = body["data"][0]

    assert error["type"] == "literal_error"


def test_edges_reject_invalid_direction() -> None:
    """节点边查询接口应拒绝非法 direction。"""

    response = client.get(
        f"{BASE_URL}/node/{NODE_ID}/edges",
        params={
            "direction": "abc",
            "limit": 50,
        },
    )

    assert_validation_error(response, "direction")

    body = response.json()
    error = body["data"][0]

    assert error["type"] == "literal_error"


def test_neighbours_reject_invalid_direction() -> None:
    """邻居节点查询接口应拒绝非法 direction。"""

    response = client.get(
        f"{BASE_URL}/node/{NODE_ID}/neighbours",
        params={
            "direction": "abc",
            "limit": 50,
        },
    )

    assert_validation_error(response, "direction")

    body = response.json()
    error = body["data"][0]

    assert error["type"] == "literal_error"
