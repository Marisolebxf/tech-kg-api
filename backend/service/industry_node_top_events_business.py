"""科技产业链点 TOP-N 事件关系业务编排服务。

流程：
  1. MySQL（dwd_industry_chain_info / dwd_org_industry_chain_dtl）：按 chain_node_id 取链节点
     信息 + 关联企业（按 chain_score 排序，limit max_orgs）。
  2. graph-search 查图 API：对每个企业 GET /graph-search/subgraph/{org_id}?depth=1，取其
     INVOLVED_IN 事件 + governance 边（EXECUTIVE_OF 等）关联的专家。
  3. 事件影响力排序：event_type 风险权重 × 金额 × 时间新鲜度 × 企业 chain_score，取 TOP-N。
  4. 构建 event→org→expert 关联，按事件类型给出风险等级。

图访问只走 FastAPI graph-search API（HTTP），不直连图；链节点/企业映射走 MySQL ORM。
"""

from __future__ import annotations

import logging
import math
import os

import httpx
from sqlalchemy import select

from biz.schemas.industry_node_top_events_business import (
    EventExpertRelation,
    IndustryNodeTopEventsRequest,
    IndustryNodeTopEventsResponse,
    TopEventItem,
)
from db_model.industry_chain import DwdIndustryChainInfo, DwdOrgIndustryChainDtl
from infra.mysql import MySQLClient

logger = logging.getLogger(__name__)

DEFAULT_BASE = os.getenv("BUSINESS_API_BASE", "http://127.0.0.1:8000")
SPACE = "dev"

GOVERNANCE_EDGES = {
    "EXECUTIVE_OF",
    "LEGAL_REP_OF",
    "ACTUAL_CONTROLLER_OF",
    "BENEFICIAL_OWNER_OF",
    "SHAREHOLDER_OF",
    "AFFILIATED_WITH",
}

# event_type → 影响力权重（风险类高，财务类中，其它低）
EVENT_WEIGHT = {
    "bankruptcy": 3.0,
    "zhixing": 3.0,
    "shixin": 3.0,
    "tax_punish": 3.0,
    "judicial_case": 3.0,
    "illegal": 3.0,
    "abnormal": 2.5,
    "pledge": 2.5,
    "chattel": 2.5,
    "equity_freeze": 3.0,
    "judicial_sale": 3.0,
    "court_filed_case": 2.5,
    "court_notice": 2.5,
    "court_announcement": 2.5,
    "financing": 2.0,
    "stock_finance": 2.0,
    "annual_finance": 2.0,
    "bid": 1.5,
    "change_record": 1.5,
    "recruit": 1.0,
    "news": 1.0,
}
RISK_EVENT_TYPES = {
    "bankruptcy",
    "zhixing",
    "shixin",
    "tax_punish",
    "judicial_case",
    "illegal",
    "equity_freeze",
    "judicial_sale",
    "abnormal",
    "pledge",
    "chattel",
}


def _impact_score(
    event_type: str | None, amount: str | None, occur_date: str | None, chain_score: float
) -> float:
    weight = EVENT_WEIGHT.get(event_type or "", 1.0)
    amt = 0.0
    try:
        amt = float(amount) if amount else 0.0
    except (TypeError, ValueError):
        amt = 0.0
    amount_factor = math.log10(amt + 1) / 10.0 if amt > 0 else 0.0
    # 时间新鲜度：按年衰减，2025+=1.0
    recency = 0.5
    if occur_date:
        s = str(occur_date)[:4]
        try:
            yr = int(s)
            recency = max(0.3, 1.0 - (2026 - yr) * 0.15)
        except ValueError:
            recency = 0.5
    return weight * (1 + amount_factor) * recency * (1 + chain_score / 100.0)


class IndustryNodeTopEventsService:
    def __init__(self, base_url: str | None = None, timeout: float = 60.0) -> None:
        self.base = (base_url or DEFAULT_BASE).rstrip("/") + "/api/v1"
        self.timeout = timeout
        self._mysql = MySQLClient()

    async def _get(self, client: httpx.AsyncClient, path: str, params: dict) -> dict:
        r = await client.get(f"{self.base}{path}", params=params, timeout=self.timeout)
        return r.json()

    def _load_chain_node(self, chain_node_id: str, max_orgs: int):
        """返回 (node_info, [(org_id, chain_score)])。"""
        with self._mysql.session_scope() as session:
            # 只取需要的列，避开 ORM 模型里 downstream_lin 与实际表 downstream_link_code 不一致的 bug
            node = session.execute(
                select(
                    DwdIndustryChainInfo.node_name,
                    DwdIndustryChainInfo.chain_name,
                    DwdIndustryChainInfo.node_imp_level,
                ).where(DwdIndustryChainInfo.node_id == chain_node_id)
            ).first()
            node_info = {}
            if node:
                node_info = {
                    "node_name": node[0],
                    "chain_name": node[1],
                    "node_imp_level": str(node[2]) if node[2] is not None else None,
                }
            rows = session.execute(
                select(DwdOrgIndustryChainDtl.antitypic, DwdOrgIndustryChainDtl.chain_score)
                .where(DwdOrgIndustryChainDtl.node_id == chain_node_id)
                .order_by(DwdOrgIndustryChainDtl.chain_score.desc())
                .limit(max_orgs)
            ).all()
            orgs = [(r[0], float(r[1] or 0)) for r in rows if r[0]]
        return node_info, orgs

    async def run(self, req: IndustryNodeTopEventsRequest) -> IndustryNodeTopEventsResponse:
        resp = IndustryNodeTopEventsResponse(chain_node_id=req.chain_node_id)
        node_info, orgs = self._load_chain_node(req.chain_node_id, req.max_orgs)
        resp.chain_node_name = node_info.get("node_name")
        resp.chain_name = node_info.get("chain_name")
        resp.node_imp_level = node_info.get("node_imp_level")
        resp.enterprises = len(orgs)
        if not orgs:
            resp.evidence.append(f"链节点 {req.chain_node_id} 下无关联企业")
            return resp

        # 每个企业一次 subgraph(depth=1)，取事件 + 专家
        events: list[
            dict
        ] = []  # {event_id, event_type, occur_date, amount, title, org_id, org_name, chain_score}
        experts_by_org: dict[
            str, list[tuple[str, str | None, str | None]]
        ] = {}  # org_id -> [(person_id, name, role)]
        async with httpx.AsyncClient() as client:
            for antitypic, chain_score in orgs:
                org_id = f"org_{antitypic}"
                try:
                    sg = await self._get(
                        client,
                        f"/graph-search/subgraph/{org_id}",
                        {"space": SPACE, "depth": 1, "limit": 50},
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("subgraph %s 失败: %s", org_id, exc)
                    continue
                data = sg.get("data") or {}
                nodes = {
                    n.get("id"): (n.get("properties") or {}) for n in (data.get("nodes") or [])
                }
                org_name = nodes.get(org_id, {}).get("name_cn")
                for e in data.get("edges") or []:
                    et = e.get("type", "")
                    s, t = e.get("source", ""), e.get("target", "")
                    if et == "INVOLVED_IN":
                        eid = t if s == org_id else s
                        ep = nodes.get(eid, {})
                        events.append(
                            {
                                "event_id": eid,
                                "event_type": ep.get("event_type"),
                                "occur_date": str(ep.get("occur_date") or "") or None,
                                "amount": str(ep.get("amount") or "") or None,
                                "title": ep.get("title"),
                                "org_id": org_id,
                                "org_name": org_name,
                                "chain_score": chain_score,
                            }
                        )
                    elif et in GOVERNANCE_EDGES:
                        pid = s if t == org_id else t
                        if pid and pid != org_id:
                            pp = nodes.get(pid, {})
                            experts_by_org.setdefault(org_id, []).append(
                                (
                                    pid,
                                    pp.get("name_cn") or pp.get("name_zh"),
                                    e.get("properties", {}).get("position"),
                                )
                            )

        # 事件类型 / 时间筛选
        def _keep(ev: dict) -> bool:
            if req.event_type and ev.get("event_type") != req.event_type:
                return False
            if req.time_range and ev.get("occur_date"):
                yr = str(ev["occur_date"])[:4]
                try:
                    lo, _, hi = req.time_range.partition("-")
                    if lo and int(yr) < int(lo[:4]):
                        return False
                    if hi and int(yr) > int(hi[:4]):
                        return False
                except ValueError:
                    pass
            return True

        events = [ev for ev in events if _keep(ev)]
        # 去重（同一事件可能被多个企业触发？按 event_id 去重保留 chain_score 高的）
        seen: dict[str, dict] = {}
        for ev in events:
            if (
                ev["event_id"] not in seen
                or ev["chain_score"] > seen[ev["event_id"]]["chain_score"]
            ):
                seen[ev["event_id"]] = ev
        events = list(seen.values())

        # 影响力排序 → TOP-N
        for ev in events:
            ev["_score"] = _impact_score(
                ev.get("event_type"),
                ev.get("amount"),
                ev.get("occur_date"),
                ev.get("chain_score", 0),
            )
        events.sort(key=lambda x: x["_score"], reverse=True)
        top = events[: req.top_n]

        resp.events = len(top)
        resp.top_events = [
            TopEventItem(
                event_id=ev["event_id"],
                event_type=ev.get("event_type"),
                occur_date=ev.get("occur_date"),
                amount=ev.get("amount"),
                title=ev.get("title"),
                impact_score=round(ev["_score"], 3),
                rank=i + 1,
                org_id=ev.get("org_id"),
                org_name=ev.get("org_name"),
            )
            for i, ev in enumerate(top)
        ]

        # 风险等级：TOP 事件含风险类→高，含财务类→中，否则低
        top_types = {ev.get("event_type") for ev in top}
        if top_types & RISK_EVENT_TYPES:
            resp.risk_level = "高"
        elif top_types & {"financing", "stock_finance", "annual_finance"}:
            resp.risk_level = "中"
        else:
            resp.risk_level = "低"

        # 事件→专家关联：TOP 事件所在企业单独查 governance 边取专家
        # （subgraph(depth=1) 可能被事件占满，专家没进，故单独查）
        top_org_ids = {ev.get("org_id") for ev in top if ev.get("org_id")}
        experts_by_org.clear()
        async with httpx.AsyncClient() as client:
            for org_id in top_org_ids:
                seen_pids: set[str] = set()
                for et in ("EXECUTIVE_OF", "LEGAL_REP_OF", "ACTUAL_CONTROLLER_OF"):
                    try:
                        ej = await self._get(
                            client,
                            f"/graph-search/node/{org_id}/edges",
                            {"space": SPACE, "edge_type": et, "direction": "in", "limit": 20},
                        )
                    except Exception:  # noqa: BLE001
                        continue
                    for e in (ej.get("data") or {}).get("edges", []):
                        pid = e.get("source") or e.get("target")
                        if pid and pid != org_id and pid not in seen_pids:
                            seen_pids.add(pid)
                            experts_by_org.setdefault(org_id, []).append(
                                (pid, None, (e.get("properties") or {}).get("position"))
                            )

        all_expert_ids: set[str] = set()
        for ev in top:
            for pid, pname, role in experts_by_org.get(ev.get("org_id", ""), []):
                all_expert_ids.add(pid)
                resp.relations.append(
                    EventExpertRelation(
                        event_id=ev["event_id"],
                        event_title=ev.get("title"),
                        expert_id=pid,
                        expert_name=pname,
                        role=role,
                        org_id=ev.get("org_id", ""),
                        org_name=ev.get("org_name"),
                    )
                )
        resp.experts = len(all_expert_ids)
        resp.evidence = [
            f"链节点 {req.chain_node_id}({resp.chain_node_name or ''}) 下 {len(orgs)} 家企业",
            f"汇总 {len(events)} 条事件，影响力排序取 TOP {len(top)}",
            f"风险等级 {resp.risk_level}（基于事件类型 {sorted(top_types)}）",
        ]
        return resp
