from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from service.expert_colleague_relation import ExpertColleagueRelationService


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
        for property_name in ("name_zh", "name_cn", "name_en", "name", "source_record_id"):
            data = await self._post(
                "/api/v1/graph-search/nodes/search",
                {"label": "Person", "limit": 5, "space": space},
                {property_name: keyword},
            )
            items = (data or {}).get("items", [])
            if items:
                return items[0]
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
        while True:
            page_params = {**params, "depth": 1, "limit": page_size, "offset": offset}
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
            if len(page_edges) < page_size or len(edges) == before:
                break
            offset += page_size
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
        return await self._service.query(FastAPIGraphSearchGateway(client), **kwargs)
