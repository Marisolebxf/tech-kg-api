from __future__ import annotations

import asyncio
import copy
import json
import threading
import time
from datetime import UTC, datetime
from typing import Any

from httpx import AsyncClient

from infra.graph_db import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings
from service.expert_colleague_relation import ExpertColleagueRelationService

# 60s 进程内读结果缓存：service.query 的图查询读结果可复用；写图副作用 _persist_relations
# 不缓存，每次照常执行（COLLEAGUE 边仍更新，persistence 计数每次现算）。
_READ_CACHE_TTL = 60.0
_read_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_read_cache_lock = threading.Lock()


def clear_caches() -> None:
    """清空进程内缓存（测试隔离用）。"""
    _read_cache.clear()


def _read_cache_key(kwargs: dict[str, Any]) -> str:
    parts: list[str] = []
    for k in sorted(kwargs):
        v = kwargs[k]
        # 用 repr 而非 join，避免 ['paper','patent'] 与 ['paper,patent'] 生成相同 key。
        if isinstance(v, (list, tuple, dict)):
            v = repr(v)
        parts.append(f"{k}={v}")
    return "|".join(parts)


class FastAPIGraphSearchGateway:
    """通过公开 FastAPI 查图契约读取图谱，业务层不接触图数据库。"""

    def __init__(self, client: AsyncClient) -> None:
        self._client = client
        self.api_calls: list[dict[str, Any]] = []

    async def resolve_person(self, keyword: str, space: str | None) -> dict[str, Any] | None:
        candidates = [keyword]
        if not keyword.startswith("person_"):
            candidates.append(f"person_{keyword}")
        for node_id in candidates:
            data = await self._get(f"/api/v1/graph-search/nodes/{node_id}", {"space": space})
            if data:
                return data
        matches: dict[str, dict[str, Any]] = {}
        for property_name in (
            "name_zh",
            "name_cn",
            "name_en",
            "name",
            "scholar_id",
            "source_record_id",
        ):
            data = await self._post(
                "/api/v1/graph-search/nodes/search",
                {"label": "Person", "limit": 50, "space": space},
                {property_name: keyword},
            )
            items = (data or {}).get("items", [])
            for item in items:
                value = str((item.get("properties") or {}).get(property_name) or "").strip()
                if value.casefold() == keyword.strip().casefold():
                    matches[str(item.get("id"))] = item
        if len(matches) == 1:
            return next(iter(matches.values()))
        if len(matches) > 1:
            candidates = "、".join(str(item.get("id")) for item in matches.values())
            raise LookupError(f"专家标识存在多个精确匹配，请改用唯一 VID: {candidates}")
        return None

    async def subgraph(
        self,
        node_id: str,
        *,
        depth: int,
        limit: int,
        direction: str = "both",
        edge_type: str | None = None,
        space: str | None = None,
    ) -> dict[str, Any]:
        params = {
            "depth": depth,
            "limit": limit,
            "direction": direction,
            "edge_type": edge_type,
            "space": space,
        }
        page_size = min(limit, 200)
        nodes: dict[str, dict[str, Any]] = {}
        edges: dict[str, dict[str, Any]] = {}
        offset = 0
        while len(edges) < limit:
            remaining = limit - len(edges)
            current_page_size = min(page_size, remaining)
            page_params = {
                **params,
                "depth": 1,
                "limit": current_page_size,
                "offset": offset,
            }
            data = await self._get(f"/api/v1/graph-search/subgraph/{node_id}", page_params)
            page = data or {"nodes": [], "edges": []}
            before = len(edges)
            for node in page.get("nodes", []):
                nodes[str(node.get("id"))] = node
            for edge in page.get("edges", []):
                key = str(
                    edge.get("id") or (edge.get("source"), edge.get("type"), edge.get("target"))
                )
                edges[key] = edge
            page_edges = page.get("edges", [])
            if len(page_edges) < current_page_size or len(edges) == before:
                break
            offset += current_page_size
        return {"nodes": list(nodes.values()), "edges": list(edges.values())}

    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        clean_params = {key: value for key, value in params.items() if value is not None}
        self.api_calls.append({"method": "GET", "path": path, "params": clean_params})
        response = await self._client.get(path, params=clean_params)
        return self._unwrap(response.json())

    async def _post(self, path: str, params: dict[str, Any], body: dict[str, Any]) -> Any:
        clean_params = {key: value for key, value in params.items() if value is not None}
        self.api_calls.append(
            {"method": "POST", "path": path, "params": clean_params, "body": body}
        )
        response = await self._client.post(path, params=clean_params, json=body)
        return self._unwrap(response.json())

    def _unwrap(self, payload: dict[str, Any]) -> Any:
        if payload.get("success") and payload.get("code") == 200:
            return payload.get("data")
        if payload.get("code") == 404:
            return None
        raise RuntimeError(payload.get("msg") or "查图 API 调用失败")


class ExpertColleagueRelationApplication:
    def __init__(self) -> None:
        self._service = ExpertColleagueRelationService()

    def describe(self) -> dict[str, object]:
        return self._service.describe()

    async def query(self, client: AsyncClient, **kwargs: Any) -> dict[str, Any]:
        # 图空间只由服务端 TRS_GRAPH_SPACE 环境变量决定，不接受请求覆盖。
        space = TRSGraphSettings.from_env().space
        kwargs["space"] = space
        cache_key = _read_cache_key(kwargs)
        with _read_cache_lock:
            entry = _read_cache.get(cache_key)
        if entry and entry[0] > time.monotonic():
            # 命中缓存：复用读结果（深拷贝，避免 _persist_relations 改到缓存对象）
            data = copy.deepcopy(entry[1])
        else:
            data = await self._service.query(FastAPIGraphSearchGateway(client), **kwargs)
            with _read_cache_lock:
                _read_cache[cache_key] = (
                    time.monotonic() + _READ_CACHE_TTL,
                    copy.deepcopy(data),
                )
        # 写图副作用不缓存：每次照常执行 COLLEAGUE 边 upsert + 现算 persistence 计数。
        data["persistence"] = await asyncio.to_thread(self._persist_relations, data)
        return data

    @staticmethod
    def _persist_relations(data: dict[str, Any]) -> dict[str, Any]:
        settings = TRSGraphSettings.from_env()
        graph = TRSGraphClient(settings)
        graph.connect()
        created = updated = 0
        try:
            graph.execute_write(
                "CREATE EDGE IF NOT EXISTS COLLEAGUE("
                "organization string, department string, effective_period string, "
                "overlap_months int, confidence double, teams_json string, "
                "work_content_json string, scenes_json string, "
                "achievement_ids_json string, evidence_json string, source string, "
                "updated_at string);"
            )
            expert_id = str(data["expert"]["id"])
            try:
                current_edges = graph.get_node_edges(
                    expert_id, direction="both", edge_type="COLLEAGUE", limit=1000
                )
            except Exception:
                current_edges = []
            existing = {
                str(edge.target_id if str(edge.source_id) == expert_id else edge.source_id): edge
                for edge in current_edges
            }
            now = datetime.now(UTC).isoformat()
            for relation in data.get("colleagues", []):
                target_id = str(relation["colleague"]["id"])
                properties = {
                    "organization": relation.get("commonOrganization") or "",
                    "department": relation.get("commonDepartment") or "",
                    "effective_period": relation.get("effectivePeriod") or "",
                    "overlap_months": int(relation.get("overlapMonths") or 0),
                    "confidence": float(relation.get("confidence") or 0),
                    "teams_json": json.dumps(
                        relation.get("commonTeamOrProject") or [], ensure_ascii=False
                    ),
                    "work_content_json": json.dumps(
                        relation.get("workContent") or [], ensure_ascii=False
                    ),
                    "scenes_json": json.dumps(
                        relation.get("collaborationScenes") or [], ensure_ascii=False
                    ),
                    "achievement_ids_json": json.dumps(
                        [item["id"] for item in relation.get("achievements", [])],
                        ensure_ascii=False,
                    ),
                    "evidence_json": json.dumps(relation.get("evidence") or [], ensure_ascii=False),
                    "source": "expert_colleague_relation_service",
                    "updated_at": now,
                }
                edge = existing.get(target_id)
                source_id, destination_id = sorted((expert_id, target_id))
                if edge is None:
                    graph.create_edge(source_id, destination_id, "COLLEAGUE", properties)
                    created += 1
                else:
                    graph.update_edge(edge.id, properties, edge_type="COLLEAGUE")
                    updated += 1
        finally:
            graph.close()
        return {
            "space": settings.space,
            "edgeType": "COLLEAGUE",
            "created": created,
            "updated": updated,
            "total": created + updated,
        }
