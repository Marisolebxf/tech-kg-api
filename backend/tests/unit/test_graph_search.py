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

        def get_nodes_bulk(self, vids: list[str]) -> dict[str, GraphNode]:
            # 批量取点同样查不到悬挂点 → 调用方按占位节点兜底
            return {
                vid: GraphNode(id=vid, labels=["Paper"], properties={"name": "论文A"})
                for vid in vids
                if vid not in ("paper_ref_10.1111/jth.14768", "paper_812578243168174080")
            }

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

    def get_nodes_bulk(self, vids: list[str]) -> dict:
        from infra.graph_db.models import GraphNode

        return {vid: GraphNode(id=vid, labels=["Thing"], properties={"name": vid}) for vid in vids}

    def get_node_edges(self, vid: str, *, direction: str = "both", edge_type=None, limit=None, **_):
        result: list[Any] = []
        for et, edge_list in self._adjacency.get(vid, {}).items():
            if edge_type is not None and et != edge_type:
                continue
            result.extend(edge_list)
        if limit is not None:
            result = result[:limit]  # 与真实接口一致：limit 截断返回页
        return result

    def get_edges_bulk(
        self,
        vids: list[str],
        edge_types: list[str],
        *,
        direction: str = "both",
        row_cap: int = 4096,
    ):
        # 完整批量回放：邻接表全量返回（真实 GO 未达行上限时同样完整）
        grouped: dict[tuple[str, str], list[Any]] = {}
        count = 0
        for vid in vids:
            for et, edge_list in self._adjacency.get(vid, {}).items():
                if et not in edge_types:
                    continue
                grouped[(vid, et)] = list(edge_list)
                count += len(edge_list)
        return grouped, count >= row_cap


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


class _CountingClient:
    """星型图桩：记录每个客户端方法的调用，验证子图补点/邻接是否真走批量。

    truncated=True 模拟批量 GO 撞到行数上限（返回标志置位）；
    starve 里的源模拟被同批超高度数源挤掉（批量结果里无行，REST 里仍有）；
    bulk_raises=True 模拟批量语句整体失败（须退回逐组合 REST）。
    """

    def __init__(
        self,
        adjacency: dict[str, list[Any]],
        *,
        truncated: bool = False,
        starve: set[str] | None = None,
        bulk_raises: bool = False,
    ) -> None:
        self._adjacency = adjacency
        self.get_node_calls: list[str] = []
        self.bulk_calls: list[list[str]] = []
        self.edge_calls: list[str] = []
        self.bulk_edge_calls: list[tuple[list[str], list[str]]] = []
        self.rest_refills: list[tuple[str, str]] = []  # 单源 REST 补查（带边类型）
        self.missing: set[str] = set()  # 批量结果里查不到的 VID（悬挂点）
        self.truncated = truncated
        self.starve = starve or set()
        self.bulk_raises = bulk_raises

    def get_node(self, vid: str):
        from infra.graph_db.models import GraphNode

        self.get_node_calls.append(vid)
        return GraphNode(id=vid, labels=["Hub"], properties={"name": vid})

    def get_nodes_bulk(self, vids: list[str]) -> dict:
        from infra.graph_db.models import GraphNode

        self.bulk_calls.append(list(vids))
        return {
            vid: GraphNode(id=vid, labels=["Person"], properties={"n": vid})
            for vid in vids
            if vid not in self.missing
        }

    def get_edges_bulk(self, vids: list[str], edge_types: list[str], **_: object):
        from infra.graph_db.models import GraphEdge

        self.bulk_edge_calls.append((list(vids), list(edge_types)))
        if self.bulk_raises:
            from infra.graph_db.exceptions import GraphRequestError

            raise GraphRequestError("批量邻接语句失败", status_code=500, body="")
        grouped: dict[tuple[str, str], list[Any]] = {}
        for vid in vids:
            if vid in self.starve:
                continue
            for edge_id, target in self._adjacency.get(vid, []):
                grouped.setdefault((vid, "REL"), []).append(
                    GraphEdge(id=edge_id, type="REL", source_id=vid, target_id=target)
                )
        return grouped, self.truncated

    def get_node_edges(
        self, vid: str, *, direction: str = "both", edge_type=None, limit=None, **_
    ) -> list[Any]:
        from infra.graph_db.models import GraphEdge

        if edge_type is not None:
            self.rest_refills.append((vid, edge_type))
        self.edge_calls.append(vid)
        return [
            GraphEdge(id=edge_id, type="REL", source_id=vid, target_id=target)
            for edge_id, target in self._adjacency.get(vid, [])
        ]


def test_collect_subgraph_collapses_neighbor_round_trips() -> None:
    """新邻居补点必须批量：一跳 100 邻居 = 1 次中心 + 1 次查边 + 1 次批量取点。

    旧实现逐邻居 get_node 是 102 次 TRS 往返（会话池高频借用 + 单请求数秒
    级串行时延）；配额/去重/发现顺序语义全部不变。
    """
    from biz.handler.graph_search import _collect_subgraph
    from infra.graph_db import TRSGraphClient

    neighbors = [f"person_{i}" for i in range(100)]
    fake = _CountingClient({"c": [(f"e{i}", n) for i, n in enumerate(neighbors)]})

    subgraph = _collect_subgraph(cast(TRSGraphClient, fake), "c", 1, 200, 0, None, "both")

    assert subgraph is not None
    assert len(subgraph["nodes"]) == 101  # 中心 + 100 个新邻居
    assert fake.get_node_calls == ["c"]  # 只有中心走单查，邻居零单查
    assert fake.edge_calls == ["c"]
    assert fake.bulk_calls == [neighbors]  # 一跳整批一次，发现顺序保留
    # 邻居属性来自批量结果而非占位（labels/properties 真实带出）
    assert all(
        n.labels == ["Person"] and n.properties == {"n": n.id} for n in subgraph["nodes"][1:]
    )


def test_collect_subgraph_batches_per_hop_and_keeps_dangling_traversal() -> None:
    """批量按跳分批；悬挂邻居仍占位渲染并作为下一跳前沿（旧语义不变）。"""
    from biz.handler.graph_search import _collect_subgraph
    from infra.graph_db import TRSGraphClient

    fake = _CountingClient({"c": [("e1", "a")], "a": [("e2", "x")]})
    fake.missing = {"a"}  # a 是悬挂点：批量取点查不到

    subgraph = _collect_subgraph(cast(TRSGraphClient, fake), "c", 2, 2, 0, None, "both")

    assert subgraph is not None
    # 每跳各一次批量：hop1 发现 a，hop2 从占位 a 继续遍历发现 x
    assert fake.bulk_calls == [["a"], ["x"]]
    assert fake.get_node_calls == ["c"]
    node_map = {n.id: n for n in subgraph["nodes"]}
    assert node_map["a"].labels == []  # 悬挂邻居占位（边端点必须可画）
    assert node_map["x"].labels == ["Person"]
    assert {e.id for e in subgraph["edges"]} == {"e1", "e2"}  # 悬挂点继续遍历


def test_collect_filtered_subgraph_batches_neighbor_fetches() -> None:
    """filtered-subgraph 补点走端点存在性预取；悬挂端点的行按 REST 口径剔除。

    批量行是裸 Nebula 结果，而 REST /traversal 会静默滤掉悬挂端点的边
    （实测 person→悬挂org 的 AFFILIATED_WITH 被吞）——预取端点存在性后在
    配额核算前剔除悬挂行，可见边集与旧逐组合 REST 路径逐字一致：悬挂边
    不收集（旧 REST 本来就不返回它）、悬挂邻居不发现、也不挤占配额。
    """
    from biz.handler.graph_search import _collect_filtered_subgraph
    from infra.graph_db import TRSGraphClient

    fake = _CountingClient({"c": [("r1", "a1"), ("r2", "a2")], "a1": [("r3", "ghost1")]})
    fake.missing = {"ghost1"}

    subgraph = _collect_filtered_subgraph(cast(TRSGraphClient, fake), "c", ["REL"], 2, 4, "both")

    assert subgraph is not None
    assert fake.get_node_calls == ["c"]
    # 每跳一次端点批量取点（已收录/前沿节点跳过）：hop1 查 a1/a2，hop2 查 ghost1
    assert fake.bulk_calls == [["a1", "a2"], ["ghost1"]]
    node_ids = {n.id for n in subgraph["nodes"]}
    assert node_ids == {"c", "a1", "a2"}  # 悬挂邻居 ghost1 不占位
    # r3 端点悬挂：与旧 REST 一致被剔除（旧实现的假桩会返回它，真实 trs 不会）
    assert {e.id for e in subgraph["edges"]} == {"r1", "r2"}


def test_collect_filtered_subgraph_dangling_row_does_not_consume_quota() -> None:
    """悬挂行在配额核算前剔除：不挤占「每类型每跳上限」的真实边名额。

    r_dangle 排在前面且 limit=1——若悬挂行进了配额，真实边 r_real 会被
    挤掉（旧 REST 路径看不到悬挂边，名额始终留给真实边）。
    """
    from biz.handler.graph_search import _collect_filtered_subgraph
    from infra.graph_db import TRSGraphClient

    fake = _CountingClient({"c": [("r_dangle", "ghost"), ("r_real", "a1")]})
    fake.missing = {"ghost"}

    subgraph = _collect_filtered_subgraph(cast(TRSGraphClient, fake), "c", ["REL"], 1, 1, "both")

    assert subgraph is not None
    assert {e.id for e in subgraph["edges"]} == {"r_real"}  # 配额给了真实边
    assert {n.id for n in subgraph["nodes"]} == {"c", "a1"}  # ghost 未被发现


def test_collect_filtered_subgraph_dedups_back_edge_by_storage_true_id() -> None:
    """跨跳回边按存储真方向 id 去重：两端的批量行规范化后 id 相同。

    BIDIRECT 单语句版此处会得到两个翻转 id（同一条边收两遍，实测边集
    81 vs 31 的根因）；拆「正向 + REVERSELY」并规范化为存储真方向后，
    边 id 与 REST 同款，seen_edge_ids 一致命中。
    """
    from biz.handler.graph_search import _collect_filtered_subgraph
    from infra.graph_db import TRSGraphClient
    from infra.graph_db.models import GraphEdge, GraphNode

    class _RawRowsClient:
        """批量行固定返回存储真方向的同一条边（c→a1），无论从哪端查询。"""

        def __init__(self) -> None:
            self.bulk_edge_calls: list[list[str]] = []

        def get_node(self, vid: str):
            return GraphNode(id=vid, labels=["Thing"], properties={"name": vid})

        def get_nodes_bulk(self, vids: list[str]) -> dict:
            return {
                vid: GraphNode(id=vid, labels=["Thing"], properties={"name": vid}) for vid in vids
            }

        def get_edges_bulk(
            self, vids: list[str], edge_types: list[str], **_: object
        ) -> tuple[dict[tuple[str, str], list[Any]], bool]:
            self.bulk_edge_calls.append(list(vids))
            same = GraphEdge(id="c->a1@0", type="REL", source_id="c", target_id="a1")
            return {(vid, "REL"): [same] for vid in vids}, False

    fake = _RawRowsClient()
    subgraph = _collect_filtered_subgraph(cast(TRSGraphClient, fake), "c", ["REL"], 2, 4, "both")

    assert subgraph is not None
    assert fake.bulk_edge_calls == [["c"], ["a1"]]  # 两跳都查了（a1 是前沿）
    assert [e.id for e in subgraph["edges"]] == ["c->a1@0"]  # 同一条边只收一次
    assert {n.id for n in subgraph["nodes"]} == {"c", "a1"}


def test_collect_filtered_subgraph_collapses_edge_queries() -> None:
    """边查询必须整跳批量：N 前沿 × M 类型从 N×M 次 REST 降为每跳 1 次 GO。

    旧实现逐组合 REST（重点企业关系 12 类型 × 46 前沿 = 552 次往返）；
    批量未截断时必须零单源 REST 补查，且不存在的边类型在语句里就不出现
    （由客户端按 schema 列表滤除，等价旧的单类型 400 跳过）。
    """
    from biz.handler.graph_search import _collect_filtered_subgraph
    from infra.graph_db import TRSGraphClient

    adjacency = {
        "c": [("r1", "a1"), ("r2", "a2")],
        "a1": [("r3", "x1")],
        "a2": [("r4", "x2")],
    }
    fake = _CountingClient(adjacency)

    subgraph = _collect_filtered_subgraph(
        cast(TRSGraphClient, fake), "c", ["REL", "R2", "R3"], 2, 4, "both"
    )

    assert subgraph is not None
    # 每跳一次批量邻接：hop1 覆盖 {c}×3 类型，hop2 覆盖 {a1,a2}×3 类型
    assert fake.bulk_edge_calls == [
        (["c"], ["REL", "R2", "R3"]),
        (["a1", "a2"], ["REL", "R2", "R3"]),
    ]
    # 批量完整（未截断）→ 零单源 REST 补查
    assert fake.rest_refills == []
    assert {e.id for e in subgraph["edges"]} == {"r1", "r2", "r3", "r4"}
    assert {n.id for n in subgraph["nodes"]} == {"c", "a1", "a2", "x1", "x2"}


def test_collect_filtered_subgraph_refills_starved_pair_on_truncation() -> None:
    """批量被行上限截断时，被挤掉的源必须回退单源 REST 补查（反饿死）。

    截断时任何配额未满的组合都会触发一次补查（真稀疏的组合补查无害：
    回放同一批边全被去重跳过）——这正是用「行数==上限」判截断的代价，
    换来的是超高度数源挤不掉任何源的配额。补查后结果集与完整批量一致。
    """
    from biz.handler.graph_search import _collect_filtered_subgraph
    from infra.graph_db import TRSGraphClient

    adjacency = {
        "c": [("r1", "a1"), ("r2", "a2")],
        "a1": [("r3", "x1")],
        "a2": [("r4", "x2")],
    }
    fake = _CountingClient(adjacency, truncated=True, starve={"a2"})

    subgraph = _collect_filtered_subgraph(cast(TRSGraphClient, fake), "c", ["REL"], 2, 4, "both")

    assert subgraph is not None
    # hop1 (c,REL)：配额 4 只收 2 条 → 补查（回放 r1/r2 全 seen，无害）；
    # hop2 (a1,REL) 同理；(a2,REL) 行被挤掉 → 补查救回 r4
    assert fake.rest_refills == [("c", "REL"), ("a1", "REL"), ("a2", "REL")]
    # 被挤掉的 a2 经补查仍拿到配额：结果集与完整批量完全一致
    clean = _CountingClient(adjacency)
    subgraph_clean = _collect_filtered_subgraph(
        cast(TRSGraphClient, clean), "c", ["REL"], 2, 4, "both"
    )
    assert {e.id for e in subgraph["edges"]} == {e.id for e in subgraph_clean["edges"]}
    assert {n.id for n in subgraph["nodes"]} == {n.id for n in subgraph_clean["nodes"]}
    assert {e.id for e in subgraph["edges"]} == {"r1", "r2", "r3", "r4"}


def test_collect_filtered_subgraph_no_refill_when_batch_complete() -> None:
    """完整批量（未截断）里没有的组合就是真无边：配额未满也不回源。"""
    from biz.handler.graph_search import _collect_filtered_subgraph
    from infra.graph_db import TRSGraphClient

    fake = _CountingClient({"c": [("r1", "a1")]})  # a1 无任何边

    subgraph = _collect_filtered_subgraph(cast(TRSGraphClient, fake), "c", ["REL"], 2, 4, "both")

    assert subgraph is not None
    assert fake.rest_refills == []  # 未截断 → 零补查
    assert {e.id for e in subgraph["edges"]} == {"r1"}


def test_collect_filtered_subgraph_rest_fallback_when_batch_errors() -> None:
    """批量语句失败不 500：退回逐组合 REST（旧路径），结果不受影响。"""
    from biz.handler.graph_search import _collect_filtered_subgraph
    from infra.graph_db import TRSGraphClient

    adjacency = {
        "c": [("r1", "a1"), ("r2", "a2")],
        "a1": [("r3", "x1")],
    }
    fake = _CountingClient(adjacency, bulk_raises=True)

    subgraph = _collect_filtered_subgraph(cast(TRSGraphClient, fake), "c", ["REL"], 2, 4, "both")

    assert subgraph is not None
    assert fake.bulk_edge_calls  # 批量确实发起过（每跳一次）
    # 全部组合走单源 REST 补查（与旧逐组合路径同调用形状）
    assert ("c", "REL") in fake.rest_refills and ("a1", "REL") in fake.rest_refills
    assert {e.id for e in subgraph["edges"]} == {"r1", "r2", "r3"}
    assert {n.id for n in subgraph["nodes"]} == {"c", "a1", "a2", "x1"}


def test_query_endpoints_return_429_envelope_when_overloaded(monkeypatch) -> None:
    """公共执行预算过载时返回业务码 429（图查询过载）——快速拒绝可见，
    而不是在无界排队里拖到上游超时（网关 502）。"""

    from contextlib import asynccontextmanager

    import biz.handler.graph_search as graph_search_module
    from infra.graph_exec_budget import GraphExecOverloaded

    @asynccontextmanager
    async def _always_overloaded():
        raise GraphExecOverloaded("图查询过载：等待队列已满，请稍后重试")
        yield  # pragma: no cover

    monkeypatch.setattr(graph_search_module, "graph_exec_slot", _always_overloaded)

    # 名额获取发生在任何图客户端调用之前：无需真实 trs 连接
    response = client.get(f"{BASE_URL}/nodes/{NODE_ID}")

    assert response.status_code == 200  # 项目统一：HTTP 200 + 业务码承载错误
    body = response.json()
    assert body["code"] == 429
    assert body["success"] is False
    assert "图查询过载" in body["msg"]


def test_stats_endpoint_reports_overload_from_background_scan(monkeypatch) -> None:
    """统计扫描同样走预算：过载时 get_stats 返回 429 包络（缓存未命中路径）。"""

    from contextlib import asynccontextmanager

    import biz.handler.graph_search as graph_search_module
    from infra.graph_exec_budget import GraphExecOverloaded

    monkeypatch.setattr(graph_search_module, "_stats_cache", {})
    monkeypatch.setattr(graph_search_module, "_stats_refreshing", set())

    @asynccontextmanager
    async def _always_overloaded():
        raise GraphExecOverloaded("图查询过载：排队超过 10s，请稍后重试")
        yield  # pragma: no cover

    monkeypatch.setattr(graph_search_module, "graph_exec_slot", _always_overloaded)

    response = client.get(f"{BASE_URL}/stats", params={"refresh": "false"})

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 429
    assert body["success"] is False
