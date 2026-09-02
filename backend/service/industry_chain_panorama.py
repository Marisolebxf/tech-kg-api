"""科技产业链全景图——通过 FastAPI 图查询 API 组合实现。

## 输出结构

1. ``summary``：本次查询结果规模（命中的分层实体数、返回子图里的关系数）。
2. ``layers``：四个分层（核心技术、领军企业、领军专家、代表成果），每层按检索
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
from typing import Any

from infra.graph_api_client import GraphAPIClient, GraphAPIError, graph_api
from infra.graph_db.config import TRSGraphSettings
from service.base_module import KGModuleScaffoldService

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
# 子图合并时最多取多少个种子节点。
_MAX_SUBGRAPH_SEEDS = 5
# 图服务（trs-graph）承受不住太高并发，全标签扫描类请求并发过多会 500，
# 用信号量把同时打到图服务的请求数压住。
_GRAPH_API_CONCURRENCY = 6
_graph_api_semaphore = asyncio.Semaphore(_GRAPH_API_CONCURRENCY)
# 全景图结果缓存：图数据按批次入库、变更频率低，实时组装一次要数秒，
# 同参数查询直接复用上次结果，过期后台刷新。
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
        "title": "代表成果",
        "labels": ["Paper", "Patent", "Project"],
        "name_props": ("title_zh", "title_en", "title", "title_original"),
        "metric_prop": "citation_nums",
        "metric_label": "被引次数",
        "type": "achievement",
        "keyword_props": ("title_zh", "title_en", "keywords"),
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
        fallback_reason: str | None = None

        try:
            async with graph_api() as client:
                resolved_anchor, layer_payload = await asyncio.gather(
                    self._resolve_anchor_from_keyword(client, industry_kw, anchor),
                    self._fetch_layers(client, industry_kw, top_k, anchor is None),
                )
                layers, seed_vids = layer_payload
                anchor = resolved_anchor
                if industry_kw and not anchor and not any(layer["items"] for layer in layers):
                    layers, seed_vids = await self._fetch_layers(client, None, top_k, True)
                    fallback_reason = "keyword_fallback_overview"
                graph = await self._fetch_graph(
                    client,
                    seed_vids,
                    anchor,
                    depth,
                    relation_types=rel_types,
                )
                graph = self._filter_graph_by_relation_types(graph, rel_types)
                query_input["anchorId"] = anchor or ""
        except GraphAPIError as exc:
            logger.warning("graph API unavailable for panorama, falling back: %s", exc)
            fallback_reason = "graph_api_error"
        except Exception:  # noqa: BLE001
            logger.exception("unexpected error while building panorama via graph API")
            fallback_reason = "unexpected_error"

        has_real_layers = any(layer["items"] for layer in layers)
        if not has_real_layers:
            # 关键词没命中时如实返回空分层并标明原因，不再塞内置示例数据，
            # 避免用户把假数据当成真实查询结果。
            if fallback_reason is None:
                fallback_reason = "keyword_no_match" if industry_kw else "empty_result"
            logger.info(
                "industry chain panorama empty result: reason=%s, industry=%s",
                fallback_reason,
                industry_kw,
            )
        summary = self._build_summary(industry_kw, layers, graph)

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
    def _select_layer_definitions(compact_without_anchor: bool) -> list[dict[str, Any]]:
        if not compact_without_anchor:
            return list(_LAYER_DEFINITIONS)
        allowed_keys = {"core_technology", "leading_enterprise"}
        return [
            definition for definition in _LAYER_DEFINITIONS if definition["key"] in allowed_keys
        ]

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
        graph: dict[str, list[Any]], relation_types: list[str]
    ) -> dict[str, list[Any]]:
        """按边类型筛选子图，并丢掉筛选后不再有连边的节点。

        Args:
            graph: ``_fetch_graph`` 产出的子图。
            relation_types: 规整后的边类型；为空表示不筛选。

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
        nodes = [n for n in (graph.get("nodes") or []) if str(n.get("id") or "") in kept_ids]
        return {"nodes": nodes, "edges": edges}

    def _rebuild_in_background(
        self,
        cache_key: tuple[str, str, int, int, str],
        *,
        industry: str | None,
        anchor_id: str | None,
        depth: int,
        top_k: int,
        relation_types: list[str] | None = None,
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
        compact_without_anchor: bool,
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
        seed_candidates_by_key: dict[str, list[dict[str, Any]]] = {}
        selected_definitions = self._select_layer_definitions(compact_without_anchor)
        # 无显式 anchorId 时只保留技术/产业节点 + 企业两层，减少全景发现成本。
        collected = await asyncio.gather(
            *(
                self._collect_layer_nodes(client, definition, industry, top_k)
                for definition in selected_definitions
            )
        )
        for definition, nodes in zip(selected_definitions, collected, strict=True):
            picked = nodes[:top_k]
            layers.append(
                {
                    "key": definition["key"],
                    "title": definition["title"],
                    "total": len(nodes),
                    "items": [self._node_to_key_entity(node, definition) for node in picked],
                }
            )
            seed_candidates_by_key[definition["key"]] = picked

        seed_vids = await self._resolve_seed_vids(client, seed_candidates_by_key)
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

        if label not in _COMPACT_SCAN_LABELS:
            return []
        page = await self._list_by_label_throttled(client, label, _COMPACT_KEYWORD_SCAN_LIMIT, 0)
        needle = industry.casefold()
        compact_matches: list[dict[str, Any]] = []
        for node in page:
            props = node.get("properties") or {}
            for prop in definition["keyword_props"]:
                value = str(props.get(prop) or "")
                if value and needle in value.casefold():
                    compact_matches.append(node)
                    break
            if len(compact_matches) >= top_k:
                break
        return compact_matches

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
        # 以锚点为中心；未指定锚点时对前几个种子各扩一跳子图再合并，
        # 只用一个种子时图里往往只有两三个节点。
        seeds = [seed] if anchor_id else [s for s in seed_vids if s != seed][:_MAX_SUBGRAPH_SEEDS]
        if not seeds:
            seeds = [seed]
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        seen_nodes: set[str] = set()
        seen_edges: set[tuple[str, str, str]] = set()

        # 多 seed 子图互相独立，并行拉取（套 semaphore 防压垮 trs-graph）；
        # 单 seed 失败 except GraphAPIError → None 跳过，合并后统一去重，结果不变。
        async def _fetch_one(seed_vid: str, edge_type: str | None = None) -> dict[str, Any] | None:
            async with _graph_api_semaphore:
                try:
                    return await client.get_subgraph(
                        seed_vid,
                        depth=depth,
                        limit=60,
                        edge_type=edge_type,
                    )
                except GraphAPIError:
                    return None

        pushed_edge_types = (
            relation_types if relation_types and len(relation_types) == 1 else [None]
        )
        subgraphs = await asyncio.gather(
            *[
                _fetch_one(seed_vid, edge_type)
                for seed_vid in seeds
                for edge_type in pushed_edge_types
            ]
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
            "sourceSystem": self._first_prop_value(props, ("source_system", "source")),
            "sourceTable": self._first_prop_value(props, ("source_table",)),
            "sourceField": self._first_prop_key(props, definition["name_props"]),
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
            for item in items[:5]:
                if not item.get("sourceRecordId"):
                    continue
                evidences.append(
                    {
                        "title": f"{layer.get('title') or layer.get('key')} · {item.get('label')}",
                        "businessTable": "科技要素数据库",
                        "technicalTable": f"{item.get('sourceSystem') or '—'}.dwd_*",
                        "recordId": str(item.get("sourceRecordId") or ""),
                        "fieldIdentifier": str(item.get("id") or ""),
                        # 溯源三要素：MySQL 源表名 / MySQL 英文字段名 / 图空间 VID
                        "sourceTable": str(item.get("sourceTable") or "—"),
                        "sourceField": str(item.get("sourceField") or "—"),
                        "graphVid": str(item.get("id") or ""),
                        "summary": (
                            f"入库批次：{item.get('ingestBatch') or '—'}；"
                            f"入库时间：{item.get('ingestTime') or '—'}"
                        ),
                    }
                )
            labels = [str(item.get("label") or item.get("id") or "") for item in items[:5]]
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

    @staticmethod
    def _first_prop_key(props: dict[str, Any], keys: tuple[str, ...]) -> str | None:
        """返回第一个有非空值的候选属性名，用于溯源展示「英文字段名」。"""
        for key in keys:
            if props.get(key):
                return key
        return None

    def _build_summary(
        self,
        industry: str | None,
        layers: list[dict[str, Any]],
        graph: dict[str, list[Any]],
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
            "totalNodes": sum(nodes_by_label.values()),
            "totalEdges": sum(edges_by_type.values()),
            "nodesByLabel": nodes_by_label,
            "edgesByType": edges_by_type,
        }
