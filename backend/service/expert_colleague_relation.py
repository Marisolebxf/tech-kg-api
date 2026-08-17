from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, Protocol

from service.base_module import KGModuleScaffoldService

PERSON_LABELS = {"Person", "Scholar", "Expert"}
ACHIEVEMENT_LABELS = {"Paper", "Project", "Patent", "Report", "Award"}
TEAM_LABELS = {"Team", "Laboratory", "Department", "Project"}
NAME_KEYS = ("name_zh", "name_cn", "name", "title", "name_en")
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
            depth=1,
            limit=200,
            direction="both",
            space=space,
        )
        context = self._context_index(context_graph)

        requested_period = self._parse_period(overlap_period)
        skipped_missing_period = 0
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
                if overlap is None:
                    skipped_missing_period += 1
                    continue
                if overlap is False:
                    continue
                expert_department = affiliation.get("department") or ""
                common_department = (
                    candidate_department
                    if candidate_department
                    and expert_department
                    and self._same_text(candidate_department, expert_department)
                    else ""
                )
                if department and not self._contains(common_department, department):
                    continue
                candidate_graph = await gateway.subgraph(
                    candidate_id, depth=1, limit=200, direction="both", space=space
                )
                candidate_context = self._context_index(candidate_graph)
                context["nodes"].update(candidate_context["nodes"])
                shared = context["neighbors"].get(expert_node["id"], set()) & candidate_context[
                    "neighbors"
                ].get(candidate_id, set())
                shared_nodes = [
                    context["nodes"][node_id] for node_id in shared if node_id in context["nodes"]
                ]
                achievements = [
                    self._achievement(item)
                    for item in shared_nodes
                    if self._labels(item) & ACHIEVEMENT_LABELS
                    and self._node_within_period(item, overlap)
                ]
                teams = [
                    self._node_name(item)
                    for item in shared_nodes
                    if self._labels(item) & TEAM_LABELS
                ]
                co_papers = coauthor_counts.get(candidate_id, 0)

                item = self._build_relation(
                    node=node,
                    organization=affiliation["name"],
                    organization_entity=affiliation["entity"],
                    department=common_department,
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
            "summary": self._summary(expert, colleagues, skipped_missing_period),
            "graph": self._build_graph(expert, colleagues),
            "rules": self._rules(colleagues),
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
                        "entity": self._entity_data(target, {"name": name}),
                    }
                )
        return result

    def _build_relation(
        self,
        *,
        node: dict[str, Any],
        organization: str,
        organization_entity: dict[str, Any],
        department: str,
        overlap: tuple[int, int] | None | bool,
        teams: list[str],
        achievements: list[dict[str, Any]],
        co_papers: int,
    ) -> dict[str, Any]:
        has_period = isinstance(overlap, tuple)
        effective_period = self._format_period(overlap) if has_period else ""
        overlap_months = self._period_months(overlap) if has_period else None
        overlap_years = round(overlap_months / 12, 1) if overlap_months else None
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
            "organizationEntity": organization_entity,
            "commonDepartment": department or None,
            "commonTeamOrProject": sorted(set(teams))[:5],
            "effectivePeriod": effective_period,
            "overlapMonths": overlap_months,
            "overlapYears": overlap_years,
            "workContent": [item["title"] for item in achievements[:5]] or ["共同机构业务协作"],
            "collaborationScenes": scenes,
            "achievements": achievements[:10],
            "confidence": round(min(confidence, 0.98), 2),
            "evidence": evidence,
            "reviewRequired": False,
        }

    def _rules(self, colleagues: list[dict[str, Any]]) -> list[dict[str, Any]]:
        team_hits = sum(1 for item in colleagues if item.get("commonTeamOrProject"))
        achievement_hits = sum(1 for item in colleagues if item.get("achievements"))
        return [
            {
                "name": "任职时间匹配规则",
                "type": "关系匹配规则",
                "target": "专家、AFFILIATED_WITH 任职边、机构实体",
                "trigger": "输入专家后查询其任职机构，再反查同机构任职人员",
                "logic": "比较核心专家和候选专家在同一机构任职边上的起止时间，并与请求 overlapPeriod 求交集；存在至少 1 个月有效交集即判定同事。",
                "output": "同事关系、生效时段、重叠月份、重叠年限、关系置信度",
                "threshold": "任职时间存在至少 1 个月交集",
                "audit": "任一任职边缺少时间或来源冲突时不生成同事关系，计入待复核",
                "appliedCount": len(colleagues),
            },
            {
                "name": "团队归属规则",
                "type": "实体匹配规则",
                "target": "机构、部门、实验室、项目组实体",
                "trigger": "同事候选已通过同机构与任职时间匹配",
                "logic": "对部门、实验室、项目组名称做规范化比较，并结合共同邻接团队或项目节点补充所属团队或协作场景。",
                "output": "共同团队、部门或项目组、协作场景",
                "threshold": "机构已直接命中，团队或部门名称规范化后相同或存在共同团队节点",
                "audit": "机构别名冲突或层级不明时进入人工确认",
                "appliedCount": team_hits,
            },
            {
                "name": "同事成果关联规则",
                "type": "关系增强规则",
                "target": "同事期间论文、项目、专利、成果记录",
                "trigger": "同事关系已确认",
                "logic": "回溯两名专家共同连接的成果节点，仅保留成果年份落入同事生效时段的记录，作为共同工作内容和协作证据。",
                "output": "期间成果、共同工作内容、协作说明",
                "threshold": "成果时间落入同事关系有效区间",
                "audit": "成果时间或归属冲突时进入人工复核",
                "appliedCount": achievement_hits,
            },
        ]

    def _summary(
        self, expert: dict[str, Any], colleagues: list[dict[str, Any]], skipped_missing_period: int
    ) -> dict[str, Any]:
        teams = {team for item in colleagues for team in item["commonTeamOrProject"]}
        achievements = {
            achievement["id"] for item in colleagues for achievement in item["achievements"]
        }
        overlaps = [item["overlapYears"] for item in colleagues if item["overlapYears"] is not None]
        primary = colleagues[0] if colleagues else None
        return {
            "coreExpert": f"{expert['name']} | {expert.get('title') or '-'}",
            "coreExpertOrganization": expert.get("organization") or "-",
            "primaryColleague": (
                f"{primary['colleague']['name']} | {primary['colleague'].get('title') or '-'}"
                if primary
                else "-"
            ),
            "commonOrganization": primary["commonOrganization"] if primary else "-",
            "departmentOrTeam": (
                " | ".join(
                    filter(
                        None,
                        [primary.get("commonDepartment"), *primary.get("commonTeamOrProject", [])],
                    )
                )
                or "-"
                if primary
                else "-"
            ),
            "effectivePeriod": primary["effectivePeriod"] if primary else "-",
            "overlapDuration": (f"{primary['overlapMonths']}个月" if primary else "-"),
            "workContent": ("、".join(primary["workContent"]) if primary else "-"),
            "collaborationScenes": ("、".join(primary["collaborationScenes"]) if primary else "-"),
            "periodAchievements": (f"{len(primary['achievements'])}项" if primary else "0项"),
            "colleagueCount": len(colleagues),
            "teamCount": len(teams),
            "maxOverlapYears": max(overlaps, default=0),
            "achievementCount": len(achievements),
            "reviewRequiredCount": skipped_missing_period,
            "generatedAt": datetime.now(UTC).isoformat(),
        }

    def _build_graph(
        self, expert: dict[str, Any], colleagues: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, Any]]]:
        node_map: dict[str, dict[str, Any]] = {
            expert["id"]: {
                "id": expert["id"],
                "type": "expert",
                "label": expert["name"],
                "data": expert,
            }
        }
        edge_map: dict[tuple[str, str, str], dict[str, Any]] = {}

        def add_edge(
            source: str, target: str, label: str, data: dict[str, Any] | None = None
        ) -> None:
            edge_map[(source, target, label)] = {
                "source": source,
                "target": target,
                "label": label,
                "data": data or {},
            }

        for item in colleagues:
            colleague = item["colleague"]
            node_map[colleague["id"]] = {
                "id": colleague["id"],
                "type": "expert",
                "label": colleague["name"],
                "data": colleague,
            }
            add_edge(
                expert["id"],
                colleague["id"],
                "同事关系",
                {
                    "organization": item["commonOrganization"],
                    "period": item["effectivePeriod"],
                    "confidence": item["confidence"],
                    "evidence": item["evidence"],
                    "ruleName": "任职时间匹配规则",
                },
            )
            org_id = f"colleague-org:{self._graph_key(item['commonOrganization'])}"
            node_map[org_id] = {
                "id": org_id,
                "type": "organization",
                "label": item["commonOrganization"],
                "data": {**item["organizationEntity"], "confidence": item["confidence"]},
            }
            add_edge(expert["id"], org_id, "共同任职", {"period": item["effectivePeriod"]})
            add_edge(colleague["id"], org_id, "共同任职", {"period": item["effectivePeriod"]})
            for team in item["commonTeamOrProject"]:
                team_id = f"colleague-team:{self._graph_key(team)}"
                node_map[team_id] = {
                    "id": team_id,
                    "type": "project",
                    "label": team,
                    "data": {"name": team},
                }
                add_edge(org_id, team_id, "所属团队")
            for achievement in item["achievements"]:
                achievement_id = achievement["id"]
                node_type = achievement["type"].casefold()
                node_map[achievement_id] = {
                    "id": achievement_id,
                    "type": node_type,
                    "label": achievement["title"],
                    "data": achievement,
                }
                add_edge(expert["id"], achievement_id, "合作成果")
                add_edge(colleague["id"], achievement_id, "合作成果")
        return {"nodes": list(node_map.values()), "edges": list(edge_map.values())}

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
            **self._entity_data(node, {}),
        }

    def _expert(self, node: dict[str, Any]) -> dict[str, Any]:
        return {
            **self._entity_data(node, {}),
            "id": str(node.get("id", "")),
            "name": self._node_name(node),
            "organization": self._property(node, ORG_KEYS) or None,
            "department": self._property(node, DEPARTMENT_KEYS) or None,
            "title": self._property(
                node, ("work_experience_position_zh", "professional_title", "position")
            )
            or None,
        }

    def _entity_data(self, node: dict[str, Any], normalized: dict[str, Any]) -> dict[str, Any]:
        properties = node.get("properties", {}) or {}
        source_table = properties.get("organization_base") or properties.get("source_table")
        if properties.get("organization_id") not in (None, ""):
            source_field, source_value = "organization_id", properties.get("organization_id")
        else:
            source_field, source_value = "source_record_id", properties.get("source_record_id")
        raw_confidence = properties.get("confidence", 1.0)
        try:
            confidence = float(raw_confidence)
        except (TypeError, ValueError):
            confidence = 1.0
        return {
            **normalized,
            "confidence": max(0.0, min(confidence, 1.0)),
            "details": properties,
            "provenance": {
                "sourceTable": str(source_table or "-"),
                "sourceField": source_field,
                "sourceValue": str(source_value or "-"),
                "ingestBatch": str(properties.get("ingest_batch") or "-"),
                "ingestTime": str(properties.get("ingest_time") or "-"),
            },
        }

    def _parse_period(self, value: str | None) -> tuple[int, int] | None:
        text = value or ""
        matches = re.findall(r"((?:19|20)\d{2})(?:[-/.年](0?[1-9]|1[0-2])(?!\d))?", text)
        if not matches:
            return None
        start_year, start_month = matches[0]
        start = int(start_year) * 12 + (int(start_month) - 1 if start_month else 0)
        if len(matches) > 1:
            end_year, end_month = matches[-1]
            end = int(end_year) * 12 + (int(end_month) - 1 if end_month else 11)
        elif re.search(r"至今|present|current|now", text, re.I):
            now = datetime.now()
            end = now.year * 12 + now.month - 1
        else:
            end = int(start_year) * 12 + (int(start_month) - 1 if start_month else 11)
        return (start, end) if start <= end else (end, start)

    def _period_months(self, period: tuple[int, int]) -> int:
        return period[1] - period[0] + 1

    def _format_period(self, period: tuple[int, int]) -> str:
        def display(point: int) -> str:
            year, month = divmod(point, 12)
            return f"{year:04d}-{month + 1:02d}"

        return f"{display(period[0])} 至 {display(period[1])}"

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

    def _same_text(self, left: str, right: str) -> bool:
        def normalize(value: str) -> str:
            return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.casefold())

        return bool(normalize(left) and normalize(left) == normalize(right))

    def _node_within_period(self, node: dict[str, Any], period: tuple[int, int]) -> bool:
        year = self._year(
            self._property(node, ("year", "publish_year", "start_year", "publication_date"))
        )
        return bool(year and period[0] <= year * 12 + 11 and year * 12 <= period[1])

    def _graph_key(self, value: str) -> str:
        return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "-", value.casefold()).strip("-") or "unknown"

    def _year(self, value: str) -> int | None:
        match = re.search(r"(?:19|20)\d{2}", value)
        return int(match.group()) if match else None
