from __future__ import annotations

from typing import Any

import pytest

from service.expert_colleague_relation import ExpertColleagueRelationService


def node(node_id: str, labels: list[str], **properties: Any) -> dict[str, Any]:
    return {"id": node_id, "labels": labels, "properties": properties}


def edge(source: str, target: str, edge_type: str, **properties: Any) -> dict[str, Any]:
    return {
        "id": f"{source}:{edge_type}:{target}",
        "source": source,
        "target": target,
        "type": edge_type,
        "properties": properties,
    }


class FakeGraphSearchGateway:
    def __init__(self) -> None:
        self.api_calls: list[dict[str, Any]] = []
        self.expert = node(
            "person_a",
            ["Person"],
            name_zh="张明远",
        )
        self.colleague = node(
            "person_b",
            ["Person"],
            name_zh="李佳宁",
        )
        self.org = node("org_1", ["Organization"], name_zh="中国科学院自动化研究所")
        self.paper = node("paper_1", ["Paper"], title="科技知识图谱关系推理", year="2022")
        # 任职时间/部门挂在 AFFILIATED_WITH 边上（与 ETL 写入位置一致）
        self.expert_aff_edge = edge(
            "person_a",
            "org_1",
            "AFFILIATED_WITH",
            affiliation_name="中国科学院自动化研究所",
            work_experience_date="2018-2023",
            work_experience_department_zh="智能系统实验室",
        )
        self.colleague_aff_edge = edge(
            "person_b",
            "org_1",
            "AFFILIATED_WITH",
            affiliation_name="中国科学院自动化研究所",
            work_experience_date="2020-2025",
            work_experience_department_zh="智能系统实验室",
        )

    async def resolve_person(self, keyword: str, space: str | None) -> dict[str, Any] | None:
        self.api_calls.append({"method": "GET", "path": "/api/v1/graph-search/nodes/person_a"})
        return self.expert

    async def subgraph(
        self,
        node_id: str,
        *,
        depth: int,
        limit: int,
        direction: str = "both",
        edge_type: str | None = None,
        space: str | None = None,
    ) -> dict[str, Any]:
        self.api_calls.append(
            {
                "method": "GET",
                "path": f"/api/v1/graph-search/subgraph/{node_id}",
                "params": {"depth": depth, "direction": direction, "edge_type": edge_type},
            }
        )
        if node_id == "person_a" and edge_type == "AFFILIATED_WITH":
            return {
                "nodes": [self.expert, self.org],
                "edges": [self.expert_aff_edge],
            }
        if node_id == "org_1":
            return {
                "nodes": [self.org, self.expert, self.colleague],
                "edges": [self.expert_aff_edge, self.colleague_aff_edge],
            }
        if edge_type == "COAUTHOR_WITH":
            return {
                "nodes": [self.expert, self.colleague],
                "edges": [edge("person_a", "person_b", "COAUTHOR_WITH", co_paper_count=3)],
            }
        return {
            "nodes": [self.expert, self.colleague, self.org, self.paper],
            "edges": [
                self.expert_aff_edge,
                self.colleague_aff_edge,
                edge("paper_1", "person_a", "AUTHORED_BY"),
                edge("paper_1", "person_b", "AUTHORED_BY"),
            ],
        }


@pytest.mark.asyncio
async def test_query_infers_colleague_from_edge_time_overlap() -> None:
    gateway = FakeGraphSearchGateway()
    result = await ExpertColleagueRelationService().query(
        gateway,
        expert_id="person_a",
        organization="自动化研究所",
        department="智能系统实验室",
        overlap_period="2020-2022",
    )

    assert result["total"] == 1
    relation = result["colleagues"][0]
    assert relation["colleague"]["id"] == "person_b"
    assert relation["effectivePeriod"] == "2020-01 至 2022-12"
    assert relation["overlapMonths"] == 36
    assert relation["overlapYears"] == 3.0
    assert relation["reviewRequired"] is False
    assert relation["achievements"][0]["id"] == "paper_1"
    assert "论文合作" in relation["collaborationScenes"]
    assert all(call["path"].startswith("/api/v1/graph-search/") for call in result["apiCalls"])


@pytest.mark.asyncio
async def test_non_overlapping_periods_exclude_colleague() -> None:
    gateway = FakeGraphSearchGateway()
    # 专家 2010-2015，同事 2020-2025 —— 时间不重叠，应被排除
    gateway.expert_aff_edge["properties"]["work_experience_date"] = "2010-2015"
    gateway.colleague_aff_edge["properties"]["work_experience_date"] = "2020-2025"

    result = await ExpertColleagueRelationService().query(gateway, expert_id="person_a")

    assert result["total"] == 0


@pytest.mark.asyncio
async def test_missing_edge_time_is_excluded_and_counted_for_review() -> None:
    gateway = FakeGraphSearchGateway()
    # 同事边上缺任职时间 → 走人工复核
    gateway.colleague_aff_edge["properties"].pop("work_experience_date")

    result = await ExpertColleagueRelationService().query(gateway, expert_id="person_a")

    assert result["colleagues"] == []
    assert result["summary"]["reviewRequiredCount"] == 1


@pytest.mark.asyncio
async def test_any_positive_month_overlap_is_included() -> None:
    gateway = FakeGraphSearchGateway()
    gateway.expert_aff_edge["properties"]["work_experience_date"] = "2022-01 至 2022-02"
    gateway.colleague_aff_edge["properties"]["work_experience_date"] = "2022-01 至 2022-12"

    result = await ExpertColleagueRelationService().query(gateway, expert_id="person_a")

    assert result["total"] == 1
    assert result["colleagues"][0]["overlapMonths"] == 2


@pytest.mark.asyncio
async def test_summary_and_graph_cover_tender_details() -> None:
    gateway = FakeGraphSearchGateway()
    result = await ExpertColleagueRelationService().query(gateway, expert_id="person_a")

    summary = result["summary"]
    assert summary["coreExpert"].startswith("张明远")
    assert summary["primaryColleague"].startswith("李佳宁")
    assert summary["commonOrganization"] == "中国科学院自动化研究所"
    assert summary["effectivePeriod"] == "2020-01 至 2023-12"
    assert summary["workContent"] == "科技知识图谱关系推理"
    node_types = {item["type"] for item in result["graph"]["nodes"]}
    assert {"expert", "organization", "paper"} <= node_types
    assert {item["label"] for item in result["graph"]["edges"]} >= {
        "同事关系",
        "共同任职",
        "合作成果",
    }
