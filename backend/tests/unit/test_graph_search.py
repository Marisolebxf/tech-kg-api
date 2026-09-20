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
    """子图查询的 limit（每跳上限）最大值应为 256。"""

    response = client.get(
        f"{BASE_URL}/subgraph/{NODE_ID}",
        params={
            "depth": 3,
            "limit": 257,
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


class _AdjacencyClient:
    """邻接表桩：按 ``{vid: {edge_type: [边]}}`` 回答 get_node_edges。"""

    def __init__(self, adjacency: dict[str, dict[str, list[Any]]]) -> None:
        self._adjacency = adjacency

    def get_node(self, vid: str):
        from infra.graph_db.models import GraphNode

        return GraphNode(id=vid, labels=["Thing"], properties={"name": vid})

    def get_node_edges(self, vid: str, *, direction: str = "both", edge_type=None, limit=None, **_):
        result: list[Any] = []
        for et, edge_list in self._adjacency.get(vid, {}).items():
            if edge_type is not None and et != edge_type:
                continue
            result.extend(edge_list)
        if limit is not None:
            result = result[:limit]  # 与真实接口一致：limit 截断返回页
        return result


def _edge(edge_id: str, edge_type: str, source: str, target: str):
    from infra.graph_db.models import GraphEdge

    return GraphEdge(id=edge_id, type=edge_type, source_id=source, target_id=target)


def test_collect_subgraph_fair_quota_within_hop() -> None:
    """limit 是每跳上限：预算逐跳重置 + 跳内按前沿节点均分配额。

    - 逐跳重置：第二跳的边不会被第一跳挤掉（老实现全局 ``edges[:limit]``
      截断后深度 2/3 的边一条都进不来）。
    - 均分配额：跳内每个前沿节点分到 ceil(预算/节点数) 条出边名额，
      靠前的节点不能吃光预算——a 有 2 条边但配额 1，e5 被挤掉；
      b 同样分到 1 条名额（e6 进来）。
    """
    from biz.handler.graph_search import _collect_subgraph
    from infra.graph_db import TRSGraphClient

    adjacency = {
        # 中心 3 条边，limit=2 → 第一跳配额 2 条（e3 超出查询页被挤掉）
        "c": {
            "REL": [
                _edge("e1", "REL", "c", "a"),
                _edge("e2", "REL", "c", "b"),
                _edge("e3", "REL", "c", "d"),
            ]
        },
        # a 有 2 条边但第二跳配额只有 1 → 只进 e4；b 分到的名额进 e6
        "a": {"REL": [_edge("e4", "REL", "a", "x"), _edge("e5", "REL", "a", "y")]},
        "b": {"REL": [_edge("e6", "REL", "b", "z")]},
    }
    subgraph = _collect_subgraph(
        cast(TRSGraphClient, _AdjacencyClient(adjacency)), "c", 2, 2, 0, None, "both"
    )
    assert subgraph is not None
    edge_ids = {edge.id for edge in subgraph["edges"]}
    # 第一跳 2 条（均分配额下 e3 出局）+ 第二跳 a/b 各 1 条
    assert edge_ids == {"e1", "e2", "e4", "e6"}
    node_ids = {node.id for node in subgraph["nodes"]}
    assert node_ids == {"c", "a", "b", "x", "z"}  # d/e5/y 未被发现

    # 余量回流：a 无边用不掉配额，b 拿到全部剩余预算（2 条都能进）
    adjacency_reflow = {
        "c": {"REL": [_edge("e1", "REL", "c", "a"), _edge("e2", "REL", "c", "b")]},
        "a": {},
        "b": {"REL": [_edge("e6", "REL", "b", "z"), _edge("e7", "REL", "b", "w")]},
    }
    subgraph2 = _collect_subgraph(
        cast(TRSGraphClient, _AdjacencyClient(adjacency_reflow)), "c", 2, 2, 0, None, "both"
    )
    assert subgraph2 is not None
    assert {edge.id for edge in subgraph2["edges"]} == {"e1", "e2", "e6", "e7"}


def test_collect_subgraph_oversamples_past_seen_edges() -> None:
    """查询页按 4 倍配额过采样：已收录的回边不占配额。

    第二跳 a 的边序列里前两条是第一跳已收录的回边（同 id 反向查回）：
    旧实现查询页 = 配额 1，页被回边占掉 → a 贡献 0 条新边；
    过采样后跳过回边仍能收到新边 new1。
    """
    from biz.handler.graph_search import _collect_subgraph
    from infra.graph_db import TRSGraphClient

    adjacency = {
        "c": {"REL": [_edge("e1", "REL", "c", "a"), _edge("e2", "REL", "c", "b")]},
        # a 的边序列：先 2 条回边（e1/e2 均为第一跳已收录），再 1 条新边
        "a": {
            "REL": [
                _edge("e1", "REL", "a", "c"),
                _edge("e2", "REL", "a", "c"),
                _edge("new1", "REL", "a", "x"),
            ]
        },
        "b": {"REL": [_edge("new2", "REL", "b", "y")]},
    }
    subgraph = _collect_subgraph(
        cast(TRSGraphClient, _AdjacencyClient(adjacency)), "c", 2, 2, 0, None, "both"
    )
    assert subgraph is not None
    # 第二跳 a/b 各分 1 条名额：a 跳过回边收 new1，b 收 new2
    assert {edge.id for edge in subgraph["edges"]} == {"e1", "e2", "new1", "new2"}
    assert {node.id for node in subgraph["nodes"]} == {"c", "a", "b", "x", "y"}


def test_collect_filtered_subgraph_oversamples_past_seen_edges() -> None:
    """filtered-subgraph 同样过采样：配额被回边占页时仍能收到新边。"""
    from biz.handler.graph_search import _collect_filtered_subgraph
    from infra.graph_db import TRSGraphClient

    adjacency = {
        "c": {"R1": [_edge("r1", "R1", "c", "a"), _edge("r2", "R1", "c", "b")]},
        # a 的边序列：先 1 条回边（r1 已收录），再 1 条新边
        "a": {"R1": [_edge("r1", "R1", "a", "c"), _edge("new1", "R1", "a", "x")]},
        "b": {},
    }
    subgraph = _collect_filtered_subgraph(
        cast(TRSGraphClient, _AdjacencyClient(adjacency)), "c", ["R1"], 2, 2, "both"
    )
    assert subgraph is not None
    # 第二跳 R1 预算重置为 2、a/b 各分 1 名额：a 跳过回边后收 new1
    # （旧实现查询页 = 配额 1 被回边吃掉 → a 贡献 0 条新边）
    assert {edge.id for edge in subgraph["edges"]} == {"r1", "r2", "new1"}
    assert {node.id for node in subgraph["nodes"]} == {"c", "a", "b", "x"}


def test_collect_filtered_subgraph_budget_per_type_per_hop() -> None:
    """filtered-subgraph：每种边类型每跳各 limit 条预算，逐跳逐类型重置 + 跳内均分。"""
    from biz.handler.graph_search import _collect_filtered_subgraph
    from infra.graph_db import TRSGraphClient

    adjacency = {
        # R1/R2 各自独立预算：limit=1 时每类型保留 1 条
        "c": {
            "R1": [_edge("r1a", "R1", "c", "a"), _edge("r1b", "R1", "c", "b")],
            "R2": [_edge("r2a", "R2", "c", "a")],
        },
        # 第二跳：R1 预算重置，a-x 能进来（全局截断语义下进不来）
        "a": {"R1": [_edge("r1c", "R1", "a", "x")]},
        "b": {},
    }
    subgraph = _collect_filtered_subgraph(
        cast(TRSGraphClient, _AdjacencyClient(adjacency)), "c", ["R1", "R2"], 2, 1, "both"
    )
    assert subgraph is not None
    edge_ids = {edge.id for edge in subgraph["edges"]}
    # 第一跳：R1 取 r1a（预算 1）、R2 取 r2a；第二跳：R1 预算重置收 r1c
    assert edge_ids == {"r1a", "r2a", "r1c"}
    node_ids = {node.id for node in subgraph["nodes"]}
    assert node_ids == {"c", "a", "x"}  # b 被 R1 第一跳预算挤掉

    # 跳内均分：R1 第二跳预算 2，a/b 各分 1 条名额——a 的第二条（r1e）被挤掉，
    # b 不会因为排在后面就拿不到名额（贪心语义下 b 一条都进不来）
    adjacency_fair = {
        "c": {"R1": [_edge("r1a", "R1", "c", "a"), _edge("r1b", "R1", "c", "b")]},
        "a": {"R1": [_edge("r1c", "R1", "a", "x"), _edge("r1e", "R1", "a", "w")]},
        "b": {"R1": [_edge("r1d", "R1", "b", "y")]},
    }
    subgraph2 = _collect_filtered_subgraph(
        cast(TRSGraphClient, _AdjacencyClient(adjacency_fair)), "c", ["R1"], 2, 2, "both"
    )
    assert subgraph2 is not None
    assert {edge.id for edge in subgraph2["edges"]} == {"r1a", "r1b", "r1c", "r1d"}
