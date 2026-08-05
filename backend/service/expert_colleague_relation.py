from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, Protocol

from service.base_module import KGModuleScaffoldService

PERSON_LABELS = {"Person", "Scholar", "Expert"}
ACHIEVEMENT_LABELS = {"Paper", "Project", "Patent", "Report", "Award"}
TEAM_LABELS = {"Team", "Laboratory", "Department", "Project"}
NAME_KEYS = ("name_zh", "name", "title", "name_en")
ORG_KEYS = ("scholar_org", "organization", "affiliation_name", "institution_zh")
DEPARTMENT_KEYS = ("work_experience_department_zh", "department", "team_name")
DATE_KEYS = ("work_experience_date", "employment_period", "tenure_period")


class GraphSearchGateway(Protocol):
    """业务层只依赖 FastAPI 查图契约，不依赖图数据库或 DAO。"""

    api_calls: list[dict[str, Any]]

    async def resolve_person(self, keyword: str, space: str | None) -> dict[str, Any] | None: ...

    async def subgraph(
        self,
        node_id: str,
        *,
        depth: int,
        limit: int,
        direction: str = "both",
        edge_type: str | None = None,
        space: str | None = None,
    ) -> dict[str, Any]: ...


class ExpertColleagueRelationService(KGModuleScaffoldService):
    module_code = "expert_colleague_relation"

    async def query(
        self,
        gateway: GraphSearchGateway,
        *,
        expert_id: str,
        organization: str | None = None,
        department: str | None = None,
        overlap_period: str | None = None,
        limit: int = 20,
        space: str | None = None,
    ) -> dict[str, Any]:
        expert_node = await gateway.resolve_person(expert_id, space)
        if expert_node is None:
            raise LookupError(f"未找到专家: {expert_id}")

        expert = self._expert(expert_node)
        affiliation_graph = await gateway.subgraph(
            expert_node["id"],
            depth=1,
            limit=100,
            direction="out",
            edge_type="AFFILIATED_WITH",
            space=space,
        )
        affiliations = self._affiliations(expert_node["id"], affiliation_graph)
        if organization:
            affiliations = [
                item for item in affiliations if self._contains(item["name"], organization)
            ]
        if not expert.get("organization") and affiliations:
            expert["organization"] = affiliations[0]["name"]

        coauthor_graph = await gateway.subgraph(
            expert_node["id"],
            depth=1,
            limit=200,
            direction="both",
            edge_type="COAUTHOR_WITH",
            space=space,
        )
        coauthor_counts = self._coauthor_counts(expert_node["id"], coauthor_graph)
        context_graph = await gateway.subgraph(
            expert_node["id"],
            depth=2,
            limit=200,
            direction="both",
            space=space,
        )
        context = self._context_index(context_graph)

        requested_period = self._parse_period(overlap_period)
        candidates: dict[str, dict[str, Any]] = {}
        for affiliation in affiliations:
            org_graph = await gateway.subgraph(
                affiliation["id"],
                depth=1,
                limit=200,
                direction="in",
                edge_type="AFFILIATED_WITH",
                space=space,
            )
            # 入边按 source(人) 索引：候选人→机构的 AFFILIATED_WITH 边携带其任职时间/部门
            edge_by_person: dict[str, dict[str, Any]] = {}
            for edge in org_graph.get("edges", []):
                if edge.get("type") != "AFFILIATED_WITH":
                    continue
                edge_by_person[str(edge.get("source"))] = edge.get("properties", {}) or {}
            for node in org_graph.get("nodes", []):
                if node.get("id") == expert_node["id"] or not self._is_person(node):
                    continue
                candidate_id = str(node.get("id", ""))
                edge_props = edge_by_person.get(candidate_id, {})
                candidate_department = self._property({"properties": edge_props}, DEPARTMENT_KEYS)
                if department and not self._contains(candidate_department, department):
                    continue
                candidate_period = self._parse_period(
                    self._property({"properties": edge_props}, DATE_KEYS)
                )
                overlap = self._overlap(
                    affiliation.get("period"), candidate_period, requested_period
                )
                if overlap is False:
                    continue
                shared = context["neighbors"].get(expert_node["id"], set()) & context[
                    "neighbors"
                ].get(candidate_id, set())
                shared_nodes = [
                    context["nodes"][node_id] for node_id in shared if node_id in context["nodes"]
                ]
                achievements = [
                    self._achievement(item)
                    for item in shared_nodes
                    if self._labels(item) & ACHIEVEMENT_LABELS
                ]
                teams = [
                    self._node_name(item)
                    for item in shared_nodes
                    if self._labels(item) & TEAM_LABELS
                ]
                co_papers = coauthor_counts.get(candidate_id, 0)
                if co_papers and not any(item["type"] == "Paper" for item in achievements):
                    achievements.append(
                        {
                            "id": f"coauthor:{expert_node['id']}:{candidate_id}",
                            "type": "Paper",
                            "title": f"共同论文 {co_papers} 篇",
                            "year": None,
                        }
                    )
                item = self._build_relation(
                    node=node,
                    organization=affiliation["name"],
                    department=candidate_department or affiliation.get("department") or "",
                    overlap=overlap,
                    teams=teams,
                    achievements=achievements,
                    co_papers=co_papers,
                )
                previous = candidates.get(candidate_id)
                if previous is None or item["confidence"] > previous["confidence"]:
                    candidates[candidate_id] = item

        colleagues = sorted(
            candidates.values(),
            key=lambda item: (item["confidence"], len(item["achievements"])),
            reverse=True,
        )[:limit]
        return {
            "expert": expert,
            "colleagues": colleagues,
            "total": len(colleagues),
            "summary": self._summary(colleagues),
            "graph": self._build_graph(expert, colleagues),
            "apiCalls": list(gateway.api_calls),
        }

    def _affiliations(self, person_id: str, graph: dict[str, Any]) -> list[dict[str, Any]]:
        nodes = {str(node.get("id")): node for node in graph.get("nodes", [])}
        result: list[dict[str, Any]] = []
        for edge in graph.get("edges", []):
            if edge.get("type") != "AFFILIATED_WITH" or str(edge.get("source")) != person_id:
                continue
            target = nodes.get(str(edge.get("target")), {})
            edge_props = edge.get("properties", {}) or {}
            edge_node = {"properties": edge_props}
            name = self._node_name(target) or self._property(edge_node, ORG_KEYS)
            if name:
                result.append(
                    {
                        "id": str(edge.get("target")),
                        "name": name,
                        "period": self._parse_period(self._property(edge_node, DATE_KEYS)),
                        "department": self._property(edge_node, DEPARTMENT_KEYS),
                    }
                )
        return result

    def _build_relation(
        self,
        *,
        node: dict[str, Any],
        organization: str,
        department: str,
        overlap: tuple[int, int] | None | bool,
        teams: list[str],
        achievements: list[dict[str, Any]],
        co_papers: int,
    ) -> dict[str, Any]:
        has_period = isinstance(overlap, tuple)
        effective_period = f"{overlap[0]}-{overlap[1]}" if has_period else "任职时间待补录"
        overlap_years = overlap[1] - overlap[0] + 1 if has_period else None
        confidence = 0.58 + (0.18 if has_period else 0) + (0.08 if department else 0)
        confidence += min(0.12, co_papers * 0.02) + (0.04 if teams else 0)
        evidence = [f"共同任职机构：{organization}"]
        if has_period:
            evidence.append(f"任职时间重叠：{effective_period}（{overlap_years} 年）")
        else:
            evidence.append("任职时间字段不完整，已标记人工复核")
        if department:
            evidence.append(f"部门/团队：{department}")
        if achievements:
            evidence.append(f"同事期间关联合作成果 {len(achievements)} 项")
        scenes = ["同机构任职"]
        if department:
            scenes.append("同部门/团队协作")
        if co_papers:
            scenes.append("论文合作")
        if teams:
            scenes.append("项目组协作")
        return {
            "colleague": self._expert(node),
            "commonOrganization": organization,
            "commonDepartment": department or None,
            "commonTeamOrProject": sorted(set(teams))[:5],
            "effectivePeriod": effective_period,
            "overlapYears": overlap_years,
            "workContent": [item["title"] for item in achievements[:5]] or ["共同机构业务协作"],
            "collaborationScenes": scenes,
            "achievements": achievements[:10],
            "confidence": round(min(confidence, 0.98), 2),
            "evidence": evidence,
            "reviewRequired": not has_period,
        }

    def _summary(self, colleagues: list[dict[str, Any]]) -> dict[str, Any]:
        teams = {team for item in colleagues for team in item["commonTeamOrProject"]}
        achievements = {
            achievement["id"] for item in colleagues for achievement in item["achievements"]
        }
        overlaps = [item["overlapYears"] for item in colleagues if item["overlapYears"] is not None]
        return {
            "colleagueCount": len(colleagues),
            "teamCount": len(teams),
            "maxOverlapYears": max(overlaps, default=0),
            "achievementCount": len(achievements),
            "reviewRequiredCount": sum(bool(item["reviewRequired"]) for item in colleagues),
            "generatedAt": datetime.now(UTC).isoformat(),
        }

    def _build_graph(
        self, expert: dict[str, Any], colleagues: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, Any]]]:
        nodes = [{"id": expert["id"], "type": "expert", "label": expert["name"], "data": expert}]
        edges: list[dict[str, Any]] = []
        for item in colleagues:
            colleague = item["colleague"]
            nodes.append(
                {
                    "id": colleague["id"],
                    "type": "expert",
                    "label": colleague["name"],
                    "data": colleague,
                }
            )
            edges.append(
                {
                    "source": expert["id"],
                    "target": colleague["id"],
                    "label": "同事关系",
                    "data": {
                        "organization": item["commonOrganization"],
                        "period": item["effectivePeriod"],
                        "confidence": item["confidence"],
                    },
                }
            )
        return {"nodes": nodes, "edges": edges}

    def _context_index(self, graph: dict[str, Any]) -> dict[str, Any]:
        nodes = {str(node.get("id")): node for node in graph.get("nodes", [])}
        neighbors: dict[str, set[str]] = defaultdict(set)
        for edge in graph.get("edges", []):
            source, target = str(edge.get("source")), str(edge.get("target"))
            neighbors[source].add(target)
            neighbors[target].add(source)
        return {"nodes": nodes, "neighbors": neighbors}

    def _coauthor_counts(self, expert_id: str, graph: dict[str, Any]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for edge in graph.get("edges", []):
            if edge.get("type") != "COAUTHOR_WITH":
                continue
            source, target = str(edge.get("source")), str(edge.get("target"))
            other = target if source == expert_id else source
            value = edge.get("properties", {}).get("co_paper_count", 1)
            counts[other] = max(counts.get(other, 0), int(value or 0))
        return counts

    def _achievement(self, node: dict[str, Any]) -> dict[str, Any]:
        labels = self._labels(node)
        kind = next((label for label in labels if label in ACHIEVEMENT_LABELS), "Achievement")
        year = self._year(
            self._property(node, ("year", "publish_year", "start_year", "publication_date"))
        )
        return {
            "id": str(node.get("id", "")),
            "type": kind,
            "title": self._node_name(node),
            "year": year,
        }

    def _expert(self, node: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(node.get("id", "")),
            "name": self._node_name(node),
            "organization": self._property(node, ORG_KEYS) or None,
            "department": self._property(node, DEPARTMENT_KEYS) or None,
            "title": self._property(
                node, ("work_experience_position_zh", "professional_title", "position")
            )
            or None,
        }

    def _parse_period(self, value: str | None) -> tuple[int, int] | None:
        years = [int(item) for item in re.findall(r"(?:19|20)\d{2}", value or "")]
        if not years:
            return None
        start, end = min(years), max(years)
        if len(years) == 1 and re.search(r"至今|present|current|now", value or "", re.I):
            end = datetime.now().year
        return start, end

    def _overlap(
        self,
        left: tuple[int, int] | None,
        right: tuple[int, int] | None,
        requested: tuple[int, int] | None,
    ) -> tuple[int, int] | None | bool:
        if left is None or right is None:
            return None
        ranges = [item for item in (left, right, requested) if item]
        start = max(item[0] for item in ranges)
        end = min(item[1] for item in ranges)
        return (start, end) if start <= end else False

    def _is_person(self, node: dict[str, Any]) -> bool:
        return bool(self._labels(node) & PERSON_LABELS)

    def _labels(self, node: dict[str, Any]) -> set[str]:
        return {str(item) for item in node.get("labels", [])}

    def _node_name(self, node: dict[str, Any]) -> str:
        return self._property(node, NAME_KEYS) or str(node.get("id", ""))

    def _property(self, node: dict[str, Any], keys: tuple[str, ...]) -> str:
        props = node.get("properties", {}) or {}
        for key in keys:
            value = props.get(key)
            if value not in (None, "", []):
                if isinstance(value, list):
                    return "；".join(str(item) for item in value)
                return str(value)
        return ""

    def _contains(self, value: str, keyword: str) -> bool:
        return keyword.strip().casefold() in value.casefold()

    def _year(self, value: str) -> int | None:
        match = re.search(r"(?:19|20)\d{2}", value)
        return int(match.group()) if match else None
