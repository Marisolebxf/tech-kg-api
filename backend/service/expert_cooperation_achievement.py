"""科技两点合作成果：按图中两边专家成果邻居求交，规则归因核心贡献与合作模式。"""

from __future__ import annotations

import os
import re
import threading
import time
from typing import Any

from infra.graph_db import GraphNotFoundError, TRSGraphClient, get_trs_graph_client
from infra.graph_db.config import TRSGraphSettings
from service.base_module import KGModuleScaffoldService

PAPER_EDGE_TYPES = frozenset({"AUTHORED_BY"})
PATENT_EDGE_TYPES = frozenset({"INVENTED_BY"})
PROJECT_EDGE_TYPES = frozenset({"LEADS", "HAS_PARTICIPANT"})
EDGE_LIMIT = 500

# 60s 进程内结果缓存：同参数请求复用，避免高并发打爆 trs-graph。
_RESULT_CACHE_TTL = float(os.getenv("RESULT_CACHE_TTL", "60"))
_result_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_result_cache_lock = threading.Lock()


def clear_caches() -> None:
    """清空进程内缓存（测试隔离用）。"""
    _result_cache.clear()


TITLE_KEYS = (
    "title",
    "title_zh",
    "title_en",
    "name",
    "name_zh",
    "name_en",
    "paper_title",
    "patent_name",
    "project_name",
)
TIME_KEYS = (
    "year",
    "publish_year",
    "publication_year",
    "publish_date",
    "publication_date",
    "pub_date",
    "complete_time",
    "completion_date",
    "end_date",
    "end_year",
    "start_date",
    "start_year",
    "date",
)
FIELD_KEYS = (
    "keywords",
    "keyword",
    "domain",
    "domains",
    "fields",
    "field",
    "tech_field",
    "tech_fields",
    "cpc",
    "cpc_codes",
    "subject",
    "subjects",
)
AWARD_KEYS = ("award", "awards", "output_awards", "honors", "honor")
EVAL_KEYS = ("evaluation", "comment", "review", "appraisal")


class ExpertCooperationAchievementService(KGModuleScaffoldService):
    module_code = "expert_cooperation_achievement"

    def __init__(self) -> None:
        super().__init__()

    def _client(self) -> TRSGraphClient:
        # 不在 service 中二次缓存进程级单例。ETL/worker 可能通过
        # close_trs_graph_client() 释放并重建它，持有旧引用会永久停留在未连接状态。
        return get_trs_graph_client()

    def query(
        self,
        *,
        source_expert_id: str,
        target_expert_id: str,
        achievement_types: list[str] | None = None,
        time_range_start: str | None = None,
        time_range_end: str | None = None,
        limit_per_type: int = 20,
    ) -> dict[str, Any]:
        if source_expert_id == target_expert_id:
            raise ValueError("sourceExpertId 与 targetExpertId 不能相同")

        cache_key = (
            f"{source_expert_id}|{target_expert_id}|"
            f"{tuple(achievement_types or [])}|{time_range_start or ''}|"
            f"{time_range_end or ''}|{limit_per_type}"
        )
        with _result_cache_lock:
            entry = _result_cache.get(cache_key)
        if entry and entry[0] > time.monotonic():
            return entry[1]

        graph = self._client()
        source = self._require_node(graph, source_expert_id, "专家")
        target = self._require_node(graph, target_expert_id, "专家")

        type_filter = set(achievement_types or ["paper", "patent", "project"])
        src_ids = self._collect_achievement_ids(graph, source_expert_id)
        tgt_ids = self._collect_achievement_ids(graph, target_expert_id)

        shared: dict[str, set[str]] = {
            "paper": src_ids["paper"] & tgt_ids["paper"],
            "patent": src_ids["patent"] & tgt_ids["patent"],
            "project": src_ids["project"] & tgt_ids["project"],
        }

        items: list[dict[str, Any]] = []
        for ach_type in ("paper", "patent", "project"):
            if ach_type not in type_filter:
                continue
            ordered = sorted(shared[ach_type], key=str)[:limit_per_type]
            for vid in ordered:
                item = self._build_item(graph, ach_type, vid)
                if not self._in_time_range(item.get("time"), time_range_start, time_range_end):
                    continue
                items.append(item)

        award_count = sum(len(i.get("awards") or []) for i in items)
        papers = sum(1 for i in items if i["type"] == "paper")
        patents = sum(1 for i in items if i["type"] == "patent")
        projects = sum(1 for i in items if i["type"] == "project")
        core = self._core_contribution(papers, patents, projects)
        mode = self._cooperation_mode(items, papers, patents, projects)

        space = (
            getattr(getattr(graph, "_settings", None), "space", None)
            or TRSGraphSettings.from_env().space
        )
        source_name = self._display_name(source)
        target_name = self._display_name(target)

        payload: dict[str, Any] = {
            "source": {"id": source_expert_id, "name": source_name},
            "target": {"id": target_expert_id, "name": target_name},
            "summary": {
                "papers": papers,
                "patents": patents,
                "projects": projects,
                "awards": award_count,
            },
            "items": items,
            "coreContribution": core,
            "cooperationMode": mode,
            "sourceMeta": {"space": space, "graph": "trs-graph", "truncated": False},
        }
        payload.update(
            self._frontend_view(
                source_id=source_expert_id,
                source_name=source_name,
                target_id=target_expert_id,
                target_name=target_name,
                papers=papers,
                patents=patents,
                projects=projects,
                award_count=award_count,
                items=items,
                core=core,
                mode=mode,
                space=str(space),
            )
        )
        with _result_cache_lock:
            _result_cache[cache_key] = (time.monotonic() + _RESULT_CACHE_TTL, payload)
        return payload

    @staticmethod
    def _require_node(graph: TRSGraphClient, node_id: str, kind: str) -> Any:
        try:
            node = graph.get_node(node_id)
        except GraphNotFoundError:
            node = None
        if node is None:
            raise KeyError(f"未找到{kind}: {node_id}")
        return node

    @staticmethod
    def _display_name(node: Any) -> str:
        props = getattr(node, "properties", None) or {}
        for key in ("name_zh", "name_cn", "name_en", "name", "scholar_id", "vid", "id"):
            val = props.get(key)
            if val:
                return str(val)
        return str(getattr(node, "id", "") or "")

    def _collect_achievement_ids(
        self, graph: TRSGraphClient, person_id: str
    ) -> dict[str, set[str]]:
        result: dict[str, set[str]] = {"paper": set(), "patent": set(), "project": set()}
        try:
            edges = graph.get_node_edges(person_id, direction="both", limit=EDGE_LIMIT)
        except GraphNotFoundError:
            return result

        for edge in edges or []:
            edge_type = str(getattr(edge, "type", "") or "")
            neighbor = self._neighbor_id(edge, person_id)
            if not neighbor:
                continue
            if edge_type in PAPER_EDGE_TYPES:
                result["paper"].add(str(neighbor))
            elif edge_type in PATENT_EDGE_TYPES:
                result["patent"].add(str(neighbor))
            elif edge_type in PROJECT_EDGE_TYPES:
                result["project"].add(str(neighbor))
        return result

    @staticmethod
    def _neighbor_id(edge: Any, person_id: str) -> str | None:
        src = str(getattr(edge, "source_id", "") or "")
        tgt = str(getattr(edge, "target_id", "") or "")
        pid = str(person_id)
        if src == pid and tgt and tgt != pid:
            return tgt
        if tgt == pid and src and src != pid:
            return src
        return None

    def _build_item(self, graph: TRSGraphClient, ach_type: str, vid: str) -> dict[str, Any]:
        try:
            node = graph.get_node(vid)
        except GraphNotFoundError:
            node = None
        props = (getattr(node, "properties", None) or {}) if node else {}
        awards = self._extract_awards(props)
        return {
            "type": ach_type,
            "id": vid,
            "title": self._pick_title(props, vid),
            "time": self._pick_time(props),
            "fields": self._pick_fields(props),
            "awards": awards,
            "evaluation": self._pick_evaluation(props),
        }

    @staticmethod
    def _pick_title(props: dict[str, Any], fallback: str) -> str:
        for key in TITLE_KEYS:
            val = props.get(key)
            if val:
                return str(val)
        return fallback

    @staticmethod
    def _pick_time(props: dict[str, Any]) -> str | None:
        for key in TIME_KEYS:
            val = props.get(key)
            if val is None or val == "":
                continue
            return str(val)
        return None

    @staticmethod
    def _pick_fields(props: dict[str, Any]) -> list[str]:
        fields: list[str] = []
        for key in FIELD_KEYS:
            val = props.get(key)
            if val is None or val == "":
                continue
            if isinstance(val, list):
                fields.extend(str(x) for x in val if x)
            elif isinstance(val, str):
                parts = re.split(r"[,，;/、|]+", val)
                fields.extend(p.strip() for p in parts if p.strip())
            else:
                fields.append(str(val))
        # dedupe preserve order
        seen: set[str] = set()
        out: list[str] = []
        for f in fields:
            if f not in seen:
                seen.add(f)
                out.append(f)
        return out

    @staticmethod
    def _pick_evaluation(props: dict[str, Any]) -> str | None:
        for key in EVAL_KEYS:
            val = props.get(key)
            if val:
                return str(val)
        return None

    def _extract_awards(self, props: dict[str, Any]) -> list[dict[str, Any]]:
        awards: list[dict[str, Any]] = []
        for key in AWARD_KEYS:
            val = props.get(key)
            if not val:
                continue
            awards.extend(self._parse_award_value(val))
        # dedupe by name+level
        seen: set[tuple[str, str]] = set()
        out: list[dict[str, Any]] = []
        for a in awards:
            sig = (a.get("name") or "", a.get("level") or "")
            if sig in seen or not sig[0]:
                continue
            seen.add(sig)
            out.append(a)
        return out

    def _parse_award_value(self, val: Any) -> list[dict[str, Any]]:
        if isinstance(val, list):
            result: list[dict[str, Any]] = []
            for item in val:
                result.extend(self._parse_award_value(item))
            return result
        if isinstance(val, dict):
            name = val.get("name") or val.get("award_name") or val.get("title")
            if not name:
                return []
            year = val.get("year")
            return [
                {
                    "name": str(name),
                    "level": str(val.get("level") or val.get("award_level") or ""),
                    "year": int(year) if year is not None and str(year).isdigit() else year,
                }
            ]
        text = str(val).strip()
        if not text:
            return []
        # simple single award string
        return [{"name": text, "level": "", "year": None}]

    @staticmethod
    def _parse_year(value: str | None) -> int | None:
        if not value:
            return None
        m = re.search(r"(19|20)\d{2}", str(value))
        if not m:
            return None
        return int(m.group(0))

    def _in_time_range(
        self,
        item_time: str | None,
        start: str | None,
        end: str | None,
    ) -> bool:
        if not start and not end:
            return True
        year = self._parse_year(item_time)
        if year is None:
            # 无法解析时间的条目在时间过滤时直接保留
            return True
        start_y = self._parse_year(start)
        end_y = self._parse_year(end)
        if start_y is not None and year < start_y:
            return False
        if end_y is not None and year > end_y:
            return False
        return True

    @staticmethod
    def _core_contribution(papers: int, patents: int, projects: int) -> str:
        parts: list[str] = []
        if patents:
            parts.append("共同专利产出")
        if projects:
            parts.append("共同项目攻关")
        if papers:
            parts.append("共同论文产出")
        if not parts:
            return "暂无结构化共同成果"
        return "、".join(parts[:2])

    def _cooperation_mode(
        self,
        items: list[dict[str, Any]],
        papers: int,
        patents: int,
        projects: int,
    ) -> str:
        total = papers + patents + projects
        if total == 0:
            return "暂无合作模式"
        years = [y for y in (self._parse_year(i.get("time")) for i in items) if y is not None]
        span_ok = bool(years) and (max(years) - min(years) >= 3) and total >= 3
        if span_ok:
            return "长期稳定型科研合作"
        type_count = sum(1 for n in (papers, patents, projects) if n > 0)
        if type_count == 1:
            if papers:
                return "单类型合作（论文）"
            if patents:
                return "单类型合作（专利）"
            return "单类型合作（项目）"
        return "多类型合作"

    def _frontend_view(
        self,
        *,
        source_id: str,
        source_name: str,
        target_id: str,
        target_name: str,
        papers: int,
        patents: int,
        projects: int,
        award_count: int,
        items: list[dict[str, Any]],
        core: str,
        mode: str,
        space: str,
    ) -> dict[str, Any]:
        total = papers + patents + projects
        type_labels = []
        if papers:
            type_labels.append("论文")
        if patents:
            type_labels.append("专利")
        if projects:
            type_labels.append("项目")

        summary_rows = [
            {"label": "专家 A", "value": f"{source_name}（{source_id}）"},
            {"label": "专家 B", "value": f"{target_name}（{target_id}）"},
            {"label": "合作成果类型", "value": "、".join(type_labels) if type_labels else "—"},
            {"label": "成果总量", "value": f"{total} 项"},
            {
                "label": "成果分布",
                "value": f"论文 {papers}、专利 {patents}、项目 {projects}",
            },
            {"label": "获奖数量", "value": str(award_count)},
            {"label": "核心贡献", "value": core},
            {"label": "合作模式", "value": mode},
            {"label": "图空间", "value": space},
        ]
        if items:
            first = items[0]
            summary_rows.insert(
                5,
                {
                    "label": "代表成果",
                    "value": f"{first.get('title') or first.get('id')}（{first.get('time') or '时间未知'}）",
                },
            )

        result_rows = [
            {"label": "合作论文", "value": str(papers), "tone": "blue"},
            {"label": "合作专利", "value": str(patents), "tone": "green"},
            {"label": "共同项目", "value": str(projects), "tone": "orange"},
            {"label": "获奖成果", "value": str(award_count), "tone": "red"},
        ]

        evidence = [
            "按论文、专利、项目邻居求交汇总共同成果。",
            "回填成果标题、时间、领域与奖项字段（有则输出）。",
            f"规则归因：核心贡献={core}；合作模式={mode}。",
        ]

        rules = [
            {
                "name": "成果关联规则",
                "type": "成果抽取规则",
                "target": "AUTHORED_BY / INVENTED_BY / LEADS / HAS_PARTICIPANT",
                "trigger": "输入两个专家节点",
                "logic": "分别收集两边成果邻居，按类型求交得到共同论文/专利/项目。",
                "output": "items、summary",
                "threshold": "至少一侧存在成果边才可能命中",
                "audit": "无共同成果时 summary 全 0，诚实降级",
            },
            {
                "name": "归因统计规则",
                "type": "统计归因规则",
                "target": "共同成果条目",
                "trigger": "求交完成后",
                "logic": "按类型计数；回填 title/time/fields/awards；生成 coreContribution 与 cooperationMode。",
                "output": "coreContribution、cooperationMode",
                "threshold": "有效成果字段尽量回填，缺失不强行编造",
                "audit": "时间无法解析时，时间过滤放行该条目",
            },
            {
                "name": "合作模式判定规则",
                "type": "分类规则",
                "target": "成果数量与时间跨度",
                "trigger": "归因统计完成后",
                "logic": "无成果→暂无；单类型→单类型合作；多年跨度且总量充足→长期稳定；否则多类型。",
                "output": "cooperationMode",
                "threshold": "跨度>=3 年且总量>=3 判长期稳定",
                "audit": "仅基于图内结构化字段",
            },
        ]

        entities = [
            {
                "id": source_id,
                "label": source_name,
                "entityType": "科技专家",
                "nodeType": "main",
                "confidence": 1.0,
                "relations": f"合作成果 {total}",
                "evidence": [f"id={source_id}"],
                "x": 220.0,
                "y": 160.0,
            },
            {
                "id": target_id,
                "label": target_name,
                "entityType": "科技专家",
                "nodeType": "expert",
                "confidence": 1.0,
                "relations": f"合作成果 {total}",
                "evidence": [f"id={target_id}"],
                "x": 520.0,
                "y": 160.0,
            },
        ]
        relations = [
            {
                "id": f"coop-{source_id}-{target_id}",
                "from": source_id,
                "to": target_id,
                "fromName": source_name,
                "toName": target_name,
                "label": mode if total else "暂无合作",
                "category": "合作成果",
                "summary": f"论文 {papers}、专利 {patents}、项目 {projects}",
            }
        ]
        nodes = list(entities)
        edges = [
            {
                "id": relations[0]["id"],
                "from": source_id,
                "to": target_id,
                "label": relations[0]["label"],
                "category": "合作成果",
            }
        ]

        type_node_map = {
            "paper": ("paper", "论文", 370.0, 320.0),
            "patent": ("topic", "专利", 520.0, 340.0),
            "project": ("project", "项目", 220.0, 340.0),
        }
        for idx, item in enumerate(items[:8]):
            ach_type = str(item.get("type") or "paper")
            node_type, type_label, base_x, base_y = type_node_map.get(
                ach_type, ("paper", "成果", 370.0, 320.0)
            )
            nid = str(item.get("id") or f"ach-{idx}")
            title = str(item.get("title") or nid)
            entity = {
                "id": nid,
                "label": title[:18],
                "entityType": type_label,
                "nodeType": node_type,
                "confidence": 0.9,
                "relations": f"{type_label} · {item.get('time') or '—'}",
                "evidence": [
                    f"type={ach_type}",
                    f"fields={','.join(item.get('fields') or []) or '-'}",
                ],
                "x": base_x + (idx % 3) * 40,
                "y": base_y + (idx // 3) * 36,
            }
            entities.append(entity)
            nodes.append(entity)
            for expert_id in (source_id, target_id):
                eid = f"{expert_id}->{nid}"
                edges.append(
                    {
                        "id": eid,
                        "from": expert_id,
                        "to": nid,
                        "label": type_label,
                        "category": "合作成果",
                    }
                )

        provenance = {
            "sourceDatabase": f"trs-graph / space={space}",
            "summary": f"共同成果 {total} 项；{mode}",
            "evidences": [
                {
                    "title": "专家 A",
                    "businessTable": "科技专家",
                    "technicalTable": "Person",
                    "recordId": source_id,
                    "fieldIdentifier": "sourceExpertId",
                    "summary": source_name,
                },
                {
                    "title": "专家 B",
                    "businessTable": "科技专家",
                    "technicalTable": "Person",
                    "recordId": target_id,
                    "fieldIdentifier": "targetExpertId",
                    "summary": target_name,
                },
                *[
                    {
                        "title": f"{it.get('type')} · {it.get('title') or it.get('id')}",
                        "businessTable": "合作成果",
                        "technicalTable": "expert_cooperation_achievement.query",
                        "recordId": str(it.get("id") or ""),
                        "fieldIdentifier": str(it.get("type") or ""),
                        "summary": f"时间 {it.get('time') or '—'}；奖项 {len(it.get('awards') or [])}",
                    }
                    for it in items[:8]
                ],
            ],
        }

        return {
            "summaryRows": summary_rows,
            "resultRows": result_rows,
            "evidence": evidence,
            "rules": rules,
            "entities": entities,
            "relations": relations,
            "graph": {"nodes": nodes, "edges": edges},
            "provenance": provenance,
        }
