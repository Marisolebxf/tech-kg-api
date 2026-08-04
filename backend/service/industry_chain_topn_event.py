from __future__ import annotations

import hashlib
from datetime import date, datetime
from typing import Any

from dao.industry_chain import IndustryChainDAO
from infra.graph_db import TRSGraphClient, get_graph_client
from service.base_module import KGModuleService


class IndustryChainTopNEventService(KGModuleService):
    module_code = "industry_chain_topn_event"

    def __init__(
        self, dao: IndustryChainDAO | None = None, graph: TRSGraphClient | None = None
    ) -> None:
        self._dao = dao or IndustryChainDAO()
        self._graph = graph

    def query(
        self,
        *,
        chain_code: str | None,
        keyword: str | None,
        node_id: str | None,
        since: str | None,
        until: str | None,
        top_n: int,
        persist: bool,
        space: str | None,
    ) -> dict[str, Any]:
        if not chain_code and not keyword:
            raise ValueError("chainCode 和 keyword 至少提供一个")
        rows = self._dao.list_news(
            chain_code=chain_code,
            keyword=keyword,
            since=since,
            until=until,
            limit=max(top_n * 5, 50),
        )
        events = [self._event(row, keyword) for row in rows]
        events.sort(key=lambda item: (item["score"], item["releaseDate"] or ""), reverse=True)
        events = events[: max(1, min(top_n, 100))]
        for rank, event in enumerate(events, start=1):
            event["rank"] = rank
        persisted = 0
        if persist and events:
            graph = self._graph or get_graph_client(space)
            source_id = node_id or chain_code
            if not source_id or graph.get_node(source_id) is None:
                raise KeyError(f"产业链图节点不存在: {source_id}")
            graph.execute_write(
                "CREATE TAG IF NOT EXISTS `IndustryEvent` "
                "(`title` string, `summary` string, `release_date` string, `source` string, "
                "`chain_code` string, `score` double);"
            )
            graph.execute_write(
                "CREATE EDGE IF NOT EXISTS `HAS_EVENT` (`score` double, `rank` int);"
            )
            for event in events:
                graph.merge_node(
                    ["IndustryEvent"],
                    {"vid": event["id"]},
                    {
                        "title": event["title"],
                        "summary": event["summary"],
                        "release_date": event["releaseDate"] or "",
                        "source": event["source"] or "",
                        "chain_code": event["chainCode"] or "",
                        "score": event["score"],
                    },
                )
                graph.create_edge(
                    source_id,
                    event["id"],
                    "HAS_EVENT",
                    {"score": event["score"], "rank": event["rank"]},
                )
                persisted += 1
        return {"total": len(events), "persisted": persisted, "items": events}

    @staticmethod
    def _event(row: dict[str, Any], keyword: str | None) -> dict[str, Any]:
        title = str(row.get("title") or "")
        summary = str(row.get("summary") or "")
        release_date = _date_value(row.get("relaese_date"))
        keyword_hits = 0
        if keyword:
            keyword_hits = (title + summary).casefold().count(keyword.casefold())
        recency = 0
        if release_date:
            try:
                days = max((date.today() - date.fromisoformat(release_date)).days, 0)
                recency = max(0, 30 - min(days // 30, 30))
            except ValueError:
                pass
        score = min(100, 50 + keyword_hits * 10 + recency)
        return {
            "id": str(
                row.get("news_id")
                or f"event:{hashlib.sha256(f'{title}|{release_date}'.encode()).hexdigest()[:20]}"
            ),
            "chainCode": row.get("chain_code"),
            "chainName": row.get("chain_name"),
            "title": title,
            "summary": summary,
            "releaseDate": release_date,
            "source": row.get("source"),
            "score": score,
            "rank": 0,
        }


def _date_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    return str(value)
