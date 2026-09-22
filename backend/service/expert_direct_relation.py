"""科技专家/人才直接关系——通过 FastAPI 图查询 API 实现（MySQL 仅作代表成果回退）。

数据流：
1. ``expertAId`` 必填。按 VID / scholar_id / 姓名定位专家A；查不到 → 空结果。
2. 若 ``expertBId`` 为空：返回专家A的全部直接关系（按共同论文数降序取 ``limit`` 条）；
   一条关系都没有时退回仅返回 A 节点（``source.reason="no_relation_for_a"``）。
3. 若 ``expertBId`` 非空：定位专家B；查不到 → 空结果。在 A、B 之间找一条
   ``COAUTHOR_WITH`` 边；找不到 → 空结果。找到则据此组装唯一一条关系。
4. 机构过滤 & 时间过滤：在服务层按 ``institution`` 关键字、``relation_time`` 过滤该条关系。
5. 图数据/详情：按业务格式组装 items + graph + provenance。
6. 代表成果：优先图上 AUTHORED_BY 共同论文；真实专家常无 AUTHORED_BY 边
   （跨域兜底 ETL 默认关闭），此时回退 MySQL 两级：先 ``dwd_scholar_paper_relation``
   自连接（标题按 paper_id / related_paper_id 两个号段从 ``dwd_scholar_papers`` /
   ``dwd_zh_paper`` / ``dwd_en_paper`` 核实）；仍无标题时按姓名反查
   ``dwd_scholar_papers.authors``（真实行 id 未灌、只能按姓名关联）——单对查询
   用双方姓名联查 SQL，列表模式（仅指定 A）按锚点姓名一次扫描建论文池（进程内
   缓存），逐行在内存按对端姓名过滤，避免每行一次全表扫描。两级均仅保留
   查得到标题的行。

查询结果一律来自图库；未命中或图服务异常时返回空结果并在 ``source.reason`` 标明原因，
不返回内置示例数据。
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import re
import threading
import time
from collections.abc import Mapping
from typing import Any

from sqlalchemy import text

from infra.graph_api_client import GraphAPIError, graph_api
from infra.graph_db.config import TRSGraphSettings
from infra.mysql import session_scope
from service.base_module import KGModuleScaffoldService
from service.confidence_scoring import edge_confidence
from service.provenance_recorder import record_node_source

# 60s 进程内结果缓存：同参数请求复用，避免高并发打爆 graph-search/trs-graph。
_RESULT_CACHE_TTL = float(os.getenv("RESULT_CACHE_TTL", "60"))
_result_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_result_cache_lock = threading.Lock()

# 锚点论文池的进程内缓存：列表模式一次 dwd_scholar_papers 全表扫描（约 2.5s）
# 的结果供 TTL 内各查询复用，避免换过滤条件就重扫。
_PAPER_POOL_CACHE_TTL = 300.0
_PAPER_POOL_CACHE_MAX = 16
_PAPER_POOL_LIMIT = 2000
_paper_pool_cache: dict[tuple[str, ...], tuple[float, list[dict[str, Any]]]] = {}
_paper_pool_cache_lock = threading.Lock()


def clear_caches() -> None:
    """清空进程内缓存（测试隔离用）。"""
    _result_cache.clear()
    with _paper_pool_cache_lock:
        _paper_pool_cache.clear()


logger = logging.getLogger(__name__)

MAX_QUERY_LIMIT = 100
_MAX_ANCHOR_CANDIDATES = 5
_MAX_EDGES_PER_EXPERT = 100

# 溯源展示的 MySQL 源表名与英文字段名（图空间 VID 逐条取自节点/边）
_SCHOLAR_SOURCE_TABLE = "dwd_scholar"
_SCHOLAR_SOURCE_FIELD = "scholar_id"
_COAUTHOR_SOURCE_TABLE = "dwd_scholar_coauthor"
_COAUTHOR_SOURCE_FIELD = "co_paper_count"

_FALLBACK_REASON_TEXT = {
    "empty_result": "图库中查不到该专家的合作关系",
    "graph_api_error": "图查询服务不可用",
    "unexpected_error": "图查询过程异常",
    "anchor_a_not_found": "图库中查不到专家A",
    "anchor_b_not_found": "图库中查不到专家B",
    "no_relation_between_a_b": "两位专家之间在图库中不存在直接合作关系",
    "institution_filtered": "该关系不匹配所给机构关键词",
    "anchor_a_only": "已定位到专家A，未指定专家B，仅返回专家A节点",
    "no_relation_for_a": "图库中该专家没有任何直接合作关系",
}

# 补对端节点详情时的并发上限，避免 limit=100 时瞬间打满 trs-graph。
_PEER_FETCH_CONCURRENCY = 5


class ExpertDirectRelationService(KGModuleScaffoldService):
    module_code = "expert_direct_relation"

    async def query(
        self,
        *,
        data_source: str = "all",
        expert_a_id: str | None = None,
        expert_b_id: str | None = None,
        institution: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 10,
        auth_headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        _ = data_source
        normalized_limit = max(1, min(int(limit or 10), MAX_QUERY_LIMIT))
        a_keyword = (expert_a_id or "").strip()
        b_keyword = (expert_b_id or "").strip()
        cache_key = (
            f"all|{a_keyword}|{b_keyword}|{(institution or '').strip()}|"
            f"{(start_time or '').strip()}|{(end_time or '').strip()}|{normalized_limit}"
        )
        with _result_cache_lock:
            entry = _result_cache.get(cache_key)
        if entry and entry[0] > time.monotonic():
            return entry[1]

        query_input = {
            "dataSource": "all",
            "expertAId": a_keyword,
            "expertBId": b_keyword,
            "institution": (institution or "").strip(),
            "startTime": (start_time or "").strip(),
            "endTime": (end_time or "").strip(),
            "limit": normalized_limit,
        }

        source: dict[str, Any] = {"requested": "all", "actual": "graph-api", "fallback": False}
        rows: list[dict[str, Any]] = []
        anchor_only_node: dict[str, Any] | None = None
        fallback_reason: str | None = None

        try:
            async with graph_api(auth_headers=auth_headers) as client:
                node_a = await self._find_person(client, a_keyword)
                if node_a is None:
                    fallback_reason = "anchor_a_not_found"
                elif not b_keyword:
                    # 仅指定专家A：返回该专家的全部直接关系（按共同论文数降序取 limit 条）。
                    collected = await self._collect_relations(
                        client, node_a, limit=normalized_limit
                    )
                    if institution:
                        collected = [
                            row for row in collected if self._matches_institution(row, institution)
                        ]
                        if not collected:
                            fallback_reason = "institution_filtered"
                    if collected:
                        rows = collected
                    elif fallback_reason is None:
                        # A 命中但一条直接关系都没有：仍然把 A 节点画出来，别给一张空图。
                        anchor_only_node = node_a
                        source = {
                            "requested": "all",
                            "actual": "graph-api",
                            "fallback": False,
                            "reason": "no_relation_for_a",
                        }
                else:
                    node_b = await self._find_person(client, b_keyword)
                    if node_b is None:
                        fallback_reason = "anchor_b_not_found"
                    else:
                        edge = await self._find_coauthor_edge(client, node_a, node_b)
                        if edge is None:
                            fallback_reason = "no_relation_between_a_b"
                        else:
                            row = self._build_row(node_a, node_b, edge)
                            if institution and not self._matches_institution(row, institution):
                                fallback_reason = "institution_filtered"
                            else:
                                rows = [row]
                if rows:
                    await self._attach_representative_achievements(client, rows, anchor_node=node_a)
        except GraphAPIError as exc:
            logger.warning("graph API unavailable: %s", exc)
            fallback_reason = "graph_api_error"
        except TimeoutError:
            # graph_api 总预算耗尽：与 GraphAPIError 同口径如实降级为图服务
            # 故障，不落进 unexpected_error 误导排障。
            logger.warning("graph API timeout while querying expert direct relations")
            fallback_reason = "graph_api_error"
        except Exception:  # noqa: BLE001 - 图服务异常一律降级
            logger.exception("unexpected error while querying graph API")
            fallback_reason = "unexpected_error"

        if fallback_reason is not None:
            source = {
                "requested": "all",
                "actual": "graph-api",
                "fallback": False,
                "reason": fallback_reason,
            }

        if anchor_only_node is not None:
            # A-only 分支：items 为空、graph 仅含 A 节点；属于正常分支，可以缓存。
            payload = {
                "taskName": "科技专家直接关系查询",
                "input": query_input,
                "total": 0,
                "items": [],
                "graph": self._build_anchor_only_graph(anchor_only_node),
                "source": source,
                "provenance": self._build_anchor_only_provenance(anchor_only_node),
                "apiResultExample": {
                    "url": "/api/v1/kg-construction/expert-direct-relations/query",
                    "method": "POST",
                    "query": query_input,
                },
            }
            with _result_cache_lock:
                _result_cache[cache_key] = (time.monotonic() + _RESULT_CACHE_TTL, payload)
            return payload

        rows = self._orient_rows(
            rows=self._filter_rows_by_time(rows, start_time, end_time),
            expert_a_id=a_keyword,
            expert_b_id=b_keyword,
        )
        items = [self._build_item(row) for row in rows]
        graph = self._build_graph(items)

        if not items and fallback_reason is None:
            # 图服务正常但未命中（理论上 A+B 命中边走不到这里，留作兜底语义）。
            fallback_reason = "empty_result"
            source = {
                "requested": "all",
                "actual": "graph-api",
                "fallback": False,
                "reason": fallback_reason,
            }

        logger.info(
            "expert direct relation result: reason=%s, a=%s, b=%s, items=%d",
            fallback_reason or "ok",
            a_keyword,
            b_keyword,
            len(items),
        )

        payload = {
            "taskName": "科技专家直接关系查询",
            "input": query_input,
            "total": len(items),
            "items": items,
            "graph": graph,
            "source": source,
            "provenance": self._build_provenance(rows, source),
            "apiResultExample": {
                "url": "/api/v1/kg-construction/expert-direct-relations/query",
                "method": "POST",
                "query": query_input,
            },
        }
        # 仅缓存图服务正常（无 fallback_reason）的结果，避免把瞬时故障缓存住。
        if fallback_reason is None:
            with _result_cache_lock:
                _result_cache[cache_key] = (time.monotonic() + _RESULT_CACHE_TTL, payload)
        return payload

    # ---------------- Graph API 调用 ----------------
    async def _find_coauthor_edge(
        self,
        client: Any,
        node_a: dict[str, Any],
        node_b: dict[str, Any],
    ) -> dict[str, Any] | None:
        """在 node_a 与 node_b 之间定位一条 COAUTHOR_WITH 边；不存在时返回 None。"""
        a_id = str(node_a.get("id") or "")
        b_id = str(node_b.get("id") or "")
        edges = await client.get_node_edges(
            a_id, edge_type="COAUTHOR_WITH", limit=_MAX_EDGES_PER_EXPERT
        )
        for edge in edges:
            peer_id = str(edge.get("target") if edge.get("source") == a_id else edge.get("source"))
            if peer_id == b_id:
                return edge
        return None

    async def _collect_relations(
        self,
        client: Any,
        node_a: dict[str, Any],
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        """拉取专家A的全部直接关系，按共同论文数降序返回前 ``limit`` 条。

        先按边属性排序，只对最终要返回的对端取节点详情，避免为一百条边打一百次
        ``get_node``。

        Args:
            client: 图查询 API 客户端。
            node_a: 已定位的专家A节点。
            limit: 最多返回多少条关系。

        Returns:
            ``_build_row`` 结构的关系行列表；没有任何直接关系时为空列表。
        """
        a_id = str(node_a.get("id") or "")
        edges = await client.get_node_edges(
            a_id, edge_type="COAUTHOR_WITH", limit=_MAX_EDGES_PER_EXPERT
        )

        def _co_paper_count(edge: dict[str, Any]) -> int:
            props = edge.get("properties") or {}
            try:
                return int(props.get("co_paper_count") or 0)
            except (TypeError, ValueError):
                return 0

        peers: list[tuple[str, dict[str, Any]]] = []
        seen: set[str] = set()
        for edge in sorted(edges, key=_co_paper_count, reverse=True):
            peer_id = str(
                edge.get("target") if str(edge.get("source")) == a_id else edge.get("source")
            )
            if not peer_id or peer_id == a_id or peer_id in seen:
                continue
            seen.add(peer_id)
            peers.append((peer_id, edge))
            if len(peers) >= limit:
                break

        # 对端节点相互独立，并发取详情；单个取不到就跳过，不影响其余关系。
        semaphore = asyncio.Semaphore(_PEER_FETCH_CONCURRENCY)

        async def _resolve(peer_id: str) -> dict[str, Any] | None:
            async with semaphore:
                try:
                    return await client.get_node(peer_id)
                except GraphAPIError:
                    return None

        nodes = await asyncio.gather(*[_resolve(peer_id) for peer_id, _ in peers])
        rows: list[dict[str, Any]] = []
        for (_, edge), node_b in zip(peers, nodes, strict=True):
            if node_b is None:
                continue
            rows.append(self._build_row(node_a, node_b, edge))
        return rows

    async def _attach_representative_achievements(
        self,
        client: Any,
        rows: list[dict[str, Any]],
        anchor_node: dict[str, Any] | None = None,
    ) -> None:
        paper_ids: dict[str, set[str]] = {}
        titles: dict[str, str] = {}
        edge_type = "AUTHORED" if TRSGraphSettings.from_env().space == "techkg" else "AUTHORED_BY"
        single_pair = len(rows) == 1
        # 列表模式的锚点论文池（懒加载）：一次全表扫描服务全部行。
        pool: list[dict[str, Any]] | None = None
        anchor_vid = str((anchor_node or {}).get("id") or "")
        peer_name_forms: dict[str, tuple[str, ...]] = {}
        for row in rows:
            try:
                for person_id in (row["expert_a_id"], row["expert_b_id"]):
                    if person_id not in paper_ids:
                        edges = await client.get_node_edges(
                            person_id, edge_type=edge_type, limit=200
                        )
                        paper_ids[person_id] = {
                            str(
                                edge["target"]
                                if edge.get("source") == person_id
                                else edge["source"]
                            )
                            for edge in edges
                            if edge.get("source") == person_id or edge.get("target") == person_id
                        }
                shared = paper_ids[row["expert_a_id"]] & paper_ids[row["expert_b_id"]]
                achievements = []
                for paper_id in sorted(shared):
                    if paper_id not in titles:
                        paper = await client.get_node(paper_id)
                        props = (paper or {}).get("properties") or {}
                        titles[paper_id] = next(
                            (
                                str(props[key]).strip()
                                for key in (
                                    "title_zh",
                                    "title_cn",
                                    "title",
                                    "title_en",
                                    "zh_name",
                                    "en_name",
                                    "name",
                                )
                                if props.get(key)
                            ),
                            "",
                        )
                    if titles[paper_id]:
                        achievements.append({"id": paper_id, "title": titles[paper_id]})
                    if len(achievements) == 3:
                        break
                if not achievements:
                    # 真实专家常无 AUTHORED_BY 边（跨域兜底 ETL 默认关闭且 Paper
                    # 顶点缺失）：回退 MySQL。单对查询（A+B 都指定）用双方姓名
                    # 联查 SQL；列表模式先走关系表自连接的索引查询，仍无标题
                    # 再按锚点姓名一次扫描建论文池（进程内缓存），逐行在内存
                    # 按对端姓名过滤——避免每行一次约 2.5s 的全表扫描。
                    a_names: tuple[str, ...] = ()
                    b_names: tuple[str, ...] = ()
                    if single_pair:
                        a_names, b_names = await self._person_name_forms(
                            client, row["expert_a_id"], row["expert_b_id"]
                        )
                    achievements = await asyncio.to_thread(
                        self._shared_paper_titles_from_mysql,
                        row["expert_a_id"],
                        row["expert_b_id"],
                        a_names,
                        b_names,
                        single_pair,
                    )
                    if not achievements and not single_pair and anchor_vid:
                        if pool is None:
                            pool = await asyncio.to_thread(
                                _anchor_paper_pool, _node_name_forms(anchor_node or {})
                            )
                        peer_vid = (
                            row["expert_b_id"]
                            if row["expert_a_id"] == anchor_vid
                            else row["expert_a_id"]
                        )
                        if peer_vid not in peer_name_forms:
                            peer_name_forms[peer_vid] = await self._one_person_name_forms(
                                client, peer_vid
                            )
                        achievements = _pool_shared_titles(pool, peer_name_forms[peer_vid])
                row["representative_achievements"] = achievements
            except GraphAPIError:
                logger.warning(
                    "Could not retrieve representative papers for %s", row["relation_key"]
                )

    @staticmethod
    async def _person_name_forms(
        client: Any, a_vid: str, b_vid: str
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """取两位专家的中英文姓名（姓名反查回退的匹配素材）。"""
        return (
            await ExpertDirectRelationService._one_person_name_forms(client, a_vid),
            await ExpertDirectRelationService._one_person_name_forms(client, b_vid),
        )

    @staticmethod
    async def _one_person_name_forms(client: Any, vid: str) -> tuple[str, ...]:
        """取一位专家的中英文姓名（姓名反查回退的匹配素材）。"""
        try:
            node = await client.get_node(vid)
        except GraphAPIError:
            node = None
        return _node_name_forms(node or {})

    @staticmethod
    def _shared_paper_titles_from_mysql(
        a_vid: str,
        b_vid: str,
        a_names: tuple[str, ...] = (),
        b_names: tuple[str, ...] = (),
        allow_name_match: bool = False,
    ) -> list[dict[str, str]]:
        """MySQL 回退：共同论文标题（仅保留标题可核实的行，按被引降序取 3 条）。

        两级：先 ``dwd_scholar_paper_relation`` 自连接（paper_id / related_paper_id
        双号段核实标题，索引查询）；仍无标题且 ``allow_name_match`` 时，按双方
        姓名同时出现在 ``dwd_scholar_papers.authors``（逗号分隔作者姓名，真实行
        无 id 无法按 paper_id 关联）反查，按发表时间降序取 3 条。
        """
        a_scholar = a_vid.removeprefix("person_")
        b_scholar = b_vid.removeprefix("person_")
        if not a_scholar or not b_scholar or a_scholar == b_scholar:
            return []
        sql = text(
            "SELECT r.paper_id, COALESCE(NULLIF(p.zh_name, ''), NULLIF(p.en_name, ''), "
            "NULLIF(zh.zh_name, ''), NULLIF(zh.en_name, ''), "
            "NULLIF(en.zh_name, ''), NULLIF(en.en_name, '')) AS title "
            "FROM dwd_scholar_paper_relation r "
            "JOIN dwd_scholar_paper_relation r2 "
            "ON r2.paper_id = r.paper_id AND r2.scholar_id = :b "
            "LEFT JOIN dwd_scholar_papers p ON p.id = r.paper_id "
            "LEFT JOIN dwd_zh_paper zh ON zh.id = r.related_paper_id "
            "LEFT JOIN dwd_en_paper en ON en.id = r.related_paper_id "
            "WHERE r.scholar_id = :a "
            "ORDER BY GREATEST(COALESCE(r.citations, 0), COALESCE(r2.citations, 0)) DESC, r.paper_id "
            "LIMIT 3"
        )
        try:
            with session_scope() as session:
                rows = session.execute(sql, {"a": a_scholar, "b": b_scholar}).mappings().all()
        except Exception:  # noqa: BLE001
            logger.warning(
                "representative achievements mysql fallback failed: %s x %s", a_vid, b_vid
            )
            return []
        achievements = [
            {"id": f"paper_{row['paper_id']}", "title": str(row["title"])}
            for row in rows
            if row["title"]
        ]
        if achievements or not allow_name_match:
            return achievements
        return _shared_paper_titles_by_author_names(a_names, b_names)

    async def _find_person(self, client: Any, keyword: str) -> dict[str, Any] | None:
        """按 VID / scholar_id / 姓名定位一个 Person 节点。

        Args:
            client: 图查询 API 客户端。
            keyword: 完整 VID、scholar_id 或中英文姓名。

        Returns:
            能按 VID 寻址的 Person 节点；找不到时返回 ``None``。
        """
        # keyword 可能是完整 VID / scholar_id / 姓名
        for candidate_vid in (keyword, f"person_{keyword}"):
            node = await client.get_node(candidate_vid)
            if node is not None:
                return node
        # 姓名精确匹配（中文/英文）。属性搜索返回的 id 不保证是业务 VID，
        # 必须先换成可寻址节点，否则后续查边一定为空。
        for name_field in ("name_zh", "name_en"):
            result = await client.search_nodes(
                label="Person", properties={name_field: keyword}, limit=_MAX_ANCHOR_CANDIDATES
            )
            items = result.get("items") if isinstance(result, dict) else []
            for item in items or []:
                resolved = await client.resolve_addressable_node(
                    item, vid_candidates=self._person_vid_candidates(item)
                )
                if resolved is not None:
                    return resolved
        return None

    @staticmethod
    def _person_vid_candidates(node: dict[str, Any]) -> list[str]:
        """按 ``person_{scholar_id}`` 命名约定重建候选 VID。"""
        props = node.get("properties") or {}
        candidates: list[str] = []
        for key in ("source_record_id", "scholar_id"):
            value = str(props.get(key) or "").strip()
            if value:
                candidates.append(f"person_{value}")
        return candidates

    def _build_row(
        self,
        anchor: dict[str, Any],
        peer: dict[str, Any],
        edge: dict[str, Any],
    ) -> dict[str, Any]:
        anchor_id = str(anchor.get("id") or "")
        peer_id = str(peer.get("id") or "")
        # 按字典序规范排序，避免同一对专家双向重复
        left, right = (anchor, peer) if anchor_id <= peer_id else (peer, anchor)
        left_id = str(left.get("id") or "")
        right_id = str(right.get("id") or "")
        edge_props = edge.get("properties") or {}
        co_count = int(edge_props.get("co_paper_count") or edge_props.get("count") or 0)
        return {
            "relation_key": f"direct:{left_id}:{right_id}",
            "expert_a_id": left_id,
            "expert_a_name": self._person_name(left),
            "expert_a_org": self._person_prop(left, "scholar_org"),
            "expert_a_h_index": self._person_int(left, "h_index"),
            "expert_a_paper_nums": self._person_int(left, "paper_nums"),
            "expert_a_citation_nums": self._person_int(left, "citation_nums"),
            "expert_a_source": self._person_source(left),
            "expert_b_id": right_id,
            "expert_b_name": self._person_name(right),
            "expert_b_org": self._person_prop(right, "scholar_org"),
            "expert_b_h_index": self._person_int(right, "h_index"),
            "expert_b_paper_nums": self._person_int(right, "paper_nums"),
            "expert_b_citation_nums": self._person_int(right, "citation_nums"),
            "expert_b_source": self._person_source(right),
            "co_paper_count": co_count,
            "evidence_kind": "paper",
            "evidence_count": co_count,
            "relation_time": edge_props.get("relation_time"),
        }

    @staticmethod
    def _person_source(node: dict[str, Any]) -> dict[str, str]:
        """查到即记：抽取节点上的入库溯源元数据；无血缘时记录图库查询来源。"""
        props = node.get("properties") or {}
        source: dict[str, str] = {}
        for key in (
            "source_system",
            "source_table",
            "source_record_id",
            "scholar_id",
            "ingest_batch",
            "ingest_time",
        ):
            value = str(props.get(key) or "").strip()
            if value:
                source[key] = value
        if "source_table" not in source:
            # 节点未携带入图血缘：如实记录本次查询来源（图空间 + 识别属性），
            # 不再默认断言 dwd_scholar。
            recorded = record_node_source(props, node.get("labels") or ("Person",))
            source["source_table"] = recorded["sourceTable"]
            source["source_field"] = recorded["sourceField"]
        return source

    @staticmethod
    def _person_name(node: dict[str, Any]) -> str:
        props = node.get("properties") or {}
        return str(props.get("name_zh") or props.get("name_en") or node.get("id") or "")

    @staticmethod
    def _person_prop(node: dict[str, Any], key: str) -> str:
        props = node.get("properties") or {}
        value = props.get(key)
        return str(value) if value else ""

    @staticmethod
    def _person_int(node: dict[str, Any], key: str) -> int:
        props = node.get("properties") or {}
        try:
            return int(props.get(key) or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _matches_institution(row: dict[str, Any], keyword: str) -> bool:
        keyword_lc = keyword.strip().lower()
        if not keyword_lc:
            return True
        for field in ("expert_a_org", "expert_b_org"):
            value = str(row.get(field) or "").lower()
            if keyword_lc in value:
                return True
        return False

    @staticmethod
    def _filter_rows_by_time(
        rows: list[dict[str, Any]],
        start_time: str | None,
        end_time: str | None,
    ) -> list[dict[str, Any]]:
        """按关系边真实 relation_time 过滤；无法验证时间的边不进入限时结果。"""
        start = (start_time or "").strip()
        end = (end_time or "").strip()
        if not start and not end:
            return rows

        def normalized_relation_date(row: dict[str, Any]) -> str | None:
            value = row.get("relation_time")
            if hasattr(value, "strftime"):
                return value.strftime("%Y-%m-%d")
            match = re.search(
                r"((?:19|20)\d{2})[-/.年](0?[1-9]|1[0-2])(?:[-/.月](0?[1-9]|[12]\d|3[01]))?",
                str(value or ""),
            )
            if not match:
                return None
            year, month, day = match.groups()
            return f"{year}-{int(month):02d}-{int(day or 1):02d}"

        lower = f"{start[:7]}-01" if start else ""
        if end and len(end) == 7:
            upper = f"{end[:7]}-31"
        else:
            upper = end[:10] if end else ""
        filtered: list[dict[str, Any]] = []
        for row in rows:
            relation_date = normalized_relation_date(row)
            if relation_date is None:
                continue
            if lower and relation_date < lower:
                continue
            if upper and relation_date > upper:
                continue
            filtered.append(row)
        return filtered

    # ---------------- 展示层组装 ----------------
    def _build_item(self, row: dict[str, Any]) -> dict[str, Any]:
        expert_a_org = str(row.get("expert_a_org") or "")
        expert_b_org = str(row.get("expert_b_org") or "")
        # 只有 A、B 机构真实相同时才算"共同机构"；否则不能把单侧机构包装成双方共有属性。
        shared_institution = expert_a_org if expert_a_org and expert_a_org == expert_b_org else ""
        institution = shared_institution or "合作关系"
        evidence_kind = str(row.get("evidence_kind") or "paper")
        evidence_count = int(row.get("evidence_count") or row.get("co_paper_count") or 0)

        if evidence_kind == "patent":
            reason_tags = ["共专利"] if evidence_count else ["专利关联"]
        elif evidence_kind == "project":
            reason_tags = ["共项目"] if evidence_count else ["项目关联"]
        else:
            reason_tags = ["共论文"] if evidence_count else ["合作关系"]
        if shared_institution:
            reason_tags.insert(0, "同机构")

        # 对数缩放：证据数量差距很大时（如 11 篇 vs 139 篇）仍能拉开置信度档位，
        # 不再是线性公式一撞到 99 上限就全部趴平。
        relation_strength = min(99, round(60 + math.log1p(evidence_count) * 10))
        relation_time = row.get("relation_time")
        if hasattr(relation_time, "strftime"):
            last_updated_at = relation_time.strftime("%Y-%m-%d")
        else:
            last_updated_at = (
                re.split(r"[T ]", str(relation_time), maxsplit=1)[0] if relation_time else None
            )

        expert_a = {
            "expertId": str(row.get("expert_a_id") or ""),
            "name": str(row.get("expert_a_name") or row.get("expert_a_id") or ""),
            "organization": expert_a_org or None,
            "title": "专家",
            "paperCount": int(row.get("expert_a_paper_nums") or 0),
            "citationCount": int(row.get("expert_a_citation_nums") or 0),
            "hIndex": int(row.get("expert_a_h_index") or 0),
        }
        expert_b = {
            "expertId": str(row.get("expert_b_id") or ""),
            "name": str(row.get("expert_b_name") or row.get("expert_b_id") or ""),
            "organization": expert_b_org or None,
            "title": "专家",
            "paperCount": int(row.get("expert_b_paper_nums") or 0),
            "citationCount": int(row.get("expert_b_citation_nums") or 0),
            "hIndex": int(row.get("expert_b_h_index") or 0),
        }

        return {
            "key": str(row.get("relation_key") or ""),
            "relationType": "直接关系",
            "expertA": expert_a,
            "expertB": expert_b,
            "institution": institution,
            "coPaperCount": evidence_count if evidence_kind == "paper" else 0,
            "relationStrength": relation_strength,
            "reasonTags": reason_tags,
            "representativeAchievements": row.get("representative_achievements", []),
            "relationSummary": " + ".join(reason_tags),
            "lastUpdatedAt": last_updated_at,
            "detailRows": [
                ["专家 A", expert_a["name"]],
                ["专家 A 机构", expert_a["organization"] or ""],
                ["专家 A H指数", expert_a["hIndex"]],
                ["专家 B", expert_b["name"]],
                ["专家 B 机构", expert_b["organization"] or ""],
                ["专家 B H指数", expert_b["hIndex"]],
                ["关系类型", "直接关系"],
                ["共同机构", shared_institution or "无"],
                ["证据类型", self._evidence_label(evidence_kind)],
                ["证据数量", evidence_count],
                ["判定依据", reason_tags],
                ["关系摘要", " + ".join(reason_tags)],
            ],
        }

    def _build_provenance(
        self, rows: list[dict[str, Any]], source: dict[str, Any]
    ) -> dict[str, Any]:
        """组装实体/关系溯源信息，字段结构与校友关系模块保持一致。

        优先使用图节点携带的真实入库元数据（``source_system`` / ``source_record_id`` /
        ``ingest_batch`` / ``ingest_time``），没有元数据时不编造溯源编号。

        Args:
            rows: 关系行，含双方属性与 ``expert_*_source`` 溯源元数据。
            source: 数据来源标记，含 ``fallback`` 与降级 ``reason``。

        Returns:
            ``{sourceDatabase, summary, evidences[]}``。
        """
        space = TRSGraphSettings.from_env().space or "dev"
        source_database = f"trs-graph / space={space}"
        if rows:
            summary_text = f"图库 COAUTHOR_WITH 边命中 {len(rows)} 条直接关系。"
        else:
            reason = str(source.get("reason") or "empty_result")
            summary_text = (
                f"图库 space={space} 未命中直接合作关系"
                f"（{_FALLBACK_REASON_TEXT.get(reason, reason)}）。"
            )

        evidences: list[dict[str, Any]] = []
        # 已输出的实体证据 vid：单专家模式（expertBId 为空）下每条关系行都
        # 重复携带核心专家（expert_a），同一专家的实体卡只保留第一次。
        seen_entity_vids: set[str] = set()
        # 覆盖全部关系行（数量已由查询 limit 封顶），保证前端点击任意
        # 关系边/节点都能按 graphVid 筛中证据。
        for row in rows:
            src_a = row.get("expert_a_source") or {}
            src_b = row.get("expert_b_source") or {}
            has_meta = bool(src_a or src_b)

            def _side_evidence(
                side: str,
                _row: dict[str, Any] = row,
                _src: dict[str, str] | None = None,
            ) -> dict[str, Any]:
                src = _src if _src is not None else {}
                name = str(_row.get(f"expert_{side}_name") or _row.get(f"expert_{side}_id") or "—")
                system = str(src.get("source_system") or "")
                record_id = str(
                    src.get("source_record_id")
                    or src.get("scholar_id")
                    or _row.get(f"expert_{side}_id")
                    or ""
                )
                return {
                    "title": f"专家实体 · {name}",
                    "businessTable": "科技专家画像",
                    "technicalTable": f"{system}.dwd_scholar" if system else "Person",
                    "recordId": record_id,
                    "fieldIdentifier": "scholar_id / name_zh",
                    # 溯源三要素：MySQL 源表名 / MySQL 英文字段名 / 图空间 VID。
                    # source_table 已由 _person_source 保证非空（无血缘时为图库来源标记）。
                    "sourceTable": src.get("source_table") or "—",
                    "sourceField": src.get("source_field") or _SCHOLAR_SOURCE_FIELD,
                    "graphVid": str(_row.get(f"expert_{side}_id") or ""),
                    "summary": (
                        f"机构：{_row.get(f'expert_{side}_org') or '—'}；"
                        f"入库批次：{src.get('ingest_batch') or '—'}；"
                        f"入库时间：{src.get('ingest_time') or '—'}"
                    ),
                }

            if has_meta:
                for side, src in (("a", src_a), ("b", src_b)):
                    side_vid = str(row.get(f"expert_{side}_id") or "")
                    if side_vid:
                        if side_vid in seen_entity_vids:
                            continue
                        seen_entity_vids.add(side_vid)
                    evidences.append(_side_evidence(side, row, src))
                evidences.append(
                    {
                        "title": (
                            f"直接关系 · {row.get('expert_a_name') or '—'} — "
                            f"{row.get('expert_b_name') or '—'}"
                        ),
                        "businessTable": "专家合作关系",
                        "technicalTable": "Person -[COAUTHOR_WITH]- Person",
                        "recordId": f"{row.get('expert_a_id') or '—'} / {row.get('expert_b_id') or '—'}",
                        "fieldIdentifier": "co_paper_count / relation_time",
                        "sourceTable": _COAUTHOR_SOURCE_TABLE,
                        "sourceField": _COAUTHOR_SOURCE_FIELD,
                        "graphVid": (
                            f"{row.get('expert_a_id') or '—'} -> {row.get('expert_b_id') or '—'}"
                        ),
                        "summary": (
                            f"共同论文 {row.get('co_paper_count') or 0} 篇；"
                            f"最近合作时间：{row.get('relation_time') or '—'}"
                        ),
                    }
                )
            else:
                evidences.append(
                    {
                        "title": (
                            f"直接关系 · {row.get('expert_a_name') or '—'} — "
                            f"{row.get('expert_b_name') or '—'}"
                        ),
                        "businessTable": "专家合作关系",
                        "technicalTable": "Person -[COAUTHOR_WITH]- Person",
                        "recordId": f"{row.get('expert_a_id') or '—'} / {row.get('expert_b_id') or '—'}",
                        "fieldIdentifier": "co_paper_count / relation_time",
                        "sourceTable": _COAUTHOR_SOURCE_TABLE,
                        "sourceField": _COAUTHOR_SOURCE_FIELD,
                        "graphVid": (
                            f"{row.get('expert_a_id') or '—'} -> {row.get('expert_b_id') or '—'}"
                        ),
                        "summary": (
                            f"共同论文 {row.get('co_paper_count') or 0} 篇；"
                            "图库中无该关系的入库元数据"
                        ),
                    }
                )

        # 机构虚拟节点/从属边（查到即记）：机构名取自专家节点的 scholar_org
        # 属性，溯源归因到宿主专家的来源，保证画布上每个节点/边都有证据可命中。
        institution_hosts: dict[str, dict[str, Any]] = {}
        institution_edges: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            for side in ("a", "b"):
                org = str(row.get(f"expert_{side}_org") or "").strip()
                expert_id = str(row.get(f"expert_{side}_id") or "")
                if not org or not expert_id:
                    continue
                expert_name = str(row.get(f"expert_{side}_name") or expert_id)
                src = row.get(f"expert_{side}_source") or {}
                institution_id = f"institution:{org}"
                host = institution_hosts.setdefault(
                    institution_id,
                    {
                        "org": org,
                        "table": str(src.get("source_table") or "—"),
                        "hosts": [],
                    },
                )
                host_label = f"{expert_name}（{expert_id}）"
                if host_label not in host["hosts"]:
                    host["hosts"].append(host_label)
                institution_edges.setdefault(
                    (expert_id, institution_id),
                    {
                        "expert_id": expert_id,
                        "expert_name": expert_name,
                        "org": org,
                        "table": str(src.get("source_table") or "—"),
                    },
                )
        for institution_id, host in institution_hosts.items():
            evidences.append(
                {
                    "title": f"任职机构 · {host['org']}",
                    "businessTable": "专家任职机构",
                    "technicalTable": "Person.scholar_org 属性",
                    "recordId": institution_id,
                    "fieldIdentifier": "scholar_org",
                    # 溯源三要素：机构名的来源是宿主专家的 scholar_org 字段
                    "sourceTable": host["table"],
                    "sourceField": "scholar_org",
                    "graphVid": institution_id,
                    "summary": (
                        f"机构名取自专家 {'、'.join(host['hosts'])} 的 "
                        "scholar_org 属性（查询路径：get_node 专家 VID）"
                    ),
                }
            )
        for (_, institution_id), edge in institution_edges.items():
            evidences.append(
                {
                    "title": f"机构从属 · {edge['expert_name']} — {edge['org']}",
                    "businessTable": "专家任职机构",
                    "technicalTable": "Person.scholar_org 属性",
                    "recordId": institution_id,
                    "fieldIdentifier": "scholar_org",
                    "sourceTable": edge["table"],
                    "sourceField": "scholar_org",
                    # 复合 vid（"专家VID -> institution:机构名"），前端点击
                    # 机构从属边时按两端同时命中筛中这条证据。
                    "graphVid": f"{edge['expert_id']} -> {institution_id}",
                    "summary": (
                        f"机构从属边由专家 {edge['expert_name']} 的 scholar_org "
                        "属性派生（非图库实体边）"
                    ),
                }
            )

        return {
            "sourceDatabase": source_database,
            "summary": summary_text,
            "evidences": evidences,
        }

    def _build_anchor_only_graph(self, anchor: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        """仅专家A分支的图：只有一个 expert 节点，无边。"""
        node = {
            "id": str(anchor.get("id") or ""),
            "type": "expert",
            "label": self._person_name(anchor),
            "subtitle": self._person_prop(anchor, "scholar_org"),
            "data": {"role": "A"},
        }
        return {"nodes": [node], "edges": []}

    def _build_anchor_only_provenance(self, anchor: dict[str, Any]) -> dict[str, Any]:
        """仅专家A分支的溯源：只含专家A的实体入库元数据。"""
        space = TRSGraphSettings.from_env().space or "dev"
        src = self._person_source(anchor)
        name = self._person_name(anchor) or str(anchor.get("id") or "—")
        system = str(src.get("source_system") or "")
        record_id = str(
            src.get("source_record_id") or src.get("scholar_id") or anchor.get("id") or ""
        )
        evidence = {
            "title": f"专家实体 · {name}",
            "businessTable": "科技专家画像",
            "technicalTable": f"{system}.dwd_scholar" if system else "Person",
            "recordId": record_id,
            "fieldIdentifier": "scholar_id / name_zh",
            "sourceTable": src.get("source_table") or _SCHOLAR_SOURCE_TABLE,
            "sourceField": _SCHOLAR_SOURCE_FIELD,
            "graphVid": str(anchor.get("id") or ""),
            "summary": (
                f"机构：{self._person_prop(anchor, 'scholar_org') or '—'}；"
                f"入库批次：{src.get('ingest_batch') or '—'}；"
                f"入库时间：{src.get('ingest_time') or '—'}"
            ),
        }
        return {
            "sourceDatabase": f"trs-graph / space={space}",
            "summary": f"已定位到专家 {name}，未指定专家B，仅返回专家A节点。",
            "evidences": [evidence],
        }

    def _build_graph(self, items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        """组装展示用子图。

        机构边只按各专家自己的 ``organization`` 连线：同机构时两人自然汇聚到同一个
        机构节点，跨机构时各连各的，不再用 "合作关系" 之类的占位字符串伪造一个
        双方共有的机构节点。没有机构属性的专家不产生机构节点与机构边。
        """
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        seen_nodes: set[str] = set()
        seen_edges: set[tuple[str, str, str]] = set()

        def add_node(node: dict[str, Any]) -> None:
            if node["id"] in seen_nodes:
                return
            seen_nodes.add(node["id"])
            nodes.append(node)

        def add_edge(source: str, target: str, label: str, data: dict[str, Any]) -> None:
            key = (source, target, label)
            if key in seen_edges:
                return
            seen_edges.add(key)
            edges.append({"source": source, "target": target, "label": label, "data": data})

        for item in items:
            expert_a = item["expertA"]
            expert_b = item["expertB"]

            for expert, role in ((expert_a, "A"), (expert_b, "B")):
                add_node(
                    {
                        "id": expert["expertId"],
                        "type": "expert",
                        "label": expert["name"],
                        "subtitle": expert["organization"],
                        "data": {"role": role},
                    }
                )

            add_edge(
                expert_a["expertId"],
                expert_b["expertId"],
                f"直接关系 / {item['relationSummary']}",
                {"strength": item["relationStrength"]},
            )

            # 机构边逐个专家按其真实 organization 连线，避免出现该专家并不存在的机构关系，
            # 也不再用 "合作关系" 兜底字符串伪造一个双方共有的机构节点。
            for expert in (expert_a, expert_b):
                organization = str(expert.get("organization") or "").strip()
                if not organization:
                    continue
                institution_id = f"institution:{organization}"
                add_node(
                    {
                        "id": institution_id,
                        "type": "institution",
                        "label": organization,
                        "subtitle": "任职机构",
                        "data": {},
                    }
                )
                # 机构从属边是专家 organization 属性直读派生（非图库真实边），
                # 置信度取边类型兜底规则（同校友模块合成边口径），避免前端显示"暂无"。
                membership_confidence = edge_confidence(None, "")
                add_edge(
                    expert["expertId"],
                    institution_id,
                    "关联机构",
                    {"strength": round(membership_confidence["confidence"] * 100)},
                )

        return {"nodes": nodes, "edges": edges}

    def _orient_rows(
        self,
        *,
        rows: list[dict[str, Any]],
        expert_a_id: str | None,
        expert_b_id: str | None,
    ) -> list[dict[str, Any]]:
        return [
            self._orient_row(row, expert_a_id=expert_a_id, expert_b_id=expert_b_id) for row in rows
        ]

    def _orient_row(
        self,
        row: dict[str, Any],
        *,
        expert_a_id: str | None,
        expert_b_id: str | None,
    ) -> dict[str, Any]:
        a_keyword = (expert_a_id or "").strip().lower()
        b_keyword = (expert_b_id or "").strip().lower()
        if not a_keyword and not b_keyword:
            return row

        left_matches_a = self._matches_row_side(row, "a", a_keyword)
        right_matches_a = self._matches_row_side(row, "b", a_keyword)
        left_matches_b = self._matches_row_side(row, "a", b_keyword)

        should_swap = False
        if a_keyword and right_matches_a and not left_matches_a:
            should_swap = True
        if a_keyword and b_keyword and right_matches_a and left_matches_b:
            should_swap = True

        if not should_swap:
            return row

        swapped = dict(row)
        for field in ("id", "name", "org", "h_index", "paper_nums", "citation_nums", "source"):
            swapped[f"expert_a_{field}"] = row.get(f"expert_b_{field}")
            swapped[f"expert_b_{field}"] = row.get(f"expert_a_{field}")
        return swapped

    def _matches_row_side(self, row: dict[str, Any], side: str, keyword: str) -> bool:
        if not keyword:
            return False
        values = [
            str(row.get(f"expert_{side}_id") or "").strip().lower(),
            str(row.get(f"expert_{side}_name") or "").strip().lower(),
        ]
        return keyword in values

    def _evidence_label(self, evidence_kind: str) -> str:
        if evidence_kind == "patent":
            return "共同专利"
        if evidence_kind == "project":
            return "共同项目"
        return "共同论文"


def _matchable_names(names: tuple[str, ...]) -> list[str]:
    """过滤可用的姓名匹配素材：非空、长度 >= 2、不是节点 VID 兜底串。"""
    return [name for name in names if len(name) >= 2 and not name.startswith("person_")]


def _shared_paper_titles_by_author_names(
    a_names: tuple[str, ...], b_names: tuple[str, ...]
) -> list[dict[str, str]]:
    """按双方姓名反查 ``dwd_scholar_papers.authors``（约 25 万行 LIKE 扫描）。

    该表真实行的 id 未灌入（无法按 paper_id 关联），但 authors 存逗号分隔的
    作者姓名——双方中/英文名任一形态同时命中的行即共同论文。中文姓名按子串
    匹配可能撞上更长的姓名，靠双方同时命中 + 仅单对查询兜底；标题取
    zh_name/en_name，按发表时间降序取 3 条。
    """
    usable_a = _matchable_names(a_names)
    usable_b = _matchable_names(b_names)
    if not usable_a or not usable_b:
        return []
    where_a = " OR ".join(f"authors LIKE :a{i}" for i in range(len(usable_a)))
    where_b = " OR ".join(f"authors LIKE :b{i}" for i in range(len(usable_b)))
    params = {f"a{i}": f"%{name}%" for i, name in enumerate(usable_a)}
    params.update({f"b{i}": f"%{name}%" for i, name in enumerate(usable_b)})
    sql = text(
        "SELECT doi, COALESCE(NULLIF(zh_name, ''), NULLIF(en_name, '')) AS title "
        "FROM dwd_scholar_papers "
        f"WHERE ({where_a}) AND ({where_b}) "
        "ORDER BY cover_date_start DESC LIMIT 3"
    )
    try:
        with session_scope() as session:
            rows = session.execute(sql, params).mappings().all()
    except Exception:  # noqa: BLE001
        logger.warning(
            "representative achievements author-name fallback failed: %s x %s",
            usable_a[0],
            usable_b[0],
        )
        return []
    return [
        {"id": str(row["doi"] or row["title"]), "title": str(row["title"])}
        for row in rows
        if row["title"]
    ]


def _node_name_forms(node: Mapping[str, Any]) -> tuple[str, ...]:
    """从节点属性提取中英文姓名（姓名反查回退的匹配素材）。"""
    props = node.get("properties") or {}
    return tuple(
        str(props[key]).strip()
        for key in ("name_zh", "name_en")
        if str(props.get(key) or "").strip()
    )


def _anchor_paper_pool(anchor_names: tuple[str, ...]) -> list[dict[str, Any]]:
    """锚点专家的论文池：authors 含其任一姓名形态，按发表时间降序取前若干条。

    列表模式逐对反查要扫 ``dwd_scholar_papers`` 全表（约 2.5s/行），改为按锚点
    姓名一次扫描建池（进程内缓存），再在内存里按对端姓名过滤。池只保留最新
    ``_PAPER_POOL_LIMIT`` 条，代表成果本就取最新在前，截断只影响更老的合著。
    """
    usable = _matchable_names(anchor_names)
    if not usable:
        return []
    key = tuple(sorted(usable))
    with _paper_pool_cache_lock:
        entry = _paper_pool_cache.get(key)
    if entry and entry[0] > time.monotonic():
        return entry[1]
    where = " OR ".join(f"authors LIKE :n{i}" for i in range(len(usable)))
    params = {f"n{i}": f"%{name}%" for i, name in enumerate(usable)}
    sql = text(
        "SELECT doi, COALESCE(NULLIF(zh_name, ''), NULLIF(en_name, '')) AS title, authors "
        "FROM dwd_scholar_papers "
        f"WHERE ({where}) "
        "ORDER BY cover_date_start DESC LIMIT :pool_limit"
    )
    try:
        with session_scope() as session:
            rows = (
                session.execute(sql, {**params, "pool_limit": _PAPER_POOL_LIMIT}).mappings().all()
            )
    except Exception:  # noqa: BLE001
        logger.warning("representative achievements anchor paper pool failed: %s", usable[0])
        return []
    pool = [
        {
            "id": str(row["doi"] or row["title"]),
            "title": str(row["title"]),
            "authors_lc": str(row["authors"] or "").lower(),
        }
        for row in rows
        if row["title"]
    ]
    with _paper_pool_cache_lock:
        _paper_pool_cache[key] = (time.monotonic() + _PAPER_POOL_CACHE_TTL, pool)
        while len(_paper_pool_cache) > _PAPER_POOL_CACHE_MAX:
            _paper_pool_cache.pop(next(iter(_paper_pool_cache)))
    return pool


def _pool_shared_titles(
    pool: list[dict[str, Any]], peer_names: tuple[str, ...]
) -> list[dict[str, str]]:
    """从锚点论文池里筛对端也署名的论文（池已按时间降序，取前 3 条）。

    与 SQL 联查口径一致：对端中/英文名任一形态命中 authors（大小写不敏感）。
    """
    names = [name.lower() for name in _matchable_names(peer_names)]
    if not names:
        return []
    achievements: list[dict[str, str]] = []
    for paper in pool:
        if any(name in paper["authors_lc"] for name in names):
            achievements.append({"id": paper["id"], "title": paper["title"]})
            if len(achievements) == 3:
                break
    return achievements
