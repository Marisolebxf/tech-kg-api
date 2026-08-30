"""科技专家校友关系：基于 Person 教育属性 / STUDIED_AT 邻域匹配，仅查询返回，不写 ALUMNI 边。"""

from __future__ import annotations

import math
import os
import re
import threading
import time
import unicodedata
from typing import Any

from infra.graph_db import GraphNotFoundError, TRSGraphClient, get_trs_graph_client
from infra.graph_db.config import TRSGraphSettings
from service.base_module import KGModuleScaffoldService

STUDIED_AT_EDGE = "STUDIED_AT"
EDGE_LIMIT = 500
LOOKUP_CANDIDATE_LIMIT = 200

# 进程内 TTL 缓存：读多写少的图查询，60s 内复用，避免高并发下打爆 trs-graph。
_RESULT_CACHE_TTL = float(os.getenv("RESULT_CACHE_TTL", "60"))
_ORG_INDEX_TTL = 60.0
_org_name_index_cache: dict[str, tuple[float, dict[str, str]]] = {}
_result_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()


def _cache_get(cache: dict[str, tuple[float, Any]], key: str) -> Any:
    entry = cache.get(key)
    if entry and entry[0] > time.monotonic():
        return entry[1]
    return None


def _cache_set(cache: dict[str, tuple[float, Any]], key: str, value: Any, ttl: float) -> None:
    cache[key] = (time.monotonic() + ttl, value)


def clear_caches() -> None:
    """清空进程内缓存（测试隔离用）。"""
    _result_cache.clear()
    _org_name_index_cache.clear()


PAPER_EDGE_TYPES = frozenset({"AUTHORED_BY"})
PATENT_EDGE_TYPES = frozenset({"INVENTED_BY"})
PROJECT_EDGE_TYPES = frozenset({"LEADS", "HAS_PARTICIPANT"})
COAUTHOR_EDGE = "COAUTHOR_WITH"

# 与前端结果详情「规则」Tab 字段对齐（name/type/target/trigger/logic/output/threshold/audit）
ALUMNI_RULES: list[dict[str, str]] = [
    {
        "name": "教育经历匹配算法",
        "type": "关系匹配规则",
        "target": "STUDIED_AT / education_background_institution_*/degree_*/date",
        "trigger": "专家存在就读边或教育院校属性",
        "logic": "沿 STUDIED_AT 院校邻域取候选（无边时 LOOKUP 院校属性兜底）；院校归一后比较；命中同校才认校友。",
        "output": "校友候选、共享院校、维度列表",
        "threshold": "至少命中「同校」",
        "audit": "无教育数据时 total=0，不编造维度；禁止全量 Person 扫描",
    },
    {
        "name": "校友维度细分规则",
        "type": "关系分类规则",
        "target": "同校 / 同学历 / 同期",
        "trigger": "同校匹配成功后",
        "logic": "学位归一相等→同学历；教育年份存在交集→同期。不编造同院系/同导师。",
        "output": "dimensions、dimensionsCatalog",
        "threshold": "同校为必要条件",
        "audit": "数据不具备的维度不得出现在结果中",
    },
    {
        "name": "后续互动关联规则",
        "type": "关系增强规则",
        "target": "COAUTHOR_WITH / AUTHORED_BY / INVENTED_BY / LEADS / HAS_PARTICIPANT",
        "trigger": "校友匹配命中后",
        "logic": "汇总两人合著边与共同论文/专利/项目计数，生成 interactions.summary。",
        "output": "interactions",
        "threshold": "无互动边时计数为 0",
        "audit": "仅作摘要，不写图",
    },
]


class ExpertAlumniRelationService(KGModuleScaffoldService):
    module_code = "expert_alumni_relation"

    def __init__(self) -> None:
        super().__init__()

    def _client(self) -> TRSGraphClient:
        # 单例可能被进程内任务释放并重建，不持有过期引用。
        return get_trs_graph_client()

    def query(
        self,
        *,
        expert_id: str,
        target_expert_id: str | None = None,
        school: str | None = None,
        education_stage: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        if target_expert_id and target_expert_id == expert_id:
            raise ValueError("expertId 与 targetExpertId 不能相同")

        cache_key = (
            f"{expert_id}|{target_expert_id or ''}|{school or ''}|{education_stage or ''}|{limit}"
        )
        cached = _cache_get(_result_cache, cache_key)
        if cached is not None:
            return cached

        graph = self._client()
        source = self._require_node(graph, expert_id, "专家")
        source_edus = self._parse_educations(getattr(source, "properties", None) or {})
        truncated = False

        if target_expert_id:
            target = self._require_node(graph, target_expert_id, "专家")
            candidates = [(target_expert_id, target)]
            mode = "pair"
        else:
            mode = "list"
            candidates, truncated = self._neighborhood_alumni_candidates(
                graph, expert_id, source, school
            )

        # 源专家的边对所有候选都相同，提前取一次复用，避免每个候选重复调 get_node_edges(expert_id)。
        expert_edges: list[Any] = []
        try:
            expert_edges = graph.get_node_edges(expert_id, direction="both", limit=EDGE_LIMIT)
        except GraphNotFoundError:
            expert_edges = []

        items: list[dict[str, Any]] = []
        dim_catalog: set[str] = set()

        for cand_id, cand_node in candidates:
            cand_props = getattr(cand_node, "properties", None) or {}
            cand_edus = self._parse_educations(cand_props)
            match = self._match_alumni(source_edus, cand_edus, school, education_stage)
            if match is None:
                continue
            shared_institutions, dimensions, match_summary = match
            interactions = self._interactions(graph, expert_id, cand_id, expert_edges)
            item = {
                "alumniId": str(cand_id),
                "name": self._display_name(cand_node),
                "sharedInstitutions": shared_institutions,
                "dimensions": dimensions,
                "educations": match_summary,
                "interactions": interactions,
                "provenance": self._person_provenance(cand_props, str(cand_id)),
            }
            items.append(item)
            dim_catalog.update(dimensions)
            if mode == "list" and len(items) >= limit:
                break

        space = (
            getattr(getattr(graph, "_settings", None), "space", None)
            or TRSGraphSettings.from_env().space
        )
        expert = {
            "id": expert_id,
            "name": self._display_name(source),
            "educations": source_edus,
            "provenance": self._person_provenance(
                getattr(source, "properties", None) or {}, expert_id
            ),
        }
        source_meta = {
            "space": space,
            "graph": "trs-graph",
            "truncated": truncated and mode == "list",
        }
        payload = {
            "expert": expert,
            "mode": mode,
            "total": len(items),
            "items": items,
            "dimensionsCatalog": sorted(dim_catalog),
            "sourceMeta": source_meta,
        }
        payload.update(self._frontend_view(payload))
        _cache_set(_result_cache, cache_key, payload, _RESULT_CACHE_TTL)
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

    @staticmethod
    def _person_provenance(props: dict[str, Any], vid: str) -> dict[str, str]:
        """Return only provenance values physically stored on the graph node."""
        return {
            "sourceTable": str(props.get("source_table") or "-"),
            "sourceField": str(props.get("source_field") or "-"),
            "graphVid": vid,
        }

    def _neighborhood_alumni_candidates(
        self,
        graph: TRSGraphClient,
        source_id: str,
        source_node: Any,
        school: str | None,
    ) -> tuple[list[tuple[str, Any]], bool]:
        """经 STUDIED_AT 院校邻域取候选；无边时按源专家院校 LOOKUP，禁止 Person 全扫。"""
        org_vids = self._resolve_school_org_vids(graph, source_id, source_node, school)
        truncated = False
        seen: set[str] = set()
        candidates: list[tuple[str, Any]] = []

        for org_vid in org_vids:
            try:
                edges = graph.get_node_edges(
                    org_vid,
                    direction="in",
                    edge_type=STUDIED_AT_EDGE,
                    limit=EDGE_LIMIT,
                )
            except GraphNotFoundError:
                edges = []
            if len(edges or []) >= EDGE_LIMIT:
                truncated = True
            for edge in edges or []:
                if str(getattr(edge, "type", "") or "") != STUDIED_AT_EDGE:
                    continue
                person_id = self._neighbor_id(edge, org_vid)
                if not person_id or person_id == source_id or person_id in seen:
                    continue
                try:
                    node = graph.get_node(person_id)
                except GraphNotFoundError:
                    node = None
                if node is None:
                    continue
                seen.add(person_id)
                candidates.append((person_id, node))

        if candidates:
            return candidates, truncated

        # org 邻域无命中：按源专家院校字符串 LOOKUP Person（院校 tag index）
        institutions = self._source_institution_names(source_node, school)
        for name in institutions:
            looked_up, hit_cap = self._lookup_persons_by_institution(graph, name)
            if hit_cap:
                truncated = True
            for nid, node in looked_up:
                if nid == source_id or nid in seen:
                    continue
                seen.add(nid)
                candidates.append((nid, node))
        return candidates, truncated

    def _resolve_school_org_vids(
        self,
        graph: TRSGraphClient,
        source_id: str,
        source_node: Any,
        school: str | None,
    ) -> list[str]:
        """源专家 STUDIED_AT 出边院校；无边时用教育属性匹配 Organization 名索引。"""
        org_vids: list[str] = []
        seen: set[str] = set()
        try:
            out_edges = graph.get_node_edges(
                source_id,
                direction="out",
                edge_type=STUDIED_AT_EDGE,
                limit=EDGE_LIMIT,
            )
        except GraphNotFoundError:
            out_edges = []
        school_norm = self._norm_text(school) if school else ""
        for edge in out_edges or []:
            if str(getattr(edge, "type", "") or "") != STUDIED_AT_EDGE:
                continue
            org_vid = self._neighbor_id(edge, source_id)
            if not org_vid or org_vid in seen:
                continue
            props = getattr(edge, "properties", None) or {}
            if school_norm:
                inst = " ".join(
                    filter(
                        None,
                        [
                            self._as_str(props.get("institution_zh")),
                            self._as_str(props.get("institution_en")),
                        ],
                    )
                )
                if not inst:
                    # 边无院校文案时读 org 节点名
                    try:
                        org_node = graph.get_node(org_vid)
                    except GraphNotFoundError:
                        org_node = None
                    op = getattr(org_node, "properties", None) or {}
                    inst = " ".join(
                        filter(
                            None,
                            [
                                self._as_str(op.get("name_cn")),
                                self._as_str(op.get("name_zh")),
                                self._as_str(op.get("name_en")),
                                self._as_str(op.get("name")),
                            ],
                        )
                    )
                inst_key = self._norm_text(inst)
                if school_norm not in inst_key and inst_key not in school_norm:
                    continue
            seen.add(org_vid)
            org_vids.append(org_vid)

        if org_vids:
            return org_vids

        # 无 STUDIED_AT：教育属性 → Organization 名索引
        index = self._org_name_index(graph)
        for name in self._source_institution_names(source_node, school):
            vid = index.get(name) or index.get(name.lower())
            if vid and vid not in seen:
                seen.add(vid)
                org_vids.append(vid)
        return org_vids

    def _source_institution_names(self, source_node: Any, school: str | None) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        if school and school.strip():
            key = school.strip()
            names.append(key)
            seen.add(self._norm_text(key))
        for edu in self._parse_educations(getattr(source_node, "properties", None) or {}):
            inst = (edu.get("institution") or "").strip()
            if not inst:
                continue
            key = self._norm_text(inst)
            if key in seen:
                continue
            seen.add(key)
            names.append(inst)
        return names

    def _org_name_index(self, graph: TRSGraphClient) -> dict[str, str]:
        space = (
            getattr(getattr(graph, "_settings", None), "space", None)
            or TRSGraphSettings.from_env().space
        )
        with _cache_lock:
            cached = _org_name_index_cache.get(space)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        index: dict[str, str] = {}
        try:
            result = graph.execute_read(
                "MATCH (v:Organization) RETURN id(v) AS vid, "
                "v.Organization.name_cn AS name_cn, v.Organization.name_en AS name_en;"
            )
        except Exception:  # noqa: BLE001
            result = None
        for rec in getattr(result, "records", None) or []:
            vid = rec.get("vid")
            if not vid:
                continue
            for k in ("name_cn", "name_en"):
                name = rec.get(k)
                if isinstance(name, str) and name.strip():
                    index[name.strip()] = str(vid)
                    index[name.strip().lower()] = str(vid)
        with _cache_lock:
            _org_name_index_cache[space] = (time.monotonic() + _ORG_INDEX_TTL, index)
        return index

    def _lookup_persons_by_institution(
        self, graph: TRSGraphClient, institution: str
    ) -> tuple[list[tuple[str, Any]], bool]:
        """院校 tag index LOOKUP；返回 (candidates, hit_limit)。"""
        lit = self._ngql_string(institution)
        queries = [
            (
                "LOOKUP ON Person WHERE Person.education_background_institution_zh == "
                f"{lit} YIELD id(vertex) AS vid | LIMIT {LOOKUP_CANDIDATE_LIMIT}"
            ),
            (
                "LOOKUP ON Person WHERE Person.education_background_institution_en == "
                f"{lit} YIELD id(vertex) AS vid | LIMIT {LOOKUP_CANDIDATE_LIMIT}"
            ),
        ]
        out: list[tuple[str, Any]] = []
        seen: set[str] = set()
        hit_cap = False
        for query in queries:
            try:
                result = graph.execute_read(query)
            except Exception:  # noqa: BLE001 — 索引未建或 LOOKUP 不可用
                continue
            rows = getattr(result, "records", None) or []
            if len(rows) >= LOOKUP_CANDIDATE_LIMIT:
                hit_cap = True
            for rec in rows:
                vid = str(rec.get("vid") or "")
                if not vid or vid in seen:
                    continue
                try:
                    node = graph.get_node(vid)
                except GraphNotFoundError:
                    node = None
                if node is None:
                    continue
                seen.add(vid)
                out.append((vid, node))
        return out, hit_cap

    @staticmethod
    def _ngql_string(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    def _scan_person_candidates(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("Person 全量扫描已移除；请使用 STUDIED_AT 邻域路径")

    def _load_person_scan(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("Person 全量扫描已移除；请使用 STUDIED_AT 邻域路径")

    def _parse_educations(self, props: dict[str, Any]) -> list[dict[str, str | None]]:
        inst_zh = self._as_str(props.get("education_background_institution_zh"))
        inst_en = self._as_str(props.get("education_background_institution_en"))
        deg_zh = self._as_str(props.get("education_background_degree_zh"))
        deg_en = self._as_str(props.get("education_background_degree_en"))
        date = self._as_str(props.get("education_background_date"))

        edus: list[dict[str, str | None]] = []
        institution = inst_zh or inst_en
        degree = deg_zh or deg_en
        if institution or degree or date:
            edus.append({"institution": institution, "degree": degree, "date": date})

        for blob_key in (
            "education_background_zh",
            "education_background_en",
            "education_background",
        ):
            blob = self._as_str(props.get(blob_key))
            if not blob:
                continue
            for segment in re.split(r"[;；\n|]+", blob):
                segment = segment.strip()
                if not segment:
                    continue
                # 极简：整段当作院校候选
                edus.append({"institution": segment, "degree": None, "date": None})

        # dedupe by institution norm
        seen: set[str] = set()
        out: list[dict[str, str | None]] = []
        for e in edus:
            key = self._norm_text(e.get("institution") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(e)
        return out

    @staticmethod
    def _as_str(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _norm_text(text: str) -> str:
        text = unicodedata.normalize("NFKC", text or "")
        text = text.strip().lower()
        text = re.sub(r"\s+", "", text)
        return text

    def _match_alumni(
        self,
        source_edus: list[dict[str, str | None]],
        cand_edus: list[dict[str, str | None]],
        school: str | None,
        education_stage: str | None,
    ) -> tuple[list[str], list[str], list[dict[str, str | None]]] | None:
        if not source_edus or not cand_edus:
            return None

        school_norm = self._norm_text(school) if school else ""
        stage_norms = {
            self._norm_text(value)
            for value in re.split(r"[,，/、;；|\s]+", education_stage or "")
            if self._norm_text(value)
        }

        shared_institutions: list[str] = []
        match_summary: list[dict[str, str | None]] = []
        has_same_degree = False
        has_overlap = False

        for s in source_edus:
            s_inst = s.get("institution") or ""
            s_key = self._norm_text(s_inst)
            if not s_key:
                continue
            for c in cand_edus:
                c_inst = c.get("institution") or ""
                c_key = self._norm_text(c_inst)
                if not c_key:
                    continue
                same_school = s_key == c_key or s_key in c_key or c_key in s_key
                if not same_school:
                    continue

                display = s_inst or c_inst
                disp_key = self._norm_text(display)
                if school_norm and school_norm not in disp_key and disp_key not in school_norm:
                    continue

                s_deg_raw = s.get("degree") or ""
                c_deg_raw = c.get("degree") or ""
                s_deg = self._norm_text(s_deg_raw)
                c_deg = self._norm_text(c_deg_raw)
                if stage_norms and not any(
                    stage in s_deg or stage in c_deg for stage in stage_norms
                ):
                    continue

                if display and display not in shared_institutions:
                    shared_institutions.append(display)
                if s_deg and c_deg and s_deg == c_deg:
                    has_same_degree = True
                if self._date_overlap(s.get("date"), c.get("date")):
                    has_overlap = True
                match_summary.append(
                    {
                        "institution": display,
                        "degree": s_deg_raw or c_deg_raw or None,
                        "date": s.get("date") or c.get("date"),
                    }
                )

        if not shared_institutions:
            return None

        dimensions = ["同校"]
        if has_same_degree:
            dimensions.append("同学历")
        if has_overlap:
            dimensions.append("同期")

        return shared_institutions, dimensions, match_summary

    def _date_overlap(self, a: str | None, b: str | None) -> bool:
        years_a = self._extract_years(a)
        years_b = self._extract_years(b)
        if not years_a or not years_b:
            return False
        # same year hit or interval overlap
        if years_a & years_b:
            return True
        if len(years_a) >= 2 and len(years_b) >= 2:
            return max(min(years_a), min(years_b)) <= min(max(years_a), max(years_b))
        return False

    @staticmethod
    def _extract_years(value: str | None) -> set[int]:
        if not value:
            return set()
        return {int(y) for y in re.findall(r"(?:19|20)\d{2}", str(value))}

    def _interactions(
        self,
        graph: TRSGraphClient,
        a_id: str,
        b_id: str,
        a_edges: list[Any] | None = None,
    ) -> dict[str, Any]:
        coauthor = False
        # a_edges（源专家的边）由 query 主流程提前取一次复用，避免每个候选重复调用。
        if a_edges is None:
            try:
                edges = graph.get_node_edges(a_id, direction="both", limit=EDGE_LIMIT)
            except GraphNotFoundError:
                edges = []
        else:
            edges = a_edges

        paper_ids: set[str] = set()
        patent_ids: set[str] = set()
        project_ids: set[str] = set()
        a_papers: set[str] = set()
        a_patents: set[str] = set()
        a_projects: set[str] = set()

        for edge in edges or []:
            et = str(getattr(edge, "type", "") or "")
            neighbor = self._neighbor_id(edge, a_id)
            if not neighbor:
                continue
            if et == COAUTHOR_EDGE and str(neighbor) == str(b_id):
                coauthor = True
            elif et in PAPER_EDGE_TYPES:
                a_papers.add(str(neighbor))
            elif et in PATENT_EDGE_TYPES:
                a_patents.add(str(neighbor))
            elif et in PROJECT_EDGE_TYPES:
                a_projects.add(str(neighbor))

        try:
            b_edges = graph.get_node_edges(b_id, direction="both", limit=EDGE_LIMIT)
        except GraphNotFoundError:
            b_edges = []
        b_papers: set[str] = set()
        b_patents: set[str] = set()
        b_projects: set[str] = set()
        for edge in b_edges or []:
            et = str(getattr(edge, "type", "") or "")
            neighbor = self._neighbor_id(edge, b_id)
            if not neighbor:
                continue
            if et == COAUTHOR_EDGE and str(neighbor) == str(a_id):
                coauthor = True
            elif et in PAPER_EDGE_TYPES:
                b_papers.add(str(neighbor))
            elif et in PATENT_EDGE_TYPES:
                b_patents.add(str(neighbor))
            elif et in PROJECT_EDGE_TYPES:
                b_projects.add(str(neighbor))

        paper_ids = a_papers & b_papers
        patent_ids = a_patents & b_patents
        project_ids = a_projects & b_projects
        paper_count = len(paper_ids)
        patent_count = len(patent_ids)
        project_count = len(project_ids)
        summary = f"共同论文 {paper_count} 篇、专利 {patent_count}、项目 {project_count}"
        if coauthor and paper_count == 0:
            summary = f"存在合著边；{summary}"

        return {
            "coauthorEdge": coauthor,
            "paperCount": paper_count,
            "patentCount": patent_count,
            "projectCount": project_count,
            "summary": summary,
        }

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

    def _frontend_view(self, payload: dict[str, Any]) -> dict[str, Any]:
        """补充前端算法测试页各 Tab 可直接渲染的结构。"""
        expert = payload["expert"]
        items: list[dict[str, Any]] = payload["items"]
        mode = payload["mode"]
        total = payload["total"]
        dims = payload["dimensionsCatalog"]
        meta = payload["sourceMeta"]
        first = items[0] if items else None

        summary_rows = [
            {"label": "专家", "value": f"{expert.get('name') or '—'}（{expert.get('id')}）"},
            {"label": "模式", "value": str(mode)},
            {"label": "校友数", "value": str(total)},
            {"label": "维度目录", "value": "、".join(dims) if dims else "—"},
            {
                "label": "截断",
                "value": "是（list 扫描未穷尽）" if meta.get("truncated") else "否",
            },
            {"label": "图空间", "value": str(meta.get("space") or "—")},
        ]
        if first:
            summary_rows.extend(
                [
                    {
                        "label": "首条校友",
                        "value": f"{first.get('name') or '—'}（{first.get('alumniId')}）",
                    },
                    {
                        "label": "共享院校",
                        "value": "、".join(first.get("sharedInstitutions") or []) or "—",
                    },
                    {
                        "label": "关系维度",
                        "value": "、".join(first.get("dimensions") or []) or "—",
                    },
                    {
                        "label": "互动摘要",
                        "value": (first.get("interactions") or {}).get("summary") or "—",
                    },
                ]
            )
        else:
            summary_rows.append({"label": "说明", "value": "未命中校友（无同校教育属性或异校）"})

        result_rows = [
            {"label": "校友数量", "value": str(total), "tone": "blue"},
            {"label": "查询模式", "value": str(mode), "tone": "green"},
            {
                "label": "关系维度",
                "value": str(len(dims)),
                "tone": "orange",
            },
            {
                "label": "截断标记",
                "value": "是" if meta.get("truncated") else "否",
                "tone": "purple",
            },
        ]

        evidence = [
            "同校为成立校友的必要条件（院校字段 NFKC 归一后比较）。",
            "同学历/同期仅在学位、教育日期可支撑时输出；不输出同院系/同导师。",
            "互动摘要汇总 COAUTHOR_WITH 与共同论文/专利/项目计数。",
        ]
        if not expert.get("educations"):
            evidence.append("源专家无教育院校属性，本次 total=0 属诚实降级。")
        if meta.get("truncated"):
            evidence.append("list 模式扫描达上限，结果可能未穷尽全图 Person。")

        entities, relations, graph = self._build_graph_entities(expert, items)
        provenance = {
            "sourceDatabase": f"trs-graph / space={meta.get('space') or 'dev'}",
            "summary": (
                f"mode={mode}，命中 {total} 名校友；维度={('、'.join(dims) if dims else '无')}"
            ),
            "evidences": [
                {
                    "title": "源专家教育属性",
                    "businessTable": "专家教育经历",
                    "technicalTable": (expert.get("provenance") or {}).get("sourceTable") or "-",
                    "recordId": str(expert.get("id") or ""),
                    "fieldIdentifier": "education_background_institution_zh/_en",
                    "sourceField": (expert.get("provenance") or {}).get("sourceField") or "-",
                    "graphVid": (expert.get("provenance") or {}).get("graphVid")
                    or str(expert.get("id") or ""),
                    "summary": (f"解析教育经历 {len(expert.get('educations') or [])} 条"),
                },
                *[
                    {
                        "title": f"校友匹配 · {item.get('name') or item.get('alumniId')}",
                        "businessTable": "校友关系查询结果",
                        "technicalTable": (item.get("provenance") or {}).get("sourceTable") or "-",
                        "recordId": str(item.get("alumniId") or ""),
                        "fieldIdentifier": "/".join(item.get("dimensions") or ["同校"]),
                        "sourceField": (item.get("provenance") or {}).get("sourceField") or "-",
                        "graphVid": (item.get("provenance") or {}).get("graphVid")
                        or str(item.get("alumniId") or ""),
                        "summary": (
                            f"共享院校："
                            f"{'、'.join(item.get('sharedInstitutions') or []) or '—'}；"
                            f"{(item.get('interactions') or {}).get('summary') or ''}"
                        ),
                    }
                    for item in items[:8]
                ],
            ],
        }

        return {
            "summaryRows": summary_rows,
            "resultRows": result_rows,
            "evidence": evidence,
            "rules": ALUMNI_RULES[:1],
            "entities": entities,
            "relations": relations,
            "graph": graph,
            "provenance": provenance,
        }

    @staticmethod
    def _build_graph_entities(
        expert: dict[str, Any], items: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
        cx, cy, radius = 220.0, 200.0, 180.0
        source_id = str(expert.get("id") or "source")
        source_name = str(expert.get("name") or source_id)
        entities: list[dict[str, Any]] = [
            {
                "id": source_id,
                "label": source_name,
                "entityType": "科技专家",
                "nodeType": "main",
                "confidence": 1.0,
                "relations": f"校友 {len(items)}",
                "evidence": [
                    f"educations={len(expert.get('educations') or [])}",
                ],
            }
        ]
        relations: list[dict[str, Any]] = []
        nodes = [
            {
                **entities[0],
                "x": cx,
                "y": cy,
            }
        ]
        edges: list[dict[str, Any]] = []

        for index, item in enumerate(items[:12]):
            aid = str(item.get("alumniId") or f"alumni-{index}")
            aname = str(item.get("name") or aid)
            dims = item.get("dimensions") or []
            dim_text = "、".join(dims) if dims else "同校"
            shared = "、".join(item.get("sharedInstitutions") or []) or "—"
            interaction = (item.get("interactions") or {}).get("summary") or "无互动"
            entity = {
                "id": aid,
                "label": aname,
                "entityType": "校友专家",
                "nodeType": "expert",
                "confidence": 0.9,
                "relations": dim_text,
                "evidence": [f"shared={shared}", interaction],
            }
            entities.append(entity)
            angle = (math.pi * 2 * index) / max(len(items[:12]), 1) - math.pi / 2
            nodes.append(
                {
                    **entity,
                    "x": cx + math.cos(angle) * radius + 200.0,
                    "y": cy + math.sin(angle) * radius,
                }
            )
            rel_id = f"alumni-{source_id}-{aid}"
            relation = {
                "id": rel_id,
                "from": source_id,
                "to": aid,
                "fromName": source_name,
                "toName": aname,
                "label": dims[0] if dims else "校友",
                "category": "校友",
                "dimensions": dims,
                "sharedInstitutions": item.get("sharedInstitutions") or [],
                "interactions": item.get("interactions") or {},
            }
            relations.append(relation)
            edges.append(
                {
                    "id": rel_id,
                    "from": source_id,
                    "to": aid,
                    "label": relation["label"],
                    "category": "校友",
                }
            )

        return entities, relations, {"nodes": nodes, "edges": edges}
