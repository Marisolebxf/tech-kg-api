"""Graph traversal service layer."""

from __future__ import annotations

from typing import Any

from graph_db.base import GraphDatabase
from graph_db.models import Edge, Node, Path


class TraversalService:
    """Encapsulates graph traversal operations.

    Usage::

        from graph_db import connect, GraphDBConfig
        from graph_db.services import TraversalService

        db = connect(GraphDBConfig.from_env())
        svc = TraversalService(db)

        neighbours = svc.neighbours(alice.id, direction="out", edge_type="KNOWS")
    """

    def __init__(self, db: GraphDatabase) -> None:
        self._db = db

    def neighbours(
        self,
        node_id: Any,
        *,
        direction: str = "both",
        edge_type: str | None = None,
        limit: int = 100,
    ) -> list[Node]:
        return self._db.get_neighbours(
            node_id, direction=direction, edge_type=edge_type, limit=limit
        )

    def node_edges(
        self,
        node_id: Any,
        *,
        direction: str = "both",
        edge_type: str | None = None,
        limit: int = 100,
    ) -> list[Edge]:
        return self._db.get_node_edges(
            node_id, direction=direction, edge_type=edge_type, limit=limit
        )

    def shortest_path(
        self,
        source_id: Any,
        target_id: Any,
        *,
        edge_type: str | None = None,
        max_depth: int = 10,
    ) -> Path | None:
        return self._db.shortest_path(
            source_id, target_id, edge_type=edge_type, max_depth=max_depth
        )
