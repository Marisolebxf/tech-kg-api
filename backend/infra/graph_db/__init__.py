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
    """techkg 图空间单例（space 固定为 'techkg'，其余读 TRS_GRAPH_* env）。"""
    global _techkg_client
    if _techkg_client is not None:
        return _techkg_client
    with _client_lock:
        if _techkg_client is not None:
            return _techkg_client
        settings = TRSGraphSettings.from_env()
        settings.space = "techkg"
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
