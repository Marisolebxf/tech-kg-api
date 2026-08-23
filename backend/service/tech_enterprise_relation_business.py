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

import json
import logging
import os
import threading
import time
from typing import Any

import httpx

from biz.schemas.tech_enterprise_relation_business import (
    BusinessPeriod,
    EnterpriseRelationItem,
    KeyEnterpriseRelationRequest,
    KeyEnterpriseRelationResponse,
)
from service.industry_node_top_events_business import RISK_EVENT_TYPES

logger = logging.getLogger(__name__)

DEFAULT_BASE = os.getenv("BUSINESS_API_BASE", "http://127.0.0.1:8000")
SPACE = os.getenv("TRS_GRAPH_SPACE", "dev")

# 60s 进程内结果缓存：同参数请求复用，避免高并发打爆 graph-search/trs-graph。
_RESULT_CACHE_TTL = float(os.getenv("RESULT_CACHE_TTL", "60"))
_result_cache: dict[str, tuple[float, KeyEnterpriseRelationResponse]] = {}
_result_cache_lock = threading.Lock()


def clear_caches() -> None:
    """清空进程内缓存（测试隔离用）。"""
    _result_cache.clear()


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

# 关系置信度（标书「企业关联置信度」）：governance 直连最高，项目/专利 2-hop 略低
COOPERATION_CONFIDENCE = {
    "governance": 0.9,
    "project_cooperation": 0.8,
    "patent_cooperation": 0.8,
}

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


def _flatten_org_props(props: dict) -> dict:
    """合并顶层属性 + extra_json 里的多表数据。

    周威的 org ETL（merge_existing_properties）把多源表数据塞进 ``extra_json`` 而非
    顶层 tag 字段——顶层只留最后写的表（多为 stock_base），base_info 的注册资本/成立年/
    行业、product 表的主营/经营范围都埋在 extra_json 里。这里摊平供 _enterprise_background 取用。

    extra_json 标准结构::
        {"existing_payload": {...base_info 字段...},
         "source_records": {"{table}:{id}": {...该表行...}, ...}}
    非标准 extra_json（如回填链上企业的 {antitypic,credit_code,...}）原样合并，无副作用。
    """
    flat: dict[str, object] = dict(props)
    raw = props.get("extra_json")
    if not raw:
        return flat
    try:
        ej = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return flat
    if not isinstance(ej, dict):
        return flat
    for bucket in (ej.get("existing_payload"),):
        if isinstance(bucket, dict):
            for k, v in bucket.items():
                if v not in (None, "", []) and flat.get(k) in (None, "", []):
                    flat[k] = v
    sr = ej.get("source_records")
    if isinstance(sr, dict):
        for row in sr.values():
            if not isinstance(row, dict):
                continue
            for k, v in row.items():
                if v not in (None, "", []) and flat.get(k) in (None, "", []):
                    flat[k] = v
    return flat


# 业务背景字段的候选源列名（顶层 tag 名 / MySQL 列名 / extra_json 内字段名）
_BG_ALIASES = {
    "industry_l1_name": ("industry_l1_name", "industry", "industry_class"),
    "industry_l2_name": ("industry_l2_name",),
    "registered_capital_value": ("registered_capital_value", "registered_capital", "capital_num"),
    "incorporation_year": ("incorporation_year", "founded_year", "est_year"),
    "main_products": ("main_products", "main_prod"),
    "legal_rep": ("legal_rep", "lerep", "legal_person"),
    "description": ("description", "main_activities", "business_scope"),
}
_BG_PASSTHROUGH = (
    "name_cn",
    "external_id",
    "org_type",
    "listing_status",
    "capital_currency",
    "province",
    "city",
    "stock_code",
    "stock_type",
    "listed_date",
    "stock_noun",
)


def _enterprise_background(props: dict) -> dict:
    """企业背景：顶层 Organization 属性 + extra_json 多表数据摊平后取值。

    标书「行业地位/技术方向/经营状况」所需的行业、注册资本、成立年、主营等字段，
    周威 ETL 写在 extra_json 里，这里经 _flatten_org_props 摊平后再按候选列名提取。
    """
    fp = _flatten_org_props(props)
    bg: dict[str, object] = {}
    for canon, candidates in _BG_ALIASES.items():
        for c in candidates:
            v = fp.get(c)
            if v not in (None, "", []):
                bg[canon] = v
                break
    for k in _BG_PASSTHROUGH:
        v = fp.get(k)
        if v not in (None, "", []):
            bg[k] = v
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

    async def run(
        self, req: KeyEnterpriseRelationRequest, *, app: Any = None
    ) -> KeyEnterpriseRelationResponse:
        cache_key = (
            f"{req.expert_id}|{req.enterprise_name}|{req.role_type}|"
            f"{req.industry}|{req.key_tech_enterprise_only}"
        )
        with _result_cache_lock:
            entry = _result_cache.get(cache_key)
        if entry and entry[0] > time.monotonic():
            return entry[1]

        resp = KeyEnterpriseRelationResponse(expert_id=req.expert_id)
        # ASGI 进程内 transport：替代真实 HTTP 回环 8200，消除 socket/accept 队列开销
        # 与高并发自调用饱和。app 由 handler 传 request.app，避免在 service 里 import main。
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as client:
            # 1) filtered-subgraph(depth=2) 只拿业务需要的 12 种边，不捞论文/合作者/引用
            edge_types = ",".join(
                [
                    "EXECUTIVE_OF",
                    "LEGAL_REP_OF",
                    "ACTUAL_CONTROLLER_OF",
                    "BENEFICIAL_OWNER_OF",
                    "SHAREHOLDER_OF",
                    "AFFILIATED_WITH",
                    "HAS_PARTICIPANT",
                    "LEADS",
                    "PARTICIPATES_IN",
                    "FUNDED_BY",
                    "INVENTED_BY",
                    "APPLIED_BY",
                ]
            )
            try:
                sg_json = await self._get(
                    client,
                    f"/graph-search/filtered-subgraph/{req.expert_id}",
                    {"space": SPACE, "edge_types": edge_types, "depth": 2, "limit": 50},
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
        # 子图不含 seed → 专家节点不存在（filtered-subgraph 对存在节点即使无边也返回 seed）
        if req.expert_id not in node_props:
            raise KeyError(f"专家不存在: {req.expert_id}")
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
            bg = _enterprise_background(op)
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
                    tech_field=bg.get("industry_l1_name") or op.get("industry"),
                    period=period,
                    enterprise_background=bg,
                    source=source,
                    confidence=COOPERATION_CONFIDENCE.get(ctype, 0.7),
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
        # 首要企业 best-effort 风险事件探测（标书「经营状况」之风险提示维度）
        # 只查 relations[0]，避免 N×调用；失败降级为空串，不阻断主流程。
        if relations:
            await self._probe_primary_risk(relations[0], app=app)
        resp.relations = relations
        resp.enterprises = len({r.enterprise_id for r in relations})
        resp.roles = len({r.role_label for r in relations if r.role_label})
        resp.cooperation_fields = sorted({r.tech_field for r in relations if r.tech_field})
        resp.confidence = max((r.confidence for r in relations), default=0.0)
        resp.evidence = [
            f"从 dev 空间专家 {req.expert_id} 2 跳子图解析出 {len(relations)} 条专家-企业关系",
            "合作时间来源：项目 research_period / 专利 application_date / 学者 work_experience_date",
            "角色定位来源：EXECUTIVE_OF.position 等边属性 + 边类型映射",
        ]
        with _result_cache_lock:
            _result_cache[cache_key] = (time.monotonic() + _RESULT_CACHE_TTL, resp)
        return resp

    async def _probe_primary_risk(
        self, primary: EnterpriseRelationItem, *, app: Any = None
    ) -> None:
        """对首要关联企业查 INVOLVED_IN 风险事件，回填 risk_summary（best-effort）。"""
        org_id = primary.enterprise_id
        if not org_id:
            return
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as client:
            try:
                rj = await self._get(
                    client,
                    f"/graph-search/filtered-subgraph/{org_id}",
                    {
                        "space": SPACE,
                        "edge_types": "INVOLVED_IN",
                        "depth": 1,
                        "limit": 20,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("首要企业风险探测失败 %s: %s", org_id, exc)
                primary.risk_summary = ""
                return
        risk_types, risk_count = self._count_risk_events(rj, org_id)
        if risk_count:
            primary.risk_summary = f"近 {risk_count} 条风险事件（{'、'.join(sorted(risk_types))}）"
        else:
            primary.risk_summary = "暂无风险事件记录"

    @staticmethod
    def _count_risk_events(subgraph_json: dict, org_id: str) -> tuple[set[str], int]:
        """从 org 的 INVOLVED_IN 子图统计风险类事件类型集合与计数。"""
        data = subgraph_json.get("data") or {}
        nodes = {n.get("id"): (n.get("properties") or {}) for n in (data.get("nodes") or [])}
        risk_types: set[str] = set()
        risk_count = 0
        for e in data.get("edges") or []:
            if e.get("type") != "INVOLVED_IN":
                continue
            s, t = e.get("source"), e.get("target")
            other = t if s == org_id else s
            if not other or other == org_id:
                continue
            et = nodes.get(other, {}).get("event_type") or ""
            if et in RISK_EVENT_TYPES:
                risk_types.add(et)
                risk_count += 1
        return risk_types, risk_count
