"""Core data models for graph database operations.

Provides Pydantic models for nodes, edges, paths, and query results
that are database-agnostic and can be mapped to/from any graph backend.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Primitive models
# ---------------------------------------------------------------------------

class Node(BaseModel):
    """A node (vertex) in the graph.

    Attributes:
        id: Unique identifier assigned by the database.
        labels: Set of labels (types) attached to the node.
        properties: Key-value property map.
    """

    id: Any = Field(description="Database-assigned unique identifier")
    labels: list[str] = Field(default_factory=list, description="Node labels / types")
    properties: dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary key-value properties"
    )


class Edge(BaseModel):
    """A directed edge (relationship) between two nodes.

    Attributes:
        id: Unique identifier assigned by the database.
        type: Relationship type string (e.g. "KNOWS", "BELONGS_TO").
        source_id: ID of the start (source) node.
        target_id: ID of the end (target) node.
        properties: Key-value property map on the relationship.
    """

    id: Any = Field(description="Database-assigned unique identifier")
    type: str = Field(description="Relationship type")
    source_id: Any = Field(description="Source node ID")
    target_id: Any = Field(description="Target node ID")
    properties: dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary key-value properties"
    )


class Path(BaseModel):
    """A traversal path consisting of alternating nodes and edges.

    The path always starts and ends with a Node.  Between every pair of
    consecutive nodes there is exactly one Edge.

    Example:
        path.nodes  -> [n0, n1, n2]
        path.edges  -> [e0, e1]  (e0 connects n0->n1, e1 connects n1->n2)
    """

    nodes: list[Node] = Field(description="Ordered list of nodes in the path")
    edges: list[Edge] = Field(description="Ordered list of edges connecting the nodes")


# ---------------------------------------------------------------------------
# Query result models
# ---------------------------------------------------------------------------

class QueryResult(BaseModel):
    """Result of a graph query (e.g. Cypher execution).

    Attributes:
        records: List of result records.  Each record is a dict mapping
            variable names to their values (Node, Edge, Path, or primitive).
        summary: Optional execution summary provided by the backend.
    """

    records: list[dict[str, Any]] = Field(default_factory=list)
    summary: Optional[dict[str, Any]] = None

    @property
    def is_empty(self) -> bool:
        return len(self.records) == 0

    @property
    def count(self) -> int:
        return len(self.records)


class PageInfo(BaseModel):
    """Pagination metadata for list/query results."""

    offset: int = 0
    limit: int = 100
    total: int = 0

    @property
    def has_next(self) -> bool:
        return self.offset + self.limit < self.total


class PagedResult(BaseModel):
    """A page of nodes or edges with pagination info."""

    items: list[Node | Edge] = Field(default_factory=list)
    page: PageInfo = Field(default_factory=PageInfo)


# ---------------------------------------------------------------------------
# Index / constraint models
# ---------------------------------------------------------------------------

class IndexSpec(BaseModel):
    """Specification for a database index.

    Attributes:
        label: Node label to index.
        properties: Property names included in the index.
        unique: Whether the index enforces uniqueness.
    """

    label: str
    properties: list[str]
    unique: bool = False


class ConstraintSpec(BaseModel):
    """Specification for a database constraint.

    Attributes:
        name: Constraint name.
        label: Node label the constraint applies to.
        property: Single property the constraint targets.
        kind: Constraint type — "unique", "node_key", or "exists".
    """

    name: str
    label: str
    property: str
    kind: str = "unique"  # unique | node_key | exists
