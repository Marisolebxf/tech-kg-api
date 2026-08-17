"""科技产业链点 TOP-N 事件关系业务编排服务。

严格按 0803 任务要求：只调用 FastAPI graph-search 查图 API（HTTP），不直连图、不直连 MySQL。
产业链节点（IndustryNode）、企业-节点关联（BELONGS_TO_NODE）、事件（INVOLVED_IN）、
专家（EXECUTIVE_OF 等）全部从 dev 图空间经 graph-search API 查。

流程：
  1. GET /graph-search/subgraph/{node_vid}?depth=1  取链节点信息 + 关联企业（BELONGS_TO_NODE）+ 产业链（HAS_NODE）
  2. GET /graph-search/filtered-subgraph/{org_id}?edge_types=INVOLVED_IN,HAS_NEWS  每个企业的事件 + 资讯
     News 节点统一记为 event_type=news 参与排序（补"发展趋势"维度）
  3. 事件影响力排序（event_type 权重 × 金额 × 时间新鲜度 × chain_score）→ TOP-N
  4. GET /graph-search/node/{org_id}/edges?edge_type=EXECUTIVE_OF  TOP 事件企业的专家
  5. 风险等级 + event→org→expert 关联
"""

from __future__ import annotations

import logging
import math
import os

import httpx

from biz.schemas.industry_node_top_events_business import (
    EventExpertRelation,
    IndustryNodeTopEventsRequest,
    IndustryNodeTopEventsResponse,
    TopEventItem,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE = os.getenv("BUSINESS_API_BASE", "http://127.0.0.1:8000")
SPACE = "dev"

GOVERNANCE_EDGES = {"EXECUTIVE_OF", "LEGAL_REP_OF", "ACTUAL_CONTROLLER_OF"}

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
# 机遇类事件：融资/财务/中标/资讯，对应标书「机遇挖掘」维度
OPP_EVENT_TYPES = {"financing", "stock_finance", "annual_finance", "bid", "news"}
FINANCE_EVENT_TYPES = {"financing", "stock_finance", "annual_finance"}
# 趋势研判基准年（脚本环境禁用 Date.now，固定 2026 与 impact_score 一致）
TREND_BASE_YEAR = 2026

# 事件置信度（标书「实体共现和语义关联置信度」）：风险类最高，资讯类低
EVENT_CONFIDENCE = {
    **{et: 0.9 for et in RISK_EVENT_TYPES},
    **{et: 0.85 for et in ("financing", "stock_finance", "annual_finance")},
    "bid": 0.8,
    "news": 0.7,
    "change_record": 0.7,
    "recruit": 0.6,
}
# 综合置信度按风险等级赋值
RISK_LEVEL_CONFIDENCE = {"高": 0.9, "中": 0.75, "低": 0.6}


def _impact_score(event_type, amount, occur_date, chain_score):
    weight = EVENT_WEIGHT.get(event_type or "", 1.0)
    try:
        amt = float(amount) if amount else 0.0
    except (TypeError, ValueError):
        amt = 0.0
    amount_factor = math.log10(amt + 1) / 10.0 if amt > 0 else 0.0
    recency = 0.5
    if occur_date:
        try:
            yr = int(str(occur_date)[:4])
            recency = max(0.3, 1.0 - (2026 - yr) * 0.15)
        except ValueError:
            recency = 0.5
    return weight * (1 + amount_factor) * recency * (1 + chain_score / 100.0)


class IndustryNodeTopEventsService:
    def __init__(self, base_url=None, timeout=60.0):
        self.base = (base_url or DEFAULT_BASE).rstrip("/") + "/api/v1"
        self.timeout = timeout

    async def _get(self, client, path, params):
        r = await client.get(f"{self.base}{path}", params=params, timeout=self.timeout)
        return r.json()

    async def run(self, req: IndustryNodeTopEventsRequest) -> IndustryNodeTopEventsResponse:
        resp = IndustryNodeTopEventsResponse(chain_node_id=req.chain_node_id)
        node_vid = (
            req.chain_node_id
            if req.chain_node_id.startswith("node_")
            else f"node_{req.chain_node_id}"
        )

        async with httpx.AsyncClient() as client:
            # 1) filtered-subgraph(depth=1) 只拿 BELONGS_TO_NODE + HAS_NODE，不捞事件/新闻
            try:
                sg = await self._get(
                    client,
                    f"/graph-search/filtered-subgraph/{node_vid}",
                    {
                        "space": SPACE,
                        "edge_types": "BELONGS_TO_NODE,HAS_NODE",
                        "depth": 1,
                        "limit": 200,
                    },
                )
            except Exception as exc:
                resp.evidence.append(f"链节点查询失败: {exc}")
                return resp
            data = sg.get("data") or {}
            nodes_map = {
                n.get("id"): (n.get("properties") or {}) for n in (data.get("nodes") or [])
            }
            node_props = nodes_map.get(node_vid, {})
            resp.chain_node_name = node_props.get("node_name")
            resp.node_imp_level = node_props.get("node_imp_level")

            orgs = []  # [(org_vid, chain_score)]
            for e in data.get("edges") or []:
                et = e.get("type", "")
                s, t = e.get("source", ""), e.get("target", "")
                if et == "BELONGS_TO_NODE" and t == node_vid:
                    cs = (e.get("properties") or {}).get("chain_score", 0)
                    try:
                        cs = float(cs)
                    except (TypeError, ValueError):
                        cs = 0.0
                    orgs.append((s, cs))
                elif et == "HAS_NODE" and s != node_vid:
                    # chain → node，s 是 chain vid
                    resp.chain_name = nodes_map.get(s, {}).get("chain_name") or resp.chain_name
                elif et == "HAS_NODE" and t != node_vid:
                    resp.chain_name = nodes_map.get(t, {}).get("chain_name") or resp.chain_name

            resp.enterprises = len(orgs)
            # 按 chain_score 排序，只取 top max_orgs 家企业查事件（避免过多调用）
            orgs.sort(key=lambda x: x[1], reverse=True)
            orgs = orgs[: req.max_orgs]
            if not orgs:
                resp.evidence.append(f"链节点 {req.chain_node_id} 无关联企业")
                return resp

            # 2) filtered-subgraph(depth=1) 每个企业拿 INVOLVED_IN 事件 + HAS_NEWS 资讯
            #    News 节点统一记为 event_type=news，参与影响力排序（资讯权重低，补"发展趋势"维度）
            events = []
            for org_vid, chain_score in orgs:
                try:
                    osg = await self._get(
                        client,
                        f"/graph-search/filtered-subgraph/{org_vid}",
                        {
                            "space": SPACE,
                            "edge_types": "INVOLVED_IN,HAS_NEWS",
                            "depth": 1,
                            "limit": 50,
                        },
                    )
                except Exception as exc:
                    logger.warning("subgraph %s 失败: %s", org_vid, exc)
                    continue
                odata = osg.get("data") or {}
                onodes = {
                    n.get("id"): (n.get("properties") or {}) for n in (odata.get("nodes") or [])
                }
                org_name = onodes.get(org_vid, {}).get("name_cn")
                for e in odata.get("edges") or []:
                    etype = e.get("type")
                    if etype not in ("INVOLVED_IN", "HAS_NEWS"):
                        continue
                    eid = e.get("target") if e.get("source") == org_vid else e.get("source")
                    ep = onodes.get(eid, {})
                    if etype == "HAS_NEWS":
                        # News 节点：title/release_date，无 event_type/amount
                        ev_type = "news"
                        occur = str(ep.get("release_date") or "") or None
                        amount = None
                    else:
                        ev_type = ep.get("event_type")
                        occur = str(ep.get("occur_date") or "") or None
                        amount = str(ep.get("amount") or "") or None
                    events.append(
                        {
                            "event_id": eid,
                            "event_type": ev_type,
                            "occur_date": occur,
                            "amount": amount,
                            "title": ep.get("title"),
                            "org_id": org_vid,
                            "org_name": org_name,
                            "chain_score": chain_score,
                        }
                    )

        # 筛选
        def _keep(ev):
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
        # 去重
        seen = {}
        for ev in events:
            if (
                ev["event_id"] not in seen
                or ev["chain_score"] > seen[ev["event_id"]]["chain_score"]
            ):
                seen[ev["event_id"]] = ev
        events = list(seen.values())

        # 排序 → TOP-N
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
                confidence=EVENT_CONFIDENCE.get(ev.get("event_type") or "", 0.7),
            )
            for i, ev in enumerate(top)
        ]

        top_types = {ev.get("event_type") for ev in top}
        if top_types & RISK_EVENT_TYPES:
            resp.risk_level = "高"
        elif top_types & {"financing", "stock_finance", "annual_finance"}:
            resp.risk_level = "中"
        else:
            resp.risk_level = "低"
        resp.confidence = RISK_LEVEL_CONFIDENCE.get(resp.risk_level, 0.6)

        # 3) TOP 事件企业查专家（governance 边）
        top_org_ids = {ev.get("org_id") for ev in top if ev.get("org_id")}
        experts_by_org = {}
        async with httpx.AsyncClient() as client:
            for org_id in top_org_ids:
                seen_pids = set()
                for et in GOVERNANCE_EDGES:
                    try:
                        ej = await self._get(
                            client,
                            f"/graph-search/node/{org_id}/edges",
                            {"space": SPACE, "edge_type": et, "direction": "in", "limit": 20},
                        )
                    except Exception:
                        continue
                    for e in (ej.get("data") or {}).get("edges", []):
                        pid = e.get("source") or e.get("target")
                        if pid and pid != org_id and pid not in seen_pids:
                            seen_pids.add(pid)
                            experts_by_org.setdefault(org_id, []).append(
                                (pid, None, (e.get("properties") or {}).get("position"))
                            )

        all_expert_ids = set()
        for ev in top:
            for pid, _, role in experts_by_org.get(ev.get("org_id", ""), []):
                all_expert_ids.add(pid)
                resp.relations.append(
                    EventExpertRelation(
                        event_id=ev["event_id"],
                        event_title=ev.get("title"),
                        expert_id=pid,
                        expert_name=None,
                        role=role,
                        org_id=ev.get("org_id", ""),
                        org_name=ev.get("org_name"),
                    )
                )
        resp.experts = len(all_expert_ids)
        # 标书分析维度：节点影响 / 发展趋势 / 机遇挖掘（从 TOP 事件池规则派生，纯内存无新图调用）
        resp.node_impact, resp.trend, resp.opportunity = self._derive_analysis(
            top, top_org_ids, resp.risk_level
        )
        resp.evidence = [
            f"链节点 {req.chain_node_id}({resp.chain_node_name or ''}) 关联 {len(orgs)} 家企业",
            f"汇总 {len(events)} 条事件，影响力排序取 TOP {len(top)}",
            f"风险等级 {resp.risk_level}（基于事件类型 {sorted(top_types)}）",
            f"节点影响：{resp.node_impact}",
            f"发展趋势：{resp.trend}",
            f"机遇挖掘：{resp.opportunity}",
        ]
        return resp

    @staticmethod
    def _derive_analysis(
        top: list[dict], top_org_ids: set, risk_level: str
    ) -> tuple[str, str, str]:
        """从 TOP 事件池派生「节点影响/发展趋势/机遇挖掘」三段分析文案。

        纯规则派生（无 LLM、无新图调用），可解释、稳定。空事件返回空串。
        """
        if not top:
            return "", "", ""

        # 节点影响：主类型 + 风险/财务/资讯计数 + 波及企业数
        type_counts: dict[str, int] = {}
        for ev in top:
            t = ev.get("event_type") or "unknown"
            type_counts[t] = type_counts.get(t, 0) + 1
        main_type = max(type_counts, key=type_counts.get)
        risk_n = sum(1 for ev in top if (ev.get("event_type") or "") in RISK_EVENT_TYPES)
        fin_n = sum(1 for ev in top if (ev.get("event_type") or "") in FINANCE_EVENT_TYPES)
        news_n = sum(1 for ev in top if ev.get("event_type") == "news")
        node_impact = (
            f"TOP {len(top)} 事件以 {main_type} 为主，风险等级 {risk_level}，"
            f"波及 {len(top_org_ids)} 家链上企业；"
            f"含 {risk_n} 条风险事件、{fin_n} 条财务事件、{news_n} 条资讯"
        )

        # 发展趋势：按年分布 + 近 2 年占比判定上升/平稳
        year_counts: dict[str, int] = {}
        for ev in top:
            d = ev.get("occur_date")
            if d:
                y = str(d)[:4]
                if y.isdigit():
                    year_counts[y] = year_counts.get(y, 0) + 1
        years = sorted(year_counts)
        recent = sum(c for y, c in year_counts.items() if int(y) >= TREND_BASE_YEAR - 1)
        trend_word = "短期热度上升" if recent * 2 > len(top) else "分布平稳"
        trend = (
            f"近期 TOP 事件 {len(top)} 条"
            + (f"，集中在 {'、'.join(years)}" if years else "")
            + f"；{trend_word}"
        )

        # 机遇挖掘：融资/中标/资讯类事件提示合作与资本运作机会
        opp_ev = [ev for ev in top if (ev.get("event_type") or "") in OPP_EVENT_TYPES]
        opp_orgs = {ev.get("org_id") for ev in opp_ev if ev.get("org_id")}
        opp_type_counts: dict[str, int] = {}
        for ev in opp_ev:
            t = ev.get("event_type") or ""
            if t:
                opp_type_counts[t] = opp_type_counts.get(t, 0) + 1
        opp_desc = "、".join(
            f"{t} {c} 条" for t, c in sorted(opp_type_counts.items(), key=lambda x: -x[1])
        )
        opportunity = (
            f"{len(opp_ev)} 条融资/中标/资讯类事件提示产业合作与资本运作机会"
            + (f"（{opp_desc}）" if opp_desc else "")
            + (f"，涉及 {len(opp_orgs)} 家企业" if opp_orgs else "")
        )
        return node_impact, trend, opportunity
