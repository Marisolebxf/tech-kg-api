"""科技产业链全景图——通过 FastAPI 图查询 API 组合实现。

## 输出结构

1. ``summary``：整体规模（各标签节点数、各类型边数）。
2. ``layers``：四个分层（核心技术、领军企业、领军专家、代表成果），每层按检索
   到的实体展示；产业关键词非空时先用属性搜索精确过滤，未命中再有界扫描做包含
   匹配，关键词为空时按标签分页取前 K。
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
# 属性搜索只支持精确等值；未命中时退化为有界扫描 + 本地包含匹配的扫描上限。
_KEYWORD_SCAN_LIMIT = 500

_LAYER_DEFINITIONS: list[dict[str, Any]] = [
    {
        "key": "core_technology",
        "title": "核心技术",
        "labels": ["Keyword", "IndustryNode"],
        "name_props": ("keyword", "node_name", "name"),
        "metric_prop": "citation_nums",
        "metric_label": "被引次数",
        "type": "technology",
        # 用作产业关键词过滤时的字段候选
        "keyword_props": ("keyword", "node_name"),
    },
    {
        "key": "leading_enterprise",
        "title": "领军企业",
        "labels": ["Organization"],
        "name_props": ("name_cn", "name_en", "name"),
        "metric_prop": "paper_nums",
        "metric_label": "发表论文数",
        "type": "organization",
        "keyword_props": ("name_cn", "name_en", "industry_class"),
    },
    {
        "key": "leading_expert",
        "title": "领军专家",
        "labels": ["Person"],
        "name_props": ("name_zh", "name_cn", "name_en"),
        "metric_prop": "h_index",
        "metric_label": "H 指数",
        "type": "expert",
        "keyword_props": ("scholar_org", "research_fields", "bio_zh"),
    },
    {
        "key": "flagship_achievement",
        "title": "代表成果",
        "labels": ["Paper", "Patent", "Project"],
        "name_props": ("title_zh", "title_en", "title", "title_original"),
        "metric_prop": "citation_nums",
        "metric_label": "被引次数",
        "type": "achievement",
        "keyword_props": ("title_zh", "title_en", "keywords"),
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

        source: dict[str, Any] = {"requested": "all", "actual": "fallback", "fallback": True}
        summary: dict[str, Any] = {}
        layers: list[dict[str, Any]] = []
        seed_vids: list[str] = []
        graph: dict[str, list[Any]] = {"nodes": [], "edges": []}
        fallback_reason: str | None = None

        try:
            async with graph_api() as client:
                summary = await self._fetch_summary(client, industry_kw)
                layers, seed_vids = await self._fetch_layers(client, industry_kw, top_k)
                graph = await self._fetch_graph(client, seed_vids, anchor, depth)
        except GraphAPIError as exc:
            logger.warning("graph API unavailable for panorama, falling back: %s", exc)
            fallback_reason = "graph_api_error"
        except Exception:  # noqa: BLE001
            logger.exception("unexpected error while building panorama via graph API")
            fallback_reason = "unexpected_error"

        has_real_layers = any(layer["items"] for layer in layers)
        if not has_real_layers:
            # 关键词没命中任何实体时同样要走降级，否则前端只看到四个空分层
            # 却被告知数据来自图查询。
            if fallback_reason is None:
                fallback_reason = "keyword_no_match" if industry_kw else "empty_result"
            layers = self._fallback_layers(top_k)
        if not summary:
            summary = self._fallback_summary(industry_kw, layers)
        if not graph["nodes"] and not has_real_layers:
            # 样例子图是按 layers 拼出来的，只有 layers 本身也是样例时才拼，
            # 避免真实实体与编造出来的边混在一张图里。
            graph = self._fallback_graph(layers)

        if fallback_reason is None:
            source = {"requested": "all", "actual": "graph-api", "fallback": False}
        else:
            logger.info(
                "industry chain panorama falls back to seed data: reason=%s, industry=%s",
                fallback_reason,
                industry_kw,
            )
            source = {
                "requested": "all",
                "actual": "fallback",
                "fallback": True,
                "reason": fallback_reason,
            }

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
        """取全库规模统计。

        Args:
            client: 图查询 API 客户端。
            industry: 产业关键词，仅原样回填到结果里。

        Returns:
            含 ``totalNodes`` / ``totalEdges`` / 分标签与分类型计数的字典。
        """
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
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """构造四个分层，并收集可用于扩展子图的种子 VID。

        Args:
            client: 图查询 API 客户端。
            industry: 产业关键词，非空时做关键词过滤。
            top_k: 每层最多返回多少个实体。

        Returns:
            ``(layers, seed_vids)``：``layers`` 为四层结果，``seed_vids`` 按
            专家 → 机构 → 技术的偏好顺序排列，只包含能按 VID 寻址的节点。
        """
        layers: list[dict[str, Any]] = []
        seeds_by_key: dict[str, list[str]] = {}
        for definition in _LAYER_DEFINITIONS:
            nodes = await self._collect_layer_nodes(client, definition, industry, top_k)
            picked = nodes[:top_k]
            layers.append(
                {
                    "key": definition["key"],
                    "title": definition["title"],
                    "total": len(nodes),
                    "items": [self._node_to_key_entity(node, definition) for node in picked],
                }
            )
            seeds_by_key[definition["key"]] = [
                str(node["id"]) for node in picked if node.get("id") and node.get("_addressable")
            ]

        seed_vids: list[str] = []
        for key in ("leading_expert", "leading_enterprise", "core_technology"):
            seed_vids.extend(seeds_by_key.pop(key, []))
        for remaining in seeds_by_key.values():
            seed_vids.extend(remaining)
        return layers, seed_vids

    async def _collect_layer_nodes(
        self,
        client: GraphAPIClient,
        definition: dict[str, Any],
        industry: str | None,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """取一个分层的候选节点。

        Args:
            client: 图查询 API 客户端。
            definition: ``_LAYER_DEFINITIONS`` 中的一项。
            industry: 产业关键词；非空时先精确搜属性，未命中再有界扫描做包含匹配。
            top_k: 目标条数。

        Returns:
            节点列表。每个节点带 ``_addressable`` 标记，表示其 ``id`` 是否能按
            VID 直接取回（只有能寻址的节点才可用于扩展子图）。
        """
        results: list[dict[str, Any]] = []
        seen: set[str] = set()

        for label in definition["labels"]:
            if industry:
                nodes = await self._search_by_keyword(client, label, definition, industry, top_k)
            else:
                nodes = await self._list_by_label(client, label, top_k)
            for node in nodes:
                vid = str(node.get("id") or "")
                if vid and vid not in seen:
                    seen.add(vid)
                    results.append(node)
            if len(results) >= top_k:
                return results
        return results

    async def _search_by_keyword(
        self,
        client: GraphAPIClient,
        label: str,
        definition: dict[str, Any],
        industry: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """按产业关键词找某个标签下的节点。

        属性搜索只支持精确等值，关键词与库里存的字面值稍有差异就会全空；因此
        精确搜索未命中时，再有界扫描 ``_KEYWORD_SCAN_LIMIT`` 个节点做包含匹配。

        Args:
            client: 图查询 API 客户端。
            label: 节点标签。
            definition: ``_LAYER_DEFINITIONS`` 中的一项。
            industry: 产业关键词。
            top_k: 目标条数。

        Returns:
            命中的节点列表，均带 ``_addressable`` 标记。
        """
        found: list[dict[str, Any]] = []
        for prop in definition["keyword_props"]:
            try:
                payload = await client.search_nodes(
                    label=label, properties={prop: industry}, limit=top_k
                )
            except GraphAPIError:
                continue
            found.extend(await self._mark_addressable(client, (payload or {}).get("items", [])))
            if len(found) >= top_k:
                return found[:top_k]
        if found:
            return found

        # 精确等值没命中，退化为有界扫描 + 本地包含匹配
        needle = industry.casefold()
        scanned = await self._list_by_label(client, label, _KEYWORD_SCAN_LIMIT)
        for node in scanned:
            props = node.get("properties") or {}
            for prop in definition["keyword_props"]:
                value = str(props.get(prop) or "")
                if value and needle in value.casefold():
                    found.append(node)
                    break
            if len(found) >= top_k:
                break
        return found

    async def _list_by_label(
        self,
        client: GraphAPIClient,
        label: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """按标签分页取节点。图服务报错时返回空列表。"""
        try:
            listing = await client.list_nodes(label=label, limit=limit)
        except GraphAPIError:
            return []
        # 按标签分页返回的是真实 VID，可直接用于扩展子图
        return [{**item, "_addressable": True} for item in (listing or {}).get("items", [])]

    @staticmethod
    async def _mark_addressable(
        client: GraphAPIClient,
        items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """标注属性搜索结果能否按 VID 寻址，并尽量换成可寻址节点。

        ``/nodes/search`` 返回的 ``id`` 不保证是业务 VID，不做校验就拿去扩展子图
        会静默查不到数据。

        Args:
            client: 图查询 API 客户端。
            items: 属性搜索返回的节点列表。

        Returns:
            与入参等长的节点列表，每项带 ``_addressable`` 标记。
        """
        marked: list[dict[str, Any]] = []
        for item in items:
            try:
                resolved = await client.resolve_addressable_node(item)
            except GraphAPIError:
                resolved = None
            if resolved is not None:
                marked.append({**resolved, "_addressable": True})
            else:
                marked.append({**item, "_addressable": False})
        return marked

    async def _fetch_graph(
        self,
        client: GraphAPIClient,
        seed_vids: list[str],
        anchor_id: str | None,
        depth: int,
    ) -> dict[str, list[Any]]:
        """以锚点或首个可寻址实体为中心扩展子图。

        Args:
            client: 图查询 API 客户端。
            seed_vids: 备选种子 VID，按偏好排序。
            anchor_id: 调用方指定的锚点 VID，优先使用。
            depth: 扩展跳数。

        Returns:
            ``{"nodes": [...], "edges": [...]}``；没有可用种子或查询失败时为空图。
        """
        seed = anchor_id or (seed_vids[0] if seed_vids else None)
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
        subtitle_prop = self._first_prop_value(
            props, ("scholar_org", "org_name", "affiliation", "industry_class", "node_type")
        )
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
                props,
                (
                    "name_zh",
                    "name_cn",
                    "name",
                    "title_zh",
                    "title",
                    "keyword",
                    "node_name",
                    "name_en",
                    "title_en",
                ),
            )
            or str(node.get("id") or ""),
            "subtitle": self._first_prop_value(
                props, ("scholar_org", "org_name", "affiliation", "industry_class", "node_type")
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
        """按候选键的先后顺序取第一个非空属性值。

        Args:
            props: 节点属性字典。
            keys: 候选属性名，按优先级排列。

        Returns:
            第一个非空值的字符串形式；全为空时返回 ``None``。
        """
        for key in keys:
            value = props.get(key)
            if value:
                return str(value)
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
        expert_layer = next((layer for layer in layers if layer["key"] == "leading_expert"), None)
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
