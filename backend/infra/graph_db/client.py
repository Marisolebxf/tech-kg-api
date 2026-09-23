"""TRSGraphClient — internal ORM-style repository over trs-graph-service.

Wraps the trs-graph-service REST API (NebulaGraph) for in-app use.
Logic ported from graph_db/backends/trs_graph_backend.py on the
refactor/trs-graph-db-api branch.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from collections.abc import Sequence
from typing import Any

import httpx

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
    GraphRequestError,
)
from infra.graph_db.models import (
    GraphConstraintSpec,
    GraphEdge,
    GraphIndexSpec,
    GraphNode,
    GraphPagedResult,
    GraphPath,
    GraphQueryResult,
)

SCHEMA_INDEXES_PATH = "/api/v1/schema/indexes"

logger = logging.getLogger("infra.graph_db")

# nGQL 直查只接受白名单标签名（SHOW TAGS 出来的标识符），防注入
_TAG_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]{1,128}$")
# SHOW STATS 快照缓存：{space: (monotonic 时间, {"tags", "edges", "total_nodes", "total_edges"})}
_stats_snapshot_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_STATS_CACHE_TTL_SECONDS = 300.0
# TAG/EDGE 类型列表缓存：{space: (monotonic 时间, [名称])}。响应缓存过期瞬间全并发回源
# 会打爆 trs-graph 会话池（用例17c 实测 250×`no extra session available`→502），故与
# 图算法侧 _single_flight_cache 同款：TTL + 每键回源锁（双检）。
_labels_cache: dict[str, tuple[float, list[str]]] = {}
_edge_types_cache: dict[str, tuple[float, list[str]]] = {}
_SCHEMA_LIST_CACHE_TTL_SECONDS = float(os.getenv("TRS_GRAPH_SCHEMA_LIST_CACHE_SECONDS", "30"))
_refresh_locks: dict[tuple[str, str], threading.Lock] = {}

# 兜底执行预算（卡口2）：所有 REST 请求在发出前先取一个 trs 执行名额，
# 覆盖不经 graph-search 公共执行层直连本客户端的调用方（校友/合作成果等
# 同步业务、schema 管理、人工修正、ETL、控制台/图算法）。graph-search 侧
# 的 async 预算（卡口1）排在前面，这里是最后一道：两层嵌套时外层无限等、
# 内层限时（acquire timeout），内层必先超时放异常，不会互相死锁。
# 注意与 console/algo 各自的外层信号量兼容：外层持有者最多把线程数压到
# 本预算值，超出的等待者在超时后拿到 GraphRequestError（过载可见）。
_TRS_EXEC_CONCURRENCY = max(1, int(os.getenv("TRS_EXEC_CONCURRENCY", "32")))
_TRS_EXEC_WAIT_TIMEOUT = max(0.0, float(os.getenv("TRS_EXEC_WAIT_TIMEOUT", "5")))
_trs_exec_slots = threading.BoundedSemaphore(_TRS_EXEC_CONCURRENCY)


def _single_flight_cached(cache: dict, kind: str, space: str, ttl: float, fetch):
    """TTL 缓存 + 每键回源锁：过期瞬间只有一个线程回源，其余等它写回缓存。

    回源失败时回退过期旧值：共享图服务会话池被瞬时打满（`no extra session
    available`→502）不应打断读路径——schema 列表/统计快照本就允许滞后。"""
    cached = cache.get(space)
    if cached and time.monotonic() - cached[0] < ttl:
        return cached[1]
    lock = _refresh_locks.setdefault((kind, space), threading.Lock())
    with lock:
        cached = cache.get(space)  # 双检：等锁期间可能已被先到线程刷新
        if cached and time.monotonic() - cached[0] < ttl:
            return cached[1]
        try:
            value = fetch()
        except Exception:  # noqa: BLE001
            if cached:
                logger.warning("%s 回源失败，沿用过期缓存 space=%s", kind, space, exc_info=True)
                return cached[1]
            raise
        cache[space] = (time.monotonic(), value)
        return value


# The trs-graph-service only treats these property keys as the Nebula vertex id
# (see NodeService.extractVid / NgqlBuilder.extractOrGenerateVid). When none of
# them is present the service generates a UUID vid internally but then *cannot
# read the node back* (it looks up vid/id/name and finds nothing → 404). So the
# client must guarantee one of these keys is set before calling the service.
_VID_KEYS: tuple[str, ...] = ("vid", "id", "name")


def _vid_has_slash(node_id: Any) -> bool:
    """DOI 类业务 VID 本身含 ``/``（如 paper_ref_10.1111/jth.14768）。

    trs-graph REST 的 ``/nodes/{id}``、``/traversal/{id}/edges`` 是单段路径
    参数，斜杠 VID（无论是否 %2F 编码）都路由不匹配，需改走 nGQL 查询端点。
    """
    return "/" in str(node_id)


def _ngql_quote(value: Any) -> str:
    """值转为 nGQL 双引号字符串字面量（转义反斜杠与双引号，防注入）。"""
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


# 批量 FETCH 单条语句的 VID 数上限：防语句过大（200 个 VID 约几 KB），
# 超出分多条语句。子图补点的一跳新邻居（12 边类型 × limit 50 上界 ~600）最多 3 条。
_BULK_FETCH_CHUNK = 200

# 批量邻接 GO 的单语句行数上限：行按源连续返回，超上限即截断（调用方须
# 对配额未满足的 (源, 类型) 回退单源 REST 补查）。4 千行含边属性约 1-2MB，
# 与 /subgraph 端点自身的响应负载同量级。
_EDGE_BULK_ROW_CAP = 4096

# GO OVER 的边类型白名单：字母/下划线开头，防 nGQL 注入（与 REST edgeType 一致）。
_EDGE_TYPE_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*", flags=re.ASCII)


def _error_detail(resp: httpx.Response) -> str:
    """从 trs-graph 错误响应体里提取人类可读信息（如 Nebula SemanticError）。"""
    try:
        data = resp.json()
    except ValueError:
        return ""
    if isinstance(data, dict):
        message = data.get("message") or data.get("error")
        if message:
            return f": {message}"
    return ""


def _ensure_vid(props: dict[str, Any]) -> dict[str, Any]:
    """Return props with a vid guaranteed.

    If a vid/id/name key is already present, props is returned unchanged. If
    props is non-empty but has no vid-key, the *first* property's value is
    promoted to the vid (this matches the techkg convention where the natural
    key — e.g. org_id / scholar_id — is also the vertex id). If props is empty,
    a random uuid is generated.
    """
    if any(k in props for k in _VID_KEYS):
        return props
    if props:
        first_value = next(iter(props.values()))
        props["vid"] = str(first_value)
    else:
        props["vid"] = uuid.uuid4().hex
    return props


class TRSGraphClient:
    """ORM-style repository over trs-graph-service.

    Args:
        settings: Connection settings.
        transport: Optional httpx transport (test seam for MockTransport).
    """

    def __init__(
        self,
        settings: TRSGraphSettings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._client: httpx.Client | None = None

    # ----- connection lifecycle -----

    def connect(self) -> None:
        if self._client is not None:
            return
        headers = {"X-Graph-Space": self._settings.space}
        if self._settings.api_key:
            headers["X-API-Key"] = self._settings.api_key
        self._client = httpx.Client(
            base_url=self._settings.base_url,
            headers=headers,
            timeout=self._settings.timeout,
            transport=self._transport,
        )
        try:
            resp = self._client.get("/health")
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            self._client.close()
            self._client = None
            raise GraphConnectionError(
                f"Cannot connect to trs-graph-service at {self._settings.base_url}"
            ) from exc
        logger.info(
            "Connected to TRS Graph at %s (space: %s)",
            self._settings.base_url,
            self._settings.space,
        )

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
            logger.info("Disconnected from TRS Graph")

    def is_connected(self) -> bool:
        if self._client is None:
            return False
        try:
            resp = self._client.get("/health")
            resp.raise_for_status()
            return resp.json().get("status") == "UP"
        except Exception:
            return False

    # ----- internal HTTP helper -----

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        if self._client is None:
            raise GraphConnectionError("Not connected — call connect() first")
        # httpx 语义：request(timeout=None) 是"禁用超时"而非"沿用客户端默认"
        # （默认值哨兵是 USE_CLIENT_DEFAULT）。不显式回退到 settings.timeout，
        # 构造函数里配的默认超时会被 None 整体关掉，慢查询将无限占用线程/连接。
        effective_timeout = timeout if timeout is not None else self._settings.timeout
        # 兜底预算：等不到执行名额按过载拒绝（快速失败可见），timeout=0 即
        # 非阻塞尝试（threading.Semaphore.acquire(timeout=0) 语义正好如此）。
        if not _trs_exec_slots.acquire(timeout=_TRS_EXEC_WAIT_TIMEOUT):
            raise GraphRequestError(
                f"{method} {path} -> 图服务过载（等待执行名额超过 {_TRS_EXEC_WAIT_TIMEOUT}s）",
                status_code=503,
                body="",
            )
        try:
            try:
                resp = self._client.request(
                    method, path, json=json, params=params, timeout=effective_timeout
                )
            except httpx.HTTPError as exc:
                detail = f"{type(exc).__name__}: {exc}".rstrip(": ")
                raise GraphConnectionError(f"Request failed: {method} {path} ({detail})") from exc
        finally:
            _trs_exec_slots.release()
        if resp.status_code == 404:
            raise GraphNotFoundError(f"{method} {path} -> 404")
        if not resp.is_success:
            raise GraphRequestError(
                f"{method} {path} -> {resp.status_code}{_error_detail(resp)}",
                status_code=resp.status_code,
                body=resp.text,
            )
        return resp

    # ==================================================================
    # Node CRUD
    # ==================================================================

    def create_node(self, labels: list[str], properties: dict[str, Any] | None = None) -> GraphNode:
        properties = _ensure_vid(dict(properties) if properties else {})
        body = _build_node_create_body(labels, properties)
        resp = self._request("POST", "/api/v1/nodes", json=body)
        return _trs_node_to_model(resp.json())

    def merge_node(
        self,
        labels: list[str],
        identity_props: dict[str, Any],
        properties: dict[str, Any] | None = None,
    ) -> GraphNode:
        identity_props = _ensure_vid(dict(identity_props) if identity_props else {})
        body = {
            "labels": labels if labels else ["Vertex"],
            "identityProps": identity_props,
            "properties": dict(properties) if properties else {},
        }
        resp = self._request("POST", "/api/v1/nodes/merge", json=body)
        return _trs_node_to_model(resp.json())

    def get_node(self, node_id: Any) -> GraphNode | None:
        if _vid_has_slash(node_id):
            return self._get_node_via_ngql(node_id)
        try:
            resp = self._request("GET", f"/api/v1/nodes/{node_id}")
        except GraphNotFoundError:
            return None
        return _trs_node_to_model(resp.json())

    def get_nodes_bulk(self, node_ids: Sequence[Any]) -> dict[str, GraphNode]:
        """按 VID 批量取节点：一条 FETCH PROP ON * 取整块，返回 vid → GraphNode。

        子图遍历的新邻居补点用它替代逐个 get_node——一跳 N 个邻居从 N 次
        TRS 往返降为 ceil(N/块大小) 次。查不到的 VID（悬挂点，边端点无 tag）
        不在结果里，由调用方兜底占位，与单查 get_node 返回 None 等价。
        含 ``/`` 的 VID 同样适用：FETCH 走查询端点，无 REST 单段路径限制。
        """
        unique_ids = [vid for vid in dict.fromkeys(str(v) for v in node_ids if v)]
        found: dict[str, GraphNode] = {}
        for start in range(0, len(unique_ids), _BULK_FETCH_CHUNK):
            chunk = unique_ids[start : start + _BULK_FETCH_CHUNK]
            quoted = ", ".join(_ngql_quote(vid) for vid in chunk)
            result = self.execute_read(f"FETCH PROP ON * {quoted} YIELD vertex AS v")
            for record in result.records or []:
                vertex = record.get("v")
                if isinstance(vertex, dict) and vertex.get("id") is not None:
                    node = _trs_node_to_model(vertex)
                    found[str(node.id)] = node
        return found

    def get_edges_bulk(
        self,
        node_ids: Sequence[Any],
        edge_types: Sequence[str],
        *,
        direction: str = "both",
        row_cap: int = _EDGE_BULK_ROW_CAP,
    ) -> tuple[dict[tuple[str, str], list[GraphEdge]], bool]:
        """多源多类型一跳邻接批量：至多两条 GO 覆盖 (源 × 边类型) 全组合。

        返回 ((起点vid, 边类型) -> 边列表, 是否被 row_cap 截断)。子图逐跳邻接
        用它替代逐组合 REST——12 边类型 × N 前沿节点从 12N 次往返降为每跳
        1-2 次。方向口径与 REST /traversal 一致（存储真方向）：GO 的 ``$^``
        恒为遍历起点（BIDIRECT/REVERSELY 下入边的 ``$^``=起点而非存储源，
        2026-09-23 dev 空间实测），单条 BIDIRECT 无法还原存储方向，故 both
        拆「正向 + REVERSELY」两条语句：正向行起点即存储源，REVERSELY 行
        对端为存储源；边 id 统一 ``src->dst@rank``（REST 同款），同一条边
        无论从哪端查询 id 一致，跨跳回边去重口径不破。
        GO 的 ``| LIMIT`` 是全批行数上限且行按源连续返回，超高度数源可占满
        行数上限把同批其他源挤掉（返回截断标志），调用方须对配额未满足的
        组合回退单源 REST 补查，不能只吃批量结果。当前空间不存在的边类型
        先按 schema 列表（TTL 缓存）滤除：GO OVER 不存在的类型整条语句
        SemanticError，REST 逐类型查则是单类型 400 可跳过，过滤后两者等价。
        注意批量行是裸 Nebula 结果：REST 会静默滤掉悬挂端点的边（实测
        person→悬挂org 的 AFFILIATED_WITH 被吞），批量不做该过滤，由调用方
        按端点存在性剔除。
        """
        roots = [str(v) for v in dict.fromkeys(str(v) for v in node_ids if v)]
        if not roots:
            return {}, False
        existing = set(self.edge_types())
        over = [
            et
            for et in dict.fromkeys(edge_types)
            if _EDGE_TYPE_PATTERN.fullmatch(et or "") and et in existing
        ]
        if not over:
            return {}, False
        # 方向拆两条语句：正向（起点=存储源）与 REVERSELY（对端=存储源）
        plans: list[tuple[str, bool]] = []
        if direction in ("out", "both"):
            plans.append(("", False))
        if direction in ("in", "both"):
            plans.append((" REVERSELY", True))
        roots_part = ", ".join(_ngql_quote(v) for v in roots)
        types_part = ", ".join(f"`{et}`" for et in over)
        grouped: dict[tuple[str, str], list[GraphEdge]] = {}
        truncated = False
        for clause, reverse in plans:
            statement = (
                f"GO 1 STEP FROM {roots_part} OVER {types_part}{clause} "
                "YIELD id($^) AS src, id($$) AS dst, type(edge) AS etype, "
                "rank(edge) AS rk, properties(edge) AS props "
                f"| LIMIT {int(row_cap)}"
            )
            result = self.execute_read(statement)
            count = 0
            for record in result.records or []:
                root = record.get("src")  # $^ 恒为遍历起点
                other = record.get("dst")  # $$ 对端
                etype = record.get("etype")
                if not root or not other or not etype:
                    continue
                rank = int(record.get("rk") or 0)
                props = record.get("props")
                edge_src, edge_dst = (other, root) if reverse else (root, other)
                grouped.setdefault((str(root), str(etype)), []).append(
                    GraphEdge(
                        id=f"{edge_src}->{edge_dst}@{rank}",
                        type=str(etype),
                        source_id=edge_src,
                        target_id=edge_dst,
                        properties=props if isinstance(props, dict) else {},
                    )
                )
                count += 1
            truncated = truncated or count >= int(row_cap)
        return grouped, truncated

    def get_nodes_by_label(
        self, label: str, *, limit: int = 100, offset: int = 0
    ) -> GraphPagedResult:
        resp = self._request(
            "GET",
            f"/api/v1/nodes/label/{label}",
            params={"limit": limit, "offset": offset},
        )
        data = resp.json()
        items = [_trs_node_to_model(n) for n in data.get("items", [])]
        return GraphPagedResult(
            items=items,
            total=data.get("page", {}).get("total", len(items)),
            limit=limit,
            offset=offset,
        )

    def paged_nodes_by_label(
        self, label: str, *, limit: int = 100, offset: int = 0
    ) -> list[GraphNode]:
        """按标签分页取节点：LOOKUP 索引枚举优先，无标签索引回退 MATCH 全扫。

        MATCH (v:`Label`) SKIP/LIMIT 即便标签有索引也不走（实测 dev2 DataSource
        39 行 2.7s，高负载 30s 超时拖垮实体列表），LOOKUP 走标签索引 0.07s；
        无索引标签 LOOKUP 立即 400 "There is no index to use"（快速失败不扫描），
        回退 MATCH 慢但正确——补建标签索引后自动切回快路径。
        REST /api/v1/nodes/label/{label} 在 trs-graph 侧附带全量总数计算，
        大标签（如 Paper 十万级）30s+ 超时（2026-09-21 实测 limit=2 也挂）；
        总数需求另走 label_count()，不要为此恢复 REST 分页端点。
        """
        if not _TAG_IDENTIFIER.fullmatch(label or ""):
            raise GraphRequestError(f"非法节点标签: {label!r}", status_code=400)
        try:
            result = self.execute_read(
                f"LOOKUP ON `{label}` YIELD vertex AS v | LIMIT {int(limit)} OFFSET {int(offset)}"
            )
        except GraphRequestError as exc:
            logger.warning("LOOKUP 分页无索引（label=%s），回退 MATCH 全扫: %s", label, exc)
            result = self.execute_read(
                f"MATCH (v:`{label}`) RETURN v SKIP {int(offset)} LIMIT {int(limit)}"
            )
        nodes: list[GraphNode] = []
        for record in result.records or []:
            data = record.get("v") if isinstance(record, dict) else None
            if not isinstance(data, dict):
                continue
            nodes.append(
                GraphNode(
                    id=data.get("id"),
                    labels=list(data.get("labels") or []),
                    properties=dict(data.get("properties") or {}),
                )
            )
        return nodes

    def label_count(self, label: str) -> int:
        """标签节点数：优先 SHOW STATS（毫秒级）；标签不在统计中，或空间从未
        跑过 SUBMIT JOB STATS（SHOW STATS 直接 400 "no any stats info"）时回退
        nGQL 标签 count 直查（走标签索引，亚秒级）。不用 REST /schema/stats/
        node-count 兜底——其在 trs-graph 侧全表扫描，11 顶点空间实测 31s+，
        大标签必超时。

        容量型失败（会话池打满 / 连接错误）直接上抛：此时逐标签 nGQL count
        只会再抢会话、把池越占越死（冷启动预热实测打出几十秒 COUNT 风暴），
        让调用方显式降级（各处均有 TTL 缓存或空值兜底）。"""
        try:
            counts = self.stats_tag_counts()
        except GraphConnectionError:
            raise
        except GraphRequestError as exc:
            if "no extra session" in str(exc):
                raise
            logger.warning(
                "SHOW STATS 不可用（space=%s label=%s），回退 nGQL 标签计数: %s",
                self._settings.space,
                label,
                exc,
            )
            counts = {}
        if label in counts:
            return counts[label]
        return self._ngql_label_count(label)

    def _ngql_label_count(self, label: str) -> int:
        """nGQL 标签计数：``MATCH (v:`Label`) RETURN count(v)``（标签过滤亚秒级）。"""
        if not _TAG_IDENTIFIER.fullmatch(label or ""):
            raise GraphRequestError(f"非法节点标签: {label!r}", status_code=400)
        result = self.execute_read(f"MATCH (v:`{label}`) RETURN count(v) AS c")
        for record in result.records or []:
            if isinstance(record, dict) and record.get("c") is not None:
                return int(record["c"])
        return 0

    def stats_snapshot(self) -> dict[str, Any]:
        """SHOW STATS 解析快照 {"tags", "edges", "total_nodes", "total_edges"}，按空间缓存 300s。

        Nebula 统计只在 SUBMIT JOB STATS 后刷新，本就允许轻微滞后，用它换掉
        逐标签/边类型全表 count（Paper 实测 45s+ 超时）。缓存模块级共享：
        即使 SHOW STATS 此刻报错（如 stats 任务卡死），300s 内成功过的快照
        仍可读——平台总览等消费方的回退路径据此兜底。过期瞬间单飞回源，
        避免并发 SHOW STATS 挤占会话池。
        """
        cached = _stats_snapshot_cache.get(self._settings.space)
        if cached and time.monotonic() - cached[0] < _STATS_CACHE_TTL_SECONDS:
            return cached[1]
        return _single_flight_cached(
            _stats_snapshot_cache,
            "stats",
            self._settings.space,
            _STATS_CACHE_TTL_SECONDS,
            self._fetch_stats_snapshot,
        )

    def _fetch_stats_snapshot(self) -> dict[str, Any]:
        result = self.execute_read("SHOW STATS;")
        tags: dict[str, int] = {}
        edges: dict[str, int] = {}
        vertices = 0
        edge_total = 0
        for record in result.records or []:
            if not isinstance(record, dict):
                continue
            rtype = record.get("Type")
            name = record.get("Name")
            count = int(record.get("Count") or 0)
            if rtype == "Tag" and name:
                tags[str(name)] = count
            elif rtype == "Edge" and name:
                edges[str(name)] = count
            elif rtype == "Space":
                if name == "vertices":
                    vertices = count
                elif name == "edges":
                    edge_total = count
        snapshot = {
            "tags": tags,
            "edges": edges,
            "total_nodes": vertices or sum(tags.values()),
            "total_edges": edge_total or sum(edges.values()),
        }
        return snapshot

    def stats_tag_counts(self) -> dict[str, int]:
        """SHOW STATS 的全标签计数（stats_snapshot 的 tags 部分，副本）。"""
        return dict(self.stats_snapshot()["tags"])

    def find_nodes(
        self,
        labels: list[str],
        properties: dict[str, Any],
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> GraphPagedResult:
        body = {
            "labels": labels if labels else ["Vertex"],
            "properties": properties,
            "limit": limit,
            "offset": offset,
        }
        resp = self._request("POST", "/api/v1/nodes/find", json=body)
        data = resp.json()
        items = [_trs_node_to_model(n) for n in data.get("items", [])]
        return GraphPagedResult(
            items=items,
            total=data.get("page", {}).get("total", len(items)),
            limit=limit,
            offset=offset,
        )

    def update_node(self, node_id: Any, properties: dict[str, Any]) -> GraphNode:
        existing = self.get_node(node_id)
        if existing is None:
            raise GraphNotFoundError(f"Node {node_id} not found")
        label = existing.labels[0] if existing.labels else "Vertex"
        body = {"label": label, "properties": properties}
        resp = self._request("PUT", f"/api/v1/nodes/{node_id}", json=body)
        data = resp.json()
        if isinstance(data, dict) and "id" in data:
            return _trs_node_to_model(data)
        existing.properties.update(properties)
        return existing

    def delete_node(self, node_id: Any, *, detach: bool = False) -> bool:
        params: dict[str, Any] = {}
        if detach:
            params["detach"] = "true"
        try:
            self._request("DELETE", f"/api/v1/nodes/{node_id}", params=params)
        except GraphNotFoundError:
            return False
        return True

    # ==================================================================
    # Edge CRUD
    # ==================================================================

    def create_edge(
        self,
        source_id: Any,
        target_id: Any,
        edge_type: str,
        properties: dict[str, Any] | None = None,
    ) -> GraphEdge:
        body = {
            "type": edge_type,
            "sourceId": str(source_id),
            "targetId": str(target_id),
            "properties": dict(properties) if properties else {},
        }
        resp = self._request("POST", "/api/v1/edges", json=body)
        return _trs_edge_to_model(resp.json())

    def merge_edge(
        self,
        source_id: Any,
        target_id: Any,
        edge_type: str,
        identity_props: dict[str, Any],
        properties: dict[str, Any] | None = None,
    ) -> GraphEdge:
        body = {
            "type": edge_type,
            "sourceId": str(source_id),
            "targetId": str(target_id),
            "identityProps": identity_props,
            "properties": dict(properties) if properties else {},
        }
        resp = self._request("POST", "/api/v1/edges/merge", json=body)
        return _trs_edge_to_model(resp.json())

    def get_edge(self, edge_id: Any, edge_type: str | None = None) -> GraphEdge | None:
        try:
            source, target, ranking = _parse_edge_id(str(edge_id))
        except (ValueError, IndexError):
            return None

        if edge_type:
            try:
                resp = self._request(
                    "GET",
                    f"/api/v1/edges/{source}/{target}",
                    params={"type": edge_type, "ranking": ranking},
                )
            except GraphNotFoundError:
                return None
            return _trs_edge_to_model(resp.json())

        # No edge_type — scan the source node's edges.
        try:
            edges = self.get_node_edges(source, direction="both", limit=500)
            for e in edges:
                if e.id == str(edge_id):
                    return e
        except Exception as exc:
            logger.debug("get_edge scan failed for edge %s: %s", edge_id, exc)
        return None

    def get_edges_by_type(
        self, edge_type: str, *, limit: int = 100, offset: int = 0
    ) -> GraphPagedResult:
        resp = self._request(
            "GET",
            f"/api/v1/edges/type/{edge_type}",
            params={"limit": limit, "offset": offset},
        )
        data = resp.json()
        items = [_trs_edge_to_model(e) for e in data.get("items", [])]
        return GraphPagedResult(
            items=items,
            total=data.get("page", {}).get("total", len(items)),
            limit=limit,
            offset=offset,
        )

    def find_edges(
        self,
        edge_type: str,
        properties: dict[str, Any],
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> GraphPagedResult:
        body = {"type": edge_type, "properties": properties, "limit": limit, "offset": offset}
        resp = self._request("POST", "/api/v1/edges/find", json=body)
        data = resp.json()
        items = [_trs_edge_to_model(e) for e in data.get("items", [])]
        return GraphPagedResult(
            items=items,
            total=data.get("page", {}).get("total", len(items)),
            limit=limit,
            offset=offset,
        )

    def update_edge(
        self, edge_id: Any, properties: dict[str, Any], edge_type: str | None = None
    ) -> GraphEdge:
        source, target, ranking = _parse_edge_id(str(edge_id))
        if not edge_type:
            found = self.get_edge(edge_id)
            edge_type = found.type if found else "unknown"
        body = {"type": edge_type, "ranking": ranking, "properties": properties}
        resp = self._request("PUT", f"/api/v1/edges/{source}/{target}", json=body)
        return _trs_edge_to_model(resp.json())

    def delete_edge(self, edge_id: Any, *, edge_type: str | None = None) -> bool:
        source, target, ranking = _parse_edge_id(str(edge_id))
        params: dict[str, Any] = {"ranking": ranking}
        if not edge_type:
            found = self.get_edge(edge_id)
            edge_type = found.type if found else "unknown"
        params["type"] = edge_type
        try:
            self._request("DELETE", f"/api/v1/edges/{source}/{target}", params=params)
        except GraphNotFoundError:
            return False
        return True

    # ==================================================================
    # Neighbourhood / traversal
    # ==================================================================

    def get_node_edges(
        self,
        node_id: Any,
        *,
        direction: str = "both",
        edge_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[GraphEdge]:
        if _vid_has_slash(node_id):
            return self._get_node_edges_via_ngql(
                node_id, direction=direction, edge_type=edge_type, limit=limit, offset=offset
            )
        params: dict[str, Any] = {"direction": direction, "limit": limit}
        if offset:
            params["offset"] = offset
        if edge_type:
            params["edgeType"] = edge_type
        resp = self._request("GET", f"/api/v1/traversal/{node_id}/edges", params=params)
        data = resp.json()
        items = data if isinstance(data, list) else data.get("items", [])
        return [_trs_edge_to_model(e) for e in items]

    def _get_node_via_ngql(self, node_id: Any) -> GraphNode | None:
        """含 ``/`` 的 VID（DOI 类）经 nGQL FETCH 取节点。

        trs-graph REST 的 ``/nodes/{id}`` 是单段路径参数，斜杠 VID 直接
        路由 404，必须走查询端点。
        """
        result = self.execute_query(f"FETCH PROP ON * {_ngql_quote(node_id)} YIELD vertex AS v")
        for record in result.records:
            vertex = record.get("v")
            if isinstance(vertex, dict) and vertex.get("id") is not None:
                return _trs_node_to_model(vertex)
        return None

    def _get_node_edges_via_ngql(
        self,
        node_id: Any,
        *,
        direction: str,
        edge_type: str | None,
        limit: int,
        offset: int,
    ) -> list[GraphEdge]:
        """含 ``/`` 的 VID（DOI 类）经 nGQL GO 取一跳边（REST 路径参数无法承载）。

        边不带属性（子图渲染只用类型与端点）；GO 不做服务端分页，Python 侧切片。
        edge_type 只放行字母数字下划线，防 nGQL 注入。
        """
        over = "*"
        if edge_type and edge_type.replace("_", "a").isalnum():
            over = edge_type
        direction_clause = {"in": "REVERSELY", "both": "BIDIRECT"}.get(direction, "")
        statement = (
            f"GO 1 STEP FROM {_ngql_quote(node_id)} OVER {over}"
            + (f" {direction_clause}" if direction_clause else "")
            + " YIELD id($^) AS src, id($$) AS dst, type(edge) AS etype"
        )
        result = self.execute_query(statement)
        edges = [
            GraphEdge(
                id=f"{record.get('src')}|{record.get('etype')}|{record.get('dst')}",
                type=str(record.get("etype")),
                source_id=record.get("src"),
                target_id=record.get("dst"),
            )
            for record in result.records
        ]
        return edges[offset : offset + limit]

    def get_neighbours(
        self,
        node_id: Any,
        *,
        direction: str = "both",
        edge_type: str | None = None,
        limit: int = 100,
    ) -> list[GraphNode]:
        params: dict[str, Any] = {"direction": direction, "limit": limit}
        if edge_type:
            params["edgeType"] = edge_type
        resp = self._request("GET", f"/api/v1/traversal/{node_id}/neighbours", params=params)
        data = resp.json()
        items = data if isinstance(data, list) else data.get("items", [])
        return [_trs_node_to_model(n) for n in items]

    def shortest_path(
        self,
        source_id: Any,
        target_id: Any,
        *,
        edge_type: str | None = None,
        max_depth: int = 10,
    ) -> GraphPath | None:
        params: dict[str, Any] = {
            "sourceId": str(source_id),
            "targetId": str(target_id),
            "maxDepth": max_depth,
        }
        if edge_type:
            params["edgeType"] = edge_type
        try:
            resp = self._request("GET", "/api/v1/traversal/path/shortest", params=params)
        except GraphNotFoundError:
            return None
        data = resp.json()
        nodes = [_trs_node_to_model(n) for n in data.get("nodes", [])]
        edges = [_trs_edge_to_model(e) for e in data.get("edges", [])]
        for i, node in enumerate(nodes):
            if not node.labels and not node.properties:
                try:
                    full = self.get_node(node.id)
                    if full:
                        nodes[i] = full
                except Exception as exc:
                    logger.debug("shortest_path backfill failed for node %s: %s", node.id, exc)
        return GraphPath(nodes=nodes, edges=edges)

    # ==================================================================
    # Query execution (nGQL)
    # ==================================================================

    def _scoped_query(self, query: str) -> str:
        if query.lstrip().upper().startswith("USE "):
            return query
        space = self._settings.space
        if not re.fullmatch(r"[A-Za-z_]\w*", space, flags=re.ASCII):
            raise GraphRequestError(
                "Invalid graph space name",
                status_code=400,
                body=space,
            )
        return f"USE {space}; {query}"

    @staticmethod
    def _query_result(data: dict[str, Any], path: str, *, expected_space: str) -> GraphQueryResult:
        summary = data.get("summary")
        if isinstance(summary, dict) and summary.get("errorCode") not in (None, 0, "0"):
            comment = summary.get("comment") or summary
            raise GraphRequestError(
                f"TRS Graph query failed on {path}: {comment}",
                status_code=200,
                body=json.dumps(data, ensure_ascii=False),
            )
        actual_space = summary.get("spaceName") if isinstance(summary, dict) else None
        if actual_space and actual_space != expected_space:
            raise GraphRequestError(
                f"TRS Graph space mismatch on {path}: expected {expected_space}, got {actual_space}",
                status_code=409,
                body=json.dumps(data, ensure_ascii=False),
            )
        return GraphQueryResult(records=data.get("records", []), summary=summary)

    def execute_query(self, query: str, params: dict[str, Any] | None = None) -> GraphQueryResult:
        body: dict[str, Any] = {"query": self._scoped_query(query)}
        if params:
            body["params"] = params
        resp = self._request("POST", "/api/v1/query", json=body)
        data = resp.json()
        return self._query_result(data, "/api/v1/query", expected_space=self._settings.space)

    def execute_read(
        self,
        query: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> GraphQueryResult:
        """单调用可覆盖读超时（秒）。全空间 MATCH 聚合在共享图库缓存变冷时可超
        默认 30s（索引重建/邻租户负载后实测），重分析类调用按需放宽。"""
        body: dict[str, Any] = {"query": self._scoped_query(query)}
        if params:
            body["params"] = params
        resp = self._request("POST", "/api/v1/query/read", json=body, timeout=timeout)
        data = resp.json()
        return self._query_result(data, "/api/v1/query/read", expected_space=self._settings.space)

    def execute_write(self, query: str, params: dict[str, Any] | None = None) -> GraphQueryResult:
        body: dict[str, Any] = {"query": self._scoped_query(query)}
        if params:
            body["params"] = params
        resp = self._request("POST", "/api/v1/query/write", json=body)
        data = resp.json()
        return self._query_result(data, "/api/v1/query/write", expected_space=self._settings.space)

    # ==================================================================
    # Batch operations
    # ==================================================================

    def batch_create_nodes(
        self,
        items: Sequence[dict[str, Any]],
        labels: list[str],
    ) -> list[GraphNode]:
        norm_items = []
        for item in items:
            norm_items.append(_ensure_vid(dict(item)))
        body = {"labels": labels if labels else ["Vertex"], "items": norm_items}
        resp = self._request("POST", "/api/v1/nodes/batch", json=body)
        data = resp.json()
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return [_trs_node_to_model(n) for n in data if isinstance(n, dict)]
        return []

    def batch_create_edges(
        self,
        items: Sequence[dict[str, Any]],
        edge_type: str,
    ) -> list[GraphEdge]:
        normalized_items: list[dict[str, Any]] = []
        for item in items:
            entry = dict(item)
            if "source_id" in entry and "sourceId" not in entry:
                entry["sourceId"] = str(entry.pop("source_id"))
            if "target_id" in entry and "targetId" not in entry:
                entry["targetId"] = str(entry.pop("target_id"))
            if "properties" in entry and isinstance(entry["properties"], dict):
                props = entry.pop("properties")
                entry.update(props)
            normalized_items.append(entry)
        body = {"type": edge_type, "items": normalized_items}
        resp = self._request("POST", "/api/v1/edges/batch", json=body)
        data = resp.json()
        return [_trs_edge_to_model(e) for e in data if isinstance(e, dict)]

    # ==================================================================
    # Schema management
    # ==================================================================

    def create_index(self, spec: GraphIndexSpec) -> None:
        body = {"label": spec.label, "properties": spec.properties, "unique": spec.unique}
        self._request("POST", SCHEMA_INDEXES_PATH, json=body)

    def drop_index(self, label: str, properties: list[str]) -> None:
        params = {"label": label, "properties": ",".join(properties)}
        self._request("DELETE", SCHEMA_INDEXES_PATH, params=params)

    def list_indexes(self, label: str | None = None) -> list[GraphIndexSpec]:
        params: dict[str, Any] = {}
        if label:
            params["label"] = label
        resp = self._request("GET", SCHEMA_INDEXES_PATH, params=params)
        data = resp.json()
        items = data if isinstance(data, list) else data.get("items", [])
        indexes: list[GraphIndexSpec] = []
        for item in items:
            idx_label = _strip_quotes(item.get("label", ""))
            raw_props = item.get("properties", [])
            clean_props: list[str] = []
            for p in raw_props if isinstance(raw_props, list) else []:
                p = _strip_quotes(p)
                if p.startswith("[") and p.endswith("]"):
                    try:
                        parsed = json.loads(p)
                        if isinstance(parsed, list):
                            clean_props.extend(_strip_quotes(x) for x in parsed)
                            continue
                    except ValueError as exc:
                        logger.debug("list_indexes could not parse bracket property %r: %s", p, exc)
                clean_props.append(p)
            indexes.append(
                GraphIndexSpec(
                    label=idx_label,
                    properties=clean_props,
                    unique=item.get("unique", False),
                )
            )
        return indexes

    def create_constraint(self, spec: GraphConstraintSpec) -> None:
        body = {
            "name": spec.name,
            "label": spec.label,
            "property": spec.property,
            "kind": spec.kind,
        }
        self._request("POST", "/api/v1/schema/constraints", json=body)

    def drop_constraint(self, name: str) -> None:
        self._request("DELETE", f"/api/v1/schema/constraints/{name}")

    def list_constraints(self) -> list[GraphConstraintSpec]:
        resp = self._request("GET", "/api/v1/schema/constraints")
        data = resp.json()
        items = data if isinstance(data, list) else data.get("items", [])
        constraints: list[GraphConstraintSpec] = []
        for item in items:
            constraints.append(
                GraphConstraintSpec(
                    name=_strip_quotes(item.get("name", "")),
                    label=_strip_quotes(item.get("label", "")),
                    property=_strip_quotes(item.get("property", "")),
                    kind=item.get("kind", "unique"),
                )
            )
        return constraints

    # ==================================================================
    # Database info
    # ==================================================================

    def node_count(self, label: str | None = None) -> int:
        params: dict[str, Any] = {}
        if label:
            params["label"] = label
        resp = self._request("GET", "/api/v1/schema/stats/node-count", params=params)
        return resp.json().get("count", 0)

    def edge_count(self, edge_type: str | None = None) -> int:
        params: dict[str, Any] = {}
        if edge_type:
            params["edgeType"] = edge_type
        resp = self._request("GET", "/api/v1/schema/stats/edge-count", params=params)
        return resp.json().get("count", 0)

    def labels(self) -> list[str]:
        """空间 TAG 列表。短 TTL 单飞缓存：实体浏览等高频路径每次响应缓存未命中
        都会调它做类型校验，无缓存时过期瞬间的全并发回源会打爆 trs-graph 会话池
        （用例17c 实测）。SHOW TAGS 结果稳定，30s 滞后可接受（DDL 本就有传播延迟）。
        """
        return list(
            _single_flight_cached(
                _labels_cache,
                "labels",
                self._settings.space,
                _SCHEMA_LIST_CACHE_TTL_SECONDS,
                self._fetch_labels,
            )
        )

    def _fetch_labels(self) -> list[str]:
        resp = self._request("GET", "/api/v1/schema/labels")
        data = resp.json()
        items = data if isinstance(data, list) else data.get("items", [])
        result: list[str] = []
        for item in items:
            if isinstance(item, dict):
                result.append(item.get("Name", item.get("name", str(item))))
            else:
                result.append(str(item))
        return result

    def edge_types(self) -> list[str]:
        """空间 EDGE 类型列表（labels 同款短 TTL 单飞缓存）。"""
        return list(
            _single_flight_cached(
                _edge_types_cache,
                "edge_types",
                self._settings.space,
                _SCHEMA_LIST_CACHE_TTL_SECONDS,
                self._fetch_edge_types,
            )
        )

    def _fetch_edge_types(self) -> list[str]:
        resp = self._request("GET", "/api/v1/schema/edge-types")
        data = resp.json()
        items = data if isinstance(data, list) else data.get("items", [])
        result: list[str] = []
        for item in items:
            if isinstance(item, dict):
                result.append(item.get("Name", item.get("name", str(item))))
            else:
                result.append(str(item))
        return result

    def list_spaces(self) -> list[str]:
        """列出所有图空间（无 REST 端点，用 nGQL SHOW SPACES）。"""
        result = self.execute_write("SHOW SPACES;")
        names: list[str] = []
        for rec in result.records:
            name = rec.get("Name", rec.get("name", ""))
            if name:
                names.append(str(name))
        return names
