"""Unit tests for infra.graph_db repository and helpers."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

import infra.graph_db as graph_pkg
from infra.graph_db import TRSGraphClient, close_trs_graph_client, get_trs_graph_client
from infra.graph_db.config import TRSGraphSettings
from infra.graph_db.convert import (
    _build_node_create_body,
    _parse_edge_id,
    _strip_quotes,
    _trs_edge_to_model,
    _trs_node_to_model,
)
from infra.graph_db.exceptions import (
    GraphConnectionError,
    GraphNotFoundError,
    GraphRepoError,
    GraphRequestError,
)
from infra.graph_db.models import (
    GraphConstraintSpec,
    GraphEdge,
    GraphIndexSpec,
    GraphNode,
    GraphPagedResult,
    GraphQueryResult,
)


class TestExceptions:
    def test_hierarchy(self):
        assert issubclass(GraphConnectionError, GraphRepoError)
        assert issubclass(GraphNotFoundError, GraphRepoError)
        assert issubclass(GraphRequestError, GraphRepoError)

    def test_request_error_carries_status_and_body(self):
        err = GraphRequestError("boom", status_code=500, body="oops")
        assert err.status_code == 500
        assert err.body == "oops"


class TestModels:
    def test_node_defaults(self):
        n = GraphNode(id="1")
        assert n.id == "1"
        assert n.labels == []
        assert n.properties == {}

    def test_edge_defaults(self):
        e = GraphEdge(id="a->b@0", type="KNOWS", source_id="a", target_id="b")
        assert e.properties == {}

    def test_paged_result_fields(self):
        p = GraphPagedResult(items=[], total=0, limit=100, offset=0)
        assert p.total == 0

    def test_query_result_defaults(self):
        q = GraphQueryResult()
        assert q.records == []
        assert q.summary is None


class TestSettings:
    def test_defaults(self, monkeypatch):
        for k in (
            "TRS_GRAPH_BASE_URL",
            "TRS_GRAPH_SPACE",
            "TRS_GRAPH_API_KEY",
            "TRS_GRAPH_TIMEOUT",
        ):
            monkeypatch.delenv(k, raising=False)
        s = TRSGraphSettings.from_env()
        assert s.base_url == "http://localhost:8090"
        assert s.space == "dev"
        assert s.api_key is None
        assert s.timeout == 30

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("TRS_GRAPH_BASE_URL", "http://graph:8090")
        monkeypatch.setenv("TRS_GRAPH_SPACE", "tech-kg")
        monkeypatch.setenv("TRS_GRAPH_API_KEY", "secret")
        monkeypatch.setenv("TRS_GRAPH_TIMEOUT", "10")
        s = TRSGraphSettings.from_env()
        assert s.base_url == "http://graph:8090"
        assert s.space == "tech-kg"
        assert s.api_key == "secret"
        assert s.timeout == 10


class TestConvert:
    def test_node_to_model(self):
        n = _trs_node_to_model({"id": "42", "labels": ["Person"], "properties": {"name": "Alice"}})
        assert isinstance(n, GraphNode)
        assert n.id == "42"
        assert n.labels == ["Person"]
        assert n.properties == {"name": "Alice"}

    def test_node_to_model_defaults(self):
        n = _trs_node_to_model({"id": "1"})
        assert n.labels == []
        assert n.properties == {}

    def test_edge_to_model(self):
        e = _trs_edge_to_model(
            {
                "id": "a->b@0",
                "type": "KNOWS",
                "sourceId": "a",
                "targetId": "b",
                "properties": {"x": 1},
            }
        )
        assert e.type == "KNOWS"
        assert e.source_id == "a"
        assert e.target_id == "b"
        assert e.properties == {"x": 1}

    def test_build_node_create_body_no_labels(self):
        assert _build_node_create_body([], {"k": "v"}) == {
            "labels": ["Vertex"],
            "properties": {"k": "v"},
        }

    def test_build_node_create_body_no_props(self):
        assert _build_node_create_body(["Tag"]) == {"labels": ["Tag"], "properties": {}}

    def test_parse_edge_id(self):
        assert _parse_edge_id("a->b@3") == ("a", "b", 3)

    def test_parse_edge_id_no_ranking(self):
        assert _parse_edge_id("a->b") == ("a", "b", 0)

    def test_strip_quotes(self):
        assert _strip_quotes('"Person"') == "Person"
        assert _strip_quotes('""Person""') == "Person"

    def test_strip_quotes_non_string(self):
        assert _strip_quotes(5) == "5"


def _make_repo(handler, *, api_key=None):
    """Build a TRSGraphClient backed by a MockTransport handler and connect it."""
    settings = TRSGraphSettings(base_url="http://test", space="test", api_key=api_key, timeout=5)
    repo = TRSGraphClient(settings, transport=httpx.MockTransport(handler))
    repo.connect()
    return repo


def _health_ok(request):
    if request.url.path == "/health":
        return httpx.Response(200, json={"status": "UP"})
    return httpx.Response(404)


class TestConnection:
    def test_connect_sets_headers(self):
        seen = {}

        def handler(request):
            seen["headers"] = request.headers
            return _health_ok(request)

        repo = _make_repo(handler, api_key="secret")
        assert seen["headers"]["x-graph-space"] == "test"
        assert seen["headers"]["x-api-key"] == "secret"
        assert repo.is_connected()
        repo.close()

    def test_connect_health_failure_raises(self):
        def handler(request):
            return httpx.Response(503)

        settings = TRSGraphSettings(base_url="http://test", space="s")
        repo = TRSGraphClient(settings, transport=httpx.MockTransport(handler))
        with pytest.raises(GraphConnectionError):
            repo.connect()

    def test_request_before_connect_raises(self):
        repo = TRSGraphClient(TRSGraphSettings())
        with pytest.raises(GraphConnectionError):
            repo._request("GET", "/x")

    def test_request_404_raises_not_found(self):
        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            return httpx.Response(404)

        repo = _make_repo(handler)
        with pytest.raises(GraphNotFoundError):
            repo._request("GET", "/api/v1/nodes/1")
        repo.close()

    def test_request_500_raises_request_error(self):
        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            return httpx.Response(500, text="boom")

        repo = _make_repo(handler)
        with pytest.raises(GraphRequestError) as exc:
            repo._request("GET", "/api/v1/nodes/1")
        assert exc.value.status_code == 500
        repo.close()

    def test_request_transport_error_maps_to_connection_error(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            raise httpx.ConnectError("boom")

        repo = _make_repo(handler)
        with pytest.raises(GraphConnectionError, match=r"ConnectError: boom"):
            repo._request("GET", "/api/v1/nodes/1")
        repo.close()


class TestRequestTimeout:
    """_request 不传 timeout 时必须落回 settings.timeout。

    httpx 的 request(timeout=None) 是"禁用超时"而非"沿用客户端默认"（默认值
    哨兵是 USE_CLIENT_DEFAULT）——直接透传 None 会把构造函数里配的默认超时
    整体关掉，挂死的图查询将无限占用调用线程与连接。
    """

    @staticmethod
    def _timeout_capturing_handler(seen):
        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            seen["timeout"] = dict(request.extensions.get("timeout") or {})
            return httpx.Response(200, json={})

        return handler

    def test_default_request_uses_settings_timeout(self):
        seen = {}
        repo = _make_repo(self._timeout_capturing_handler(seen))  # settings.timeout = 5
        repo._request("GET", "/api/v1/nodes/1")
        assert seen["timeout"] == {"connect": 5, "read": 5, "write": 5, "pool": 5}
        repo.close()

    def test_explicit_timeout_overrides_settings(self):
        seen = {}
        repo = _make_repo(self._timeout_capturing_handler(seen))
        repo._request("GET", "/api/v1/nodes/1", timeout=120)
        assert seen["timeout"] == {"connect": 120, "read": 120, "write": 120, "pool": 120}
        repo.close()

    def test_read_timeout_enforced_against_hanging_server(self):
        """端到端行为验证：连接建立但响应迟迟不来的端点在 settings.timeout 内被掐断。"""

        class _HangingHandler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format, *args):  # noqa: A002 - 参数名与基类签名一致
                pass

            def do_GET(self):
                if self.path == "/health":
                    body = b'{"status": "UP"}'
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                time.sleep(15)  # 模拟 trs-graph 慢查询：连接已建、响应迟迟不来
                try:
                    self.send_response(200)
                    self.send_header("Content-Length", "2")
                    self.end_headers()
                    self.wfile.write(b"{}")
                except Exception:
                    pass  # 客户端已超时断开，写回应失败是预期

        server = ThreadingHTTPServer(("127.0.0.1", 0), _HangingHandler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            settings = TRSGraphSettings(
                base_url=f"http://127.0.0.1:{server.server_address[1]}",
                space="test",
                timeout=1,
            )
            repo = TRSGraphClient(settings)
            repo.connect()
            started = time.monotonic()
            with pytest.raises(GraphConnectionError, match="ReadTimeout"):
                repo.get_node("person_x")
            elapsed = time.monotonic() - started
            # 1s 超时必须生效：远小于服务端 15s 的挂死窗口（宽松上界留给 CI 抖动）
            assert elapsed < 10, f"timeout took {elapsed:.1f}s to fire"
            repo.close()
        finally:
            server.shutdown()
            server.server_close()


class TestNodeCrud:
    def test_create_node(self):
        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            assert request.url.path == "/api/v1/nodes"
            assert request.method == "POST"
            assert json.loads(request.content) == {
                "labels": ["Person"],
                "properties": {"name": "Alice"},
            }
            return httpx.Response(
                200, json={"id": "1", "labels": ["Person"], "properties": {"name": "Alice"}}
            )

        repo = _make_repo(handler)
        n = repo.create_node(["Person"], {"name": "Alice"})
        assert n.id == "1"
        repo.close()

    def test_merge_node(self):
        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            assert request.url.path == "/api/v1/nodes/merge"
            return httpx.Response(
                200, json={"id": "1", "labels": ["Person"], "properties": {"name": "Alice"}}
            )

        repo = _make_repo(handler)
        n = repo.merge_node(["Person"], {"name": "Alice"}, {"age": 30})
        assert n.properties == {"name": "Alice"}
        repo.close()

    def test_create_node_injects_vid_when_missing(self):
        """Without a vid/id/name key the client must inject one so the service
        can read the node back (otherwise the service 404s on its internal
        read-back). The first property value is promoted to the vid, matching
        the techkg natural-key-as-vid convention."""
        seen = {}

        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            seen["body"] = json.loads(request.content)
            props = seen["body"]["properties"]
            vid = props["vid"]
            return httpx.Response(200, json={"id": vid, "labels": ["Org"], "properties": props})

        repo = _make_repo(handler)
        n = repo.create_node(["Org"], {"org_id": "ENT001", "name_cn": "Acme"})
        # org_id value promoted to vid; org_id kept as a tag property
        assert seen["body"]["properties"]["vid"] == "ENT001"
        assert seen["body"]["properties"]["org_id"] == "ENT001"
        assert n.id == "ENT001"
        repo.close()

    def test_merge_node_injects_vid_from_identity(self):
        seen = {}

        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            seen["body"] = json.loads(request.content)
            vid = seen["body"]["identityProps"]["vid"]
            return httpx.Response(
                200, json={"id": vid, "labels": ["Scholar"], "properties": {"scholar_id": vid}}
            )

        repo = _make_repo(handler)
        n = repo.merge_node(["Scholar"], {"scholar_id": "E10001"}, {"name_zh": "专家"})
        assert seen["body"]["identityProps"]["vid"] == "E10001"
        assert n.id == "E10001"
        repo.close()

    def test_get_node_found(self):
        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            return httpx.Response(200, json={"id": "1", "labels": ["Person"], "properties": {}})

        repo = _make_repo(handler)
        assert repo.get_node("1") is not None
        repo.close()

    def test_get_node_missing_returns_none(self):
        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            return httpx.Response(404)

        repo = _make_repo(handler)
        assert repo.get_node("999") is None
        repo.close()

    def test_get_nodes_by_label(self):
        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            assert request.url.path == "/api/v1/nodes/label/Person"
            assert request.url.params["limit"] == "10"
            # real trs-graph-service shape: total nested under "page"
            return httpx.Response(
                200,
                json={
                    "items": [{"id": "1", "labels": ["Person"], "properties": {}}],
                    "page": {"offset": 0, "limit": 10, "total": 1, "hasNext": False},
                },
            )

        repo = _make_repo(handler)
        page = repo.get_nodes_by_label("Person", limit=10, offset=0)
        assert page.total == 1
        assert page.items[0].id == "1"
        repo.close()

    def test_get_nodes_by_label_total_exceeds_items(self):
        """total must come from page.total, not fall back to len(items)."""

        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            return httpx.Response(
                200,
                json={
                    "items": [{"id": "1", "labels": ["Person"], "properties": {}}],
                    "page": {"offset": 0, "limit": 1, "total": 200, "hasNext": True},
                },
            )

        repo = _make_repo(handler)
        page = repo.get_nodes_by_label("Person", limit=1)
        assert page.total == 200
        assert len(page.items) == 1
        repo.close()

    def test_find_nodes(self):
        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            assert request.url.path == "/api/v1/nodes/find"
            return httpx.Response(200, json={"items": [], "total": 0})

        repo = _make_repo(handler)
        page = repo.find_nodes(["Person"], {"name": "Alice"})
        assert page.items == []
        repo.close()

    def test_update_node_fetches_label(self):
        calls = []

        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            calls.append((request.method, request.url.path))
            if request.method == "GET":
                return httpx.Response(200, json={"id": "1", "labels": ["Person"], "properties": {}})
            return httpx.Response(
                200, json={"id": "1", "labels": ["Person"], "properties": {"age": 30}}
            )

        repo = _make_repo(handler)
        n = repo.update_node("1", {"age": 30})
        assert ("GET", "/api/v1/nodes/1") in calls
        assert ("PUT", "/api/v1/nodes/1") in calls
        assert n.properties["age"] == 30
        repo.close()

    def test_update_node_missing_raises(self):
        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            return httpx.Response(404)

        repo = _make_repo(handler)
        with pytest.raises(GraphNotFoundError):
            repo.update_node("999", {"age": 30})
        repo.close()

    def test_update_node_response_without_id_merges_existing(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            if request.method == "GET":
                return httpx.Response(
                    200, json={"id": "1", "labels": ["Person"], "properties": {"name": "Alice"}}
                )
            # PUT returns a body without "id" -> triggers the fallback merge branch
            return httpx.Response(200, json={"updated": True})

        repo = _make_repo(handler)
        n = repo.update_node("1", {"age": 30})
        assert n.id == "1"
        assert n.properties == {"name": "Alice", "age": 30}
        repo.close()

    def test_delete_node(self):
        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            assert request.url.path == "/api/v1/nodes/1"
            return httpx.Response(204)

        repo = _make_repo(handler)
        assert repo.delete_node("1") is True
        repo.close()

    def test_delete_node_missing_returns_false(self):
        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            return httpx.Response(404)

        repo = _make_repo(handler)
        assert repo.delete_node("999") is False
        repo.close()


class TestBulkNodeFetch:
    """get_nodes_bulk：FETCH PROP ON * 批量取点（子图补点去 N+1，2026-09-23）。"""

    @staticmethod
    def _bulk_handler(captured: list):
        """解析 FETCH 语句里的 VID 列表并回放 vertex 记录；ghost_ 前缀视为悬挂点。"""

        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            assert request.url.path == "/api/v1/query/read"
            query = json.loads(request.content)["query"]
            captured.append(query)
            vid_list = query.split("FETCH PROP ON * ", 1)[1].rsplit(" YIELD", 1)[0]
            vids = [v for v in vid_list.split(", ") if v]
            records = [
                {"v": {"id": vid.strip('"'), "labels": ["Person"], "properties": {"k": "x"}}}
                for vid in vids
                if not vid.strip('"').startswith("ghost_")
            ]
            return httpx.Response(200, json={"records": records, "summary": None})

        return handler

    def test_bulk_fetch_chunks_into_one_round_trip_per_block(self):
        """250 个 VID 按块 200 分两条语句，各自一次往返，全部取到。"""
        captured: list[str] = []
        repo = _make_repo(self._bulk_handler(captured))

        found = repo.get_nodes_bulk([f"person_{i}" for i in range(250)])

        assert len(captured) == 2
        first_vids = captured[0].split("FETCH PROP ON * ", 1)[1].rsplit(" YIELD", 1)[0]
        second_vids = captured[1].split("FETCH PROP ON * ", 1)[1].rsplit(" YIELD", 1)[0]
        assert first_vids.count(", ") == 199  # 第一块 200 个
        assert second_vids.count(", ") == 49  # 第二块 50 个
        assert len(found) == 250
        assert found["person_0"].labels == ["Person"]
        assert found["person_249"].properties == {"k": "x"}
        repo.close()

    def test_bulk_fetch_missing_vids_absent_from_result(self):
        """查不到的 VID（悬挂点）不进结果，与单查 get_node 返回 None 等价。"""
        captured: list[str] = []
        repo = _make_repo(self._bulk_handler(captured))

        found = repo.get_nodes_bulk(["person_1", "ghost_a", "ghost_b", "person_2"])

        assert set(found) == {"person_1", "person_2"}
        repo.close()

    def test_bulk_fetch_dedupes_and_skips_empty(self):
        """重复/空 VID 只取一次，不重复下语句。"""
        captured: list[str] = []
        repo = _make_repo(self._bulk_handler(captured))

        found = repo.get_nodes_bulk(["a", "a", "", "b"])

        vid_list = captured[0].split("FETCH PROP ON * ", 1)[1].rsplit(" YIELD", 1)[0]
        assert vid_list == '"a", "b"'
        assert set(found) == {"a", "b"}
        repo.close()

    def test_bulk_fetch_empty_input_makes_no_request(self):
        captured: list[str] = []
        repo = _make_repo(self._bulk_handler(captured))

        assert repo.get_nodes_bulk([]) == {}
        assert captured == []
        repo.close()

    def test_bulk_fetch_statement_shape_and_slash_vids(self):
        """语句形状 USE + FETCH PROP ON * + YIELD vertex；斜杠 VID 走查询端点。"""
        captured: list[str] = []
        repo = _make_repo(self._bulk_handler(captured))

        found = repo.get_nodes_bulk(["paper_ref_10.1111/jth.14768", "person_1"])

        query = captured[0]
        assert query.startswith("USE test; FETCH PROP ON * ")
        assert query.endswith(" YIELD vertex AS v")
        assert '"paper_ref_10.1111/jth.14768"' in query
        assert set(found) == {"person_1", "paper_ref_10.1111/jth.14768"}
        repo.close()


class TestBulkEdgeFetch:
    """get_edges_bulk：多源多类型 GO 批量取邻接（子图去 N×M 往返，2026-09-23）。

    方向按「正向 + REVERSELY」两条语句拆分：GO 的 $^ 恒为遍历起点（实测
    BIDIRECT/REVERSELY 下入边 $^=起点而非存储源），单条 BIDIRECT 无法还原
    存储真方向；两条语句各自规范化后边 id 与 REST 同款，跨跳回边去重不破。
    """

    @pytest.fixture(autouse=True)
    def _clear_edge_types_cache(self):
        # edge_types() 是模块级 TTL 缓存，space 均为 "test"——不清理会读到
        # 前一个用例缓存的类型列表，语句断言失真。
        client_mod = __import__("infra.graph_db.client", fromlist=["_edge_types_cache"])
        client_mod._edge_types_cache.clear()
        yield
        client_mod._edge_types_cache.clear()

    @staticmethod
    def _bulk_handler(captured: list, rows: list):
        """回放行（(是否属于 REVERSELY 语句, 记录) 列表）。

        按语句的方向子句与源列表过滤回放，尊重 LIMIT 截行——模拟 Nebula
        「REVERSELY 行的 $^ 仍是遍历起点」的真实返回形状。
        """

        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            if request.url.path == "/api/v1/schema/edge-types":
                return httpx.Response(200, json=[{"Name": "R1"}, {"Name": "R2"}])
            assert request.url.path == "/api/v1/query/read"
            query = json.loads(request.content)["query"]
            captured.append(query)
            limit = int(query.rsplit("| LIMIT ", 1)[1])
            reverse = "REVERSELY" in query
            roots_part = query.split(" FROM ", 1)[1].split(" OVER ", 1)[0]
            roots = {r.strip('"') for r in roots_part.split(", ")}
            records = [rec for is_rev, rec in rows if is_rev == reverse and rec["src"] in roots]
            return httpx.Response(200, json={"records": records[:limit], "summary": None})

        return handler

    def test_bulk_edges_statement_and_grouping(self):
        """both 拆两条语句（正向+REVERSELY）；类型滤除；按 (起点,类型) 分组。"""
        captured: list[str] = []
        rows = [
            # 正向语句的行：起点即存储源
            (False, {"src": "a", "dst": "x", "etype": "R1", "rk": 0, "props": {"w": 1}}),
            (False, {"src": "a", "dst": "y", "etype": "R1", "rk": 3, "props": None}),
            # REVERSELY 语句的行：$^=起点（存储目标），对端才是存储源
            (True, {"src": "b", "dst": "z", "etype": "R2", "rk": 0, "props": {"k": "v"}}),
        ]
        repo = _make_repo(self._bulk_handler(captured, rows))

        grouped, truncated = repo.get_edges_bulk(
            ["a", "b"], ["R1", "R2", "MISSING_TYPE", "R1); DROP SPACE dev2"], direction="both"
        )

        # both → 两条语句：先正向（无子句）后 REVERSELY
        assert len(captured) == 2
        plain, reverse = captured
        for query in (plain, reverse):
            assert query.startswith("USE test; GO 1 STEP FROM ")
            assert '"a", "b"' in query  # 多源同语句
            assert "OVER `R1`, `R2` " in query  # 不在 schema 的类型滤除
            assert "BIDIRECT" not in query  # BIDIRECT 无法还原存储方向，弃用
            assert "DROP SPACE" not in query  # 非法标识符过不了白名单
            assert "rank(edge) AS rk" in query and "properties(edge) AS props" in query
            assert query.endswith("| LIMIT 4096")
        assert "REVERSELY" not in plain
        assert "OVER `R1`, `R2` REVERSELY" in reverse
        assert truncated is False
        # 按 (起点, 类型) 分组；正向行起点即存储源，id 用 REST 同款 src->dst@rank
        assert [e.id for e in grouped[("a", "R1")]] == ["a->x@0", "a->y@3"]
        assert grouped[("a", "R1")][0].properties == {"w": 1}
        assert grouped[("a", "R1")][1].properties == {}  # 非 dict 属性兜底空
        # REVERSELY 行规范化为存储真方向：源 z → 目标 b，分组键仍是起点 b
        edge = grouped[("b", "R2")][0]
        assert edge.id == "z->b@0" and edge.source_id == "z" and edge.target_id == "b"
        assert edge.properties == {"k": "v"}
        assert ("a", "R2") not in grouped and ("b", "R1") not in grouped
        repo.close()

    def test_bulk_edges_reverse_row_matches_rest_edge_id(self):
        """同一条边从两端批量查：REVERSELY 行规范化后的 id 与正向行一致。

        这是跨跳回边去重的前提——BIDIRECT 版本此处会得到两个翻转 id，
        同一条边被收两遍（2026-09-23 实测边集 81 vs 31 的根因之一）。
        """
        captured: list[str] = []
        rows = [
            (False, {"src": "a", "dst": "x", "etype": "R1", "rk": 7, "props": {}}),
            (True, {"src": "x", "dst": "a", "etype": "R1", "rk": 7, "props": {}}),
        ]
        repo = _make_repo(self._bulk_handler(captured, rows))

        grouped, _truncated = repo.get_edges_bulk(["a", "x"], ["R1"], direction="both")

        from_a = grouped[("a", "R1")][0]
        from_x = grouped[("x", "R1")][0]
        assert from_a.id == from_x.id == "a->x@7"
        assert (
            (from_x.source_id, from_x.target_id)
            == ("a", "x")
            == (
                from_a.source_id,
                from_a.target_id,
            )
        )
        repo.close()

    def test_bulk_edges_direction_mapping(self):
        """in→单条 REVERSELY、out→单条正向、both→两条（不用 BIDIRECT）。"""
        captured: list[str] = []
        repo = _make_repo(self._bulk_handler(captured, {}))

        repo.get_edges_bulk(["a"], ["R1"], direction="in")
        assert len(captured) == 1
        assert "REVERSELY" in captured[0] and "BIDIRECT" not in captured[0]

        repo.get_edges_bulk(["a"], ["R1"], direction="out")
        assert len(captured) == 2
        assert "REVERSELY" not in captured[1] and "BIDIRECT" not in captured[1]

        repo.get_edges_bulk(["a"], ["R1"], direction="both")
        assert len(captured) == 4
        assert "REVERSELY" not in captured[2] and "REVERSELY" in captured[3]
        repo.close()

    def test_bulk_edges_truncated_flag_follows_row_cap(self):
        """任一语句回放行数达 row_cap 即截断标志置位（调用方据此单源补查）。"""
        captured: list[str] = []
        rows = [
            (False, {"src": "a", "dst": f"n{i}", "etype": "R1", "rk": 0, "props": {}})
            for i in range(5)
        ] + [
            (True, {"src": "a", "dst": f"m{i}", "etype": "R1", "rk": 0, "props": {}})
            for i in range(4)
        ]
        repo = _make_repo(self._bulk_handler(captured, rows))

        grouped, truncated = repo.get_edges_bulk(["a"], ["R1"], row_cap=4)
        assert truncated is True  # 正向 5 行 > 4 截断（REVERSELY 4 行恰好触顶同样置位）
        assert len(grouped[("a", "R1")]) == 8  # 两条语句各按 LIMIT 截行后合并

        grouped, truncated = repo.get_edges_bulk(["a"], ["R1"], row_cap=10)
        assert truncated is False
        assert len(grouped[("a", "R1")]) == 9
        repo.close()

    def test_bulk_edges_empty_or_no_overlap_makes_no_query(self):
        """空源列表 / 类型全不在 schema → 不发查询语句（返回空、未截断）。"""
        captured: list[str] = []
        repo = _make_repo(self._bulk_handler(captured, {}))

        assert repo.get_edges_bulk([], ["R1"]) == ({}, False)
        assert repo.get_edges_bulk(["a"], ["NOPE"]) == ({}, False)
        assert captured == []
        repo.close()


class TestTraversal:
    def test_get_node_edges(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            assert request.url.path == "/api/v1/traversal/1/edges"
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "1->2@0",
                        "type": "KNOWS",
                        "sourceId": "1",
                        "targetId": "2",
                        "properties": {},
                    }
                ],
            )

        repo = _make_repo(handler)
        edges = repo.get_node_edges("1", direction="both")
        assert len(edges) == 1
        repo.close()

    def test_get_neighbours(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            assert request.url.path == "/api/v1/traversal/1/neighbours"
            return httpx.Response(200, json=[{"id": "2", "labels": ["Person"], "properties": {}}])

        repo = _make_repo(handler)
        nbrs = repo.get_neighbours("1")
        assert nbrs[0].id == "2"
        repo.close()

    def test_shortest_path_backfills_incomplete_nodes(self):
        calls = []

        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            if request.url.path == "/api/v1/traversal/path/shortest":
                return httpx.Response(
                    200,
                    json={
                        "nodes": [
                            {"id": "1", "labels": [], "properties": {}},
                            {"id": "2", "labels": ["P"], "properties": {"x": 1}},
                        ],
                        "edges": [],
                    },
                )
            if request.url.path == "/api/v1/nodes/1":
                calls.append("backfill")
                return httpx.Response(
                    200, json={"id": "1", "labels": ["Person"], "properties": {"name": "A"}}
                )
            return httpx.Response(404)

        repo = _make_repo(handler)
        path = repo.shortest_path("1", "2")
        assert path is not None
        assert path.nodes[0].labels == ["Person"]
        assert "backfill" in calls
        assert path.nodes[1].properties == {"x": 1}
        repo.close()

    def test_shortest_path_missing_returns_none(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(404)

        repo = _make_repo(handler)
        assert repo.shortest_path("1", "2") is None
        repo.close()

    def test_shortest_path_passes_edgeType_param(self):
        """The traversal shortest-path endpoint expects ?edgeType= (not ?type=);
        sending the wrong name silently ignores the edge-type filter."""

        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            assert request.url.path == "/api/v1/traversal/path/shortest"
            assert request.url.params["edgeType"] == "KNOWS"
            assert "type" not in request.url.params
            return httpx.Response(
                200,
                json={
                    "nodes": [
                        {"id": "1", "labels": ["P"], "properties": {}},
                        {"id": "2", "labels": ["P"], "properties": {}},
                    ],
                    "edges": [],
                },
            )

        repo = _make_repo(handler)
        path = repo.shortest_path("1", "2", edge_type="KNOWS")
        assert path is not None
        assert len(path.nodes) == 2
        repo.close()


class TestEdgeCrud:
    def test_create_edge(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            body = json.loads(request.content)
            assert body == {"type": "KNOWS", "sourceId": "1", "targetId": "2", "properties": {}}
            return httpx.Response(
                200,
                json={
                    "id": "1->2@0",
                    "type": "KNOWS",
                    "sourceId": "1",
                    "targetId": "2",
                    "properties": {},
                },
            )

        repo = _make_repo(handler)
        e = repo.create_edge("1", "2", "KNOWS")
        assert e.id == "1->2@0"
        repo.close()

    def test_get_edge_with_type(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            assert request.url.path == "/api/v1/edges/1/2"
            assert request.url.params["type"] == "KNOWS"
            return httpx.Response(
                200,
                json={
                    "id": "1->2@0",
                    "type": "KNOWS",
                    "sourceId": "1",
                    "targetId": "2",
                    "properties": {},
                },
            )

        repo = _make_repo(handler)
        e = repo.get_edge("1->2@0", edge_type="KNOWS")
        assert e is not None
        repo.close()

    def test_get_edge_missing_returns_none(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(404)

        repo = _make_repo(handler)
        assert repo.get_edge("1->2@0", edge_type="KNOWS") is None
        repo.close()

    def test_update_edge_without_type_looks_up(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            if request.method == "GET":
                return httpx.Response(
                    200,
                    json=[
                        {
                            "id": "1->2@0",
                            "type": "KNOWS",
                            "sourceId": "1",
                            "targetId": "2",
                            "properties": {},
                        }
                    ],
                )
            return httpx.Response(
                200,
                json={
                    "id": "1->2@0",
                    "type": "KNOWS",
                    "sourceId": "1",
                    "targetId": "2",
                    "properties": {"w": 5},
                },
            )

        repo = _make_repo(handler)
        e = repo.update_edge("1->2@0", {"w": 5})
        assert e.properties["w"] == 5
        repo.close()

    def test_delete_edge(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            if request.method == "GET":
                return httpx.Response(
                    200,
                    json=[
                        {
                            "id": "1->2@0",
                            "type": "KNOWS",
                            "sourceId": "1",
                            "targetId": "2",
                            "properties": {},
                        }
                    ],
                )
            assert request.url.params["type"] == "KNOWS"
            return httpx.Response(204)

        repo = _make_repo(handler)
        assert repo.delete_edge("1->2@0") is True
        repo.close()

    def test_delete_edge_missing_returns_false(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            if request.method == "GET":
                return httpx.Response(404)
            return httpx.Response(404)

        repo = _make_repo(handler)
        assert repo.delete_edge("1->2@0") is False
        repo.close()

    def test_get_edge_without_type_scans_node_edges(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            assert request.url.path == "/api/v1/traversal/1/edges"
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "1->3@0",
                        "type": "KNOWS",
                        "sourceId": "1",
                        "targetId": "3",
                        "properties": {},
                    },
                    {
                        "id": "1->2@0",
                        "type": "KNOWS",
                        "sourceId": "1",
                        "targetId": "2",
                        "properties": {},
                    },
                ],
            )

        repo = _make_repo(handler)
        e = repo.get_edge("1->2@0")  # no edge_type -> scan branch
        assert e is not None
        assert e.target_id == "2"
        repo.close()

    def test_get_edge_without_type_not_found_returns_none(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "1->3@0",
                        "type": "KNOWS",
                        "sourceId": "1",
                        "targetId": "3",
                        "properties": {},
                    }
                ],
            )

        repo = _make_repo(handler)
        assert repo.get_edge("1->9@0") is None
        repo.close()


class TestQuery:
    def test_execute_query(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            assert request.url.path == "/api/v1/query"
            assert json.loads(request.content) == {
                "query": "USE test; MATCH (n) RETURN n",
                "params": {"k": 1},
            }
            return httpx.Response(
                200, json={"records": [{"n": {"id": "1"}}], "summary": {"count": 1}}
            )

        repo = _make_repo(handler)
        r = repo.execute_query("MATCH (n) RETURN n", {"k": 1})
        assert r.records == [{"n": {"id": "1"}}]
        assert r.summary == {"count": 1}
        repo.close()

    def test_rejects_response_from_wrong_space(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(
                200,
                json={
                    "records": [],
                    "summary": {"spaceName": "techkg", "errorCode": 0},
                },
            )

        repo = _make_repo(handler)
        with pytest.raises(GraphRequestError, match="space mismatch"):
            repo.execute_read("SHOW TAGS")
        repo.close()

    def test_execute_read(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            assert request.url.path == "/api/v1/query/read"
            return httpx.Response(200, json={"records": [], "summary": None})

        repo = _make_repo(handler)
        r = repo.execute_read("MATCH (n) RETURN n")
        assert r.records == []
        repo.close()

    def test_execute_write(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            assert request.url.path == "/api/v1/query/write"
            return httpx.Response(200, json={"records": [], "summary": None})

        repo = _make_repo(handler)
        repo.execute_write("CREATE TAG T(name string)")
        repo.close()


class TestBatch:
    def test_batch_create_nodes(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            body = json.loads(request.content)
            assert body["labels"] == ["Person"]
            assert body["items"] == [{"name": "Alice"}, {"name": "Bob"}]
            return httpx.Response(
                200,
                json=[
                    {"id": "1", "labels": ["Person"], "properties": {"name": "Alice"}},
                    {"id": "2", "labels": ["Person"], "properties": {"name": "Bob"}},
                ],
            )

        repo = _make_repo(handler)
        nodes = repo.batch_create_nodes([{"name": "Alice"}, {"name": "Bob"}], ["Person"])
        assert [n.id for n in nodes] == ["1", "2"]
        repo.close()

    def test_batch_create_nodes_empty_response(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(200, json=[])

        repo = _make_repo(handler)
        assert repo.batch_create_nodes([{"name": "A"}], ["Person"]) == []
        repo.close()

    def test_batch_create_edges_flattens_properties(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            body = json.loads(request.content)
            assert body["type"] == "KNOWS"
            assert body["items"][0]["sourceId"] == "1"
            assert body["items"][0]["targetId"] == "2"
            # properties flattened to top level
            assert body["items"][0]["since"] == 2020
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "1->2@0",
                        "type": "KNOWS",
                        "sourceId": "1",
                        "targetId": "2",
                        "properties": {},
                    }
                ],
            )

        repo = _make_repo(handler)
        edges = repo.batch_create_edges(
            [{"source_id": "1", "target_id": "2", "properties": {"since": 2020}}], "KNOWS"
        )
        assert len(edges) == 1
        repo.close()


class TestSchema:
    def test_create_index(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            assert request.url.path == "/api/v1/schema/indexes"
            assert json.loads(request.content) == {
                "label": "Person",
                "properties": ["name"],
                "unique": True,
            }
            return httpx.Response(201)

        repo = _make_repo(handler)
        repo.create_index(GraphIndexSpec(label="Person", properties=["name"], unique=True))
        repo.close()

    def test_list_indexes_strips_quotes(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(
                200,
                json=[{"label": '"Person"', "properties": ['"name"'], "unique": False}],
            )

        repo = _make_repo(handler)
        indexes = repo.list_indexes()
        assert indexes[0].label == "Person"
        assert indexes[0].properties == ["name"]
        repo.close()

    def test_list_indexes_parses_bracket_list_properties(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(
                200,
                json=[{"label": "Person", "properties": ['["name","age"]'], "unique": False}],
            )

        repo = _make_repo(handler)
        indexes = repo.list_indexes()
        assert indexes[0].label == "Person"
        assert indexes[0].properties == ["name", "age"]
        repo.close()

    def test_drop_index(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            assert request.method == "DELETE"
            assert request.url.params["label"] == "Person"
            assert request.url.params["properties"] == "name,age"
            return httpx.Response(204)

        repo = _make_repo(handler)
        repo.drop_index("Person", ["name", "age"])
        repo.close()

    def test_create_constraint(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            assert json.loads(request.content) == {
                "name": "c1",
                "label": "Person",
                "property": "name",
                "kind": "unique",
            }
            return httpx.Response(201)

        repo = _make_repo(handler)
        repo.create_constraint(GraphConstraintSpec(name="c1", label="Person", property="name"))
        repo.close()

    def test_list_constraints_strips_quotes(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(
                200,
                json=[
                    {"name": '"c1"', "label": '"Person"', "property": '"name"', "kind": "unique"}
                ],
            )

        repo = _make_repo(handler)
        cs = repo.list_constraints()
        assert cs[0].name == "c1"
        assert cs[0].label == "Person"
        repo.close()

    def test_drop_constraint(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            assert request.url.path == "/api/v1/schema/constraints/c1"
            return httpx.Response(204)

        repo = _make_repo(handler)
        repo.drop_constraint("c1")
        repo.close()


class TestDbInfo:
    def test_node_count(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            assert request.url.path == "/api/v1/schema/stats/node-count"
            return httpx.Response(200, json={"count": 42})

        repo = _make_repo(handler)
        assert repo.node_count() == 42
        repo.close()

    def test_edge_count(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(200, json={"count": 7})

        repo = _make_repo(handler)
        assert repo.edge_count() == 7
        repo.close()

    def test_edge_count_passes_edgeType_param(self):
        """The service's edge-count endpoint expects ?edgeType= (not ?type=);
        sending the wrong name makes it count ALL edges in the space."""

        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            assert request.url.path == "/api/v1/schema/stats/edge-count"
            assert request.url.params["edgeType"] == "EMPLOYED_BY"
            assert "type" not in request.url.params
            return httpx.Response(200, json={"count": 5})

        repo = _make_repo(handler)
        assert repo.edge_count("EMPLOYED_BY") == 5
        repo.close()

    def test_labels(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(200, json=[{"Name": "Person"}, {"Name": "Tag"}])

        repo = _make_repo(handler)
        assert repo.labels() == ["Person", "Tag"]
        repo.close()

    def test_edge_types_plain_strings(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(200, json=["KNOWS", "LIKES"])

        repo = _make_repo(handler)
        assert repo.edge_types() == ["KNOWS", "LIKES"]
        repo.close()


class TestSingleton:
    def test_get_trs_graph_client_caches(self, monkeypatch):
        # Force connectable settings; patch connect/is_connected to avoid real network.
        monkeypatch.setenv("TRS_GRAPH_BASE_URL", "http://test")
        monkeypatch.setenv("TRS_GRAPH_SPACE", "s")
        monkeypatch.setenv("TRS_GRAPH_API_KEY", "")
        close_trs_graph_client()  # reset any prior singleton
        monkeypatch.setattr(TRSGraphClient, "connect", lambda self: None)
        monkeypatch.setattr(TRSGraphClient, "is_connected", lambda self: True)
        r1 = get_trs_graph_client()
        r2 = get_trs_graph_client()
        assert r1 is r2
        close_trs_graph_client()
        assert graph_pkg._client is None

    def test_get_trs_graph_client_resets_when_connect_fails(self, monkeypatch):
        monkeypatch.setenv("TRS_GRAPH_BASE_URL", "http://test")
        monkeypatch.setenv("TRS_GRAPH_SPACE", "s")
        monkeypatch.setenv("TRS_GRAPH_API_KEY", "")
        close_trs_graph_client()  # reset

        def _fail_connect(self):
            raise GraphConnectionError("service down")

        monkeypatch.setattr(TRSGraphClient, "connect", _fail_connect)
        with pytest.raises(GraphConnectionError):
            get_trs_graph_client()
        assert graph_pkg._client is None
        close_trs_graph_client()


class TestSlashVidNgqlFallback:
    """含 / 的 VID（DOI 类，如 paper_ref_10.1111/jth.14768）应改走 nGQL。

    trs-graph REST 的 /nodes/{id}、/traversal/{id}/edges 是单段路径参数，
    斜杠 VID 路由不匹配（Spring 404 / Tomcat 拒绝 %2F）。
    """

    @staticmethod
    def _query_handler(captured, records):
        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            if request.url.path == "/api/v1/query":
                captured.append(json.loads(request.content)["query"])
                return httpx.Response(200, json={"records": records, "summary": {}})
            return httpx.Response(404, json={"error": "NotFound"})

        return handler

    def test_get_node_slash_vid_uses_fetch(self):
        captured: list[str] = []
        records = [
            {
                "v": {
                    "id": "paper_ref_10.1111/jth.14768",
                    "labels": ["Paper", "organization_base"],
                    "properties": {"doi": "10.1111/jth.14768"},
                }
            }
        ]
        repo = _make_repo(self._query_handler(captured, records))

        node = repo.get_node("paper_ref_10.1111/jth.14768")

        assert node is not None
        assert node.id == "paper_ref_10.1111/jth.14768"
        assert node.labels == ["Paper", "organization_base"]
        assert len(captured) == 1
        assert 'FETCH PROP ON * "paper_ref_10.1111/jth.14768" YIELD vertex AS v' in captured[0]

    def test_get_node_slash_vid_missing_returns_none(self):
        captured: list[str] = []
        repo = _make_repo(self._query_handler(captured, []))

        assert repo.get_node("paper_ref_10.1111/jth.14768") is None

    def test_get_node_edges_slash_vid_uses_go(self):
        captured: list[str] = []
        records = [
            {
                "src": "paper_ref_10.1111/jth.14768",
                "dst": "paper_812578243168174080",
                "etype": "CITES",
            },
            {
                "src": "paper_864145551824782225",
                "dst": "paper_ref_10.1111/jth.14768",
                "etype": "CITES",
            },
        ]
        repo = _make_repo(self._query_handler(captured, records))

        edges = repo.get_node_edges(
            "paper_ref_10.1111/jth.14768", direction="both", edge_type="CITES", limit=1, offset=0
        )

        # GO 一跳边 + Python 侧分页切片
        assert len(edges) == 1
        assert edges[0].type == "CITES"
        assert str(edges[0].source_id) == "paper_ref_10.1111/jth.14768"
        assert "BIDIRECT" in captured[0]
        assert "OVER CITES" in captured[0]

    def test_get_node_edges_slash_vid_rejects_injected_edge_type(self):
        captured: list[str] = []
        repo = _make_repo(self._query_handler(captured, []))

        repo.get_node_edges("a/b", edge_type="CITES; DROP SPACE dev2", limit=10)

        # 非法边类型不下入 nGQL，回退 OVER *
        assert "OVER *" in captured[0]
        assert "DROP SPACE" not in captured[0]

    def test_normal_vid_still_uses_rest(self):
        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            if request.url.path == "/api/v1/nodes/person_1":
                return httpx.Response(
                    200, json={"id": "person_1", "labels": ["Person"], "properties": {}}
                )
            return httpx.Response(404, json={"error": "NotFound"})

        repo = _make_repo(handler)

        node = repo.get_node("person_1")

        assert node is not None
        assert node.id == "person_1"


class TestStatsAndPagedNodes:
    """SHOW STATS 计数与 nGQL 分页直查（大标签绕开 REST 全量扫描，2026-09-21）。"""

    @pytest.fixture(autouse=True)
    def _clear_stats_cache(self):
        client_mod = __import__("infra.graph_db.client", fromlist=["_stats_snapshot_cache"])
        client_mod._stats_snapshot_cache.clear()
        yield
        client_mod._stats_snapshot_cache.clear()

    @staticmethod
    def _stats_payload():
        return {
            "records": [
                {"Type": "Tag", "Name": "Paper", "Count": 176614},
                {"Type": "Tag", "Name": "Journal", "Count": 2134},
                {"Type": "Edge", "Name": "STUDIED_AT", "Count": 999},
                {"Type": "Space", "Name": "vertices", "Count": 178748},
                {"Type": "Space", "Name": "edges", "Count": 1001},
            ],
            "summary": None,
        }

    def test_stats_snapshot_parses_tags_edges_and_totals(self):
        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            return httpx.Response(200, json=self._stats_payload())

        repo = _make_repo(handler)
        snap = repo.stats_snapshot()
        assert snap["tags"] == {"Paper": 176614, "Journal": 2134}
        assert snap["edges"] == {"STUDIED_AT": 999}
        assert snap["total_nodes"] == 178748  # Space 行优先于 tags 求和
        assert snap["total_edges"] == 1001
        repo.close()

    def test_stats_tag_counts_parses_tags_and_caches(self):
        calls = []

        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            assert request.url.path == "/api/v1/query/read"
            calls.append(json.loads(request.content)["query"])
            return httpx.Response(200, json=self._stats_payload())

        repo = _make_repo(handler)
        assert repo.stats_tag_counts() == {"Paper": 176614, "Journal": 2134}  # 边类型被排除
        assert repo.stats_tag_counts() == {"Paper": 176614, "Journal": 2134}  # 第二次命中缓存
        assert len(calls) == 1
        repo.close()

    def test_label_count_prefers_stats_and_falls_back_to_ngql_count(self):
        queries = []

        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            if request.url.path == "/api/v1/query/read":
                query = json.loads(request.content)["query"]
                if query.endswith("SHOW STATS;"):
                    # 统计里没有 NotIndexed 标签 → 走 nGQL count 兜底
                    return httpx.Response(
                        200, json={"records": [{"Type": "Tag", "Name": "Paper", "Count": 7}]}
                    )
                queries.append(query)
                assert "MATCH (v:`NotIndexed`)" in query
                return httpx.Response(200, json={"records": [{"c": 42}]})
            return httpx.Response(404)

        repo = _make_repo(handler)
        assert repo.label_count("Paper") == 7  # 命中统计
        assert queries == []
        assert repo.label_count("NotIndexed") == 42  # 统计缺失 → nGQL count
        assert queries and "MATCH (v:`NotIndexed`)" in queries[0]
        repo.close()

    def test_label_count_falls_back_when_show_stats_never_run(self):
        """空间从未 SUBMIT JOB STATS（SHOW STATS 400 "no any stats info"）时回退
        nGQL 标签 count，不让异常抛穿拖垮实体列表浏览。"""

        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            if request.url.path == "/api/v1/query/read":
                query = json.loads(request.content)["query"]
                if query.endswith("SHOW STATS;"):
                    return httpx.Response(
                        400,
                        json={
                            "error": "There is no any stats info to show, please execute `submit job stats' firstly!"
                        },
                    )
                assert "MATCH (v:`Expert`)" in query
                return httpx.Response(200, json={"records": [{"c": 11}]})
            # REST node-count 不再作兜底（实测 31s+ 超时），出现即失败
            if request.url.path == "/api/v1/schema/stats/node-count":
                return httpx.Response(500, json={"error": "should not be called"})
            return httpx.Response(404)

        repo = _make_repo(handler)
        assert repo.label_count("Expert") == 11  # SHOW STATS 400 → nGQL count 兜底
        repo.close()

    def test_label_count_raises_fast_when_session_pool_exhausted(self):
        """会话池打满（500 no extra session）时快速上抛：不再逐标签 nGQL count
        回退——那会在池最紧张的时刻再抢会话（冷启动预热 COUNT 风暴的根因）。"""
        queries = []

        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            if request.url.path == "/api/v1/query/read":
                queries.append(json.loads(request.content)["query"])
                return httpx.Response(
                    500,
                    json={"error": "Query execution failed: no extra session available"},
                )
            return httpx.Response(404)

        repo = _make_repo(handler)
        with pytest.raises(GraphRequestError, match="no extra session"):
            repo.label_count("Paper")
        # 只有 SHOW STATS 一次往返，没有跟进任何 nGQL count
        assert len(queries) == 1 and queries[0].endswith("SHOW STATS;")
        repo.close()

    def test_stats_snapshot_cached_even_when_show_stats_later_fails(self):
        """stats 任务卡死（SHOW STATS 开始报错）时，300s 内成功过的快照仍可读。"""
        state = {"fail": False}

        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            if state["fail"]:
                return httpx.Response(400, json={"error": "stats job running"})
            return httpx.Response(200, json=self._stats_payload())

        repo = _make_repo(handler)
        assert repo.stats_snapshot()["tags"]["Paper"] == 176614
        state["fail"] = True
        assert repo.stats_snapshot()["tags"]["Paper"] == 176614  # 命中缓存，不再报错
        repo.close()

    def test_paged_nodes_by_label_builds_ngql_and_parses_vertices(self):
        captured = []

        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            assert request.url.path == "/api/v1/query/read"
            captured.append(json.loads(request.content)["query"])
            return httpx.Response(
                200,
                json={
                    "records": [
                        {
                            "v": {
                                "id": "paper_1",
                                "labels": ["Paper"],
                                "properties": {"name": "综述"},
                            }
                        },
                        {"other": "ignored"},
                    ]
                },
            )

        repo = _make_repo(handler)
        nodes = repo.paged_nodes_by_label("Paper", limit=20, offset=40)
        # LOOKUP 索引枚举优先（MATCH 分页不走索引，实测 30s 超时拖垮实体列表）
        assert captured == ["USE test; LOOKUP ON `Paper` YIELD vertex AS v | LIMIT 20 OFFSET 40"]
        assert len(nodes) == 1
        assert nodes[0].id == "paper_1"
        assert nodes[0].properties == {"name": "综述"}
        repo.close()

    def test_paged_nodes_by_label_falls_back_to_match_without_index(self):
        """无标签索引 LOOKUP 立即 400（不扫描），回退 MATCH 全扫保住可用性。"""
        captured = []

        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            assert request.url.path == "/api/v1/query/read"
            query = json.loads(request.content)["query"]
            captured.append(query)
            if "LOOKUP ON" in query:
                return httpx.Response(400, json={"error": "There is no index to use at runtime"})
            assert "MATCH (v:`Paper`)" in query
            return httpx.Response(200, json={"records": []})

        repo = _make_repo(handler)
        assert repo.paged_nodes_by_label("Paper", limit=10, offset=0) == []
        assert len(captured) == 2
        assert "LOOKUP ON `Paper`" in captured[0]
        assert captured[1] == "USE test; MATCH (v:`Paper`) RETURN v SKIP 0 LIMIT 10"
        repo.close()

    def test_paged_nodes_by_label_rejects_injection(self):
        repo = _make_repo(_health_ok)
        with pytest.raises(GraphRequestError, match="非法节点标签"):
            repo.paged_nodes_by_label("Paper`); DROP SPACE dev2; --")
        repo.close()


class TestSchemaListCache:
    """labels()/edge_types() 短 TTL 单飞缓存（响应缓存过期瞬间的会话池保护，2026-09-21）。"""

    @pytest.fixture(autouse=True)
    def _clear_schema_list_caches(self):
        client_mod = __import__(
            "infra.graph_db.client",
            fromlist=["_labels_cache", "_edge_types_cache"],
        )
        client_mod._labels_cache.clear()
        client_mod._edge_types_cache.clear()
        yield
        client_mod._labels_cache.clear()
        client_mod._edge_types_cache.clear()

    @staticmethod
    def _labels_payload():
        return [{"Name": "Paper"}, {"Name": "Expert"}]

    def test_labels_cached_across_calls(self):
        calls = []

        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            calls.append(request.url.path)
            return httpx.Response(200, json=self._labels_payload())

        repo = _make_repo(handler)
        assert repo.labels() == ["Paper", "Expert"]
        assert repo.labels() == ["Paper", "Expert"]
        assert calls == ["/api/v1/schema/labels"]  # 第二次命中缓存，不打 REST
        repo.close()

    def test_edge_types_cached_across_calls(self):
        calls = []

        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            calls.append(request.url.path)
            return httpx.Response(200, json=[{"Name": "STUDIED_AT"}])

        repo = _make_repo(handler)
        assert repo.edge_types() == ["STUDIED_AT"]
        assert repo.edge_types() == ["STUDIED_AT"]
        assert calls == ["/api/v1/schema/edge-types"]
        repo.close()

    def test_labels_refetch_after_ttl_expiry(self, monkeypatch):
        client_mod = __import__(
            "infra.graph_db.client", fromlist=["_SCHEMA_LIST_CACHE_TTL_SECONDS"]
        )
        monkeypatch.setattr(client_mod, "_SCHEMA_LIST_CACHE_TTL_SECONDS", 0.0)
        calls = []

        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            calls.append(request.url.path)
            return httpx.Response(200, json=self._labels_payload())

        repo = _make_repo(handler)
        repo.labels()
        repo.labels()
        assert calls == ["/api/v1/schema/labels"] * 2  # TTL=0 每次都回源
        repo.close()

    def test_labels_serve_stale_cache_when_refetch_fails(self, monkeypatch):
        """回源失败（会话池瞬时打满→502）时沿用过期旧值，读路径不 502。"""
        client_mod = __import__(
            "infra.graph_db.client", fromlist=["_SCHEMA_LIST_CACHE_TTL_SECONDS"]
        )
        monkeypatch.setattr(client_mod, "_SCHEMA_LIST_CACHE_TTL_SECONDS", 0.0)
        state = {"ok": True}

        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            if state["ok"]:
                return httpx.Response(200, json=self._labels_payload())
            return httpx.Response(502, json={"error": "no extra session available"})

        repo = _make_repo(handler)
        assert repo.labels() == ["Paper", "Expert"]
        state["ok"] = False
        assert repo.labels() == ["Paper", "Expert"]  # 回源失败回退过期值
        state["ok"] = True
        assert repo.labels() == ["Paper", "Expert"]  # 恢复后可再次回源
        repo.close()

    def test_labels_cache_isolated_per_space(self):
        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            space = request.headers.get("X-Graph-Space", "")
            names = ["Paper"] if space == "space_a" else ["Expert"]
            return httpx.Response(200, json=[{"Name": name} for name in names])

        settings_a = TRSGraphSettings(
            base_url="http://test", space="space_a", api_key=None, timeout=5
        )
        repo_a = TRSGraphClient(settings_a, transport=httpx.MockTransport(handler))
        repo_a.connect()
        settings_b = TRSGraphSettings(
            base_url="http://test", space="space_b", api_key=None, timeout=5
        )
        repo_b = TRSGraphClient(settings_b, transport=httpx.MockTransport(handler))
        repo_b.connect()
        assert repo_a.labels() == ["Paper"]
        assert repo_b.labels() == ["Expert"]
        assert repo_a.labels() == ["Paper"]  # 不被另一空间的缓存覆盖
        repo_a.close()
        repo_b.close()


class TestExecBudget:
    """_request 的兜底执行预算（卡口2）：名额占满限时等待，超时按过载拒绝。"""

    def test_request_rejects_when_slots_exhausted(self, monkeypatch):
        """名额占满且等待超时 → 快速抛 GraphRequestError(图服务过载)，不无限排队。"""
        from infra.graph_db import client as trs_client_module

        monkeypatch.setattr(trs_client_module, "_TRS_EXEC_WAIT_TIMEOUT", 0.05)
        monkeypatch.setattr(trs_client_module, "_trs_exec_slots", threading.BoundedSemaphore(1))
        repo = _make_repo(lambda request: _health_ok(request))

        assert trs_client_module._trs_exec_slots.acquire(timeout=0)
        try:
            start = time.monotonic()
            with pytest.raises(GraphRequestError) as exc_info:
                repo._request("GET", "/api/v1/nodes/x")
            assert time.monotonic() - start < 1.0  # 秒级快速失败，而非拖到请求超时
            assert "图服务过载" in str(exc_info.value)
            assert exc_info.value.status_code == 503
        finally:
            trs_client_module._trs_exec_slots.release()

    def test_request_releases_slot_on_http_error(self, monkeypatch):
        """请求失败（5xx）也释放名额，不泄漏：下一个请求立即可用。"""
        from infra.graph_db import client as trs_client_module

        monkeypatch.setattr(trs_client_module, "_trs_exec_slots", threading.BoundedSemaphore(1))

        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            return httpx.Response(500, json={"message": "boom"})

        repo = _make_repo(handler)
        with pytest.raises(GraphRequestError):
            repo._request("GET", "/api/v1/nodes/x")

        # 名额已随异常释放：非阻塞再取必须成功
        assert trs_client_module._trs_exec_slots.acquire(timeout=0)
        trs_client_module._trs_exec_slots.release()

    def test_request_zero_timeout_is_nonblocking_try(self, monkeypatch):
        """_TRS_EXEC_WAIT_TIMEOUT=0 = 非阻塞尝试：有空位成功，无空位立即拒绝。"""
        from infra.graph_db import client as trs_client_module

        monkeypatch.setattr(trs_client_module, "_TRS_EXEC_WAIT_TIMEOUT", 0)
        monkeypatch.setattr(trs_client_module, "_trs_exec_slots", threading.BoundedSemaphore(1))

        def handler(request):
            if request.url.path == "/health":
                return _health_ok(request)
            return httpx.Response(200, json={})

        repo = _make_repo(handler)

        # 空位时正常通过
        repo._request("GET", "/api/v1/nodes/x")

        assert trs_client_module._trs_exec_slots.acquire(timeout=0)
        try:
            with pytest.raises(GraphRequestError, match="图服务过载"):
                repo._request("GET", "/api/v1/nodes/x")
        finally:
            trs_client_module._trs_exec_slots.release()
