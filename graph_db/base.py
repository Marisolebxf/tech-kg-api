"""Abstract base class defining the generic graph database API.

Every backend (Neo4j, Memgraph, NebulaGraph, etc.) must implement this
interface so that application code remains database-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from graph_db.models import (
    ConstraintSpec,
    Edge,
    IndexSpec,
    Node,
    PagedResult,
    Path,
    QueryResult,
)

# ---------------------------------------------------------------------------
# Transaction protocol — lightweight context-manager wrapper
# ---------------------------------------------------------------------------


@runtime_checkable
class Transaction(Protocol):
    """Protocol for an in-flight transaction.

    Used as a context manager so users can write:

        with db.transaction() as tx:
            tx.create_node(...)
            tx.create_edge(...)
            # auto-commit on success, auto-rollback on exception
    """

    def create_node(self, labels: list[str], properties: dict[str, Any] | None = None) -> Node: ...

    def merge_node(
        self,
        labels: list[str],
        identity_props: dict[str, Any],
        properties: dict[str, Any] | None = None,
    ) -> Node: ...

    def get_node(self, node_id: Any) -> Node | None: ...

    def update_node(self, node_id: Any, properties: dict[str, Any]) -> Node: ...

    def delete_node(self, node_id: Any, detach: bool = False) -> bool: ...

    def create_edge(
        self,
        source_id: Any,
        target_id: Any,
        edge_type: str,
        properties: dict[str, Any] | None = None,
    ) -> Edge: ...

    def merge_edge(
        self,
        source_id: Any,
        target_id: Any,
        edge_type: str,
        identity_props: dict[str, Any],
        properties: dict[str, Any] | None = None,
    ) -> Edge: ...

    def get_edge(self, edge_id: Any) -> Edge | None: ...

    def update_edge(self, edge_id: Any, properties: dict[str, Any]) -> Edge: ...

    def delete_edge(self, edge_id: Any) -> bool: ...

    def run(self, query: str, params: dict[str, Any] | None = None) -> QueryResult: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def __enter__(self) -> Transaction: ...

    def __exit__(self, exc_type, exc_val, exc_tb) -> None: ...


# ---------------------------------------------------------------------------
# Abstract graph database
# ---------------------------------------------------------------------------


class GraphDatabase(ABC):
    """Database-agnostic graph database interface.

    Design principles
    -----------------
    1. **CRUD-first**: Node and Edge CRUD are first-class citizens.
    2. **Query escape hatch**: Raw Cypher / Gremlin is always available
       via ``execute_query`` / ``execute_read`` / ``execute_write``.
    3. **Transaction support**: Explicit transactions for atomicity,
       plus auto-commit convenience methods.
    4. **Batch operations**: Bulk create/update for high-throughput
       ingestion scenarios.
    5. **Schema management**: Index and constraint lifecycle.

    Subclass this for each backend (Neo4j, Memgraph, …) and implement
    every ``@abstractmethod``.
    """

    # ----- connection lifecycle -----

    @abstractmethod
    def connect(self) -> None:
        """Establish a connection to the database."""

    @abstractmethod
    def close(self) -> None:
        """Close the connection and release resources."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Return ``True`` if the connection is alive."""

    # ----- convenience context manager -----

    def __enter__(self) -> GraphDatabase:
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # ==================================================================
    # Node CRUD
    # ==================================================================

    @abstractmethod
    def create_node(self, labels: list[str], properties: dict[str, Any] | None = None) -> Node:
        """Create a node with the given labels and properties.

        Returns the created node with its database-assigned ``id``.
        """

    @abstractmethod
    def merge_node(
        self,
        labels: list[str],
        identity_props: dict[str, Any],
        properties: dict[str, Any] | None = None,
    ) -> Node:
        """Merge (upsert) a node identified by *identity_props*.

        If a node matching *labels* + *identity_props* exists, its
        properties are updated with *properties*.  Otherwise a new node
        is created.
        """

    @abstractmethod
    def get_node(self, node_id: Any) -> Node | None:
        """Retrieve a node by its database ID.  Returns ``None`` if not found."""

    @abstractmethod
    def get_nodes_by_label(
        self,
        label: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> PagedResult:
        """List nodes with a given label, with pagination."""

    @abstractmethod
    def find_nodes(
        self,
        labels: list[str],
        properties: dict[str, Any],
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> PagedResult:
        """Find nodes matching all given labels and property equality checks."""

    @abstractmethod
    def update_node(self, node_id: Any, properties: dict[str, Any]) -> Node:
        """Update properties on an existing node (merge-style)."""

    @abstractmethod
    def delete_node(self, node_id: Any, *, detach: bool = False) -> bool:
        """Delete a node.

        Args:
            detach: If ``True``, also delete all attached edges.
                    If ``False`` and edges exist, the backend may raise.
        Returns:
            ``True`` if the node was deleted.
        """

    # ==================================================================
    # Edge CRUD
    # ==================================================================

    @abstractmethod
    def create_edge(
        self,
        source_id: Any,
        target_id: Any,
        edge_type: str,
        properties: dict[str, Any] | None = None,
    ) -> Edge:
        """Create a directed edge from *source_id* to *target_id*."""

    @abstractmethod
    def merge_edge(
        self,
        source_id: Any,
        target_id: Any,
        edge_type: str,
        identity_props: dict[str, Any],
        properties: dict[str, Any] | None = None,
    ) -> Edge:
        """Merge (upsert) an edge identified by *identity_props*."""

    @abstractmethod
    def get_edge(self, edge_id: Any) -> Edge | None:
        """Retrieve an edge by its database ID."""

    @abstractmethod
    def get_edges_by_type(
        self,
        edge_type: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> PagedResult:
        """List edges of a given type, with pagination."""

    @abstractmethod
    def find_edges(
        self,
        edge_type: str,
        properties: dict[str, Any],
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> PagedResult:
        """Find edges matching type and property equality checks."""

    @abstractmethod
    def update_edge(self, edge_id: Any, properties: dict[str, Any]) -> Edge:
        """Update properties on an existing edge (merge-style)."""

    @abstractmethod
    def delete_edge(self, edge_id: Any) -> bool:
        """Delete an edge.  Returns ``True`` if deleted."""

    # ==================================================================
    # Neighbourhood / traversal
    # ==================================================================

    @abstractmethod
    def get_node_edges(
        self,
        node_id: Any,
        *,
        direction: str = "both",  # "in" | "out" | "both"
        edge_type: str | None = None,
        limit: int = 100,
    ) -> list[Edge]:
        """Get edges connected to a node, optionally filtered by direction and type."""

    @abstractmethod
    def get_neighbours(
        self,
        node_id: Any,
        *,
        direction: str = "both",
        edge_type: str | None = None,
        limit: int = 100,
    ) -> list[Node]:
        """Get neighbouring nodes (1-hop), optionally filtered."""

    @abstractmethod
    def shortest_path(
        self,
        source_id: Any,
        target_id: Any,
        *,
        edge_type: str | None = None,
        max_depth: int = 10,
    ) -> Path | None:
        """Find the shortest path between two nodes.  Returns ``None`` if no path exists."""

    # ==================================================================
    # Query execution
    # ==================================================================

    @abstractmethod
    def execute_query(self, query: str, params: dict[str, Any] | None = None) -> QueryResult:
        """Execute a raw query string (Cypher / Gremlin) and return results.

        This is the *escape hatch* — use it when the CRUD / traversal
        methods don't cover your use case.
        """

    @abstractmethod
    def execute_read(self, query: str, params: dict[str, Any] | None = None) -> QueryResult:
        """Execute a read-only query (may be routed to a read replica)."""

    @abstractmethod
    def execute_write(self, query: str, params: dict[str, Any] | None = None) -> QueryResult:
        """Execute a write query with auto-retry on transient errors."""

    # ==================================================================
    # Transactions
    # ==================================================================

    @abstractmethod
    def transaction(self) -> Transaction:
        """Start an explicit transaction.

        Usage::

            with db.transaction() as tx:
                n = tx.create_node(["Person"], {"name": "Alice"})
                tx.commit()
        """

    # ==================================================================
    # Batch operations
    # ==================================================================

    @abstractmethod
    def batch_create_nodes(
        self,
        items: Sequence[dict[str, Any]],
        labels: list[str],
    ) -> list[Node]:
        """Bulk-create nodes.

        Each item in *items* is a property dict for one node.
        """

    @abstractmethod
    def batch_create_edges(
        self,
        items: Sequence[dict[str, Any]],
        edge_type: str,
    ) -> list[Edge]:
        """Bulk-create edges.

        Each item must contain ``source_id`` and ``target_id`` keys plus
        any additional properties.
        """

    # ==================================================================
    # Schema management
    # ==================================================================

    @abstractmethod
    def create_index(self, spec: IndexSpec) -> None:
        """Create an index (or unique constraint) as specified."""

    @abstractmethod
    def drop_index(self, label: str, properties: list[str]) -> None:
        """Drop an existing index."""

    @abstractmethod
    def list_indexes(self, label: str | None = None) -> list[IndexSpec]:
        """List indexes, optionally filtered by label."""

    @abstractmethod
    def create_constraint(self, spec: ConstraintSpec) -> None:
        """Create a constraint."""

    @abstractmethod
    def drop_constraint(self, name: str) -> None:
        """Drop a constraint by name."""

    @abstractmethod
    def list_constraints(self) -> list[ConstraintSpec]:
        """List all constraints."""

    # ==================================================================
    # Database info
    # ==================================================================

    @abstractmethod
    def node_count(self, label: str | None = None) -> int:
        """Count nodes, optionally filtered by label."""

    @abstractmethod
    def edge_count(self, edge_type: str | None = None) -> int:
        """Count edges, optionally filtered by type."""

    @abstractmethod
    def labels(self) -> list[str]:
        """List all node labels in the database."""

    @abstractmethod
    def edge_types(self) -> list[str]:
        """List all relationship types in the database."""
