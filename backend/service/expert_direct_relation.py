"""科技专家/人才直接关系——通过 FastAPI 图查询 API 实现（不直连 DAO/MySQL）。

数据流：
1. 定位起点专家：调用 ``GET /nodes/search?label=Person`` 按 scholar_id / 姓名过滤；
   ``expertAId`` 支持传 scholar_id 或直接 VID (``person_{scholar_id}``)。
2. 拉合作关系：调用 ``GET /node/{vid}/edges?edge_type=COAUTHOR_WITH`` 拿全部合作边。
3. 拿对端专家：对每条边的对端 VID 调用 ``GET /nodes/{vid}`` 补齐属性。
4. 机构过滤 & 排序：在服务层按 ``institution`` 关键字过滤、按合作论文数排序。
5. 图数据/详情：按业务格式组装 items + graph。

查询结果一律来自图库；未命中或图服务异常时返回空结果并在 ``source.reason`` 标明原因，
不返回内置示例数据。
"""

from __future__ import annotations

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
}


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
        normalized_limit = max(1, min(int(limit or 10), MAX_QUERY_LIMIT))
        cache_key = (
            f"all|{(expert_a_id or '').strip()}|{(expert_b_id or '').strip()}|"
            f"{(institution or '').strip()}|{(start_time or '').strip()}|"
            f"{(end_time or '').strip()}|{normalized_limit}"
        )
        with _result_cache_lock:
            entry = _result_cache.get(cache_key)
        if entry and entry[0] > time.monotonic():
            return entry[1]

        query_input = {
            "dataSource": "all",
            "expertAId": (expert_a_id or "").strip(),
            "expertBId": (expert_b_id or "").strip(),
            "institution": (institution or "").strip(),
            "startTime": (start_time or "").strip(),
            "endTime": (end_time or "").strip(),
            "limit": normalized_limit,
        }

        source = {"requested": "all", "actual": "fallback", "fallback": True}
        rows: list[dict[str, Any]] = []
        fallback_reason: str | None = None

        try:
            rows = await self._query_via_graph_api(
                expert_a_id=expert_a_id,
                expert_b_id=expert_b_id,
                institution=institution,
                limit=normalized_limit,
            )
            source = {"requested": "all", "actual": "graph-api", "fallback": False}
        except GraphAPIError as exc:
            logger.warning("graph API unavailable, falling back to seed data: %s", exc)
            fallback_reason = "graph_api_error"
            rows = []
        except Exception:  # noqa: BLE001 - 图服务异常一律降级
            logger.exception("unexpected error while querying graph API")
            fallback_reason = "unexpected_error"
            rows = []

        if not rows:
            # 图服务报错和"图里确实没有"都如实返回空结果，不再塞内置示例数据，
            # 避免用户把假数据当成真实查询结果。
            logger.info(
                "expert direct relation empty result: reason=%s, a=%s, b=%s",
                fallback_reason or "empty_result",
                expert_a_id,
                expert_b_id,
            )
            source = {
                "requested": "all",
                "actual": "graph-api",
                "fallback": False,
                "reason": fallback_reason or "empty_result",
            }

        rows = self._orient_rows(
            rows=self._filter_rows_by_time(rows, start_time, end_time),
            expert_a_id=expert_a_id,
            expert_b_id=expert_b_id,
        )
        items = [self._build_item(row) for row in rows]
        graph = self._build_graph(items)

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
    async def _query_via_graph_api(
        self,
        *,
        expert_a_id: str | None,
        expert_b_id: str | None,
        institution: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """通过图查询 API 拉合作关系。

        Args:
            expert_a_id: 起点专家的 VID / scholar_id / 姓名，可为空。
            expert_b_id: 另一位专家的标识，可为空。
            institution: 机构关键词，非空时只保留任一端命中该机构的关系。
            limit: 最多返回多少条关系。

        Returns:
            关系行列表，每行包含双方属性与 ``co_paper_count`` 等字段；无命中时为空列表。
        """
        async with graph_api() as client:
            anchors = await self._resolve_anchors(client, expert_a_id, expert_b_id)
            rows: list[dict[str, Any]] = []
            seen_keys: set[str] = set()
            for anchor in anchors:
                anchor_id = anchor["id"]
                edges = await client.get_node_edges(
                    anchor_id, edge_type="COAUTHOR_WITH", limit=_MAX_EDGES_PER_EXPERT
                )
                for edge in edges:
                    peer_id = edge["target"] if edge["source"] == anchor_id else edge["source"]
                    peer = await client.get_node(peer_id)
                    if peer is None:
                        continue
                    row = self._build_row(anchor, peer, edge)
                    if institution and not self._matches_institution(row, institution):
                        continue
                    key = row["relation_key"]
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    rows.append(row)
                    if len(rows) >= limit:
                        return rows
            return rows

    async def _resolve_anchors(
        self,
        client: Any,
        expert_a_id: str | None,
        expert_b_id: str | None,
    ) -> list[dict[str, Any]]:
        """定位起点专家节点。空条件时取任意若干位学者作为锚点。

        Args:
            client: 图查询 API 客户端。
            expert_a_id: 起点专家标识，可为空。
            expert_b_id: 另一位专家标识，可为空。

        Returns:
            锚点 Person 节点列表；两个标识都为空时返回库里前若干位学者（仅用于展示）；
            指定了标识但图里查不到时返回空列表。
        """
        keywords = [kw.strip() for kw in (expert_a_id, expert_b_id) if kw and kw.strip()]
        if keywords:
            # 指定了专家却查不到时必须返回空，否则会把库里任意几位学者当成查询结果返回，
            # 用户看到的是一堆和输入无关的专家。
            candidates: list[dict[str, Any]] = []
            for keyword in keywords:
                node = await self._find_person(client, keyword)
                if node is not None:
                    candidates.append(node)
            return candidates
        # 无条件时取库里前若干位学者作为锚点，仅用于展示
        listing = await client.list_nodes(label="Person", limit=_MAX_ANCHOR_CANDIDATES)
        return list(listing.get("items", []))

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
        upper = f"{end[:7]}-31" if end and len(end) == 7 else end[:10] if end else ""
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
        last_updated_at = (
            relation_time.strftime("%Y-%m-%d %H:%M:%S")
            if hasattr(relation_time, "strftime")
            else (str(relation_time) if relation_time else None)
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
