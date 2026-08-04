"""重点关注科技企业关系业务编排服务。

只调用 FastAPI 后端 graph-search 查图 API（HTTP），不直连图。用一次 subgraph(depth=2) 取
专家 2 跳内全部关联，解析出三类专家↔企业关系：

  - governance：Person→Organization 直连边（EXECUTIVE_OF/LEGAL_REP_OF/ACTUAL_CONTROLLER_OF/
    BENEFICIAL_OWNER_OF/SHAREHOLDER_OF/AFFILIATED_WITH），角色来自 position，无合作时间。
  - project_cooperation：Person→Project→Organization（HAS_PARTICIPANT/LEADS + PARTICIPATES_IN/
    FUNDED_BY），合作时间 = Project.research_period / approval_time。
  - patent_cooperation：Person→Patent→Organization（INVENTED_BY + APPLIED_BY），合作时间 =
    Patent.application_date。

企业背景从 Organization 节点属性（listing_status/stock_type/industry/...）取。重点科技企业
筛选：排除高校/研究院/政府/MOCK，保留上市/公司类。支持 enterprise_name/role_type/industry 过滤。
"""

from __future__ import annotations

import logging
import os

import httpx

from biz.schemas.tech_enterprise_relation_business import (
    BusinessPeriod,
    EnterpriseRelationItem,
    KeyEnterpriseRelationRequest,
    KeyEnterpriseRelationResponse,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE = os.getenv("BUSINESS_API_BASE", "http://127.0.0.1:8000")
SPACE = "dev"

# governance 直连边 → 合作模式
GOVERNANCE_MODE = {
    "EXECUTIVE_OF": "高管任职",
    "LEGAL_REP_OF": "法人代表",
    "ACTUAL_CONTROLLER_OF": "实际控制",
    "BENEFICIAL_OWNER_OF": "受益所有",
    "SHAREHOLDER_OF": "股东持股",
    "AFFILIATED_WITH": "任职",
}
PROJECT_PERSON_EDGES = {"HAS_PARTICIPANT", "LEADS"}  # Project↔Person
PROJECT_ORG_EDGES = {"PARTICIPATES_IN", "FUNDED_BY"}  # Project↔Organization
PATENT_PERSON_EDGES = {"INVENTED_BY"}  # Patent→Person
PATENT_ORG_EDGES = {"APPLIED_BY"}  # Patent→Organization

_NON_ENTERPRISE_KEYWORDS = (
    "大学",
    "学院",
    "研究院",
    "研究所",
    "医院",
    "政府",
    "管理局",
    "委员会",
    "MOCK",
    "测试",
)

_ROLE_LEVEL_RULES = [
    (
        (
            "董事长",
            "副董事长",
            "chairman",
            "ceo",
            "总裁",
            "总经理",
            "法人",
            "控制人",
            "受益",
            "股东",
        ),
        "L1",
    ),
    (
        (
            "cto",
            "首席",
            "总工程师",
            "chief",
            "技术总监",
            "研发总监",
            "技术负责人",
            "总监",
            "副总经理",
            "副总",
        ),
        "L2",
    ),
    (("工程师", "技术员", "主管", "骨干", "engineer", "经理"), "L3"),
]


def _role_level(position: str | None) -> str | None:
    if not position:
        return None
    p = position.lower()
    for keys, level in _ROLE_LEVEL_RULES:
        if any(k.lower() in p for k in keys):
            return level
    return None


def _is_key_tech_enterprise(name: str | None, bg: dict) -> bool:
    if not name:
        return False
    if any(k in name for k in _NON_ENTERPRISE_KEYWORDS):
        return False
    if bg.get("listing_status") and bg.get("listing_status") not in ("", "未上市"):
        return True
    if bg.get("stock_code"):
        return True
    if any(k in name for k in ("公司", "集团", "企业", "厂")):
        return True
    return False


def _enterprise_background(props: dict) -> dict:
    bg: dict[str, object] = {}
    for k in (
        "name_cn",
        "external_id",
        "org_type",
        "industry",
        "industry_l1_name",
        "industry_l2_name",
        "listing_status",
        "registered_capital_value",
        "capital_currency",
        "incorporation_year",
        "province",
        "city",
        "stock_code",
        "stock_type",
        "listed_date",
        "stock_noun",
    ):
        if props.get(k) not in (None, "", []):
            bg[k] = props.get(k)
    return bg


def _parse_period(*vals: object) -> BusinessPeriod:
    """从 research_period('2023-07-01 至 2027-06-30') / approval_time / application_date 解析起止。"""
    for v in vals:
        if not v:
            continue
        s = str(v)
        if "至" in s:
            parts = [p.strip() for p in s.split("至", 1)]
            return BusinessPeriod(start=parts[0], end=parts[1] if len(parts) > 1 else None)
        if s.strip():
            return BusinessPeriod(start=s.strip())
    return BusinessPeriod()


class KeyEnterpriseRelationService:
    def __init__(self, base_url: str | None = None, timeout: float = 60.0) -> None:
        self.base = (base_url or DEFAULT_BASE).rstrip("/") + "/api/v1"
        self.timeout = timeout

    async def _get(self, client: httpx.AsyncClient, path: str, params: dict) -> dict:
        r = await client.get(f"{self.base}{path}", params=params, timeout=self.timeout)
        return r.json()

    async def run(self, req: KeyEnterpriseRelationRequest) -> KeyEnterpriseRelationResponse:
        resp = KeyEnterpriseRelationResponse(expert_id=req.expert_id)
        async with httpx.AsyncClient() as client:
            # 1) 一次 subgraph(depth=2) 拿专家 2 跳内全部点边
            try:
                sg_json = await self._get(
                    client,
                    f"/graph-search/subgraph/{req.expert_id}",
                    {"space": SPACE, "depth": 2, "limit": 200},
                )
            except Exception as exc:  # noqa: BLE001
                resp.evidence.append(f"subgraph 查询失败: {exc}")
                return resp
            data = sg_json.get("data") or {}
            nodes = data.get("nodes", []) or []
            edges = data.get("edges", []) or []

        # 节点属性表 + 标签
        node_props: dict[str, dict] = {
            n.get("id"): (n.get("properties") or {}) for n in nodes if n.get("id")
        }
        node_labels: dict[str, set[str]] = {
            n.get("id"): set(n.get("labels") or []) for n in nodes if n.get("id")
        }
        expert_props = node_props.get(req.expert_id, {})
        resp.expert_name = (
            expert_props.get("name_cn")
            or expert_props.get("name_zh")
            or expert_props.get("name_en")
        )

        # 邻接表：vid -> [(edge_type, other_vid, edge_props)]
        adj: dict[str, list[tuple[str, str, dict]]] = {}
        for e in edges:
            et = e.get("type", "")
            s, t, props = e.get("source", ""), e.get("target", ""), (e.get("properties") or {})
            if not s or not t:
                continue
            adj.setdefault(s, []).append((et, t, props))
            adj.setdefault(t, []).append((et, s, props))

        relations: list[EnterpriseRelationItem] = []

        def _add(
            org_id: str,
            ctype: str,
            mode: str,
            role: str | None,
            period: BusinessPeriod,
            source: str,
        ):
            if not org_id or org_id == req.expert_id:
                return
            if "Organization" not in node_labels.get(org_id, set()):
                return
            op = node_props.get(org_id, {})
            relations.append(
                EnterpriseRelationItem(
                    enterprise_id=org_id,
                    enterprise_name=op.get("name_cn") or op.get("name_en"),
                    cooperation_type=ctype,
                    cooperation_mode=mode,
                    role_label=role or mode,
                    role_level=_role_level(role)
                    or (
                        "L1"
                        if ctype == "governance"
                        and mode in {"法人代表", "实际控制", "受益所有", "股东持股"}
                        else None
                    ),
                    tech_field=op.get("industry_l1_name") or op.get("industry"),
                    period=period,
                    enterprise_background=_enterprise_background(op),
                    source=source,
                )
            )

        # 2) governance 直连边（expert→Organization）
        for et, other, props in adj.get(req.expert_id, []):
            if et in GOVERNANCE_MODE and "Organization" in node_labels.get(other, set()):
                role = props.get("position") or ""
                period = BusinessPeriod()
                if et == "AFFILIATED_WITH":
                    period = _parse_period(expert_props.get("work_experience_date"))
                _add(other, "governance", GOVERNANCE_MODE[et], role, period, et)

        # 3) 项目合作 expert→Project→Organization
        for et, proj_id, _props in adj.get(req.expert_id, []):
            if et not in PROJECT_PERSON_EDGES or "Project" not in node_labels.get(proj_id, set()):
                continue
            pj = node_props.get(proj_id, {})
            period = _parse_period(pj.get("research_period"), pj.get("approval_time"))
            for et2, org_id, _p2 in adj.get(proj_id, []):
                if et2 in PROJECT_ORG_EDGES and "Organization" in node_labels.get(org_id, set()):
                    _add(
                        org_id,
                        "project_cooperation",
                        "项目合作",
                        "项目参与人",
                        period,
                        f"project:{proj_id}",
                    )

        # 4) 专利合作 expert→Patent→Organization
        for et, pat_id, _props in adj.get(req.expert_id, []):
            if et not in PATENT_PERSON_EDGES or "Patent" not in node_labels.get(pat_id, set()):
                continue
            pp = node_props.get(pat_id, {})
            period = _parse_period(pp.get("application_date"))
            for et2, org_id, _p2 in adj.get(pat_id, []):
                if et2 in PATENT_ORG_EDGES and "Organization" in node_labels.get(org_id, set()):
                    _add(
                        org_id,
                        "patent_cooperation",
                        "专利合作",
                        "发明人",
                        period,
                        f"patent:{pat_id}",
                    )

        # 5) 过滤：重点科技企业 + enterprise_name/role_type/industry
        def _keep(rel: EnterpriseRelationItem) -> bool:
            if req.key_tech_enterprise_only and not _is_key_tech_enterprise(
                rel.enterprise_name, rel.enterprise_background
            ):
                return False
            if req.enterprise_name and req.enterprise_name not in (rel.enterprise_name or ""):
                return False
            if req.industry and req.industry not in (rel.tech_field or ""):
                return False
            if req.role_type and req.role_type not in (rel.role_label or ""):
                return False
            return True

        relations = [r for r in relations if _keep(r)]
        resp.relations = relations
        resp.enterprises = len({r.enterprise_id for r in relations})
        resp.roles = len({r.role_label for r in relations if r.role_label})
        resp.cooperation_fields = sorted({r.tech_field for r in relations if r.tech_field})
        resp.evidence = [
            f"从 dev 空间专家 {req.expert_id} 2 跳子图解析出 {len(relations)} 条专家-企业关系",
            "合作时间来源：项目 research_period / 专利 application_date / 学者 work_experience_date",
            "角色定位来源：EXECUTIVE_OF.position 等边属性 + 边类型映射",
        ]
        return resp
