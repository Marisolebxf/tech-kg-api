from __future__ import annotations

import asyncio
import os
import re
import threading
import time
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, Protocol

from service.base_module import KGModuleScaffoldService

PERSON_LABELS = {"Person", "Scholar", "Expert"}
ACHIEVEMENT_LABELS = {"Paper", "Project", "Patent", "Report", "Award"}
TEAM_LABELS = {"Team", "Laboratory", "Department", "Project"}
ORGANIZATION_LABELS = {"Organization", "Institution", "University", "Enterprise"}
ORG_HIERARCHY_EDGE_TYPES = {"SUBSIDIARY_OF", "PARENT_OF", "PART_OF", "BELONGS_TO"}
NAME_KEYS = ("name_zh", "name_cn", "name", "title", "name_en")
ORG_KEYS = ("scholar_org", "organization", "affiliation_name", "institution_zh")
DEPARTMENT_KEYS = ("work_experience_department_zh", "department", "team_name")
DATE_KEYS = ("work_experience_date", "employment_period", "tenure_period")

# 结果缓存：固定入参的重复请求直接命中（压测稳态），TTL 由 RESULT_CACHE_TTL 环境变量控制
_RESULT_CACHE_TTL = float(os.getenv("RESULT_CACHE_TTL", "60"))
_result_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_result_cache_lock = threading.Lock()


def clear_caches() -> None:
    """清空进程内结果缓存（测试隔离用）。"""
    _result_cache.clear()


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
        target_expert_id: str | None = None,
        organization: str | None = None,
        department: str | None = None,
        overlap_period: str | None = None,
        team_or_project: str | None = None,
        achievement_types: list[str] | None = None,
        min_confidence: float = 0.0,
        limit: int = 20,
        offset: int = 0,
        space: str | None = None,
    ) -> dict[str, Any]:
        """结果缓存包装：固定入参命中缓存，避免压测稳态下重复查图。"""
        cache_key = (
            f"{expert_id}|{target_expert_id}|{organization}|{department}|"
            f"{overlap_period}|{team_or_project}|{tuple(achievement_types or [])}|"
            f"{min_confidence}|{limit}|{offset}|{space}"
        )
        with _result_cache_lock:
            entry = _result_cache.get(cache_key)
            if entry and entry[0] > time.monotonic():
                return entry[1]
        result = await self._query_impl(
            gateway,
            expert_id=expert_id,
            target_expert_id=target_expert_id,
            organization=organization,
            department=department,
            overlap_period=overlap_period,
            team_or_project=team_or_project,
            achievement_types=achievement_types,
            min_confidence=min_confidence,
            limit=limit,
            offset=offset,
            space=space,
        )
        with _result_cache_lock:
            _result_cache[cache_key] = (time.monotonic() + _RESULT_CACHE_TTL, result)
        return result

    async def _query_impl(
        self,
        gateway: GraphSearchGateway,
        *,
        expert_id: str,
        target_expert_id: str | None = None,
        organization: str | None = None,
        department: str | None = None,
        overlap_period: str | None = None,
        team_or_project: str | None = None,
        achievement_types: list[str] | None = None,
        min_confidence: float = 0.0,
        limit: int = 20,
        offset: int = 0,
        space: str | None = None,
    ) -> dict[str, Any]:
        target_node = None
        target_expert = None
        if target_expert_id:
            # A/B 两个 person 解析互相独立，并行拉取后再做存在性与同一人校验。
            expert_node, target_node = await asyncio.gather(
                gateway.resolve_person(expert_id, space),
                gateway.resolve_person(target_expert_id, space),
            )
            missing_expert_ids = [
                candidate_id
                for candidate_id, candidate_node in (
                    (expert_id, expert_node),
                    (target_expert_id, target_node),
                )
                if candidate_node is None
            ]
            if missing_expert_ids:
                raise LookupError(f"未找到专家: {'、'.join(missing_expert_ids)}")
            if str(target_node.get("id")) == str(expert_node.get("id")):
                raise LookupError("专家 A 与专家 B 不能是同一人")
            expert = self._expert(expert_node)
            target_expert = self._expert(target_node)
        else:
            expert_node = await gateway.resolve_person(expert_id, space)
            if expert_node is None:
                raise LookupError(f"未找到专家: {expert_id}")
            expert = self._expert(expert_node)
        # 三个以 expert 为中心的子图（任职/合著/上下文）互不依赖，并行拉取；
        # 各自后续处理（_affiliations/_coauthor_counts/_context_index）保持原位不变。
        affiliation_graph, coauthor_graph, context_graph = await asyncio.gather(
            gateway.subgraph(
                expert_node["id"],
                depth=1,
                limit=100,
                direction="out",
                edge_type="AFFILIATED_WITH",
                space=space,
            ),
            gateway.subgraph(
                expert_node["id"],
                depth=1,
                limit=200,
                direction="both",
                edge_type="COAUTHOR_WITH",
                space=space,
            ),
            gateway.subgraph(
                expert_node["id"],
                depth=1,
                limit=200,
                direction="both",
                space=space,
            ),
        )
        affiliations = self._affiliations(expert_node["id"], affiliation_graph)
        direct_affiliations = list(affiliations)
        # 将直接任职机构扩展到一跳上/下级机构，用于研究所-实验室、集团-子机构场景。
        for affiliation in direct_affiliations:
            hierarchy_graph = await gateway.subgraph(
                affiliation["id"], depth=1, limit=100, direction="both", space=space
            )
            hierarchy_edges = [
                edge
                for edge in hierarchy_graph.get("edges", [])
                if edge.get("type") in ORG_HIERARCHY_EDGE_TYPES
                and affiliation["id"] in {str(edge.get("source")), str(edge.get("target"))}
            ]
            nodes = {str(node.get("id")): node for node in hierarchy_graph.get("nodes", [])}
            for edge in hierarchy_edges:
                related_id = (
                    str(edge.get("target"))
                    if str(edge.get("source")) == affiliation["id"]
                    else str(edge.get("source"))
                )
                related = nodes.get(related_id)
                if not related or not (self._labels(related) & ORGANIZATION_LABELS):
                    continue
                related_name = self._node_name(related)
                if not related_name:
                    continue
                affiliations.append(
                    {
                        **affiliation,
                        "id": related_id,
                        "name": related_name,
                        "entity": self._entity_data(related, {"name": related_name}),
                        "hierarchyPath": [affiliation["name"], related_name],
                    }
                )
        affiliations = list({item["id"]: item for item in affiliations}.values())
        if organization:
            affiliations = [
                item for item in affiliations if self._contains(item["name"], organization)
            ]
        if not expert.get("organization") and affiliations:
            expert["organization"] = affiliations[0]["name"]

        coauthor_counts = self._coauthor_counts(expert_node["id"], coauthor_graph)
        coauthor_edges = self._coauthor_edges(expert_node["id"], coauthor_graph)
        context = self._context_index(context_graph)

        requested_period = self._parse_period(overlap_period)
        skipped_missing_period: set[tuple[str, str]] = set()
        candidates: dict[str, dict[str, Any]] = {}
        candidate_graph_cache: dict[str, dict[str, Any]] = {}
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
            edge_by_person: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for edge in org_graph.get("edges", []):
                if edge.get("type") != "AFFILIATED_WITH":
                    continue
                edge_by_person[str(edge.get("source"))].append(edge.get("properties", {}) or {})
            for node in org_graph.get("nodes", []):
                if node.get("id") == expert_node["id"] or not self._is_person(node):
                    continue
                candidate_id = str(node.get("id", ""))
                if target_node is not None and candidate_id != str(target_node.get("id")):
                    continue
                matching_periods: list[tuple[str, tuple[int, int], dict[str, Any]]] = []
                for edge_props in edge_by_person.get(candidate_id, []):
                    candidate_department = self._property(
                        {"properties": edge_props}, DEPARTMENT_KEYS
                    )
                    candidate_period = self._parse_period(
                        self._property({"properties": edge_props}, DATE_KEYS)
                    )
                    overlap = self._overlap(affiliation.get("period"), candidate_period, None)
                    if overlap is None:
                        skipped_missing_period.add((candidate_id, affiliation["id"]))
                        continue
                    if overlap is False:
                        continue
                    if requested_period and self._overlap(overlap, requested_period, None) is False:
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
                    matching_periods.append((common_department, overlap, edge_props))
                if not matching_periods:
                    continue
                candidate_graph = candidate_graph_cache.get(candidate_id)
                if candidate_graph is None:
                    candidate_graph = await gateway.subgraph(
                        candidate_id, depth=1, limit=200, direction="both", space=space
                    )
                    candidate_graph_cache[candidate_id] = candidate_graph
                candidate_context = self._context_index(candidate_graph)
                context["nodes"].update(candidate_context["nodes"])
                context["edges"].extend(candidate_context["edges"])
                shared = context["neighbors"].get(expert_node["id"], set()) & candidate_context[
                    "neighbors"
                ].get(candidate_id, set())
                shared_nodes = [
                    context["nodes"][node_id] for node_id in shared if node_id in context["nodes"]
                ]
                teams = sorted(
                    {
                        self._node_name(item)
                        for item in shared_nodes
                        if self._labels(item) & TEAM_LABELS and self._node_name(item)
                    }
                )
                if team_or_project and not any(
                    self._contains(team, team_or_project) for team in teams
                ):
                    continue
                co_papers = coauthor_counts.get(candidate_id, 0)
                if achievement_types and not any(
                    item.casefold() == "paper" for item in achievement_types
                ):
                    co_papers = 0

                for common_department, overlap, candidate_edge_props in matching_periods:
                    achievements = [
                        self._achievement(
                            item,
                            expert_node["id"],
                            candidate_id,
                            context["edges"],
                        )
                        for item in shared_nodes
                        if self._labels(item) & ACHIEVEMENT_LABELS
                        and (not achievement_types or self._labels(item) & set(achievement_types))
                        and self._node_within_period(item, overlap)
                    ]
                    item = self._build_relation(
                        node=node,
                        organization=affiliation["name"],
                        organization_id=affiliation["id"],
                        organization_entity=affiliation["entity"],
                        department=common_department,
                        overlap=overlap,
                        teams=teams,
                        achievements=achievements,
                        co_papers=co_papers,
                        coauthor_edge=coauthor_edges.get(candidate_id),
                        hierarchy_path=affiliation.get("hierarchyPath"),
                        expert_edge_properties=affiliation.get("edgeProperties", {}),
                        colleague_edge_properties=candidate_edge_props,
                    )
                    previous = candidates.get(candidate_id)
                    candidates[candidate_id] = (
                        item if previous is None else self._merge_relations(previous, item)
                    )

        all_colleagues = sorted(
            (item for item in candidates.values() if item["confidence"] >= min_confidence),
            key=lambda item: (item["confidence"], len(item["achievements"])),
            reverse=True,
        )
        colleagues = all_colleagues[offset : offset + limit]
        return {
            "expert": expert,
            "targetExpert": target_expert,
            "queryMode": "pair" if target_expert_id else "network",
            "colleagues": colleagues,
            "total": len(all_colleagues),
            "returnedCount": len(colleagues),
            "offset": offset,
            "limit": limit,
            "summary": self._summary(expert, colleagues, len(skipped_missing_period)),
            "graph": self._build_graph(expert, colleagues),
            "rules": self._rules(colleagues)[:1],
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
                        "edgeProperties": edge_props,
                        "entity": self._entity_data(target, {"name": name}),
                    }
                )
        return result

    def _build_relation(
        self,
        *,
        node: dict[str, Any],
        organization: str,
        organization_id: str = "",
        organization_entity: dict[str, Any],
        department: str,
        overlap: tuple[int, int] | None | bool,
        teams: list[str],
        achievements: list[dict[str, Any]],
        co_papers: int,
        coauthor_edge: dict[str, Any] | None = None,
        hierarchy_path: list[str] | None = None,
        expert_edge_properties: dict[str, Any] | None = None,
        colleague_edge_properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        has_period = isinstance(overlap, tuple)
        effective_period = self._format_period(overlap) if has_period else ""
        overlap_months = self._period_months(overlap) if has_period else None
        overlap_years = round(overlap_months / 12, 1) if overlap_months else None
        score_breakdown = {
            "sameOrganization": 0.42,
            "overlapDuration": min(0.22, (overlap_months or 0) / 120 * 0.22),
            "sameDepartment": 0.12 if department else 0.0,
            "coauthorEvidence": min(0.12, co_papers * 0.02),
            "sharedTeam": 0.05 if teams else 0.0,
            "sharedAchievements": min(0.05, len(achievements) * 0.01),
        }
        confidence = sum(score_breakdown.values())
        evidence = [f"共同任职机构：{organization}"]
        if hierarchy_path:
            evidence.append(f"机构层级匹配：{' → '.join(hierarchy_path)}")
        if has_period:
            evidence.append(f"任职时间重叠：{effective_period}（{overlap_years} 年）")
        else:
            evidence.append("任职时间字段不完整，已标记人工复核")
        if department:
            evidence.append(f"部门/团队：{department}")
        if achievements:
            evidence.append(f"同事期间关联合作成果 {len(achievements)} 项")
        if co_papers:
            evidence.append(f"合著关系统计：共同论文 {co_papers} 篇")
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
            "organizationId": organization_id,
            "organizationEntity": organization_entity,
            "organizationHierarchy": hierarchy_path or [],
            "commonDepartment": department or None,
            "commonTeamOrProject": sorted(set(teams))[:5],
            "effectivePeriod": effective_period,
            "overlapMonths": overlap_months,
            "overlapYears": overlap_years,
            "workContent": [item["title"] for item in achievements[:5]]
            or ([f"合著统计（{co_papers} 篇，暂无论文实体明细）"] if co_papers else []),
            "collaborationScenes": scenes,
            "achievements": achievements[:10],
            "coPaperCount": co_papers,
            "coauthorEdge": coauthor_edge or {},
            "confidence": round(min(confidence, 0.98), 2),
            "evidence": evidence,
            "reviewRequired": False,
            "employmentHistory": [
                {
                    "organization": organization,
                    "department": department or None,
                    "effectivePeriod": effective_period,
                    "overlapMonths": overlap_months,
                    "overlapYears": overlap_years,
                }
            ],
            "employmentEdges": {
                "expert": expert_edge_properties or {},
                "colleague": colleague_edge_properties or {},
            },
            "scoreBreakdown": {key: round(value, 4) for key, value in score_breakdown.items()},
        }

    def _merge_relations(self, current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        histories = current["employmentHistory"] + incoming["employmentHistory"]
        history_keys = {
            (item["organization"], item.get("department"), item["effectivePeriod"]): item
            for item in histories
        }
        achievements = {
            item["id"]: item for item in current["achievements"] + incoming["achievements"]
        }
        best = incoming if incoming["confidence"] > current["confidence"] else current
        merged = {**best}
        merged["employmentHistory"] = list(history_keys.values())
        merged["achievements"] = list(achievements.values())[:10]
        merged["employmentEdges"] = {
            **current.get("employmentEdges", {}),
            **incoming.get("employmentEdges", {}),
        }
        merged["commonTeamOrProject"] = sorted(
            set(current["commonTeamOrProject"] + incoming["commonTeamOrProject"])
        )[:5]
        merged["collaborationScenes"] = list(
            dict.fromkeys(current["collaborationScenes"] + incoming["collaborationScenes"])
        )
        merged["evidence"] = list(dict.fromkeys(current["evidence"] + incoming["evidence"]))
        merged["workContent"] = list(
            dict.fromkeys(current["workContent"] + incoming["workContent"])
        )[:5]
        return merged

    def _rules(self, colleagues: list[dict[str, Any]]) -> list[dict[str, Any]]:
        achievement_hits = sum(1 for item in colleagues if item.get("achievements"))
        team_hits = sum(
            1
            for item in colleagues
            if item.get("commonDepartment") or item.get("commonTeamOrProject")
        )
        return [
            {
                "name": "任职时间匹配与团队归属算法",
                "type": "关系匹配规则",
                "target": "两位专家及其 AFFILIATED_WITH 任职边",
                "trigger": "两位专家均可唯一定位",
                "logic": "将 work_experience_date/employment_period/tenure_period 解析为月份序号区间（年×12+月），以双方任职期交集作为同事关系生效时段；请求时间仅用于判断关系是否命中，不截断生效时段。含“至今/present/current/now”时终点取当前年月，单点日期覆盖到该年12月，起止颠倒自动交换。",
                "output": "同事关系生效时段、重叠月份、重叠年限",
                "threshold": "任职时间存在至少 1 个月交集",
                "audit": "任一任职边缺少时间字段时不生成同事关系，计入待复核",
                "appliedCount": len(colleagues),
            },
            {
                "name": "团队归属规则",
                "type": "关系匹配规则",
                "target": "AFFILIATED_WITH 任职边、机构层级边、部门/团队字段与节点",
                "trigger": "任职时间交集成立后",
                "logic": "匹配共同任职机构或一跳机构层级（SUBSIDIARY_OF/PARENT_OF/PART_OF/BELONGS_TO），归一化比较部门/团队字段（work_experience_department_zh/department/team_name），并匹配 Team/Laboratory/Department/Project 共同节点，标注所属团队/项目组；同机构、同部门、共享团队分别计入置信度加权（0.42/0.12/0.05）。",
                "output": "共同机构、所属部门/团队、协作场景",
                "threshold": "共同机构为同事必要前提；部门/团队匹配用于置信度加权，非强制",
                "audit": "任职来源冲突时不生成同事关系，计入待复核",
                "appliedCount": team_hits,
            },
            {
                "name": "同事成果关联规则",
                "type": "关系增强规则",
                "target": "同事期间论文、项目、专利、成果记录",
                "trigger": "同事关系已确认",
                "logic": "取两位专家共同邻接的 Paper、Project、Patent、Report、Award 真实节点，按节点年份过滤同事生效区间，并保留原图成果连接边；COAUTHOR_WITH 的 co_paper_count 只作统计，不创建论文节点。",
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
        period_achievements = "0项"
        if primary and primary["achievements"]:
            period_achievements = f"{len(primary['achievements'])}项具体成果"
        elif primary and primary.get("coPaperCount"):
            period_achievements = (
                f"0项具体成果（合著统计{primary.get('coPaperCount', 0)}篇）"
            )
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
            "periodAchievements": period_achievements,
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
                    "ruleName": "同事关系判定规则",
                },
            )
            coauthor_edge = item.get("coauthorEdge") or {}
            if coauthor_edge:
                add_edge(
                    coauthor_edge["source"],
                    coauthor_edge["target"],
                    "COAUTHOR_WITH",
                    {
                        **coauthor_edge.get("properties", {}),
                        "existingGraphEdge": True,
                    },
                )
            org_id = item.get("organizationId")
            if not org_id:
                continue
            node_map[org_id] = {
                "id": org_id,
                "type": "organization",
                "label": item["commonOrganization"],
                "data": {**item["organizationEntity"], "confidence": item["confidence"]},
            }
            add_edge(
                expert["id"],
                org_id,
                "AFFILIATED_WITH",
                {
                    **item.get("employmentEdges", {}).get("expert", {}),
                    "period": item["effectivePeriod"],
                    "existingGraphEdge": True,
                },
            )
            add_edge(
                colleague["id"],
                org_id,
                "AFFILIATED_WITH",
                {
                    **item.get("employmentEdges", {}).get("colleague", {}),
                    "period": item["effectivePeriod"],
                    "existingGraphEdge": True,
                },
            )
            for achievement in item["achievements"]:
                achievement_id = achievement["id"]
                node_type = achievement["type"].casefold()
                node_map[achievement_id] = {
                    "id": achievement_id,
                    "type": node_type,
                    "label": achievement["title"],
                    "data": achievement,
                }
                for link in achievement.get("graphLinks", []):
                    add_edge(
                        link["source"],
                        link["target"],
                        link["type"],
                        {**link.get("properties", {}), "existingGraphEdge": True},
                    )
        return {"nodes": list(node_map.values()), "edges": list(edge_map.values())}

    def _context_index(self, graph: dict[str, Any]) -> dict[str, Any]:
        nodes = {str(node.get("id")): node for node in graph.get("nodes", [])}
        neighbors: dict[str, set[str]] = defaultdict(set)
        for edge in graph.get("edges", []):
            source, target = str(edge.get("source")), str(edge.get("target"))
            neighbors[source].add(target)
            neighbors[target].add(source)
        return {"nodes": nodes, "neighbors": neighbors, "edges": list(graph.get("edges", []))}

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

    def _coauthor_edges(self, expert_id: str, graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for edge in graph.get("edges", []):
            if edge.get("type") != "COAUTHOR_WITH":
                continue
            source, target = str(edge.get("source")), str(edge.get("target"))
            other = target if source == expert_id else source
            current = result.get(other)
            current_count = int((current or {}).get("properties", {}).get("co_paper_count", 0) or 0)
            edge_count = int((edge.get("properties") or {}).get("co_paper_count", 0) or 0)
            if current is None or edge_count > current_count:
                result[other] = {
                    "source": source,
                    "target": target,
                    "properties": edge.get("properties", {}) or {},
                }
        return result

    def _achievement(
        self,
        node: dict[str, Any],
        expert_id: str,
        colleague_id: str,
        graph_edges: list[dict[str, Any]],
    ) -> dict[str, Any]:
        labels = self._labels(node)
        kind = next((label for label in labels if label in ACHIEVEMENT_LABELS), "Achievement")
        year = self._year(
            self._property(node, ("year", "publish_year", "start_year", "publication_date"))
        )
        node_id = str(node.get("id", ""))
        graph_links = [
            {
                "source": str(edge.get("source")),
                "target": str(edge.get("target")),
                "type": str(edge.get("type") or "RELATED_TO"),
                "properties": edge.get("properties", {}) or {},
            }
            for edge in graph_edges
            if node_id in {str(edge.get("source")), str(edge.get("target"))}
            and (
                expert_id in {str(edge.get("source")), str(edge.get("target"))}
                or colleague_id in {str(edge.get("source")), str(edge.get("target"))}
            )
        ]
        return {
            "id": str(node.get("id", "")),
            "type": kind,
            "title": self._node_name(node),
            "year": year,
            "graphLinks": list(
                {
                    (item["source"], item["target"], item["type"]): item for item in graph_links
                }.values()
            ),
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
        if self._labels(node) & PERSON_LABELS and properties.get("source_record_id") not in (
            None,
            "",
        ):
            source_field = "scholar_id" if source_table == "dwd_scholar" else "source_record_id"
            source_value = properties.get("source_record_id")
        elif properties.get("organization_id") == "scholar_id" and properties.get(
            "source_record_id"
        ) not in (None, ""):
            source_field, source_value = "scholar_id", properties.get("source_record_id")
        elif properties.get("organization_id") not in (None, ""):
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
