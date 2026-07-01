"""专家企业关系挖掘服务：从学者传记 LLM 抽取企业 → 消歧 → 建图节点 → 编排调 build/annotate/analyze。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from dao.gkx_organization import GkxOrganizationDAO
from dao.gkx_scholar import GkxScholarDAO
from db_model.scholar import DwdScholar
from infra.gkx import get_gkx_session
from infra.graph_db import TRSGraphClient, get_techkg_client
from infra.llm import LLMClient, get_llm_client
from service.base_module import KGModuleScaffoldService
from service.enterprise_background_analysis import EnterpriseBackgroundAnalysisService
from service.enterprise_mining_disambiguator import disambiguate, merge_matches
from service.enterprise_mining_extractor import extract_relations
from service.enterprise_relation_catalog import relation_label, role_info
from service.expert_enterprise_relation import EDGE_TYPE, ExpertEnterpriseRelationService
from service.relation_detail_annotation import RelationDetailAnnotationService

logger = logging.getLogger(__name__)

DEFAULT_DIMENSIONS = ["industry_status", "core_tech", "financial"]


class ExpertEnterpriseMiningService(KGModuleScaffoldService):
    module_code = "expert_enterprise_mining"

    def __init__(
        self,
        gkx_session=None,
        graph: TRSGraphClient | None = None,
        llm: LLMClient | None = None,
    ) -> None:
        super().__init__()
        self._gkx_session = gkx_session
        self._graph = graph
        self._llm = llm
        self._build_svc = ExpertEnterpriseRelationService()
        self._annotate_svc = RelationDetailAnnotationService()
        self._analyze_svc = EnterpriseBackgroundAnalysisService()
        # 测试可注入的工厂/函数
        self._scholar_dao_factory: Callable = GkxScholarDAO
        self._org_dao_factory: Callable = GkxOrganizationDAO
        self._extract_fn = extract_relations

    # ----- 依赖懒加载 -----
    def _session(self):
        if self._gkx_session is None:
            self._gkx_session = get_gkx_session()
        return self._gkx_session

    def _graph_client(self) -> TRSGraphClient:
        if self._graph is None:
            self._graph = get_techkg_client()
        return self._graph

    def _llm_client(self):
        if self._llm is None:
            self._llm = get_llm_client()
        return self._llm

    # ----- 主流程 -----
    def mine(self, payload: dict[str, Any]) -> dict[str, Any]:
        scholar_id = payload.get("scholarId", "")
        regenerate = bool(payload.get("regenerate", False))
        top_n = min(max(int(payload.get("topN") or 5), 1), 10)
        dims = payload.get("analysisDimensions") or DEFAULT_DIMENSIONS

        graph = self._graph_client()

        # regenerate=False 时，先查图库已构建的 EMPLOYED_BY 关系；有则直接返回，不跑 LLM/三接口
        if not regenerate:
            existing = self._collect_existing_relations(graph, scholar_id)
            if existing:
                scholar_node = graph.get_node(scholar_id)
                sp = scholar_node.properties if scholar_node is not None else {}
                return {
                    "status": "success",
                    "scholarId": scholar_id,
                    "scholarName": sp.get("name_zh", "") or "",
                    "scholarOrg": sp.get("scholar_org_name_zh", "") or "",
                    "profile": {},
                    "degraded": False,
                    "cached": True,
                    "reminder": "",
                    "minedRelations": existing,
                    "skipped": [],
                    "totalMined": len(existing),
                }

        session = self._session()
        scholar = self._scholar_dao_factory(session).get_by_id(scholar_id)
        if scholar is None:
            raise KeyError(f"学者不存在: {scholar_id}")
        directions = self._scholar_dao_factory(session).get_research_directions(scholar_id)

        profile = {
            "name_zh": scholar.name_zh or "",
            "scholar_org_name_zh": scholar.scholar_org_name_zh or "",
            "bio_zh": scholar.bio_zh or "",
            "work_experience_zh": scholar.work_experience_zh or "",
            "education_background_zh": scholar.education_background_zh or "",
        }
        items, degraded = self._extract_fn(self._llm_client(), profile)

        candidates = self._org_dao_factory(session).list_name_id()
        matches: list[dict] = []
        skipped: list[dict] = []
        for it in items:
            m = disambiguate(it["enterprise_name"], candidates)
            if m is None:
                skipped.append(
                    {"name": it["enterprise_name"], "reason": "未匹配到企业(置信度低于阈值)"}
                )
                continue
            matches.append({**it, **m})
        merged = merge_matches(matches)
        merged.sort(key=lambda x: x["score"], reverse=True)
        top = merged[:top_n]

        self._provision_scholar_node(graph, scholar)
        org_dao = self._org_dao_factory(session)

        relations: list[dict] = []
        for rank, m in enumerate(top, start=1):
            self._provision_org_node(graph, m["org_id"], org_dao)
            relation_type = m["relation_types"][0] if m["relation_types"] else "tech_cooperation"
            role_label, _ = role_info(m["role"])
            entry: dict[str, Any] = {
                "rank": rank,
                "status": "matched",
                "enterpriseId": m["org_id"],
                "enterpriseName": m["name_cn"],
                "matchScore": m["score"],
                "relationType": relation_type,
                "relationLabel": relation_label(m["relation_types"]),
                "role": m["role"],
                "roleLabel": role_label,
                "techField": m["tech_field"],
                "period": {"start": m["period_start"], "end": m["period_end"]},
                "evidence": m["evidence"],
                "build": None,
                "annotate": None,
                "analyze": None,
            }
            # build
            built_id = None
            try:
                b = self._build_svc.build(
                    {
                        "scholarId": scholar_id,
                        "enterpriseId": m["org_id"],
                        "relationTypes": m["relation_types"] or [relation_type],
                    }
                )
                entry["build"] = {
                    "effective": bool(b.get("effective")),
                    "builtRelationId": b.get("builtRelationId"),
                }
                built_id = b.get("builtRelationId")
            except Exception as exc:  # noqa: BLE001
                logger.warning("mining build failed for %s: %s", m["org_id"], exc)
            # annotate（仅当 build 成功）
            if built_id:
                try:
                    a = self._annotate_svc.annotate(
                        {
                            "relationId": built_id,
                            "roleType": m["role"],
                            "techField": m["tech_field"],
                            "period": {"start": m["period_start"], "end": m["period_end"]},
                        }
                    )
                    entry["annotate"] = {"annotated": bool(a.get("annotated"))}
                except Exception as exc:  # noqa: BLE001
                    logger.warning("mining annotate failed for %s: %s", m["org_id"], exc)
            # analyze（传 gkx session）
            try:
                an = self._analyze_svc.analyze(
                    {"enterpriseId": m["org_id"], "analysisDimensions": dims, "patentCPC": []},
                    session=session,
                )
                entry["analyze"] = {
                    "dimensions": an.get("dimensions"),
                    "coreTechLayout": an.get("coreTechLayout"),
                }
            except Exception as exc:  # noqa: BLE001
                logger.warning("mining analyze failed for %s: %s", m["org_id"], exc)
            relations.append(entry)

        matched_count = len(relations)
        # 未在企业表中找到的抽取企业，也带入关系列表并提醒（status=unmatched）
        for idx, sk in enumerate(skipped, start=matched_count + 1):
            relations.append(
                {
                    "rank": idx,
                    "status": "unmatched",
                    "enterpriseName": sk["name"],
                    "matchScore": None,
                    "reminder": "未在 gkx 企业表中找到匹配，无法构建关系",
                    "build": None,
                    "annotate": None,
                    "analyze": None,
                }
            )

        if matched_count == 0 and not skipped:
            reminder = "未从学者传记中抽取出关联企业（学者可能为纯学术背景，或 LLM 不可用）"
        elif skipped:
            names = "、".join(s["name"] for s in skipped)
            reminder = f"其中 {len(skipped)} 个企业未在企业表中找到匹配：{names}"
        else:
            reminder = ""

        return {
            "status": "success",
            "scholarId": scholar_id,
            "scholarName": scholar.name_zh or "",
            "scholarOrg": scholar.scholar_org_name_zh or "",
            "profile": {"bio_zh": scholar.bio_zh or "", "researchDirections": directions},
            "degraded": degraded,
            "cached": False,
            "reminder": reminder,
            "minedRelations": relations,
            "skipped": skipped,
            "totalMined": matched_count,
        }

    # ----- 图库已建关系读取（regenerate=False 快速路径）-----
    def _collect_existing_relations(
        self, graph: TRSGraphClient, scholar_id: str
    ) -> list[dict[str, Any]]:
        """读取学者在图库中已构建的 EMPLOYED_BY 关系。

        关系已持久化在 trs 图库（build 写边、annotate 写角色/领域/时段），故
        regenerate=False 时直接返回，避免重跑 LLM 抽取/消歧/三接口。matchScore/
        evidence/analyze 未落图，故置空。
        """
        try:
            edges = graph.get_node_edges(
                scholar_id, direction="out", edge_type=EDGE_TYPE, limit=100
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("collect existing relations failed: %s", exc)
            return []
        if not edges:
            return []
        relations: list[dict[str, Any]] = []
        for e in edges:
            try:
                org = graph.get_node(e.target_id)
                if org is None:
                    continue
                op = org.properties or {}
                ep = e.properties or {}
            except Exception:  # noqa: BLE001
                continue
            eid = str(op.get("org_id", e.target_id))
            rt_codes = [c for c in str(ep.get("relation_type", "") or "").split("/") if c]
            role = str(ep.get("role", "") or "")
            role_label = ""
            if role:
                try:
                    role_label, _ = role_info(role)
                except Exception:  # noqa: BLE001
                    role_label = ""
            relations.append(
                {
                    "rank": len(relations) + 1,
                    "status": "matched",
                    "enterpriseId": eid,
                    "enterpriseName": op.get("name_cn", "") or "",
                    "matchScore": None,
                    "relationType": rt_codes[0] if rt_codes else "",
                    "relationLabel": relation_label(rt_codes) if rt_codes else "",
                    "role": role,
                    "roleLabel": role_label,
                    "techField": str(ep.get("tech_field", "") or ""),
                    "period": {
                        "start": str(ep.get("start_date", "") or ""),
                        "end": str(ep.get("end_date", "") or ""),
                    },
                    "evidence": "",
                    "build": {
                        "effective": True,
                        "builtRelationId": str(e.id) or f"{scholar_id}->{eid}@0",
                    },
                    "annotate": {"annotated": bool(role)},
                    "analyze": None,
                }
            )
        return relations

    # ----- 图库建点 -----
    @staticmethod
    def _provision_scholar_node(graph: TRSGraphClient, scholar: DwdScholar) -> None:
        try:
            if graph.get_node(scholar.scholar_id) is not None:
                return
            graph.create_node(
                ["Scholar"],
                {
                    "scholar_id": scholar.scholar_id,
                    "name_zh": scholar.name_zh or "",
                    "name_en": scholar.name_en or "",
                    "scholar_org_name_zh": scholar.scholar_org_name_zh or "",
                    "h_index": int(scholar.h_index or 0),
                    "citation_nums": int(scholar.citation_nums or 0),
                    "paper_nums": int(scholar.paper_nums or 0),
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("provision scholar node failed: %s", exc)

    @staticmethod
    def _provision_org_node(
        graph: TRSGraphClient, org_id: str, org_dao: GkxOrganizationDAO
    ) -> None:
        try:
            if graph.get_node(org_id) is not None:
                return
            org = org_dao.get_by_id(org_id)
            if org is not None:
                # 主表企业：含 province/listing_status 等完整字段
                # （reg_info 用 listing_status，stock_base 用 listed_status）
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
                return
            # 仅出现在 detail 表的企业：从候选缓存取名字建最小节点（build/annotate 只需节点存在）
            name = org_dao.get_name_by_id(org_id) if hasattr(org_dao, "get_name_by_id") else None
            if name:
                graph.create_node(["Organization"], {"org_id": org_id, "name_cn": name})
        except Exception as exc:  # noqa: BLE001
            logger.warning("provision org node failed: %s", exc)
