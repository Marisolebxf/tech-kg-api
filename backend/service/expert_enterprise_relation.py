"""专家-企业关系构建服务（向 techkg 图写入 EMPLOYED_BY 边）。"""

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
        scholar_id = payload.get("scholarId", "")
        enterprise_id = payload.get("enterpriseId", "")
        relation_types = payload.get("relationTypes", []) or []
        graph = self._client()

        def _result(effective: bool) -> list[dict[str, Any]]:
            return [
                {
                    "relationId": f"{scholar_id}->{enterprise_id}@{i}",
                    "relationType": rt,
                    "effective": effective,
                }
                for i, rt in enumerate(relation_types)
            ]

        # 1) 两端节点必须存在
        if graph.get_node(scholar_id) is None or graph.get_node(enterprise_id) is None:
            return {
                "status": "success",
                "scholarId": scholar_id,
                "enterpriseId": enterprise_id,
                "relations": _result(False),
            }

        # 2) 对每个关系类型写一条 EMPLOYED_BY 边（rank=index）
        relations: list[dict[str, Any]] = []
        for i, rt in enumerate(relation_types):
            rid = f"{scholar_id}->{enterprise_id}@{i}"
            stmt = (
                f"INSERT EDGE EMPLOYED_BY(relation_type,role,start_date,end_date,source) "
                f'VALUES "{scholar_id}"->"{enterprise_id}"@{i}:'
                f'("{rt}","","","","build");'
            )
            try:
                graph.execute_write(stmt)
                relations.append({"relationId": rid, "relationType": rt, "effective": True})
            except Exception:
                relations.append({"relationId": rid, "relationType": rt, "effective": False})

        return {
            "status": "success",
            "scholarId": scholar_id,
            "enterpriseId": enterprise_id,
            "relations": relations,
        }
