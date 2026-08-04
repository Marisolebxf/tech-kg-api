"""Internal trs-graph ORM repository for app services.

Public API::

    from infra.graph_db import get_trs_graph_client

    repo = get_trs_graph_client()
    node = repo.create_node(["Person"], {"name": "Alice"})
"""

from __future__ import annotations

import threading

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
    "TRSGraphSettings",
    "get_trs_graph_client",
    "close_trs_graph_client",
    "get_techkg_client",
    "close_techkg_client",
    "get_graph_client",
    "close_graph_clients",
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
_client_lock = threading.RLock()
_space_clients: dict[str, TRSGraphClient] = {}


def get_trs_graph_client() -> TRSGraphClient:
    """Return the process-wide connected TRSGraphClient singleton (lazy, thread-safe)."""
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


_techkg_client: TRSGraphClient | None = None


def get_techkg_client() -> TRSGraphClient:
    """兼容旧调用名；图空间统一读取 TRS_GRAPH_SPACE。"""
    global _techkg_client
    if _techkg_client is not None:
        return _techkg_client
    with _client_lock:
        if _techkg_client is not None:
            return _techkg_client
        settings = TRSGraphSettings.from_env()
        client = TRSGraphClient(settings)
        client.connect()
        _techkg_client = client
    return _techkg_client


def close_techkg_client() -> None:
    """关闭并释放 techkg 单例。"""
    global _techkg_client
    with _client_lock:
        if _techkg_client is not None:
            _techkg_client.close()
            _techkg_client = None


def get_graph_client(space: str | None = None) -> TRSGraphClient:
    """Return the default client or a cached client for an explicitly selected space."""
    if not space:
        return get_trs_graph_client()
    with _client_lock:
        if space not in _space_clients:
            settings = TRSGraphSettings.from_env().model_copy(update={"space": space})
            client = TRSGraphClient(settings)
            client.connect()
            _space_clients[space] = client
        return _space_clients[space]


def close_graph_clients() -> None:
    """Close default, compatibility, and explicit-space graph clients."""
    global _client, _techkg_client
    with _client_lock:
        clients = [
            *(_space_clients.values()),
            *([_client] if _client is not None else []),
            *([_techkg_client] if _techkg_client is not None else []),
        ]
        seen: set[int] = set()
        for client in clients:
            if id(client) not in seen:
                client.close()
                seen.add(id(client))
        _space_clients.clear()
        _client = None
        _techkg_client = None
