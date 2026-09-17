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
    "close_space_clients",
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
    """
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


def close_space_clients() -> None:
    """关闭并清空所有按空间缓存的客户端（应用停机时调用）。"""
    with _space_clients_lock:
        for client in _space_clients.values():
            client.close()
        _space_clients.clear()
