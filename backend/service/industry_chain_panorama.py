"""科技产业链全景图——通过 FastAPI 图查询 API 组合实现。

## 输出结构

1. ``summary``：整体规模（各标签节点数、各类型边数）。
2. ``layers``：四个分层（核心技术、领军企业、领军专家、代表成果），每层按检索
   到的实体展示；产业关键词非空时用属性搜索过滤，空时按标签分页取前 K。
3. ``graph``：以 ``anchorId`` 或首个专家/机构为中心的 ``depth`` 跳子图，直接返回
   给前端渲染。

## 图查询 API 使用

- ``GET /graph-search/stats`` — 全库统计
- ``GET /graph-search/nodes?label=X`` — 按标签分页
- ``POST /graph-search/nodes/search`` — 按属性搜索（产业关键词）
- ``GET /graph-search/subgraph/{vid}?depth=N`` — 以核心节点扩展子图

图服务不可用时降级到内置样例数据保证接口可用。
"""

from __future__ import annotations

import logging
from typing import Any

from infra.graph_api_client import GraphAPIClient, GraphAPIError, graph_api
from service.base_module import KGModuleScaffoldService

logger = logging.getLogger(__name__)

MAX_TOP_K = 20

_LAYER_DEFINITIONS: list[dict[str, Any]] = [
    {
        "key": "core_technology",
        "title": "核心技术",
        "labels": ["Technology", "ResearchField", "Field"],
        "name_props": ("name", "label", "field_name"),
        "metric_prop": "citation_nums",
        "metric_label": "被引次数",
        "type": "technology",
        # 用作产业关键词过滤时的字段候选
        "keyword_props": ("name", "keywords", "description"),
    },
    {
        "key": "leading_enterprise",
        "title": "领军企业",
        "labels": ["Organization", "Enterprise", "Company"],
        "name_props": ("name", "org_name", "canonical_name"),
        "metric_prop": "paper_nums",
        "metric_label": "发表论文数",
        "type": "organization",
        "keyword_props": ("name", "canonical_name", "aliases"),
    },
    {
        "key": "leading_expert",
        "title": "领军专家",
        "labels": ["Person", "Scholar"],
        "name_props": ("name_zh", "name_en", "name"),
        "metric_prop": "h_index",
        "metric_label": "H 指数",
        "type": "expert",
        "keyword_props": ("scholar_org", "research_fields", "biography"),
    },
    {
        "key": "flagship_achievement",
        "title": "代表成果",
        "labels": ["Paper", "Patent", "Project"],
        "name_props": ("title", "name", "chinese_title"),
        "metric_prop": "citation_nums",
        "metric_label": "被引次数",
        "type": "achievement",
        "keyword_props": ("title", "keywords", "abstract"),
    },
]


_FALLBACK_LAYERS: list[dict[str, Any]] = [
    {
        "key": "core_technology",
        "title": "核心技术",
        "type": "technology",
        "items": [
            {"id": "tech_ai_llm", "label": "大规模语言模型"},
            {"id": "tech_ai_perception", "label": "多模态感知"},
            {"id": "tech_ai_agent", "label": "自主智能体"},
        ],
    },
    {
        "key": "leading_enterprise",
        "title": "领军企业",
        "type": "organization",
        "items": [
            {"id": "org_baidu", "label": "百度"},
            {"id": "org_tsinghua", "label": "清华大学"},
            {"id": "org_zte", "label": "中兴通讯"},
        ],
    },
    {
        "key": "leading_expert",
        "title": "领军专家",
        "type": "expert",
        "items": [
            {"id": "person_fallback_zhangmingyuan", "label": "张明远", "subtitle": "清华大学"},
            {"id": "person_fallback_lijianing", "label": "李佳宁", "subtitle": "清华大学"},
        ],
    },
    {
        "key": "flagship_achievement",
        "title": "代表成果",
        "type": "achievement",
        "items": [
            {"id": "paper_fallback_llm_survey", "label": "大模型综述: 从预训练到智能体"},
            {"id": "patent_fallback_agent_router", "label": "面向智能体协作的路由方法"},
        ],
    },
]


class IndustryChainPanoramaService(KGModuleScaffoldService):
    module_code = "industry_chain_panorama"

    async def query(
        self,
        *,
        industry: str | None = None,
        anchor_id: str | None = None,
        depth: int = 2,
        top_k: int = 5,
    ) -> dict[str, Any]:
        industry_kw = (industry or "").strip() or None
        anchor = (anchor_id or "").strip() or None
        top_k = max(1, min(int(top_k or 5), MAX_TOP_K))
        depth = max(1, min(int(depth or 2), 3))
        query_input = {
            "dataSource": "all",
            "industry": industry_kw or "",
            "anchorId": anchor or "",
            "depth": depth,
            "topK": top_k,
        }

        source = {"requested": "all", "actual": "fallback", "fallback": True}
        summary: dict[str, Any] = {}
        layers: list[dict[str, Any]] = []
        graph: dict[str, list[Any]] = {"nodes": [], "edges": []}

        try:
            async with graph_api() as client:
                summary = await self._fetch_summary(client, industry_kw)
                layers = await self._fetch_layers(client, industry_kw, top_k)
                graph = await self._fetch_graph(client, layers, anchor, depth)
            source = {"requested": "all", "actual": "graph-api", "fallback": False}
        except GraphAPIError as exc:
            logger.warning("graph API unavailable for panorama, falling back: %s", exc)
        except Exception:  # noqa: BLE001
            logger.exception("unexpected error while building panorama via graph API")

        if not layers:
            layers = self._fallback_layers(top_k)
        if not summary:
            summary = self._fallback_summary(industry_kw, layers)
        if not graph["nodes"]:
            graph = self._fallback_graph(layers)

        return {
            "taskName": "科技产业链全景图",
            "input": query_input,
            "summary": summary,
            "layers": layers,
            "graph": graph,
            "source": source,
            "apiResultExample": {
                "url": "/api/v1/kg-construction/industry-chain-panorama/query",
                "method": "POST",
                "query": query_input,
            },
        }

    # ---------------- 各分层数据 ----------------
    async def _fetch_summary(
        self,
        client: GraphAPIClient,
        industry: str | None,
    ) -> dict[str, Any]:
        stats = await client.get_stats()
        nodes_by_label = dict(stats.get("nodes") or {})
        edges_by_type = dict(stats.get("edges") or {})
        return {
            "industry": industry,
            "totalNodes": sum(nodes_by_label.values()),
            "totalEdges": sum(edges_by_type.values()),
            "nodesByLabel": nodes_by_label,
            "edgesByType": edges_by_type,
        }

    async def _fetch_layers(
        self,
        client: GraphAPIClient,
        industry: str | None,
        top_k: int,
    ) -> list[dict[str, Any]]:
        layers: list[dict[str, Any]] = []
        for definition in _LAYER_DEFINITIONS:
            nodes = await self._collect_layer_nodes(client, definition, industry, top_k)
            layers.append(
                {
                    "key": definition["key"],
                    "title": definition["title"],
                    "total": len(nodes),
                    "items": [
                        self._node_to_key_entity(node, definition) for node in nodes[:top_k]
                    ],
                }
            )
        return layers

    async def _collect_layer_nodes(
        self,
        client: GraphAPIClient,
        definition: dict[str, Any],
        industry: str | None,
        top_k: int,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        seen: set[str] = set()

        for label in definition["labels"]:
            if industry:
                # 关键词过滤：逐个候选属性尝试属性搜索
                for prop in definition["keyword_props"]:
                    try:
                        found = await client.search_nodes(
                            label=label, properties={prop: industry}, limit=top_k
                        )
                    except GraphAPIError:
                        continue
                    for item in (found or {}).get("items", []):
                        vid = str(item.get("id") or "")
                        if vid and vid not in seen:
                            seen.add(vid)
                            results.append(item)
                    if len(results) >= top_k:
                        return results
            else:
                try:
                    listing = await client.list_nodes(label=label, limit=top_k)
                except GraphAPIError:
                    continue
                for item in (listing or {}).get("items", []):
                    vid = str(item.get("id") or "")
                    if vid and vid not in seen:
                        seen.add(vid)
                        results.append(item)
                if len(results) >= top_k:
                    return results
        return results

    async def _fetch_graph(
        self,
        client: GraphAPIClient,
        layers: list[dict[str, Any]],
        anchor_id: str | None,
        depth: int,
    ) -> dict[str, list[Any]]:
        seed = anchor_id or self._pick_seed_vid(layers)
        if not seed:
            return {"nodes": [], "edges": []}
        try:
            subgraph = await client.get_subgraph(seed, depth=depth, limit=60)
        except GraphAPIError:
            return {"nodes": [], "edges": []}
        return {
            "nodes": [self._node_to_graph_node(n) for n in subgraph.get("nodes", [])],
            "edges": [self._edge_to_graph_edge(e) for e in subgraph.get("edges", [])],
        }

    # ---------------- 转换器 ----------------
    def _node_to_key_entity(
        self, node: dict[str, Any], definition: dict[str, Any]
    ) -> dict[str, Any]:
        props = node.get("properties") or {}
        label = self._first_prop_value(props, definition["name_props"]) or str(node.get("id"))
        metric_value = props.get(definition["metric_prop"])
        try:
            metric_value_num = int(metric_value) if metric_value is not None else None
        except (TypeError, ValueError):
            metric_value_num = None
        subtitle_prop = self._first_prop_value(props, ("scholar_org", "org_name", "affiliation"))
        return {
            "id": str(node.get("id") or ""),
            "label": label,
            "type": definition["type"],
            "subtitle": subtitle_prop,
            "metric": definition["metric_label"] if metric_value_num is not None else None,
            "metricValue": metric_value_num,
        }

    def _node_to_graph_node(self, node: dict[str, Any]) -> dict[str, Any]:
        props = node.get("properties") or {}
        labels = node.get("labels") or []
        primary_label = labels[0] if labels else "Node"
        return {
            "id": str(node.get("id") or ""),
            "type": primary_label,
            "label": self._first_prop_value(
                props, ("name_zh", "name", "title", "canonical_name")
            )
            or str(node.get("id") or ""),
            "subtitle": self._first_prop_value(
                props, ("scholar_org", "org_name", "affiliation", "description")
            ),
            "data": {"labels": labels},
        }

    def _edge_to_graph_edge(self, edge: dict[str, Any]) -> dict[str, Any]:
        return {
            "source": str(edge.get("source") or ""),
            "target": str(edge.get("target") or ""),
            "label": str(edge.get("type") or ""),
            "data": edge.get("properties") or {},
        }

    @staticmethod
    def _first_prop_value(props: dict[str, Any], keys: tuple[str, ...]) -> str | None:
        for key in keys:
            value = props.get(key)
            if value:
                return str(value)
        return None

    def _pick_seed_vid(self, layers: list[dict[str, Any]]) -> str | None:
        for preferred in ("leading_expert", "leading_enterprise", "core_technology"):
            for layer in layers:
                if layer["key"] != preferred:
                    continue
                for item in layer.get("items", []):
                    if item.get("id"):
                        return str(item["id"])
        for layer in layers:
            for item in layer.get("items", []):
                if item.get("id"):
                    return str(item["id"])
        return None

    # ---------------- 降级样例 ----------------
    def _fallback_layers(self, top_k: int) -> list[dict[str, Any]]:
        layers = []
        for definition, sample in zip(_LAYER_DEFINITIONS, _FALLBACK_LAYERS, strict=False):
            items = sample.get("items", [])[:top_k]
            layers.append(
                {
                    "key": definition["key"],
                    "title": definition["title"],
                    "total": len(items),
                    "items": [
                        {
                            "id": item["id"],
                            "label": item["label"],
                            "type": definition["type"],
                            "subtitle": item.get("subtitle"),
                            "metric": None,
                            "metricValue": None,
                        }
                        for item in items
                    ],
                }
            )
        return layers

    def _fallback_summary(
        self, industry: str | None, layers: list[dict[str, Any]]
    ) -> dict[str, Any]:
        nodes_by_label = {"Person": 2, "Organization": 3, "Technology": 3, "Paper": 2}
        edges_by_type = {"AFFILIATED_WITH": 4, "COAUTHOR_WITH": 3, "AUTHORED_BY": 4}
        return {
            "industry": industry,
            "totalNodes": sum(nodes_by_label.values()),
            "totalEdges": sum(edges_by_type.values()),
            "nodesByLabel": nodes_by_label,
            "edgesByType": edges_by_type,
        }

    def _fallback_graph(self, layers: list[dict[str, Any]]) -> dict[str, list[Any]]:
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        # 以「领军专家」为中心，与其它三类连接
        expert_layer = next(
            (layer for layer in layers if layer["key"] == "leading_expert"), None
        )
        center_id: str | None = None
        if expert_layer and expert_layer["items"]:
            center_id = expert_layer["items"][0]["id"]
            center = expert_layer["items"][0]
            nodes.append(
                {
                    "id": center["id"],
                    "type": "expert",
                    "label": center["label"],
                    "subtitle": center.get("subtitle"),
                    "data": {},
                }
            )
            seen_ids.add(center["id"])

        for layer in layers:
            if not center_id:
                break
            for item in layer["items"]:
                if item["id"] == center_id:
                    continue
                if item["id"] not in seen_ids:
                    nodes.append(
                        {
                            "id": item["id"],
                            "type": layer["key"],
                            "label": item["label"],
                            "subtitle": item.get("subtitle"),
                            "data": {},
                        }
                    )
                    seen_ids.add(item["id"])
                edges.append(
                    {
                        "source": center_id,
                        "target": item["id"],
                        "label": {
                            "core_technology": "研究方向",
                            "leading_enterprise": "所属机构",
                            "flagship_achievement": "代表成果",
                        }.get(layer["key"], "关联"),
                        "data": {},
                    }
                )
        return {"nodes": nodes, "edges": edges}
