"""专家-企业关系构建服务（向 techkg 图写入 EMPLOYED_BY 边并返回该专家全部企业关系）。

同一人才-企业对只保留一条 EMPLOYED_BY 边（rank=0），多个关系类型用 "/" 合并存于
relation_type 属性。
"""

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

    def _existing_relation_types(
        self, graph: TRSGraphClient, scholar_id: str, enterprise_id: str
    ) -> list[str]:
        """取该人才-企业现有边的 relation_type（按 / 拆分）。无则空。"""
        try:
            edges = graph.get_node_edges(
                scholar_id, direction="out", edge_type="EMPLOYED_BY", limit=100
            )
        except Exception:
            return []
        for e in edges:
            if str(e.target_id) == str(enterprise_id):
                rt = e.properties.get("relation_type", "") or ""
                return [t for t in rt.split("/") if t]
        return []

    def build(self, payload: dict[str, Any]) -> dict[str, Any]:
        scholar_id = payload.get("scholarId", "")
        enterprise_id = payload.get("enterpriseId", "")
        relation_type = payload.get("relationType", "")
        graph = self._client()

        scholar = graph.get_node(scholar_id)
        scholar_name = scholar.properties.get("name_zh") if scholar else None

        built_relation_id: str | None = None
        effective = False
        if scholar is not None:
            enterprise = graph.get_node(enterprise_id)
            if enterprise is not None and relation_type:
                built_relation_id = f"{scholar_id}->{enterprise_id}@0"
                types = self._existing_relation_types(graph, scholar_id, enterprise_id)
                if relation_type not in types:
                    types.append(relation_type)
                new_rt = "/".join(types)
                stmt = (
                    f"INSERT EDGE EMPLOYED_BY(relation_type,role,start_date,end_date,source) "
                    f'VALUES "{scholar_id}"->"{enterprise_id}"@0:'
                    f'("{new_rt}","","","","build");'
                )
                try:
                    graph.execute_write(stmt)
                    effective = True
                except Exception:
                    effective = False

        # 查询该专家的全部企业关系（每个企业一条边，relation_type 为 / 合并）
        relations: list[dict[str, Any]] = []
        if scholar is not None:
            try:
                edges = graph.get_node_edges(
                    scholar_id, direction="out", edge_type="EMPLOYED_BY", limit=100
                )
            except Exception:
                edges = []
            for e in edges:
                org = graph.get_node(e.target_id)
                if org is None:
                    continue
                op = org.properties
                relations.append(
                    {
                        "relationId": e.id,
                        "enterpriseId": str(op.get("org_id", e.target_id)),
                        "enterpriseName": op.get("name_cn", "") or "",
                        "relationType": e.properties.get("relation_type", "") or "",
                    }
                )

        return {
            "status": "success",
            "scholarId": scholar_id,
            "scholarName": scholar_name,
            "builtRelationId": built_relation_id,
            "relationType": relation_type,
            "effective": effective,
            "relations": relations,
        }
