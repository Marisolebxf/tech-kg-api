"""专家-企业关系构建服务（向 techkg 图写入 EMPLOYED_BY 边并返回该专家全部企业关系）。

同一人才-企业对只保留一条 EMPLOYED_BY 边（rank=0），多个关系类型用 "/" 合并存于
relation_type 属性。返回时按企业去重，每个企业一条关系。
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

    def _edges_to(
        self, graph: TRSGraphClient, scholar_id: str, enterprise_id: str
    ) -> list[Any]:
        try:
            edges = graph.get_node_edges(
                scholar_id, direction="out", edge_type="EMPLOYED_BY", limit=100
            )
        except Exception:
            return []
        return [e for e in edges if str(e.target_id) == str(enterprise_id)]

    @staticmethod
    def _parse_rank(eid: Any) -> str:
        """从 edge id 'src->dst@rank' 取 rank（默认 0）。"""
        rest = str(eid).split("->")[-1]
        return rest.split("@")[-1] if "@" in rest else "0"

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
                # 合并该对现有所有边的关系类型
                types: list[str] = []
                existing = self._edges_to(graph, scholar_id, enterprise_id)
                for e in existing:
                    rt = e.properties.get("relation_type", "") or ""
                    for t in rt.split("/"):
                        if t and t not in types:
                            types.append(t)
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
                    # 合并后删除该对多余的 rank 边，只留 @0
                    for e in existing:
                        if self._parse_rank(e.id) != "0":
                            try:
                                graph.execute_write(
                                    f'DELETE EDGE EMPLOYED_BY "{scholar_id}"->"{enterprise_id}"@{self._parse_rank(e.id)};'
                                )
                            except Exception:
                                pass
                except Exception:
                    effective = False

        # 查询该专家全部企业关系，按企业去重合并
        relations: list[dict[str, Any]] = []
        if scholar is not None:
            try:
                edges = graph.get_node_edges(
                    scholar_id, direction="out", edge_type="EMPLOYED_BY", limit=100
                )
            except Exception:
                edges = []
            by_ent: dict[str, dict[str, Any]] = {}
            for e in edges:
                org = graph.get_node(e.target_id)
                if org is None:
                    continue
                op = org.properties
                eid = str(op.get("org_id", e.target_id))
                entry = by_ent.setdefault(
                    eid,
                    {
                        "relationId": f"{scholar_id}->{e.target_id}@0",
                        "enterpriseId": eid,
                        "enterpriseName": op.get("name_cn", "") or "",
                        "types": [],
                    },
                )
                rt = e.properties.get("relation_type", "") or ""
                for t in rt.split("/"):
                    if t and t not in entry["types"]:
                        entry["types"].append(t)
            for entry in by_ent.values():
                relations.append(
                    {
                        "relationId": entry["relationId"],
                        "enterpriseId": entry["enterpriseId"],
                        "enterpriseName": entry["enterpriseName"],
                        "relationType": "/".join(entry["types"]),
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
