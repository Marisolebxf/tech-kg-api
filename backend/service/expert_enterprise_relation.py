"""专家-企业关系构建服务（查 techkg 图）。"""

from __future__ import annotations

from typing import Any

from infra.graph_db import TRSGraphClient, get_techkg_client
from service.base_module import KGModuleScaffoldService


class ExpertEnterpriseRelationService(KGModuleScaffoldService):
    module_code = "expert_enterprise_relation"

    def __init__(self) -> None:
        super().__init__()
        self._graph: TRSGraphClient | None = None

    def _client(self) -> TRSGraphClient:
        if self._graph is None:
            self._graph = get_techkg_client()
        return self._graph

    def build(self, payload: dict[str, Any]) -> dict[str, Any]:
        expert_a_id = payload.get("expertAId", "")
        relation_type = payload.get("relationType", "all")
        graph = self._client()

        # 1) 按 scholar_id 找专家节点
        found = graph.find_nodes(["Scholar"], {"scholar_id": expert_a_id}, limit=1)
        if not found.items:
            return {
                "status": "success",
                "expert": None,
                "expert_id": expert_a_id,
                "title": None,
                "enterprises": [],
            }
        scholar = found.items[0]
        props = scholar.properties

        # 2) 取 EMPLOYED_BY 边
        edges = graph.get_node_edges(
            scholar.id, direction="out", edge_type="EMPLOYED_BY", limit=100
        )
        enterprises: list[dict[str, Any]] = []
        for e in edges:
            if relation_type and relation_type != "all":
                if e.properties.get("relation_type", "任职") != relation_type:
                    continue
            org = graph.get_node(e.target_id)
            if org is None:
                continue
            op = org.properties
            enterprises.append(
                {
                    "enterprise_id": str(op.get("org_id", org.id)),
                    "name": op.get("name_cn", "") or "",
                    "type": op.get("org_type", "") or "",
                    "province": op.get("province", "") or "",
                    "relation": e.properties.get("relation_type", "任职"),
                    "role": e.properties.get("role", "") or "",
                    "start_date": e.properties.get("start_date", "") or "",
                    "end_date": e.properties.get("end_date", "") or "",
                }
            )

        return {
            "status": "success",
            "expert": props.get("name_zh") or None,
            "expert_id": props.get("scholar_id") or expert_a_id,
            "title": "",
            "enterprises": enterprises,
        }
