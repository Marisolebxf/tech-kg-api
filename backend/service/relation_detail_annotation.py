"""角色与合作详情标注服务：更新 EMPLOYED_BY 边的 role/tech_field/时段。"""

from __future__ import annotations

from typing import Any

from infra.graph_db import TRSGraphClient, get_techkg_client
from service.base_module import KGModuleScaffoldService
from service.enterprise_relation_catalog import role_info

EDGE_TYPE = "EMPLOYED_BY"


class RelationDetailAnnotationService(KGModuleScaffoldService):
    module_code = "relation_detail_annotation"

    def __init__(self) -> None:
        super().__init__()
        self._graph: TRSGraphClient | None = None

    def _client(self) -> TRSGraphClient:
        if self._graph is None:
            self._graph = get_techkg_client()
        return self._graph

    def annotate(self, payload: dict[str, Any]) -> dict[str, Any]:
        relation_id = payload.get("relationId", "")
        role_type = payload.get("roleType", "")
        tech_field = payload.get("techField", "")
        period = payload.get("period") or {}
        start = period.get("start", "") if isinstance(period, dict) else ""
        end = period.get("end", "") if isinstance(period, dict) else ""

        role_label, role_level = role_info(role_type)
        graph = self._client()

        existing = graph.get_edge(relation_id, edge_type=EDGE_TYPE)
        if existing is None:
            raise KeyError(f"关系不存在: {relation_id}")

        graph.update_edge(
            relation_id,
            properties={
                "role": role_type,
                "tech_field": tech_field,
                "start_date": start or "",
                "end_date": end or "",
            },
            edge_type=EDGE_TYPE,
        )

        return {
            "status": "success",
            "relationId": relation_id,
            "roleType": role_type,
            "roleLabel": role_label,
            "roleLevel": role_level,
            "techField": tech_field,
            "period": {"start": start or "", "end": end or ""},
            "annotated": True,
        }
