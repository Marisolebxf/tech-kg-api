"""Node CRUD service layer."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from graph_db.base import GraphDatabase
from graph_db.models import Node, PagedResult


class NodeService:
    """Encapsulates all node-related operations.

    Usage::

        from graph_db import connect, GraphDBConfig
        from graph_db.services import NodeService

        db = connect(GraphDBConfig.from_env())
        svc = NodeService(db)

        alice = svc.create(["Person"], {"name": "Alice"})
    """

    def __init__(self, db: GraphDatabase) -> None:
        self._db = db

    def create(self, labels: list[str], properties: dict[str, Any] | None = None) -> Node:
        return self._db.create_node(labels, properties)

    def merge(
        self,
        labels: list[str],
        identity_props: dict[str, Any],
        properties: dict[str, Any] | None = None,
    ) -> Node:
        return self._db.merge_node(labels, identity_props, properties)

    def get(self, node_id: Any) -> Node | None:
        return self._db.get_node(node_id)

    def list_by_label(self, label: str, *, limit: int = 100, offset: int = 0) -> PagedResult:
        return self._db.get_nodes_by_label(label, limit=limit, offset=offset)

    def find(
        self,
        labels: list[str],
        properties: dict[str, Any],
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> PagedResult:
        return self._db.find_nodes(labels, properties, limit=limit, offset=offset)

    def update(self, node_id: Any, properties: dict[str, Any]) -> Node:
        return self._db.update_node(node_id, properties)

    def delete(self, node_id: Any, *, detach: bool = False) -> bool:
        return self._db.delete_node(node_id, detach=detach)

    def batch_create(self, items: Sequence[dict[str, Any]], labels: list[str]) -> list[Node]:
        return self._db.batch_create_nodes(items, labels)
