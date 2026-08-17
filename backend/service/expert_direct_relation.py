"""科技专家/人才直接关系——通过 FastAPI 图查询 API 实现（不直连 DAO/MySQL）。

数据流：
1. 定位起点专家：调用 ``GET /nodes/search?label=Person`` 按 scholar_id / 姓名过滤；
   ``expertAId`` 支持传 scholar_id 或直接 VID (``person_{scholar_id}``)。
2. 拉合作关系：调用 ``GET /node/{vid}/edges?edge_type=COAUTHOR_WITH`` 拿全部合作边。
3. 拿对端专家：对每条边的对端 VID 调用 ``GET /nodes/{vid}`` 补齐属性。
4. 机构过滤 & 排序：在服务层按 ``institution`` 关键字过滤、按合作论文数排序。
5. 图数据/详情：按业务格式组装 items + graph。

当图服务不可用（GraphAPIError）时，回退到内置 ``FALLBACK_ITEMS`` 保证接口可用。
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from infra.graph_api_client import GraphAPIError, graph_api
from service.base_module import KGModuleScaffoldService

logger = logging.getLogger(__name__)

FALLBACK_ITEMS: list[dict[str, Any]] = [
    {
        "relation_key": "direct:fallback:zhangmingyuan:lijianing",
        "expert_a_id": "fallback_zhangmingyuan",
        "expert_a_name": "张明远",
        "expert_a_org": "清华大学",
        "expert_a_h_index": 36,
        "expert_a_paper_nums": 128,
        "expert_a_citation_nums": 4380,
        "expert_b_id": "fallback_lijianing",
        "expert_b_name": "李佳宁",
        "expert_b_org": "清华大学",
        "expert_b_h_index": 24,
        "expert_b_paper_nums": 86,
        "expert_b_citation_nums": 1930,
        "co_paper_count": 4,
        "evidence_kind": "paper",
        "evidence_count": 4,
        "relation_time": datetime(2026, 6, 29, 12, 0, 0),
    },
    {
        "relation_key": "direct:fallback:lijianning:zhouxinyi",
        "expert_a_id": "fallback_lijianing",
        "expert_a_name": "李佳宁",
        "expert_a_org": "智能决策联合实验室",
        "expert_a_h_index": 24,
        "expert_a_paper_nums": 86,
        "expert_a_citation_nums": 1930,
        "expert_b_id": "fallback_zhouxinyi",
        "expert_b_name": "周欣怡",
        "expert_b_org": "北京航空航天大学计算机学院",
        "expert_b_h_index": 41,
        "expert_b_paper_nums": 149,
        "expert_b_citation_nums": 5160,
        "co_paper_count": 2,
        "evidence_kind": "paper",
        "evidence_count": 2,
        "relation_time": datetime(2026, 6, 29, 12, 5, 0),
    },
]

MAX_QUERY_LIMIT = 100
_MAX_ANCHOR_CANDIDATES = 5
_MAX_EDGES_PER_EXPERT = 100


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
            # 区分"图服务报错"和"图里确实没有这两位专家的合作关系"，
            # 否则线上只能靠翻日志才知道降级原因。
            logger.info(
                "expert direct relation falls back to seed data: reason=%s, a=%s, b=%s",
                fallback_reason or "empty_result",
                expert_a_id,
                expert_b_id,
            )
            source = {
                "requested": "all",
                "actual": "fallback",
                "fallback": True,
                "reason": fallback_reason or "empty_result",
            }
            rows = FALLBACK_ITEMS[: max(1, min(normalized_limit, len(FALLBACK_ITEMS)))]

        rows = self._orient_rows(
            rows=rows,
            expert_a_id=expert_a_id,
            expert_b_id=expert_b_id,
        )
        items = [self._build_item(row) for row in rows]
        graph = self._build_graph(items)

        return {
            "taskName": "科技专家直接关系查询",
            "input": query_input,
            "total": len(items),
            "items": items,
            "graph": graph,
            "source": source,
            "apiResultExample": {
                "url": "/api/v1/kg-construction/expert-direct-relations/query",
                "method": "POST",
                "query": query_input,
            },
        }

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
            锚点 Person 节点列表；两个标识都为空时返回库里前若干位学者（仅用于展示）。
        """
        candidates: list[dict[str, Any]] = []
        for keyword in (expert_a_id, expert_b_id):
            if not keyword:
                continue
            node = await self._find_person(client, keyword.strip())
            if node is not None:
                candidates.append(node)
        if candidates:
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
            "expert_b_id": right_id,
            "expert_b_name": self._person_name(right),
            "expert_b_org": self._person_prop(right, "scholar_org"),
            "expert_b_h_index": self._person_int(right, "h_index"),
            "expert_b_paper_nums": self._person_int(right, "paper_nums"),
            "expert_b_citation_nums": self._person_int(right, "citation_nums"),
            "co_paper_count": co_count,
            "evidence_kind": "paper",
            "evidence_count": co_count,
            "relation_time": edge_props.get("relation_time"),
        }

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
        for field in ("id", "name", "org", "h_index", "paper_nums", "citation_nums"):
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

    def fallback_limit(self) -> int:
        return int(os.getenv("EXPERT_DIRECT_RELATION_REAL_LIMIT", "20"))
