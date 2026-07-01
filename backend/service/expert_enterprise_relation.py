"""专家-企业关系构建服务（向 techkg 图写入 EMPLOYED_BY 边并返回该专家全部企业关系）。

同一人才-企业对只保留一条 EMPLOYED_BY 边（rank=0），多个关系类型英文码用 "/" 合并
存于 relation_type 属性；响应映射为中文标签。返回时按企业去重。
"""

from __future__ import annotations

from typing import Any

from dao.gkx_organization import GkxOrganizationDAO
from dao.gkx_scholar import GkxScholarDAO
from infra.gkx import get_gkx_session
from infra.graph_db import TRSGraphClient, get_techkg_client
from service.base_module import KGModuleScaffoldService
from service.enterprise_relation_catalog import relation_label, validate_relation_types

EDGE_TYPE = "EMPLOYED_BY"


class ExpertEnterpriseRelationService(KGModuleScaffoldService):
    module_code = "expert_enterprise_relation"

    def __init__(self) -> None:
        super().__init__()
        self._graph: TRSGraphClient | None = None

    def _client(self) -> TRSGraphClient:
        if self._graph is None:
            self._graph = get_techkg_client()
        return self._graph

    @staticmethod
    def _parse_rank(eid: Any) -> int:
        rest = str(eid).split("->")[-1]
        if "@" in rest:
            try:
                return int(rest.split("@")[-1])
            except ValueError:
                return 0
        return 0

    @staticmethod
    def _split_codes(rt: str) -> list[str]:
        return [c for c in (rt or "").split("/") if c]

    def _edges_to(self, graph: TRSGraphClient, scholar_id: str, enterprise_id: str) -> list[Any]:
        try:
            edges = graph.get_node_edges(
                scholar_id, direction="out", edge_type=EDGE_TYPE, limit=100
            )
        except Exception:
            return []
        return [e for e in edges if str(e.target_id) == str(enterprise_id)]

    def _provision_scholar(self, graph: TRSGraphClient, scholar_id: str) -> Any:
        """图库无该学者时，从 gkx_local.dwd_scholar 查真实信息并创建图库节点。"""
        try:
            session = get_gkx_session()
            try:
                s = GkxScholarDAO(session).get_by_id(scholar_id)
            finally:
                session.close()
        except Exception:
            # gkx 不可用（如 CI 无 DB），返回 None 让 build 抛 KeyError
            return None
        if s is None:
            return None
        try:
            graph.create_node(
                ["Scholar"],
                {
                    "scholar_id": s.scholar_id,
                    "name_zh": s.name_zh or "",
                    "name_en": s.name_en or "",
                    "scholar_org_name_zh": s.scholar_org_name_zh or "",
                    "h_index": int(s.h_index or 0),
                    "citation_nums": int(s.citation_nums or 0),
                    "paper_nums": int(s.paper_nums or 0),
                },
            )
        except Exception:
            return None
        return graph.get_node(scholar_id)

    def _provision_enterprise(self, graph: TRSGraphClient, enterprise_id: str) -> Any:
        """图库无该企业时，从 gkx 企业表查真实信息并创建图库节点。"""
        try:
            session = get_gkx_session()
            try:
                org = GkxOrganizationDAO(session).get_by_id(enterprise_id)
            finally:
                session.close()
        except Exception:
            return None
        if org is None:
            return None
        try:
            graph.create_node(
                ["Organization"],
                {
                    "org_id": org.org_id,
                    "name_cn": org.name_cn or "",
                    "province": getattr(org, "province", None) or "",
                    "listing_status": getattr(org, "listing_status", None)
                    or getattr(org, "listed_status", None)
                    or "",
                },
            )
        except Exception:
            return None
        return graph.get_node(enterprise_id)

    def build(self, payload: dict[str, Any]) -> dict[str, Any]:
        scholar_id = payload.get("scholarId", "")
        enterprise_id = payload.get("enterpriseId", "")
        codes = validate_relation_types(list(payload.get("relationTypes", [])))
        graph = self._client()

        scholar = graph.get_node(scholar_id)
        if scholar is None:
            scholar = self._provision_scholar(graph, scholar_id)
        if scholar is None:
            raise KeyError(f"专家不存在: {scholar_id}")
        scholar_name = scholar.properties.get("name_zh") or scholar_id

        enterprise = graph.get_node(enterprise_id)
        if enterprise is None:
            enterprise = self._provision_enterprise(graph, enterprise_id)
        if enterprise is None:
            raise KeyError(f"企业不存在: {enterprise_id}")

        built_relation_id = f"{scholar_id}->{enterprise_id}@0"
        existing = self._edges_to(graph, scholar_id, enterprise_id)
        merged: list[str] = []
        for e in existing:
            for c in self._split_codes(e.properties.get("relation_type", "")):
                if c not in merged:
                    merged.append(c)
        for c in codes:
            if c not in merged:
                merged.append(c)

        props = {
            "relation_type": "/".join(merged),
            "role": "",
            "start_date": "",
            "end_date": "",
            "source": "build",
        }
        effective = False
        try:
            graph.create_edge(scholar_id, enterprise_id, EDGE_TYPE, props)
            effective = True
            for e in existing:
                if self._parse_rank(e.id) != 0:
                    try:
                        graph.delete_edge(e.id, edge_type=EDGE_TYPE)
                    except Exception:
                        pass
        except Exception:
            effective = False

        relations = self._collect_relations(graph, scholar_id)

        return {
            "status": "success",
            "scholarId": scholar_id,
            "scholarName": scholar_name,
            "builtRelationId": built_relation_id,
            "relationType": relation_label(merged) if merged else relation_label(codes),
            "effective": effective,
            "relations": relations,
        }

    def _collect_relations(self, graph: TRSGraphClient, scholar_id: str) -> list[dict[str, Any]]:
        try:
            edges = graph.get_node_edges(
                scholar_id, direction="out", edge_type=EDGE_TYPE, limit=100
            )
        except Exception:
            return []
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
                    "codes": [],
                },
            )
            for c in self._split_codes(e.properties.get("relation_type", "")):
                if c not in entry["codes"]:
                    entry["codes"].append(c)
        return [
            {
                "relationId": v["relationId"],
                "enterpriseId": v["enterpriseId"],
                "enterpriseName": v["enterpriseName"],
                "relationType": relation_label(v["codes"]) if v["codes"] else "",
            }
            for v in by_ent.values()
        ]
