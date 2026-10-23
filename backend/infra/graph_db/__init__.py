"""Internal trs-graph ORM repository for app services.

Public API::

    from infra.graph_db import get_trs_graph_client

    repo = get_trs_graph_client()
    node = repo.create_node(["Person"], {"name": "Alice"})
"""

from __future__ import annotations

import threading

from infra.graph_db.algorithm_client import (
    AlgorithmJob,
    AlgorithmJobBusyError,
    AlgorithmJobFailedError,
    AlgorithmJobTimeoutError,
    TRSAlgorithmClient,
)
from infra.graph_db.client import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings
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
    GraphPath,
    GraphQueryResult,
)

__all__ = [
    "TRSGraphClient",
    "TRSAlgorithmClient",
    "TRSGraphSettings",
    "get_trs_graph_client",
    "close_trs_graph_client",
    "get_algorithm_client",
    "close_algorithm_client",
    "get_space_client",
    "get_business_space_client",
    "close_space_clients",
    "get_space_algorithm_client",
    "close_space_algorithm_clients",
    "AlgorithmJob",
    "AlgorithmJobBusyError",
    "AlgorithmJobFailedError",
    "AlgorithmJobTimeoutError",
    "GraphNode",
    "GraphEdge",
    "GraphPath",
    "GraphQueryResult",
    "GraphPagedResult",
    "GraphIndexSpec",
    "GraphConstraintSpec",
    "GraphRepoError",
    "GraphConnectionError",
    "GraphNotFoundError",
    "GraphRequestError",
]

_client: TRSGraphClient | None = None
_client_lock = threading.Lock()


def get_trs_graph_client() -> TRSGraphClient:
    """Return the process-wide connected TRSGraphClient singleton (lazy, thread-safe).

    图空间统一读取 TRS_GRAPH_SPACE；历史上另有 get_techkg_client 双单例别名，已收敛到本函数。
    九大业务请求（require_business_data 置位 business_data_plane）优先返回
    TRS_GRAPH_BUSINESS_* 独立连接，未配置时回落到下面的常规路径。
    """
    from service.graph_space_context import (
        business_data_plane,
        business_space_override,
        selected_graph_space,
    )

    if business_data_plane.get():
        business = get_business_space_client(selected_graph_space.get())
        if business is not None:
            return business
    space = business_space_override.get() or selected_graph_space.get()
    if space:
        return get_space_client(space)
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None:
            return _client
        repo = TRSGraphClient(TRSGraphSettings.from_env())
        repo.connect()  # may raise; only cache on success
        _client = repo
    return _client


def close_trs_graph_client() -> None:
    """Close and release the singleton repo (called on app shutdown)."""
    global _client
    with _client_lock:
        if _client is not None:
            _client.close()
            _client = None


_space_clients: dict[str, TRSGraphClient] = {}
_space_clients_lock = threading.Lock()


_algo_client: TRSAlgorithmClient | None = None
_algo_client_lock = threading.Lock()


def get_algorithm_client() -> TRSAlgorithmClient:
    """Return the process-wide connected TRSAlgorithmClient singleton (lazy, thread-safe).

    图算法作业走独立的 Spark 计算通道（/api/v1/algorithms/**），连接参数与
    TRSGraphClient 相同（TRS_GRAPH_* env）。仅在首次真正提交算法作业时建连。
    """
    global _algo_client
    if _algo_client is not None:
        return _algo_client
    with _algo_client_lock:
        if _algo_client is not None:
            return _algo_client
        client = TRSAlgorithmClient(TRSGraphSettings.from_env())
        client.connect()  # may raise; only cache on success
        _algo_client = client
    return _algo_client


def close_algorithm_client() -> None:
    """关闭并释放图算法客户端单例（应用停机时调用）。"""
    global _algo_client
    with _algo_client_lock:
        if _algo_client is not None:
            _algo_client.close()
            _algo_client = None


def get_space_client(space: str) -> TRSGraphClient:
    """获取指向指定图空间的客户端（按空间名缓存，连接参数仍取自 env）。"""
    if space in _space_clients:
        return _space_clients[space]
    with _space_clients_lock:
        if space in _space_clients:
            return _space_clients[space]
        settings = TRSGraphSettings.from_env()
        settings.space = space
        client = TRSGraphClient(settings)
        client.connect()
        _space_clients[space] = client
        return client


def get_business_space_client(request_space: str | None) -> TRSGraphClient | None:
    """九大业务数据面客户端；TRS_GRAPH_BUSINESS_BASE_URL 未配置时返回 None（回落平台面）。

    连接参数见 infra.graph_db.config.business_plane_settings；X-Business-Graph-Space
    覆盖（business_space_override ContextVar）优先于 TRS_GRAPH_BUSINESS_SPACE 钉死。
    与 get_space_client 共用 _space_clients 缓存（key 带 business:: 前缀），因此
    close_space_clients 的停机清理同样覆盖业务面连接，无需在 lifespan 里单独接线。
    """
    from infra.graph_db.config import business_plane_settings
    from service.graph_space_context import business_space_override

    settings = business_plane_settings(request_space, business_space_override.get())
    if settings is None:
        return None
    key = f"business::{settings.base_url}::{settings.space}"
    with _space_clients_lock:
        cached = _space_clients.get(key)
        if cached is not None:
            return cached
        client = TRSGraphClient(settings)
        client.connect()  # may raise; only cache on success
        _space_clients[key] = client
        return client


def close_space_clients() -> None:
    """关闭并清空所有按空间缓存的客户端（应用停机时调用）。"""
    with _space_clients_lock:
        for client in _space_clients.values():
            client.close()
        _space_clients.clear()


_space_algo_clients: dict[str, TRSAlgorithmClient] = {}
_space_algo_clients_lock = threading.Lock()


def get_space_algorithm_client(space: str) -> TRSAlgorithmClient:
    """获取指向指定图空间的算法作业客户端（按空间名缓存，连接参数仍取自 env）。

    综合查询页「图算法」模式允许用户切换图空间提交作业，而 get_algorithm_client
    固定指向 TRS_GRAPH_SPACE，故镜像 get_space_client 提供按空间版本。
    """
    if space in _space_algo_clients:
        return _space_algo_clients[space]
    with _space_algo_clients_lock:
        if space in _space_algo_clients:
            return _space_algo_clients[space]
        settings = TRSGraphSettings.from_env()
        settings.space = space
        client = TRSAlgorithmClient(settings)
        client.connect()
        _space_algo_clients[space] = client
        return client


def close_space_algorithm_clients() -> None:
    """关闭并清空所有按空间缓存的算法作业客户端（应用停机时调用）。"""
    with _space_algo_clients_lock:
        for client in _space_algo_clients.values():
            client.close()
        _space_algo_clients.clear()
