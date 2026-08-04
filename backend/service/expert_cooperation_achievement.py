"""科技两点合作成果：按图中两边专家成果邻居求交，规则归因核心贡献与合作模式。"""

from __future__ import annotations

import re
from typing import Any

from infra.graph_db import TRSGraphClient, get_techkg_client
from infra.graph_db.config import TRSGraphSettings
from service.base_module import KGModuleScaffoldService

PAPER_EDGE_TYPES = frozenset({"AUTHORED_BY"})
PATENT_EDGE_TYPES = frozenset({"INVENTED_BY"})
PROJECT_EDGE_TYPES = frozenset({"LEADS", "HAS_PARTICIPANT"})
EDGE_LIMIT = 500

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
        self._graph: TRSGraphClient | None = None

    def _client(self) -> TRSGraphClient:
        if self._graph is None:
            self._graph = get_techkg_client()
        return self._graph

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

        space = (
            getattr(getattr(graph, "_settings", None), "space", None)
            or TRSGraphSettings.from_env().space
        )

        return {
            "source": {"id": source_expert_id, "name": self._display_name(source)},
            "target": {"id": target_expert_id, "name": self._display_name(target)},
            "summary": {
                "papers": papers,
                "patents": patents,
                "projects": projects,
                "awards": award_count,
            },
            "items": items,
            "coreContribution": self._core_contribution(papers, patents, projects),
            "cooperationMode": self._cooperation_mode(items, papers, patents, projects),
            "sourceMeta": {"space": space, "graph": "trs-graph", "truncated": False},
        }

    @staticmethod
    def _require_node(graph: TRSGraphClient, node_id: str, kind: str) -> Any:
        try:
            node = graph.get_node(node_id)
        except Exception:
            node = None
        if node is None:
            raise KeyError(f"{kind}不存在: {node_id}")
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
        except Exception:
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
        except Exception:
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
