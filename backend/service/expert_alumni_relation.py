"""科技专家校友关系：基于 Person 教育属性匹配，仅查询返回，不写 ALUMNI 边。"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from infra.graph_db import TRSGraphClient, get_techkg_client
from infra.graph_db.config import TRSGraphSettings
from service.base_module import KGModuleScaffoldService

PERSON_LABELS = ("Person", "Scholar")
LIST_PAGE_SIZE = 50
LIST_MAX_PAGES = 10
EDGE_LIMIT = 200

PAPER_EDGE_TYPES = frozenset({"AUTHORED_BY"})
PATENT_EDGE_TYPES = frozenset({"INVENTED_BY"})
PROJECT_EDGE_TYPES = frozenset({"LEADS", "HAS_PARTICIPANT"})
COAUTHOR_EDGE = "COAUTHOR_WITH"


class ExpertAlumniRelationService(KGModuleScaffoldService):
    module_code = "expert_alumni_relation"

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
        expert_id: str,
        target_expert_id: str | None = None,
        school: str | None = None,
        education_stage: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        graph = self._client()
        source = self._require_node(graph, expert_id, "专家")
        source_edus = self._parse_educations(getattr(source, "properties", None) or {})
        truncated = False

        if target_expert_id:
            if target_expert_id == expert_id:
                raise ValueError("expertId 与 targetExpertId 不能相同")
            target = self._require_node(graph, target_expert_id, "专家")
            candidates = [(target_expert_id, target)]
            mode = "pair"
        else:
            mode = "list"
            candidates, truncated = self._scan_person_candidates(graph, expert_id)

        items: list[dict[str, Any]] = []
        dim_catalog: set[str] = set()

        for cand_id, cand_node in candidates:
            cand_props = getattr(cand_node, "properties", None) or {}
            cand_edus = self._parse_educations(cand_props)
            match = self._match_alumni(source_edus, cand_edus, school, education_stage)
            if match is None:
                continue
            shared_institutions, dimensions, match_summary = match
            interactions = self._interactions(graph, expert_id, cand_id)
            item = {
                "alumniId": str(cand_id),
                "name": self._display_name(cand_node),
                "sharedInstitutions": shared_institutions,
                "dimensions": dimensions,
                "educations": match_summary,
                "interactions": interactions,
            }
            items.append(item)
            dim_catalog.update(dimensions)
            if mode == "list" and len(items) >= limit:
                break

        if mode == "pair" and not items:
            # pair 模式无匹配仍返回空列表 total=0
            pass

        space = (
            getattr(getattr(graph, "_settings", None), "space", None)
            or TRSGraphSettings.from_env().space
        )

        return {
            "expert": {
                "id": expert_id,
                "name": self._display_name(source),
                "educations": source_edus,
            },
            "mode": mode,
            "total": len(items),
            "items": items,
            "dimensionsCatalog": sorted(dim_catalog),
            "sourceMeta": {
                "space": space,
                "graph": "trs-graph",
                "truncated": truncated and mode == "list",
            },
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

    def _scan_person_candidates(
        self, graph: TRSGraphClient, exclude_id: str
    ) -> tuple[list[tuple[str, Any]], bool]:
        candidates: list[tuple[str, Any]] = []
        truncated = False
        seen: set[str] = set()
        for label in PERSON_LABELS:
            for page in range(LIST_MAX_PAGES):
                try:
                    page_result = graph.get_nodes_by_label(
                        label, limit=LIST_PAGE_SIZE, offset=page * LIST_PAGE_SIZE
                    )
                except Exception:
                    break
                items = getattr(page_result, "items", None) or []
                if not items:
                    break
                for node in items:
                    nid = str(getattr(node, "id", "") or "")
                    if not nid or nid == exclude_id or nid in seen:
                        continue
                    seen.add(nid)
                    candidates.append((nid, node))
                if len(items) < LIST_PAGE_SIZE:
                    break
                if page == LIST_MAX_PAGES - 1:
                    truncated = True
            if candidates:
                # Prefer first label that returns data (Person OR Scholar)
                break
        return candidates, truncated

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
        stage_norm = self._norm_text(education_stage) if education_stage else ""

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
                if stage_norm and stage_norm not in s_deg and stage_norm not in c_deg:
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

    def _interactions(self, graph: TRSGraphClient, a_id: str, b_id: str) -> dict[str, Any]:
        coauthor = False
        try:
            edges = graph.get_node_edges(a_id, direction="both", limit=EDGE_LIMIT)
        except Exception:
            edges = []

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
        except Exception:
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
