"""科技专家/人才直接关系——通过 FastAPI 图查询 API 实现（不直连 DAO/MySQL）。

数据流：
1. ``expertAId`` 必填。按 VID / scholar_id / 姓名定位专家A；查不到 → 空结果。
2. 若 ``expertBId`` 为空：返回专家A的全部直接关系（按共同论文数降序取 ``limit`` 条）；
   一条关系都没有时退回仅返回 A 节点（``source.reason="no_relation_for_a"``）。
3. 若 ``expertBId`` 非空：定位专家B；查不到 → 空结果。在 A、B 之间找一条
   ``COAUTHOR_WITH`` 边；找不到 → 空结果。找到则据此组装唯一一条关系。
4. 机构过滤 & 时间过滤：在服务层按 ``institution`` 关键字、``relation_time`` 过滤该条关系。
5. 图数据/详情：按业务格式组装 items + graph + provenance。

查询结果一律来自图库；未命中或图服务异常时返回空结果并在 ``source.reason`` 标明原因，
不返回内置示例数据。
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import threading
import time
from typing import Any

from infra.graph_api_client import GraphAPIError, graph_api
from infra.graph_db.config import TRSGraphSettings
from service.base_module import KGModuleScaffoldService

# 60s 进程内结果缓存：同参数请求复用，避免高并发打爆 graph-search/trs-graph。
_RESULT_CACHE_TTL = float(os.getenv("RESULT_CACHE_TTL", "60"))
_result_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_result_cache_lock = threading.Lock()


def clear_caches() -> None:
    """清空进程内缓存（测试隔离用）。"""
    _result_cache.clear()


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
            async with graph_api() as client:
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
        except GraphAPIError as exc:
            logger.warning("graph API unavailable: %s", exc)
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
        """抽取节点上真实的入库溯源元数据（source_system / ingest_batch 等）。"""
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
        institution = str(row.get("institution") or expert_a_org or expert_b_org or "合作关系")
        evidence_kind = str(row.get("evidence_kind") or "paper")
        evidence_count = int(row.get("evidence_count") or row.get("co_paper_count") or 0)

        if evidence_kind == "patent":
            reason_tags = ["共专利"] if evidence_count else ["专利关联"]
        elif evidence_kind == "project":
            reason_tags = ["共项目"] if evidence_count else ["项目关联"]
        else:
            reason_tags = ["共论文"] if evidence_count else ["合作关系"]
        if expert_a_org and expert_b_org and expert_a_org == expert_b_org:
            reason_tags.insert(0, "同机构")

        relation_strength = min(99, max(60, 60 + evidence_count * 5 + len(reason_tags) * 4))
        relation_time = row.get("relation_time")
        if hasattr(relation_time, "strftime"):
            last_updated_at = relation_time.strftime("%Y-%m-%d %H:%M:%S")
        else:
            last_updated_at = str(relation_time) if relation_time else None

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
                ["共同机构/主关系", institution],
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
        for row in rows[:8]:
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
                    # 溯源三要素：MySQL 源表名 / MySQL 英文字段名 / 图空间 VID
                    "sourceTable": src.get("source_table") or _SCHOLAR_SOURCE_TABLE,
                    "sourceField": _SCHOLAR_SOURCE_FIELD,
                    "graphVid": str(_row.get(f"expert_{side}_id") or ""),
                    "summary": (
                        f"机构：{_row.get(f'expert_{side}_org') or '—'}；"
                        f"入库批次：{src.get('ingest_batch') or '—'}；"
                        f"入库时间：{src.get('ingest_time') or '—'}"
                    ),
                }

            if has_meta:
                evidences.append(_side_evidence("a", row, src_a))
                evidences.append(_side_evidence("b", row, src_b))
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
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        seen_nodes: set[str] = set()

        for item in items[:4]:
            expert_a = item["expertA"]
            expert_b = item["expertB"]
            institution = item["institution"] or "合作关系"
            institution_id = f"institution:{institution}"

            for node in (
                {
                    "id": expert_a["expertId"],
                    "type": "expert",
                    "label": expert_a["name"],
                    "subtitle": expert_a["organization"],
                    "data": {"role": "A"},
                },
                {
                    "id": expert_b["expertId"],
                    "type": "expert",
                    "label": expert_b["name"],
                    "subtitle": expert_b["organization"],
                    "data": {"role": "B"},
                },
                {
                    "id": institution_id,
                    "type": "institution",
                    "label": institution,
                    "subtitle": "关系归属",
                    "data": {},
                },
            ):
                if node["id"] not in seen_nodes:
                    seen_nodes.add(node["id"])
                    nodes.append(node)

            edges.append(
                {
                    "source": expert_a["expertId"],
                    "target": expert_b["expertId"],
                    "label": f"直接关系 / {item['relationSummary']}",
                    "data": {"strength": item["relationStrength"]},
                }
            )
            edges.append(
                {
                    "source": expert_a["expertId"],
                    "target": institution_id,
                    "label": "关联机构",
                    "data": {},
                }
            )
            edges.append(
                {
                    "source": expert_b["expertId"],
                    "target": institution_id,
                    "label": "关联机构",
                    "data": {},
                }
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
