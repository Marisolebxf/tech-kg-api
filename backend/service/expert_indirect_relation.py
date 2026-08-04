from __future__ import annotations

from collections import defaultdict
from typing import Any

from infra.graph_db import TRSGraphClient, get_graph_client
from service.base_module import KGModuleService


class ExpertIndirectRelationService(KGModuleService):
    module_code = "expert_indirect_relation"

    def __init__(self, graph: TRSGraphClient | None = None) -> None:
        self._graph = graph

    def query(
        self,
        *,
        expert_id: str,
        edge_types: list[str] | None = None,
        limit: int = 20,
        space: str | None = None,
    ) -> dict[str, Any]:
        graph = self._graph or get_graph_client(space)
        center = graph.get_node(expert_id)
        if center is None:
            raise KeyError(f"图节点不存在: {expert_id}")
        allowed = {item for item in edge_types or [] if item}
        first_edges = graph.get_node_edges(expert_id, direction="both", limit=500)
        direct_ids: set[str] = set()
        first_by_neighbor: dict[str, list[Any]] = defaultdict(list)
        for edge in first_edges:
            if allowed and edge.type not in allowed:
                continue
            neighbor = str(edge.target_id if str(edge.source_id) == expert_id else edge.source_id)
            direct_ids.add(neighbor)
            first_by_neighbor[neighbor].append(edge)

        paths: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for intermediary, incoming in first_by_neighbor.items():
            for outgoing in graph.get_node_edges(intermediary, direction="both", limit=500):
                if allowed and outgoing.type not in allowed:
                    continue
                target = str(
                    outgoing.target_id
                    if str(outgoing.source_id) == intermediary
                    else outgoing.source_id
                )
                if target == expert_id or target in direct_ids:
                    continue
                for first in incoming:
                    paths[target].append(
                        {
                            "nodes": [expert_id, intermediary, target],
                            "edgeTypes": [first.type, outgoing.type],
                            "edgeIds": [str(first.id), str(outgoing.id)],
                        }
                    )

        items = []
        for target_id, target_paths in paths.items():
            node = graph.get_node(target_id)
            if node is None:
                continue
            intermediaries = sorted({path["nodes"][1] for path in target_paths})
            items.append(
                {
                    "target": _node_data(node),
                    "pathCount": len(target_paths),
                    "intermediaryCount": len(intermediaries),
                    "intermediaries": intermediaries,
                    "score": min(100, 45 + len(target_paths) * 12 + len(intermediaries) * 8),
                    "paths": target_paths[:10],
                }
            )
        items.sort(key=lambda item: (item["score"], item["pathCount"]), reverse=True)
        items = items[: max(1, min(limit, 100))]
        return {
            "center": _node_data(center),
            "total": len(items),
            "items": items,
            "graph": _indirect_graph(center, items, graph),
        }


def _node_data(node: Any) -> dict[str, Any]:
    return {"id": str(node.id), "labels": node.labels, "properties": node.properties}


def _indirect_graph(
    center: Any, items: list[dict[str, Any]], graph: TRSGraphClient
) -> dict[str, Any]:
    nodes = {str(center.id): _node_data(center)}
    edges: dict[str, dict[str, Any]] = {}
    for item in items:
        nodes[item["target"]["id"]] = item["target"]
        for path in item["paths"]:
            intermediary = path["nodes"][1]
            if intermediary not in nodes and (node := graph.get_node(intermediary)) is not None:
                nodes[intermediary] = _node_data(node)
            for index, edge_id in enumerate(path["edgeIds"]):
                edges.setdefault(
                    edge_id,
                    {
                        "id": edge_id,
                        "source": path["nodes"][index],
                        "target": path["nodes"][index + 1],
                        "type": path["edgeTypes"][index],
                    },
                )
    return {"nodes": list(nodes.values()), "edges": list(edges.values())}
