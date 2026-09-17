"""图谱搜索 API 基础测试。

本文件只测试路由注册和请求参数校验，不连接真实 TRSGraph。
项目会将 FastAPI 参数校验异常统一包装为：
HTTP 200 + 业务 code 422 + success false。
"""

from typing import Any, cast

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

    # 本项目将参数校验错误统一包装成 HTTP 200。
    assert response.status_code == 200

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


def test_subgraph_accepts_vid_containing_slash() -> None:
    """含 ``/`` 的 VID（DOI 类，如 paper_ref_10.1111/jth.14768）应命中子图路由。

    网关/uvicorn 会把 %2F 解码成路径分隔符，单段路径参数直接 404 Not Found
    （前端 PageRank 排名行点击图谱高亮即此坑）。路径改用 path 转换器后，
    解码后的多段 URL 也能匹配。用非法 depth 触发统一参数校验 422 作为
    「路由已命中」的确定性判据（路由未命中是 HTTP 404 detail=Not Found）。
    """

    response = client.get(
        f"{BASE_URL}/subgraph/paper_ref_10.1111/jth.14768",
        params={"depth": 9},
    )

    assert_validation_error(response, "depth")

    # %2F 编码形态同样应命中（前端 encodeURIComponent 的原样输出）
    response_encoded = client.get(
        f"{BASE_URL}/subgraph/paper_ref_10.1111%2Fjth.14768",
        params={"depth": 9},
    )

    assert_validation_error(response_encoded, "depth")


def test_get_node_accepts_vid_containing_slash() -> None:
    """含 ``/`` 的 VID 应命中节点详情路由（同子图接口的 path 转换器）。"""

    response = client.get(
        f"{BASE_URL}/nodes/paper_ref_10.1111/jth.14768",
    )

    # 只断言「命中路由、返回统一 ApiResponse 信封」：不连接真实图库时
    # 走 _graph_query_error（业务 500），连接时可能业务 200/404，
    # 但都不会是路由级 404 的 {"detail": "Not Found"}。
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body.get("success"), bool)
    assert "detail" not in body


def test_collect_subgraph_keeps_dangling_vertex_center() -> None:
    """悬挂点（无 tag 属性但有边，如引用边的 DOI 端点）应渲染占位中心而非 404。

    dev2 的 CITES 数据里中心与邻居可能同为悬挂点：边端点也需占位进入 nodes，
    否则画布上边指向幽灵节点。
    """

    from biz.handler.graph_search import _collect_subgraph
    from infra.graph_db import TRSGraphClient
    from infra.graph_db.models import GraphEdge, GraphNode

    class _FakeClient:
        """悬挂点模拟：中心与邻居 VID 均查不到属性。"""

        def __init__(self, edges: list[GraphEdge]) -> None:
            self._edges = edges

        def get_node(self, vid: str) -> GraphNode | None:
            if vid in ("paper_ref_10.1111/jth.14768", "paper_812578243168174080"):
                return None  # 悬挂点：FETCH/MATCH 均不可见
            return GraphNode(id=vid, labels=["Paper"], properties={"name": "论文A"})

        def get_node_edges(self, vid: str, **_: object) -> list[GraphEdge]:
            return self._edges

    edges = [
        GraphEdge(
            id="e1",
            type="CITES",
            source_id="paper_ref_10.1111/jth.14768",
            target_id="paper_812578243168174080",
        )
    ]

    subgraph = _collect_subgraph(
        cast(TRSGraphClient, _FakeClient(edges)),
        "paper_ref_10.1111/jth.14768",
        1,
        40,
        0,
        None,
        "both",
    )

    assert subgraph is not None
    assert subgraph["nodes"][0].id == "paper_ref_10.1111/jth.14768"
    assert subgraph["nodes"][0].labels == []
    # 悬挂邻居占位出现在 nodes（边端点必须可画）
    neighbor = next(n for n in subgraph["nodes"] if n.id == "paper_812578243168174080")
    assert neighbor.labels == []
    assert subgraph["edges"][0].type == "CITES"

    # 完全不存在的 vid（无属性也无边）仍返回 None → 业务 404
    class _GhostClient(_FakeClient):
        def get_node(self, vid: str) -> GraphNode | None:
            return None

    assert (
        _collect_subgraph(cast(TRSGraphClient, _GhostClient([])), "ghost", 1, 40, 0, None, "both")
        is None
    )
