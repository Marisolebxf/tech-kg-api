"""FastAPI 图查询 API 的进程内 HTTP 客户端。

## 设计动机

按新规则，业务模块（如"专家直接关系"、"科技产业链全景图"）只能调用 FastAPI 已经
暴露给外部厂商的接口——具体来说是 ``/api/v1/graph-search/*`` 系列图查询接口，而
不能直接触碰 DAO / MySQL / TRSGraphClient。

## 实现方式

使用 ``httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app))`` 把主 FastAPI
应用作为 ASGI transport 挂在客户端里。相较外部厂商真实的 HTTP 调用：

- **同**：完整走 FastAPI 路由匹配、请求/响应模型校验、异常处理器；接口契约变了
  这里也会立即失败——这正是"用业务验证 API 设计"要的效果。
- **优**：不用配 loopback 端口、不受本机代理干扰、单元测试可插桩。

## 使用

```python
from infra.graph_api_client import graph_api

async def foo():
    async with graph_api() as client:
        node = await client.get_node("person_123")
        edges = await client.get_node_edges("person_123", edge_type="COAUTHOR_WITH")
```
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from contextlib import asynccontextmanager
from typing import Any, Literal

import httpx

logger = logging.getLogger(__name__)

_API_PREFIX = "/api/v1/graph-search"
# 进程内回环调用也要设超时：底层 trs-graph-service / Milvus 卡住时不能让请求悬挂。
_DEFAULT_TIMEOUT_SECONDS = 30.0


class GraphAPIError(RuntimeError):
    """图查询 API 返回非成功响应或网络异常。"""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class GraphAPIClient:
    """薄封装：把 ``/api/v1/graph-search/*`` 的响应剥壳成 Python dict/list。

    所有方法都是 async。响应统一为 ``ApiResponse(code, success, data, msg)`` 结构，
    ``success == False`` 时抛 :class:`GraphAPIError`。
    """

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http = http_client

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET ``/api/v1/graph-search{path}``。

        Args:
            path: 前缀之后的路径，如 ``/nodes``。
            params: 查询参数。

        Returns:
            剥壳后的 ``data`` 字段。
        """
        response = await self._http.get(f"{_API_PREFIX}{path}", params=params)
        return self._unwrap(response)

    async def _post(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> Any:
        """POST ``/api/v1/graph-search{path}``。

        Args:
            path: 前缀之后的路径，如 ``/nodes/search``。
            params: 查询参数。
            json: 请求体。

        Returns:
            剥壳后的 ``data`` 字段。
        """
        response = await self._http.post(f"{_API_PREFIX}{path}", params=params, json=json)
        return self._unwrap(response)

    @staticmethod
    def _unwrap(response: httpx.Response) -> Any:
        """剥掉 ``ApiResponse`` 外壳。

        Args:
            response: 图查询接口的原始响应。

        Returns:
            ``data`` 字段；非 ``ApiResponse`` 结构时原样返回响应体。

        Raises:
            GraphAPIError: 响应不是 JSON，或 ``success`` 为 ``False``。
        """
        try:
            payload = response.json()
        except ValueError as exc:  # 非 JSON 响应，直接透传
            raise GraphAPIError(
                f"graph api returned non-json body: {response.text!r}",
                status_code=response.status_code,
            ) from exc
        # ApiResponse 结构 {code, success, data, msg}
        if isinstance(payload, dict) and "success" in payload:
            if not payload.get("success", True):
                raise GraphAPIError(
                    payload.get("msg") or f"graph api failed (code={payload.get('code')})",
                    status_code=payload.get("code"),
                )
            return payload.get("data")
        # 兜底：非 ApiResponse（例如 describe 端点直接返回 dict）
        return payload

    # ------------- 图查询原子能力 -------------
    async def get_node(self, vid: str, *, space: str | None = None) -> dict[str, Any] | None:
        """按 VID 取节点详情。节点不存在时返回 ``None``。"""
        params = {"space": space} if space else None
        try:
            return await self._get(f"/nodes/{vid}", params=params)
        except GraphAPIError as exc:
            if exc.status_code == 404:
                return None
            raise

    async def list_nodes(
        self,
        *,
        label: str,
        limit: int = 20,
        offset: int = 0,
        space: str | None = None,
    ) -> dict[str, Any]:
        """按标签分页拉节点。返回 ``{"items": [...], "total": N}``。"""
        params: dict[str, Any] = {"label": label, "limit": limit, "offset": offset}
        if space:
            params["space"] = space
        return await self._get("/nodes", params=params)

    async def search_nodes(
        self,
        *,
        label: str,
        properties: dict[str, Any] | None = None,
        limit: int = 20,
        space: str | None = None,
    ) -> dict[str, Any]:
        """按属性搜节点。返回 ``{"items": [...], "total": N}``。"""
        params: dict[str, Any] = {"label": label, "limit": limit}
        if space:
            params["space"] = space
        return await self._post("/nodes/search", params=params, json=properties or {})

    async def resolve_addressable_node(
        self,
        node: dict[str, Any],
        *,
        vid_candidates: Sequence[str] = (),
        space: str | None = None,
    ) -> dict[str, Any] | None:
        """把属性搜索返回的节点换成能按 VID 寻址的节点。

        ``/nodes/search`` 返回的 ``id`` 不保证是业务 VID（图服务可能返回内部标识），
        直接拿去查边或扩展子图会查不到数据。这里逐个候选 VID 用 :meth:`get_node`
        验证，返回第一个能寻址到的节点。

        Args:
            node: 属性搜索返回的节点。
            vid_candidates: 额外的候选 VID（按业务命名约定重建，优先级低于原 ``id``）。
            space: 图空间名。

        Returns:
            可按 VID 寻址的节点；全部候选都取不到时返回 ``None``。
        """
        candidates: list[str] = []
        for value in (str(node.get("id") or ""), *vid_candidates):
            if value and value not in candidates:
                candidates.append(value)
        for vid in candidates:
            resolved = await self.get_node(vid, space=space)
            if resolved is not None:
                return resolved
        return None

    async def get_node_edges(
        self,
        vid: str,
        *,
        direction: Literal["out", "in", "both"] = "both",
        edge_type: str | None = None,
        limit: int = 50,
        space: str | None = None,
    ) -> list[dict[str, Any]]:
        """取节点的所有边（不含邻居节点属性）。"""
        params: dict[str, Any] = {"direction": direction, "limit": limit}
        if edge_type:
            params["edge_type"] = edge_type
        if space:
            params["space"] = space
        data = await self._get(f"/node/{vid}/edges", params=params)
        return data.get("edges", []) if isinstance(data, dict) else []

    async def get_neighbours(
        self,
        vid: str,
        *,
        direction: Literal["out", "in", "both"] = "both",
        edge_type: str | None = None,
        limit: int = 50,
        space: str | None = None,
    ) -> list[dict[str, Any]]:
        """取节点的邻居节点（含属性）。"""
        params: dict[str, Any] = {"direction": direction, "limit": limit}
        if edge_type:
            params["edge_type"] = edge_type
        if space:
            params["space"] = space
        data = await self._get(f"/node/{vid}/neighbours", params=params)
        return data.get("nodes", []) if isinstance(data, dict) else []

    async def get_subgraph(
        self,
        vid: str,
        *,
        depth: int = 1,
        limit: int = 50,
        edge_type: str | None = None,
        direction: Literal["out", "in", "both"] = "both",
        space: str | None = None,
    ) -> dict[str, Any]:
        """取 N 跳子图。返回 ``{"nodes": [...], "edges": [...]}``。"""
        params: dict[str, Any] = {"depth": depth, "limit": limit, "direction": direction}
        if edge_type:
            params["edge_type"] = edge_type
        if space:
            params["space"] = space
        return await self._get(f"/subgraph/{vid}", params=params) or {"nodes": [], "edges": []}

    async def shortest_path(
        self,
        *,
        source: str,
        target: str,
        max_depth: int = 10,
        space: str | None = None,
    ) -> dict[str, Any]:
        """两点最短路径。返回 ``{"nodes": [...], "edges": [...], "found": bool}``。"""
        params: dict[str, Any] = {
            "source": source,
            "target": target,
            "max_depth": max_depth,
        }
        if space:
            params["space"] = space
        return await self._get("/shortest-path", params=params) or {
            "nodes": [],
            "edges": [],
            "found": False,
        }

    async def get_stats(self, *, space: str | None = None) -> dict[str, Any]:
        """图统计。返回 ``{"nodes": {label: count}, "edges": {type: count}}``。"""
        params = {"space": space} if space else None
        return await self._get("/stats", params=params) or {"nodes": {}, "edges": {}}


def _load_app() -> Any:
    """延迟导入 ``main.app``，避免 service 层与 main 循环依赖。"""
    from main import app

    return app


@asynccontextmanager
async def graph_api(
    *,
    base_url: str = "http://kg-internal",
    timeout: float = _DEFAULT_TIMEOUT_SECONDS,
) -> Any:
    """构造一个绑定当前 FastAPI 应用（ASGI transport）的 :class:`GraphAPIClient`。

    ``base_url`` 只是给 httpx 一个虚拟主机名，实际不会发起网络请求；请求会经
    ``ASGITransport`` 直达 FastAPI 路由。``timeout`` 用于兜住底层图服务/Milvus
    卡住的情况，避免请求长期悬挂。
    """
    app = _load_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url=base_url, timeout=timeout
    ) as http_client:
        yield GraphAPIClient(http_client)
