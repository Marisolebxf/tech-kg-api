"""科技产业链点 TOP-N 事件关系业务编排服务。

查图方式：直接调用 infra graph client（dev 空间），不再 HTTP 回调本服务 graph-search 接口。
原 HTTP 自调用在 500 并发下会与处理请求的 worker 互锁导致全超时；直调 infra 消除互锁根因，
并配合 asyncio.gather 并行化多企业查询、60s 结果缓存，显著降低单次延迟与高并发负载。

流程：
  1. 链节点 subgraph（BELONGS_TO_NODE + HAS_NODE）取链节点信息 + 关联企业 + 产业链
  2. 每个企业的 subgraph（INVOLVED_IN + HAS_NEWS）取事件 + 资讯，并行
  3. 事件影响力排序（event_type 权重 × 金额 × 时间新鲜度 × chain_score）→ TOP-N
  4. TOP 事件企业的 governance 边（EXECUTIVE_OF 等）查专家，并行
  5. 风险等级 + event→org→expert 关联
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import threading
import time
from typing import Any

from biz.schemas.industry_node_top_events_business import (
    EventExpertRelation,
    IndustryNodeTopEventsRequest,
    IndustryNodeTopEventsResponse,
    TopEventItem,
)
from infra.graph_db import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings

logger = logging.getLogger(__name__)

DEFAULT_BASE = os.getenv("BUSINESS_API_BASE", "http://127.0.0.1:8000")
SPACE = "dev"

GOVERNANCE_EDGES = {"EXECUTIVE_OF", "LEGAL_REP_OF", "ACTUAL_CONTROLLER_OF"}

# 进程内 dev 空间 graph client（缓存，避免每次请求重建连接）
_dev_client: TRSGraphClient | None = None
_dev_lock = threading.Lock()

# 60s 结果缓存：读多写少，同 chain_node_id+参数 的请求复用结果，避免高并发打爆 trs-graph
_RESULT_CACHE_TTL = float(os.getenv("RESULT_CACHE_TTL", "60"))
_result_cache: dict[str, tuple[float, IndustryNodeTopEventsResponse]] = {}
_result_cache_lock = threading.Lock()


def _get_dev_client() -> TRSGraphClient:
    """获取 dev 空间的 trs-graph 客户端（进程内单例，懒加载）。"""
    global _dev_client
    if _dev_client is not None:
        return _dev_client
    with _dev_lock:
        if _dev_client is None:
            settings = TRSGraphSettings.from_env()
            settings.space = SPACE
            client = TRSGraphClient(settings)
            client.connect()
            _dev_client = client
        return _dev_client


def _result_cache_get(key: str) -> IndustryNodeTopEventsResponse | None:
    entry = _result_cache.get(key)
    if entry and entry[0] > time.monotonic():
        # 调用方只做 model_dump（只读，不改对象），直接返回缓存对象，省 deepcopy
        # 的 CPU/GIL 开销——500 并发下 deepcopy 是瓶颈（命中变 dict查找，微秒级）。
        return entry[1]
    return None


def _result_cache_set(key: str, value: IndustryNodeTopEventsResponse) -> None:
    _result_cache[key] = (time.monotonic() + _RESULT_CACHE_TTL, value)


def _subgraph_sync(
    client: TRSGraphClient, vid: str, edge_types: list[str], limit: int
) -> dict[str, Any]:
    """同步取单跳子图：中心节点 + 指定边类型的边 + 邻居节点属性。

    返回结构与 graph-search /filtered-subgraph 的 data 一致，供 run() 原有解析逻辑复用：
    {"nodes": [{"id","properties"}], "edges": [{"source","target","type","properties"}]}
    """
    center = client.get_node(vid)
    if center is None:
        return {"nodes": [], "edges": []}
    nodes: list[dict[str, Any]] = [{"id": str(center.id), "properties": center.properties or {}}]
    edges: list[dict[str, Any]] = []
    seen_vids = {str(center.id)}
    for et in edge_types:
        try:
            edge_list = client.get_node_edges(vid, direction="both", edge_type=et, limit=limit)
        except Exception:
            continue
        for e in edge_list:
            edges.append(
                {
                    "source": str(e.source_id),
                    "target": str(e.target_id),
                    "type": str(e.type),
                    "properties": e.properties or {},
                }
            )
            neighbor = str(e.target_id if str(e.source_id) == vid else e.source_id)
            if neighbor and neighbor not in seen_vids:
                try:
                    n = client.get_node(neighbor)
                except Exception:
                    n = None
                if n is not None:
                    nodes.append({"id": str(n.id), "properties": n.properties or {}})
                    seen_vids.add(str(n.id))
    # 对齐 graph-search /filtered-subgraph 的截断（limit × 边类型数），避免事件密集企业取过多邻居。
    cap = limit * len(edge_types)
    if len(nodes) > cap:
        nodes = nodes[:cap]
    if len(edges) > cap:
        edges = edges[:cap]
    return {"nodes": nodes, "edges": edges}


def _fetch_org_events_sync(
    client: TRSGraphClient, org_vid: str, chain_score: float
) -> list[dict[str, Any]]:
    """同步取单个企业的事件 + 资讯，返回事件 dict 列表（含 org_id/org_name/chain_score）。"""
    sg = _subgraph_sync(client, org_vid, ["INVOLVED_IN", "HAS_NEWS"], 50)
    onodes = {n.get("id"): (n.get("properties") or {}) for n in sg["nodes"]}
    org_name = onodes.get(org_vid, {}).get("name_cn")
    events: list[dict[str, Any]] = []
    for e in sg["edges"]:
        etype = e.get("type")
        if etype not in ("INVOLVED_IN", "HAS_NEWS"):
            continue
        eid = e.get("target") if e.get("source") == org_vid else e.get("source")
        ep = onodes.get(eid, {})
        if etype == "HAS_NEWS":
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
    return events


def _fetch_org_governance_sync(client: TRSGraphClient, org_id: str) -> list[tuple[str, str | None]]:
    """同步取单个企业的 governance 边关联专家，返回 [(expert_id, position), ...]。"""
    seen_pids: set[str] = set()
    experts: list[tuple[str, str | None]] = []
    for et in GOVERNANCE_EDGES:
        try:
            edge_list = client.get_node_edges(org_id, direction="in", edge_type=et, limit=20)
        except Exception:
            continue
        for e in edge_list:
            pid = str(e.source_id if str(e.target_id) == org_id else e.target_id)
            if pid and pid != org_id and pid not in seen_pids:
                seen_pids.add(pid)
                experts.append((pid, (e.properties or {}).get("position")))
    return experts


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
        # 保留参数以兼容旧调用/测试；查图已改为直调 infra graph client，不再走 HTTP。
        self.base = (base_url or DEFAULT_BASE).rstrip("/") + "/api/v1"
        self.timeout = timeout

    async def run(self, req: IndustryNodeTopEventsRequest) -> IndustryNodeTopEventsResponse:
        cache_key = (
            f"{req.chain_node_id}|{req.top_n}|{req.event_type}|{req.time_range}|{req.max_orgs}"
        )
        cached = _result_cache_get(cache_key)
        if cached is not None:
            return cached

        resp = IndustryNodeTopEventsResponse(chain_node_id=req.chain_node_id)
        node_vid = (
            req.chain_node_id
            if req.chain_node_id.startswith("node_")
            else f"node_{req.chain_node_id}"
        )

        client = _get_dev_client()

        # 1) 链节点子图：BELONGS_TO_NODE + HAS_NODE（depth=1）
        try:
            data = await asyncio.to_thread(
                _subgraph_sync, client, node_vid, ["BELONGS_TO_NODE", "HAS_NODE"], 200
            )
        except Exception as exc:
            resp.evidence.append(f"链节点查询失败: {exc}")
            return resp
        nodes_map = {n.get("id"): (n.get("properties") or {}) for n in (data.get("nodes") or [])}
        # 子图不含 seed → 链节点不存在（_subgraph_sync 对存在节点必返回 center）
        if node_vid not in nodes_map:
            raise KeyError(f"产业链节点不存在: {req.chain_node_id}")
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

        # 2) 每个企业并行取 INVOLVED_IN 事件 + HAS_NEWS 资讯
        #    News 节点统一记为 event_type=news，参与影响力排序（资讯权重低，补"发展趋势"维度）
        org_event_lists = await asyncio.gather(
            *[
                asyncio.to_thread(_fetch_org_events_sync, client, org_vid, chain_score)
                for org_vid, chain_score in orgs
            ],
            return_exceptions=True,
        )
        events: list[dict[str, Any]] = []
        for org_vid, result in zip(orgs, org_event_lists, strict=False):
            if isinstance(result, Exception):
                logger.warning("subgraph %s 失败: %s", org_vid[0], result)
                continue
            events.extend(result)

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

        # 3) TOP 事件企业并行查专家（governance 边）
        top_org_ids = {ev.get("org_id") for ev in top if ev.get("org_id")}
        gov_results = await asyncio.gather(
            *[
                asyncio.to_thread(_fetch_org_governance_sync, client, org_id)
                for org_id in top_org_ids
            ],
            return_exceptions=True,
        )
        experts_by_org: dict[str, list[tuple[str, str | None]]] = {}
        for org_id, result in zip(top_org_ids, gov_results, strict=False):
            if isinstance(result, Exception):
                continue
            experts_by_org[org_id] = result

        all_expert_ids = set()
        for ev in top:
            for pid, role in experts_by_org.get(ev.get("org_id", ""), []):
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
        _result_cache_set(cache_key, resp)
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
