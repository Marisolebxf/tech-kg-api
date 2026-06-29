"""Pydantic models for the trs-graph repository (app-owned, graph_db-independent)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    """A node (vertex) in the graph."""

    id: Any = Field(description="Database-assigned unique identifier")
    labels: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    """A directed edge (relationship) between two nodes."""

    id: Any = Field(description="Edge id, e.g. 'sourceId->targetId@ranking'")
    type: str = Field(description="Relationship type")
    source_id: Any = Field(description="Source node id")
    target_id: Any = Field(description="Target node id")
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphPath(BaseModel):
    """A traversal path of alternating nodes and edges."""

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class GraphQueryResult(BaseModel):
    """Result of a raw nGQL query."""

    records: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] | None = None


class GraphPagedResult(BaseModel):
    """A page of nodes or edges with pagination metadata."""

    items: list[Any] = Field(default_factory=list)
    total: int = 0
    limit: int = 100
    offset: int = 0


class GraphIndexSpec(BaseModel):
    """Specification for a graph index."""

    label: str
    properties: list[str]
    unique: bool = False


class GraphConstraintSpec(BaseModel):
    """Specification for a graph constraint."""

    name: str
    label: str
    property: str
    kind: str = "unique"
