"""科技产业链全景图——通过 FastAPI 图查询 API 组合实现。

## 输出结构

1. ``summary``：本次查询结果规模（命中的分层实体数、返回子图里的关系数）。
2. ``layers``：四个分层（核心技术、领军企业、领军专家、产业动态事件），每层按检索
   到的实体展示；产业关键词非空时先用属性搜索精确过滤，未命中再有界扫描做包含
   匹配，关键词为空时按标签分页取前 K。
3. ``graph``：以 ``anchorId`` 或首个专家/机构为中心的 ``depth`` 跳子图，直接返回
   给前端渲染。

## 图查询 API 使用

- ``GET /graph-search/nodes?label=X`` — 按标签分页
- ``POST /graph-search/nodes/search`` — 按属性搜索（产业关键词）
- ``GET /graph-search/subgraph/{vid}?depth=N`` — 以核心节点扩展子图

查询结果一律来自图库；关键词未命中或图服务异常时返回空结果并在 ``source.reason``
标明原因，不返回内置示例数据。
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping
from typing import Any

from infra.graph_api_client import GraphAPIClient, GraphAPIError, graph_api
from infra.graph_db.config import TRSGraphSettings
from service.base_module import KGModuleScaffoldService
from service.provenance_recorder import record_node_source

logger = logging.getLogger(__name__)

MAX_TOP_K = 20
MAX_RELATION_TYPES = 20
_PRESET_INDUSTRY_ALIASES: dict[str | None, tuple[str, ...]] = {
    None: ("产业全景", "全景图", "全产业链", "全部产业"),
    "人工智能": ("人工智能", "人工智能产业", "人工智能产业链", "ai", "AI"),
    "集成电路": ("集成电路", "集成电路产业", "集成电路产业链", "芯片", "半导体"),
}
_PRESET_FAST_ANCHOR_HINTS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "人工智能": (
        ("IndustryChain", ("name", "chain_name")),
        ("IndustryNode", ("node_name", "name")),
        ("Keyword", ("keyword",)),
    ),
    "集成电路": (
        ("IndustryNode", ("node_name", "name")),
        ("IndustryChain", ("name", "chain_name")),
        ("Keyword", ("keyword",)),
    ),
}
# 属性搜索只支持精确等值；未命中时退化为有界扫描 + 本地包含匹配的扫描上限。
_KEYWORD_SCAN_LIMIT = 50
# 精确未命中后的兜底只做小范围扫描，控制在单页内，避免全量分页拖慢接口。
_COMPACT_KEYWORD_SCAN_LIMIT = 50
_COMPACT_SCAN_LABELS = {"IndustryNode", "IndustryChain", "Keyword"}
# 专家属性检索依赖图库索引；索引缺失时做有界分页扫描，并按研究领域相关性排序。
_EXPERT_SCAN_LIMIT = 500
_INDUSTRY_EXPERT_SCAN_PAGES: dict[str, int] = {
    # 低空经济相关学者在专家库中的分布较靠后，有限扩展到 5 页即可覆盖
    # 无人机网络、农业无人机和无人机视觉等核心方向。
    "低空经济": 5,
}
_INDUSTRY_EXPERT_TERMS: dict[str, tuple[str, ...]] = {
    "集成电路": (
        "集成电路",
        "芯片",
        "半导体",
        "integrated circuit",
        "chip",
        "semiconductor",
        "vlsi",
        "system-on-chip",
        "fpga",
    ),
    "低空经济": (
        "低空经济",
        "无人机",
        "无人驾驶航空器",
        "通用航空",
        "unmanned aerial vehicle",
        "uav",
        "drone",
        "general aviation",
    ),
}
# 子图合并时最多取多少个种子节点。
_MAX_SUBGRAPH_SEEDS = 5
# 锚点（产业链）结构子图：HAS_NODE 一跳最多带多少个链下环节进图。
_ANCHOR_CHAIN_NODE_LIMIT = 40
# 最多对多少个叶子环节探查 BELONGS_TO_NODE 企业边（每个环节一次一跳子图请求）。
_ANCHOR_ORG_PROBE_COUNT = 6
# 摘要「产业链名称」最多统计多少条产业链。
_INDUSTRY_CHAIN_LABEL_LIMIT = 10
# 图服务（trs-graph）承受不住太高并发，全标签扫描类请求并发过多会 500，
# 用信号量把同时打到图服务的请求数压住。
_GRAPH_API_CONCURRENCY = 6
_graph_api_semaphore = asyncio.Semaphore(_GRAPH_API_CONCURRENCY)
_PANORAMA_CACHE_TTL_SECONDS = 600.0
# 缓存键：产业关键词 / 锚点 VID / 展开层级 / topK / 关系筛选（逗号拼接的边类型）
_panorama_cache: dict[tuple[str, str, int, int, str], tuple[float, dict[str, Any]]] = {}
_panorama_rebuilding: set[tuple[str, str, int, int, str]] = set()

_FALLBACK_REASON_TEXT = {
    "empty_result": "图库中没有可用实体",
    "keyword_no_match": "产业关键词未命中任何实体",
    "graph_api_error": "图查询服务不可用",
    "unexpected_error": "图查询过程异常",
    "keyword_fallback_overview": "关键词未命中，已回退到紧凑全景",
}

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
        "title": "产业动态事件",
        "labels": ["Event"],
        "name_props": ("title", "name", "event_name", "event_type"),
        "metric_prop": "amount",
        "metric_label": "事件金额",
        "type": "event",
        "keyword_props": ("title", "content", "event_type"),
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
        relation_types: list[str] | None = None,
        refresh: bool = False,
        auth_headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        industry_kw = self._normalize_industry_keyword(industry)
        anchor = (anchor_id or "").strip() or None
        top_k = max(1, min(int(top_k or 5), MAX_TOP_K))
        depth = max(1, min(int(depth or 2), 3))
        rel_types = self._normalize_relation_types(relation_types)
        cache_key = (industry_kw or "", anchor or "", depth, top_k, ",".join(rel_types))
        if refresh:
            # 页面「刷新图谱」：丢掉缓存直接实时重组，保证拿到最新入图数据。
            _panorama_cache.pop(cache_key, None)
        cached = None if refresh else _panorama_cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < _PANORAMA_CACHE_TTL_SECONDS:
            return cached[1]
        if cached:
            # 过期先返回旧结果，后台重建，不让用户等一次实时组装。
            self._rebuild_in_background(
                cache_key,
                industry=industry_kw,
                anchor_id=anchor,
                depth=depth,
                top_k=top_k,
                relation_types=rel_types,
                auth_headers=auth_headers,
            )
            return cached[1]
        query_input = {
            "dataSource": "all",
            "industry": industry_kw or "",
            "anchorId": anchor or "",
            "depth": depth,
            "topK": top_k,
            "relationTypes": rel_types,
        }

        source: dict[str, Any] = {"requested": "all", "actual": "fallback", "fallback": True}
        summary: dict[str, Any] = {}
        layers: list[dict[str, Any]] = []
        seed_vids: list[str] = []
        graph: dict[str, list[Any]] = {"nodes": [], "edges": []}
        industry_chains: list[str] = []
        fallback_reason: str | None = None

        try:
            async with graph_api(auth_headers=auth_headers) as client:
                resolved_anchor, layer_payload, industry_chains = await asyncio.gather(
                    self._resolve_anchor_from_keyword(client, industry_kw, anchor),
                    self._fetch_layers(client, industry_kw, top_k),
                    self._fetch_industry_chain_labels(client),
                )
                layers, seed_vids = layer_payload
                anchor = resolved_anchor
                if industry_kw and not anchor and not any(layer["items"] for layer in layers):
                    layers, seed_vids = await self._fetch_layers(client, None, top_k)
                    fallback_reason = "keyword_fallback_overview"
                if rel_types:
                    graph = await self._fetch_graph(
                        client,
                        seed_vids,
                        anchor,
                        depth,
                        relation_types=rel_types,
                    )
                else:
                    graph = await self._fetch_graph(client, seed_vids, anchor, depth)
                layers = self._backfill_empty_layers_from_graph(layers, graph, top_k)
                if anchor and seed_vids and any(not layer["items"] for layer in layers):
                    # 锚点子图只覆盖链自身结构（新入图的链可能只挂了新闻），
                    # 第一轮回填后空层仍可能拿不到实体：用分层种子再扩一轮
                    # 子图合并进图、只补仍为空的分层（已非空的层回填不动）。
                    # 无锚点时子图本就从种子扩展而来，不做重复拉取。
                    seed_graph = await self._fetch_graph(client, seed_vids, None, depth)
                    graph = self._merge_graphs(graph, seed_graph)
                    layers = self._backfill_empty_layers_from_graph(layers, graph, top_k)
                graph = self._filter_graph_by_relation_types(graph, rel_types, anchor_id=anchor)
                query_input["anchorId"] = anchor or ""
        except GraphAPIError as exc:
            logger.warning("graph API unavailable for panorama, falling back: %s", exc)
            fallback_reason = "graph_api_error"
        except Exception:  # noqa: BLE001
            logger.exception("unexpected error while building panorama via graph API")
            fallback_reason = "unexpected_error"

        has_real_layers = any(layer["items"] for layer in layers)
        if not has_real_layers:
            if fallback_reason is None:
                fallback_reason = "keyword_no_match" if industry_kw else "empty_result"
            logger.info(
                "industry chain panorama empty result: reason=%s, industry=%s",
                fallback_reason,
                industry_kw,
            )
        summary = self._build_summary(industry_kw, layers, graph, industry_chains)

        source = {
            "requested": "all",
            "actual": "graph-api",
            "fallback": False,
        }
        if industry_kw != (industry or "").strip() and (industry or "").strip():
            source["normalizedIndustry"] = industry_kw or ""
        if anchor and not anchor_id:
            source["autoAnchorId"] = anchor
        if fallback_reason is not None:
            source["reason"] = fallback_reason

        result = {
            "taskName": "科技产业链全景图",
            "input": query_input,
            "summary": summary,
            "layers": layers,
            "graph": graph,
            "source": source,
            "provenance": self._build_provenance(summary, layers, graph, source),
            "apiResultExample": {
                "url": "/api/v1/kg-construction/industry-chain-panorama/query",
                "method": "POST",
                "query": query_input,
            },
        }
        if has_real_layers:
            # 只缓存真实命中；空结果可能是图服务瞬时抖动，缓存住会让下一个
            # 请求 10 分钟内都拿不到数据。
            _panorama_cache[cache_key] = (time.monotonic(), result)
        return result

    @classmethod
    def _normalize_industry_keyword(cls, industry: str | None) -> str | None:
        raw = (industry or "").strip()
        if not raw:
            return None
        folded = raw.casefold()
        for canonical, aliases in _PRESET_INDUSTRY_ALIASES.items():
            if any(folded == alias.casefold() for alias in aliases):
                return canonical
        return raw

    async def _resolve_anchor_from_keyword(
        self,
        client: GraphAPIClient,
        industry: str | None,
        anchor_id: str | None,
    ) -> str | None:
        """显式 anchor 优先；否则对热点关键词做轻量唯一命中，直转 anchorId。"""
        if anchor_id:
            return anchor_id
        if not industry:
            return None

        preset = _PRESET_FAST_ANCHOR_HINTS.get(industry)
        if preset:
            for label, props in preset:  # 只按关键词做轻量唯一命中，不依赖固定图 ID
                resolved = await self._resolve_unique_anchor_candidate(
                    client, label, props, industry
                )
                if resolved:
                    return resolved

        generic_plan = (
            ("IndustryNode", ("node_name", "name")),
            ("IndustryChain", ("name", "chain_name")),
            ("Keyword", ("keyword",)),
        )
        for label, props in generic_plan:
            resolved = await self._resolve_unique_anchor_candidate(client, label, props, industry)
            if resolved:
                return resolved
        return None

    async def _resolve_unique_anchor_candidate(
        self,
        client: GraphAPIClient,
        label: str,
        props: tuple[str, ...],
        industry: str,
    ) -> str | None:
        seen: dict[str, dict[str, Any]] = {}
        for prop in props:
            payload = await self._safe_search_nodes(client, label, prop, industry, 2)
            for item in (payload or {}).get("items", []):
                item_id = str(item.get("id") or "")
                if item_id and item_id not in seen:
                    seen[item_id] = item
            if len(seen) > 1:
                return None
        if not seen:
            # trs-graph 的属性查找依赖对应字段索引。部分部署只有 VID 索引，
            # find_nodes 会返回 IndexNotFound；此时对单页候选做严格等值匹配，
            # 仍可把真实 IndustryChain 节点解析为锚点，避免回退到无关全库数据。
            candidates = await self._list_by_label_throttled(
                client, label, _COMPACT_KEYWORD_SCAN_LIMIT, 0
            )
            expected = industry.casefold()
            for item in candidates:
                item_props = item.get("properties") or {}
                if not any(
                    str(item_props.get(prop) or "").strip().casefold() == expected for prop in props
                ):
                    continue
                item_id = str(item.get("id") or "")
                if item_id and item_id not in seen:
                    seen[item_id] = item
                if len(seen) > 1:
                    return None
        if len(seen) != 1:
            return None
        candidate = next(iter(seen.values()))
        try:
            resolved = await client.resolve_addressable_node(
                candidate,
                vid_candidates=self._node_vid_candidates(candidate),
            )
        except GraphAPIError:
            return None
        return str(resolved.get("id") or "") if resolved else None

    @staticmethod
    def _normalize_relation_types(relation_types: list[str] | None) -> list[str]:
        """规整关系筛选入参：去空、大写、去重，最多保留 20 项。

        Args:
            relation_types: 调用方传入的边类型，如 ``["COAUTHOR_WITH"]``。

        Returns:
            规整后的边类型列表；不筛选时为空列表。
        """
        if not relation_types:
            return []
        seen: set[str] = set()
        normalized: list[str] = []
        for item in relation_types:
            value = str(item or "").strip().upper()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
            if len(normalized) >= MAX_RELATION_TYPES:
                break
        return normalized

    @staticmethod
    def _filter_graph_by_relation_types(
        graph: dict[str, list[Any]],
        relation_types: list[str],
        *,
        anchor_id: str | None = None,
    ) -> dict[str, list[Any]]:
        """按边类型筛选子图，并丢掉筛选后不再有连边的节点。

        链节点（IndustryChain）与锚点节点是子图的结构骨架：链只通过 HAS_NODE
        结构边连环节，若筛选不含 HAS_NODE（如只选产业链归属 BELONGS_TO_NODE），
        裁边会把链节点一并裁掉，前端中心只能退化为页面合成的虚拟节点，链的
        溯源信息（源数据表/英文字段名/图空间 VID）随之丢失。骨架节点始终
        保留，其余节点仍在裁掉无连边者之列。

        Args:
            graph: ``_fetch_graph`` 产出的子图。
            relation_types: 规整后的边类型；为空表示不筛选。
            anchor_id: 调用方指定或关键词解析出的锚点 VID；始终保留。

        Returns:
            筛选后的子图；不筛选时原样返回。
        """
        if not relation_types:
            return graph
        wanted = set(relation_types)
        edges = [e for e in (graph.get("edges") or []) if str(e.get("label") or "") in wanted]
        kept_ids = {str(e.get("source") or "") for e in edges} | {
            str(e.get("target") or "") for e in edges
        }
        skeleton_ids = {anchor_id} if anchor_id else set()
        nodes = [
            n
            for n in (graph.get("nodes") or [])
            if str(n.get("id") or "") in kept_ids
            or str(n.get("id") or "") in skeleton_ids
            or "industrychain" in str(n.get("type") or "").casefold()
        ]
        return {"nodes": nodes, "edges": edges}

    @staticmethod
    def _merge_graphs(
        base: dict[str, list[Any]], extra: dict[str, list[Any]]
    ) -> dict[str, list[Any]]:
        """合并两个子图，节点按 id、边按 (source, target, label) 去重（base 优先）。

        Args:
            base: 锚点子图。
            extra: 分层种子扩展出的补充子图。

        Returns:
            合并后的 ``{"nodes": [...], "edges": [...]}``。
        """
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        seen_nodes: set[str] = set()
        seen_edges: set[tuple[str, str, str]] = set()
        for graph in (base, extra):
            for node in graph.get("nodes") or []:
                node_id = str(node.get("id") or "")
                if not node_id or node_id in seen_nodes:
                    continue
                seen_nodes.add(node_id)
                nodes.append(node)
            for edge in graph.get("edges") or []:
                key = (
                    str(edge.get("source") or ""),
                    str(edge.get("target") or ""),
                    str(edge.get("label") or ""),
                )
                if key in seen_edges:
                    continue
                seen_edges.add(key)
                edges.append(edge)
        return {"nodes": nodes, "edges": edges}

    @staticmethod
    def _backfill_empty_layers_from_graph(
        layers: list[dict[str, Any]],
        graph: dict[str, list[Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """用锚点真实子图补齐空分层，避免关键词索引缺失时展示无关抽样。"""
        # 各层接受的实体类型（casefold 后比较）。News 是挂在链上的产业动态
        # （COVERS_CHAIN），作为「产业动态事件」层的回填来源。
        types_by_layer = {
            "core_technology": {"keyword", "industrynode", "technology"},
            "leading_enterprise": {"organization", "company"},
            "leading_expert": {"person", "scholar", "expert"},
            "flagship_achievement": {"event", "news"},
        }
        entity_type_by_layer = {
            "core_technology": "technology",
            "leading_enterprise": "organization",
            "leading_expert": "expert",
            "flagship_achievement": "event",
        }
        output: list[dict[str, Any]] = []
        for original in layers:
            layer = {**original, "items": list(original.get("items") or [])}
            if layer["items"]:
                output.append(layer)
                continue
            layer_key = str(layer.get("key") or "")
            allowed_types = types_by_layer.get(layer_key, set())
            items: list[dict[str, Any]] = []
            seen_ids: set[str] = set()
            seen_labels: set[str] = set()
            layer_limit = (
                min(top_k, 3) if layer_key in {"leading_expert", "flagship_achievement"} else top_k
            )
            for node in graph.get("nodes") or []:
                node_type = str(node.get("type") or "").casefold()
                node_id = str(node.get("id") or "")
                # organization_base 是入图时打到几乎所有节点上的基础标签（论文、
                # 专家、关键词都会带），节点的 type（首个标签）因此常是它而非真实
                # 类型。这里对节点的全部标签做匹配：真企业同时带 Organization 等
                # 企业标签，纯 organization_base（或叠加 Paper/Person 等标签）的
                # 节点不会命中任何分层，避免论文被误当成领军企业。
                raw_labels = node.get("data", {}).get("labels") or node.get("labels") or []
                label_set = {
                    str(label or "").casefold() for label in raw_labels if str(label or "").strip()
                }
                if (
                    (node_type not in allowed_types and not label_set & allowed_types)
                    or not node_id
                    or node_id in seen_ids
                ):
                    continue
                seen_ids.add(node_id)
                node_label = str(node.get("label") or node_id)
                if layer_key == "flagship_achievement" and node_label in seen_labels:
                    continue
                seen_labels.add(node_label)
                items.append(
                    {
                        "id": node_id,
                        "label": node_label,
                        "type": entity_type_by_layer[layer_key],
                        "subtitle": node.get("subtitle"),
                        "metric": None,
                        "metricValue": None,
                        # 查到即记：子图节点已记录的溯源字段随回填透传，点击
                        # 分层连线时溯源三要素不缺（此前回填丢字段，前端
                        # 只能显示「—」）。
                        "sourceTable": node.get("sourceTable"),
                        "sourceField": node.get("sourceField"),
                        "sourceRecordId": node.get("sourceRecordId"),
                        "ingestBatch": node.get("ingestBatch"),
                        "ingestTime": node.get("ingestTime"),
                    }
                )
                if len(items) >= layer_limit:
                    break
            layer["items"] = items
            layer["total"] = len(items)
            output.append(layer)
        return output

    def _rebuild_in_background(
        self,
        cache_key: tuple[str, str, int, int, str],
        *,
        industry: str | None,
        anchor_id: str | None,
        depth: int,
        top_k: int,
        relation_types: list[str] | None = None,
        auth_headers: Mapping[str, str] | None = None,
    ) -> None:
        """缓存过期时后台重建，期间请求继续用旧结果。"""
        if cache_key in _panorama_rebuilding:
            return
        _panorama_rebuilding.add(cache_key)
        _panorama_cache.pop(cache_key, None)

        async def _run() -> None:
            try:
                await self.query(
                    industry=industry,
                    anchor_id=anchor_id,
                    depth=depth,
                    top_k=top_k,
                    relation_types=relation_types,
                    auth_headers=auth_headers,
                )
            except Exception:  # noqa: BLE001 - 后台重建失败保留空位，下次请求再现场组装
                logger.warning("panorama background rebuild failed", exc_info=True)
            finally:
                _panorama_rebuilding.discard(cache_key)

        asyncio.get_running_loop().create_task(_run())

    # ---------------- 各分层数据 ----------------
    async def _fetch_layers(
        self,
        client: GraphAPIClient,
        industry: str | None,
        top_k: int,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """构造四个分层，并收集可用于扩展子图的种子 VID。

        无关键词、无锚点（如重置参数后执行）时同样收集全部四层：此时各层走
        单页 ``list_nodes`` 廉价路径，核心专家/产业动态事件不会因省成本被裁掉。

        Args:
            client: 图查询 API 客户端。
            industry: 产业关键词，非空时做关键词过滤。
            top_k: 每层最多返回多少个实体。

        Returns:
            ``(layers, seed_vids)``：``layers`` 为四层结果，``seed_vids`` 按
            专家 → 机构 → 技术的偏好顺序排列，只包含能按 VID 寻址的节点。
        """
        layers: list[dict[str, Any]] = []
        seed_candidates_by_key: dict[str, list[dict[str, Any]]] = {}
        collected = await asyncio.gather(
            *(
                self._collect_layer_nodes(client, definition, industry, top_k)
                for definition in _LAYER_DEFINITIONS
            )
        )
        for definition, nodes in zip(_LAYER_DEFINITIONS, collected, strict=True):
            layer_limit = (
                min(top_k, 3)
                if definition["key"] in {"leading_expert", "flagship_achievement"}
                else top_k
            )
            picked = nodes[:layer_limit]
            layers.append(
                {
                    "key": definition["key"],
                    "title": definition["title"],
                    "total": len(picked),
                    "items": [self._node_to_key_entity(node, definition) for node in picked],
                }
            )
            seed_candidates_by_key[definition["key"]] = picked

        seed_vids = await self._resolve_seed_vids(client, seed_candidates_by_key)
        return layers, seed_vids

    async def _fetch_industry_chain_labels(self, client: GraphAPIClient) -> list[str]:
        """列出图库中的产业链名称，供摘要「产业链名称」统计展示。

        IndustryChain 数量很少（个位数），单页列举即可；失败按空处理，
        不影响其余分层结果。
        """
        try:
            nodes = await self._list_by_label(client, "IndustryChain", _INDUSTRY_CHAIN_LABEL_LIMIT)
        except GraphAPIError:
            return []
        labels: list[str] = []
        seen: set[str] = set()
        for node in nodes:
            props = node.get("properties") or {}
            label = str(props.get("name") or props.get("chain_name") or "").strip()
            if not label or label in seen:
                continue
            seen.add(label)
            labels.append(label)
        return labels

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
            industry: 产业关键词；非空时先精确搜属性，未命中仅做小范围扫描。
            top_k: 目标条数。

        Returns:
            节点列表。分层展示直接使用命中节点；是否能扩展子图会在后续种子解析阶段
            再判断，避免为每个候选都额外打一轮寻址请求。
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

        属性搜索先做精确等值；未命中时只在少量候选标签上做单页小范围包含匹配，
        避免继续走大范围分页扫描。

        Args:
            client: 图查询 API 客户端。
            label: 节点标签。
            definition: ``_LAYER_DEFINITIONS`` 中的一项。
            industry: 产业关键词。
            top_k: 目标条数。

        Returns:
            命中的节点列表。
        """
        found: list[dict[str, Any]] = []
        # 各候选属性的精确搜索并发执行（每个都是图服务侧的全标签扫描）。
        search_results = await asyncio.gather(
            *(
                self._safe_search_nodes(client, label, prop, industry, top_k)
                for prop in definition["keyword_props"]
            )
        )
        for payload in search_results:
            found.extend((payload or {}).get("items", []))
            if len(found) >= top_k:
                return found[:top_k]
        if found:
            return found

        if label not in _COMPACT_SCAN_LABELS and label != "Person":
            return []
        scan_limit = _EXPERT_SCAN_LIMIT if label == "Person" else _COMPACT_KEYWORD_SCAN_LIMIT
        scan_pages = _INDUSTRY_EXPERT_SCAN_PAGES.get(industry, 1) if label == "Person" else 1
        pages = await asyncio.gather(
            *(
                self._list_by_label_throttled(client, label, scan_limit, page_index * scan_limit)
                for page_index in range(scan_pages)
            )
        )
        page = [node for nodes in pages for node in nodes]
        terms = (
            _INDUSTRY_EXPERT_TERMS.get(industry, (industry,)) if label == "Person" else (industry,)
        )
        folded_terms = tuple(term.casefold() for term in terms)
        scored_matches: list[tuple[int, dict[str, Any]]] = []
        seen_ids: set[str] = set()
        for node in page:
            node_id = str(node.get("id") or "")
            if node_id and node_id in seen_ids:
                continue
            if node_id:
                seen_ids.add(node_id)
            props = node.get("properties") or {}
            score = 0
            for prop in definition["keyword_props"]:
                value = str(props.get(prop) or "").casefold()
                if not value:
                    continue
                weight = 3 if prop == "research_fields" else 1
                score += weight * sum(term in value for term in folded_terms)
            if score:
                scored_matches.append((score, node))
        scored_matches.sort(key=lambda item: item[0], reverse=True)
        return [node for _score, node in scored_matches[:top_k]]

    @staticmethod
    async def _safe_search_nodes(
        client: GraphAPIClient,
        label: str,
        prop: str,
        industry: str,
        top_k: int,
    ) -> dict[str, Any]:
        """属性精确搜索，图服务报错时按未命中处理。"""
        async with _graph_api_semaphore:
            try:
                return await client.search_nodes(
                    label=label, properties={prop: industry}, limit=top_k
                )
            except GraphAPIError:
                return {}

    async def _list_by_label_throttled(
        self,
        client: GraphAPIClient,
        label: str,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        """带并发限流的分页取节点。"""
        async with _graph_api_semaphore:
            return await self._list_by_label(client, label, limit, offset)

    async def _list_by_label(
        self,
        client: GraphAPIClient,
        label: str,
        limit: int,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """按标签分页取节点。图服务偶发抖动时空页重试一次，仍失败按空处理。"""
        for _attempt in range(2):
            try:
                listing = await client.list_nodes(label=label, limit=limit, offset=offset)
                return [{**item, "_addressable": True} for item in (listing or {}).get("items", [])]
            except GraphAPIError:
                if _attempt == 1:
                    return []
                await asyncio.sleep(0.3)

    async def _resolve_seed_vids(
        self,
        client: GraphAPIClient,
        candidates_by_key: dict[str, list[dict[str, Any]]],
    ) -> list[str]:
        """只为可能用于扩图的少量候选解析可寻址 VID。"""
        ordered: list[dict[str, Any]] = []
        seen_raw_ids: set[str] = set()
        preferred_keys = ("leading_expert", "leading_enterprise", "core_technology")
        for key in preferred_keys:
            for node in candidates_by_key.get(key, []):
                raw_id = str(node.get("id") or "")
                if raw_id and raw_id not in seen_raw_ids:
                    seen_raw_ids.add(raw_id)
                    ordered.append(node)
        for key, nodes in candidates_by_key.items():
            if key in preferred_keys:
                continue
            for node in nodes:
                raw_id = str(node.get("id") or "")
                if raw_id and raw_id not in seen_raw_ids:
                    seen_raw_ids.add(raw_id)
                    ordered.append(node)

        if not ordered:
            return []

        async def _resolve(node: dict[str, Any]) -> str | None:
            try:
                resolved = await client.resolve_addressable_node(
                    node,
                    vid_candidates=self._node_vid_candidates(node),
                )
            except GraphAPIError:
                return None
            return str(resolved.get("id") or "") if resolved else None

        seed_vids: list[str] = []
        seen_seed_ids: set[str] = set()
        max_seed_count = _MAX_SUBGRAPH_SEEDS + 1
        batch_size = max_seed_count
        for start in range(0, len(ordered), batch_size):
            batch = ordered[start : start + batch_size]
            resolved_ids = await asyncio.gather(*[_resolve(node) for node in batch])
            for resolved_id in resolved_ids:
                if not resolved_id or resolved_id in seen_seed_ids:
                    continue
                seen_seed_ids.add(resolved_id)
                seed_vids.append(resolved_id)
                if len(seed_vids) >= max_seed_count:
                    return seed_vids
        return seed_vids

    @staticmethod
    def _node_vid_candidates(node: dict[str, Any]) -> list[str]:
        """基于常见主键字段补一组候选 VID，提升属性搜索结果的可寻址率。"""
        props = node.get("properties") or {}
        candidates: list[str] = []
        for value in (
            node.get("id"),
            props.get("vid"),
            props.get("id"),
            props.get("source_record_id"),
            props.get("scholar_id"),
            props.get("org_id"),
            props.get("keyword_id"),
            props.get("paper_id"),
            props.get("patent_id"),
            props.get("project_id"),
        ):
            text = str(value or "").strip()
            if text and text not in candidates:
                candidates.append(text)
        scholar_id = str(props.get("scholar_id") or "").strip()
        if scholar_id:
            person_vid = f"person_{scholar_id}"
            if person_vid not in candidates:
                candidates.append(person_vid)
        return candidates

    async def _fetch_graph(
        self,
        client: GraphAPIClient,
        seed_vids: list[str],
        anchor_id: str | None,
        depth: int,
        relation_types: list[str] | None = None,
    ) -> dict[str, list[Any]]:
        """以锚点或分层种子为中心扩展子图。

        锚点是产业链时，链上 News（COVERS_CHAIN 常有数十条）会先把统一 limit
        占满，HAS_NODE 环节与 BELONGS_TO_NODE 企业边全被挤掉，图里只剩新闻，
        重点企业分层与关系置信度随之缺失。因此有锚点时补两路结构子图：
        HAS_NODE 一跳带出链下环节（环节名常不含产业关键词，分层搜索会 miss），
        再对前几个叶子环节各取 BELONGS_TO_NODE 一跳，把企业和 chain_score
        置信度带进图。用户筛选了单一关系类型时严格按筛选返回，不做额外扩展。

        Args:
            client: 图查询 API 客户端。
            seed_vids: 备选种子 VID，按偏好排序。
            anchor_id: 调用方指定的锚点 VID，优先使用。
            depth: 扩展跳数。
            relation_types: 规整后的边类型筛选；为空表示不筛选。

        Returns:
            ``{"nodes": [...], "edges": [...]}``；没有可用种子或查询失败时为空图。
        """
        seed = anchor_id or (seed_vids[0] if seed_vids else None)
        if not seed:
            return {"nodes": [], "edges": []}
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        seen_nodes: set[str] = set()
        seen_edges: set[tuple[str, str, str]] = set()

        # 多 seed 子图互相独立，并行拉取（套 semaphore 防压垮 trs-graph）；
        # 单 seed 失败 except GraphAPIError → None 跳过，合并后统一去重，结果不变。
        async def _fetch_one(
            seed_vid: str,
            edge_type: str | None = None,
            *,
            fetch_depth: int | None = None,
            limit: int = 60,
        ) -> dict[str, Any] | None:
            async with _graph_api_semaphore:
                try:
                    return await client.get_subgraph(
                        seed_vid,
                        depth=fetch_depth if fetch_depth is not None else depth,
                        limit=limit,
                        edge_type=edge_type,
                    )
                except GraphAPIError:
                    return None

        pushed_edge_types = (
            relation_types if relation_types and len(relation_types) == 1 else [None]
        )
        if anchor_id:
            jobs: list[tuple[str, str | None, int]] = [
                (anchor_id, edge_type, 60) for edge_type in pushed_edge_types
            ]
            if "HAS_NODE" not in pushed_edge_types:
                jobs.append((anchor_id, "HAS_NODE", _ANCHOR_CHAIN_NODE_LIMIT))
        else:
            jobs = [
                (vid, edge_type, 60)
                for vid in seed_vids[:_MAX_SUBGRAPH_SEEDS]
                for edge_type in pushed_edge_types
            ]
        subgraphs = list(
            await asyncio.gather(
                *(_fetch_one(vid, edge_type, limit=limit) for vid, edge_type, limit in jobs)
            )
        )

        if anchor_id and pushed_edge_types == [None]:
            # 企业边几乎只挂叶子环节；从 HAS_NODE 子图挑叶子环节探 BELONGS_TO_NODE。
            has_node_subgraph = next(
                (
                    subgraph
                    for (_, edge_type, _), subgraph in zip(jobs, subgraphs, strict=True)
                    if edge_type == "HAS_NODE"
                ),
                None,
            )
            probe_vids = self._select_org_probe_vids(has_node_subgraph)
            subgraphs.extend(
                await asyncio.gather(
                    *(_fetch_one(vid, "BELONGS_TO_NODE", fetch_depth=1) for vid in probe_vids)
                )
            )

        for subgraph in subgraphs:
            if not subgraph:
                continue
            for n in subgraph.get("nodes", []):
                node = self._node_to_graph_node(n)
                if node["id"] and node["id"] not in seen_nodes:
                    seen_nodes.add(node["id"])
                    nodes.append(node)
            for e in subgraph.get("edges", []):
                edge = self._edge_to_graph_edge(e)
                key = (edge["source"], edge["target"], edge["label"])
                if key not in seen_edges:
                    seen_edges.add(key)
                    edges.append(edge)
        return {"nodes": nodes, "edges": edges}

    @staticmethod
    def _select_org_probe_vids(has_node_subgraph: dict[str, Any] | None) -> list[str]:
        """从 HAS_NODE 子图里挑最可能挂企业的环节做企业边探测。

        企业边（BELONGS_TO_NODE）几乎只挂在叶子/产品环节（node_type=2）上，
        分类环节（node_type=1）基本没有；重点环节（node_imp_level=1，源数据
        标注的核心方向）挂的企业最多，优先探测。节点缺这些属性时退化为按
        原顺序取。
        """
        if not has_node_subgraph:
            return []
        key_leaf_vids: list[str] = []
        leaf_vids: list[str] = []
        fallback_vids: list[str] = []
        for node in has_node_subgraph.get("nodes", []):
            vid = str(node.get("id") or "").strip()
            if not vid or "IndustryNode" not in (node.get("labels") or []):
                continue
            props = node.get("properties") or {}
            fallback_vids.append(vid)
            if str(props.get("node_type") or "") != "2":
                continue
            leaf_vids.append(vid)
            if str(props.get("node_imp_level") or "") == "1":
                key_leaf_vids.append(vid)
        return (key_leaf_vids + [v for v in leaf_vids if v not in key_leaf_vids] or fallback_vids)[
            :_ANCHOR_ORG_PROBE_COUNT
        ]

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
        # 查到即记：入图血缘透传；无血缘时记录图库查询来源（保证非空）。
        recorded = record_node_source(props, node.get("labels") or [], space=self._graph_space())
        return {
            "id": str(node.get("id") or ""),
            "label": label,
            "type": definition["type"],
            "subtitle": subtitle_prop,
            "metric": definition["metric_label"] if metric_value_num is not None else None,
            "metricValue": metric_value_num,
            "sourceSystem": self._first_prop_value(props, ("source_system", "source")),
            "sourceTable": recorded["sourceTable"],
            "sourceField": recorded["sourceField"],
            "sourceRecordId": self._first_prop_value(props, ("source_record_id",)),
            "ingestBatch": self._first_prop_value(props, ("ingest_batch",)),
            "ingestTime": self._first_prop_value(props, ("ingest_time",)),
        }

    def _build_provenance(
        self,
        summary: dict[str, Any],
        layers: list[dict[str, Any]],
        graph: dict[str, list[Any]],
        source: dict[str, Any],
    ) -> dict[str, Any]:
        """组装实体/关系溯源信息，字段结构与校友关系模块保持一致。

        Args:
            summary: 本次查询命中的实体/关系统计。
            layers: 四个分层结果。
            graph: 已组装的子图。
            source: 数据来源标记，含 ``fallback`` 与降级 ``reason``。

        Returns:
            ``{sourceDatabase, summary, evidences[]}``；降级时如实说明数据来自内置样例。
        """
        fallback = bool(source.get("fallback"))
        space = TRSGraphSettings.from_env().space or "dev"
        source_database = f"trs-graph / space={space}"
        if fallback or source.get("reason"):
            reason = str(source.get("reason") or "unknown")
            head = f"图库未命中（{_FALLBACK_REASON_TEXT.get(reason, reason)}），无可用实体。"
        elif not any(layer.get("items") for layer in layers):
            head = "图库未命中任何实体。"
        else:
            head = "分层实体与子图均来自图查询 API。"

        nodes = graph.get("nodes") or []
        edges = graph.get("edges") or []
        provenance_summary = (
            f"{head}本次命中 {summary.get('totalNodes') or 0} 个实体 / "
            f"{summary.get('totalEdges') or 0} 条关系；本次子图 {len(nodes)} 节点 / {len(edges)} 关系。"
        )

        evidences: list[dict[str, Any]] = []
        label_by_key = {
            str(definition["key"]): "/".join(definition["labels"])
            for definition in _LAYER_DEFINITIONS
        }
        for layer in layers:
            items = layer.get("items") or []
            if not items:
                continue
            # 覆盖分层全部 items（每层数量已被 topK 封顶），保证前端
            # 点击任意分层节点都能按 graphVid 筛中证据；查到即记——
            # 无入图血缘的 item 也如实记录图库查询来源。
            for item in items:
                source_table = str(item.get("sourceTable") or "")
                if source_table.startswith("trs-graph / space="):
                    item_note = "节点未携带入图血缘，来源为本次图库查询"
                else:
                    item_note = (
                        f"入库批次：{item.get('ingestBatch') or '—'}；"
                        f"入库时间：{item.get('ingestTime') or '—'}"
                    )
                evidences.append(
                    {
                        "title": f"{layer.get('title') or layer.get('key')} · {item.get('label')}",
                        "businessTable": "科技要素数据库",
                        "technicalTable": f"{item.get('sourceSystem') or '—'}.dwd_*",
                        "recordId": str(item.get("sourceRecordId") or ""),
                        "fieldIdentifier": str(item.get("id") or ""),
                        # 溯源三要素：MySQL 源表名 / MySQL 英文字段名 / 图空间 VID
                        "sourceTable": source_table or "—",
                        "sourceField": str(item.get("sourceField") or "—"),
                        "graphVid": str(item.get("id") or ""),
                        "summary": item_note,
                    }
                )
            labels = [str(item.get("label") or item.get("id") or "") for item in items]
            evidences.append(
                {
                    "title": f"分层 · {layer.get('title') or layer.get('key')}",
                    "businessTable": "产业链全景图分层" if not fallback else "接口示例分层",
                    "technicalTable": label_by_key.get(str(layer.get("key")), "—"),
                    "recordId": str(items[0].get("id") or ""),
                    "fieldIdentifier": str(items[0].get("metric") or "name_zh/title"),
                    "sourceTable": str(items[0].get("sourceTable") or "—"),
                    "sourceField": str(items[0].get("sourceField") or "—"),
                    "graphVid": str(items[0].get("id") or ""),
                    "summary": (
                        f"命中 {layer.get('total') or len(items)} 个实体，"
                        f"展示 {len(items)} 个：{'、'.join(labels) or '—'}"
                    ),
                }
            )

        edge_types: dict[str, int] = {}
        for edge in edges:
            key = str((edge or {}).get("label") or "UNKNOWN")
            edge_types[key] = edge_types.get(key, 0) + 1
        if edge_types:
            top_types = sorted(edge_types.items(), key=lambda kv: kv[1], reverse=True)[:6]
            evidences.append(
                {
                    "title": "子图关系构成",
                    "businessTable": "产业链关联关系" if not fallback else "内置样例关系",
                    "technicalTable": "graph-search/subgraph",
                    "recordId": str((nodes[0] or {}).get("id") or "") if nodes else "",
                    "fieldIdentifier": "edge.type",
                    "sourceTable": "graph-search/subgraph",
                    "sourceField": "edge.type",
                    "graphVid": str((nodes[0] or {}).get("id") or "") if nodes else "—",
                    "summary": "；".join(f"{name} × {count}" for name, count in top_types),
                }
            )

        return {
            "sourceDatabase": source_database,
            "summary": provenance_summary,
            "evidences": evidences,
        }

    @staticmethod
    def _graph_space() -> str:
        return TRSGraphSettings.from_env().space or "dev"

    def _node_to_graph_node(self, node: dict[str, Any]) -> dict[str, Any]:
        props = node.get("properties") or {}
        labels = node.get("labels") or []
        primary_label = labels[0] if labels else "Node"
        # 查到即记：子图（展开层）节点的溯源字段。带血缘透传；无血缘时
        # 记录图库查询来源标记，保证前端点击任意展开层节点都能合成溯源卡。
        recorded = record_node_source(props, labels, space=self._graph_space())
        return {
            "id": str(node.get("id") or ""),
            "type": primary_label,
            "label": self._first_prop_value(
                props,
                (
                    "chain_name",
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
            "sourceTable": recorded["sourceTable"],
            "sourceField": recorded["sourceField"],
            "sourceRecordId": self._first_prop_value(props, ("source_record_id",)),
            "ingestBatch": self._first_prop_value(props, ("ingest_batch",)),
            "ingestTime": self._first_prop_value(props, ("ingest_time",)),
            "data": {"labels": labels},
        }

    def _edge_to_graph_edge(self, edge: dict[str, Any]) -> dict[str, Any]:
        props = edge.get("properties") or {}
        # 不同边类型的置信度字段名/量纲不同：chain_score 是 0-100 的产业链匹配分，
        # confidence 已经是 0-1；统一换算成 0-1，避免前端拿不到值只能显示"暂无"。
        confidence: float | None = None
        if isinstance(props.get("confidence"), (int, float)):
            confidence = min(1.0, max(0.0, float(props["confidence"])))
        elif isinstance(props.get("chain_score"), (int, float)):
            confidence = min(1.0, max(0.0, float(props["chain_score"]) / 100))
        return {
            "source": str(edge.get("source") or ""),
            "target": str(edge.get("target") or ""),
            "label": str(edge.get("type") or ""),
            "confidence": confidence,
            "data": props,
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

    def _build_summary(
        self,
        industry: str | None,
        layers: list[dict[str, Any]],
        graph: dict[str, list[Any]],
        industry_chains: list[str] | None = None,
    ) -> dict[str, Any]:
        """汇总本次查询命中的实体和关系，不做全库扫描。"""
        nodes_by_label = {
            str(layer.get("title") or layer.get("key")): len(layer.get("items") or [])
            for layer in layers
        }
        edges_by_type: dict[str, int] = {}
        for edge in graph.get("edges") or []:
            edge_type = str((edge or {}).get("label") or "UNKNOWN")
            edges_by_type[edge_type] = edges_by_type.get(edge_type, 0) + 1
        return {
            "industry": industry,
            "industryChains": list(industry_chains or []),
            "totalNodes": sum(nodes_by_label.values()),
            "totalEdges": sum(edges_by_type.values()),
            "nodesByLabel": nodes_by_label,
            "edgesByType": edges_by_type,
        }
