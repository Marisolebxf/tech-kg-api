"""Conversion helpers between trs-graph-service JSON and app models."""

from __future__ import annotations

from typing import Any

from infra.graph_db.models import GraphEdge, GraphNode


def _trs_node_to_model(data: dict[str, Any]) -> GraphNode:
    """Convert trs-graph-service Node JSON to a GraphNode."""
    return GraphNode(
        id=data["id"],
        labels=data.get("labels", []),
        properties=data.get("properties", {}),
    )


def _trs_edge_to_model(data: dict[str, Any]) -> GraphEdge:
    """Convert trs-graph-service Edge JSON to a GraphEdge."""
    return GraphEdge(
        id=data["id"],
        type=data["type"],
        source_id=data["sourceId"],
        target_id=data["targetId"],
        properties=data.get("properties", {}),
    )


def _build_node_create_body(
    labels: list[str], properties: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build request body for node creation. First label maps to the Nebula TAG."""
    return {
        "labels": labels if labels else ["Vertex"],
        "properties": dict(properties) if properties else {},
    }


def _parse_edge_id(edge_id: str) -> tuple[str, str, int]:
    """Parse TRS Graph edge id ``"sourceId->targetId@ranking"``."""
    parts = str(edge_id).split("@")
    ranking = int(parts[1]) if len(parts) > 1 else 0
    src_dst = parts[0].split("->")
    return src_dst[0], src_dst[1], ranking


def _strip_quotes(val: Any) -> str:
    """Strip extra surrounding quotes from TRS Graph API responses."""
    if not isinstance(val, str):
        return str(val)
    s = val.strip()
    while s.startswith('"') and s.endswith('"') and len(s) >= 2:
        s = s[1:-1]
    return s
