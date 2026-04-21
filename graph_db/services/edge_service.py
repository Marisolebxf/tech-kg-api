"""Edge CRUD service layer."""

from __future__ import annotations

from typing import Any, Sequence

from graph_db.base import GraphDatabase
from graph_db.models import Edge, PagedResult


class EdgeService:
    """Encapsulates all edge-related operations.

    Usage::

        from graph_db import connect, GraphDBConfig
        from graph_db.services import EdgeService

        db = connect(GraphDBConfig.from_env())
        svc = EdgeService(db)

        edge = svc.create(alice.id, bob.id, "KNOWS", {"since": 2020})
    """

    def __init__(self, db: GraphDatabase) -> None:
        self._db = db

    def create(
        self,
        source_id: Any,
        target_id: Any,
        edge_type: str,
        properties: dict[str, Any] | None = None,
    ) -> Edge:
        return self._db.create_edge(source_id, target_id, edge_type, properties)

    def merge(
        self,
        source_id: Any,
        target_id: Any,
        edge_type: str,
        identity_props: dict[str, Any],
        properties: dict[str, Any] | None = None,
    ) -> Edge:
        return self._db.merge_edge(source_id, target_id, edge_type, identity_props, properties)

    def get(self, edge_id: Any) -> Edge | None:
        return self._db.get_edge(edge_id)

    def list_by_type(self, edge_type: str, *, limit: int = 100, offset: int = 0) -> PagedResult:
        return self._db.get_edges_by_type(edge_type, limit=limit, offset=offset)

    def find(
        self,
        edge_type: str,
        properties: dict[str, Any],
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> PagedResult:
        return self._db.find_edges(edge_type, properties, limit=limit, offset=offset)

    def update(self, edge_id: Any, properties: dict[str, Any]) -> Edge:
        return self._db.update_edge(edge_id, properties)

    def delete(self, edge_id: Any) -> bool:
        return self._db.delete_edge(edge_id)

    def batch_create(self, items: Sequence[dict[str, Any]], edge_type: str) -> list[Edge]:
        return self._db.batch_create_edges(items, edge_type)
