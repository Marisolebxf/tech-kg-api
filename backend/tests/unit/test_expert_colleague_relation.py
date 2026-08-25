from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from application.expert_colleague_relation import (
    ExpertColleagueRelationApplication,
    FastAPIGraphSearchGateway,
    clear_caches,
)
from biz.schemas.expert_colleague_relation import ExpertColleagueRelationRequest
from service.expert_colleague_relation import ExpertColleagueRelationService


@pytest.fixture(autouse=True)
def _isolate_caches():
    """每条用例前后清空进程内 TTL 缓存，避免用例间串味。"""
    clear_caches()
    yield
    clear_caches()


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
        "AFFILIATED_WITH",
        "AUTHORED_BY",
    }
    assert all(
        not item["id"].startswith("colleague-co-paper:") for item in result["graph"]["nodes"]
    )


def test_request_validates_period_and_normalizes_filters() -> None:
    request = ExpertColleagueRelationRequest(
        expertId="person_a",
        organization=" 自动化研究所 ",
        overlapPeriod="2020-2022",
        offset=10,
    )

    assert request.expertId == "person_a"
    assert request.organization == "自动化研究所"
    assert request.offset == 10
    with pytest.raises(ValidationError):
        ExpertColleagueRelationRequest(expertId="person_a", overlapPeriod="not-a-period")

    request = ExpertColleagueRelationRequest(
        expert_a_id="person_a",
        expert_b_id="person_b",
        start_time="2021-01",
        end_time="2022-12",
    )
    assert request.startTime == "2021-01"
    assert request.endTime == "2022-12"
    with pytest.raises(ValidationError):
        ExpertColleagueRelationRequest(expert_a_id="person_a", start_time="2022-01")
    with pytest.raises(ValidationError):
        ExpertColleagueRelationRequest(
            expert_a_id="person_a",
            start_time="2023-01",
            end_time="2022-12",
        )


@pytest.mark.parametrize("field", ["expert_a_id", "expert_b_id"])
def test_request_rejects_overlong_and_abnormal_expert_ids(field: str) -> None:
    payload = {"expert_a_id": "person_a", "expert_b_id": "person_b"}
    payload[field] = "XXADASDDDDDDDDDDDDDDDAXZSSSSSSSSSZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZX"
    with pytest.raises(ValidationError, match="64"):
        ExpertColleagueRelationRequest.model_validate(payload)

    payload[field] = "person_a!@#￥%&"
    with pytest.raises(ValidationError, match="异常字符"):
        ExpertColleagueRelationRequest.model_validate(payload)

    payload[field] = "person a"
    with pytest.raises(ValidationError, match="空格"):
        ExpertColleagueRelationRequest.model_validate(payload)


def test_request_rejects_future_month_range() -> None:
    today = date.today()
    future_month = f"{today.year + (1 if today.month == 12 else 0)}-{1 if today.month == 12 else today.month + 1:02d}"
    with pytest.raises(ValidationError, match="当前月份"):
        ExpertColleagueRelationRequest.model_validate(
            {
                "expert_a_id": "person_a",
                "expert_b_id": "person_b",
                "start_time": future_month,
                "end_time": future_month,
            }
        )


def test_merge_relations_keeps_multiple_employment_periods() -> None:
    service = ExpertColleagueRelationService()

    colleague = node("person_b", ["Person"], name_zh="李佳宁")
    first = service._build_relation(
        node=colleague,
        organization="机构甲",
        organization_entity={},
        department="部门一",
        overlap=(2020 * 12, 2021 * 12 + 11),
        teams=[],
        achievements=[],
        co_papers=0,
    )
    second = service._build_relation(
        node=colleague,
        organization="机构乙",
        organization_entity={},
        department="部门二",
        overlap=(2023 * 12, 2024 * 12 + 11),
        teams=["联合实验室"],
        achievements=[],
        co_papers=2,
    )

    merged = service._merge_relations(first, second)

    assert len(merged["employmentHistory"]) == 2
    assert {item["organization"] for item in merged["employmentHistory"]} == {
        "机构甲",
        "机构乙",
    }
    assert "scoreBreakdown" in merged


@pytest.mark.asyncio
async def test_query_returns_pagination_metadata() -> None:
    result = await ExpertColleagueRelationService().query(
        FakeGraphSearchGateway(), expert_id="person_a", limit=1, offset=1
    )

    assert result["total"] == 1
    assert result["returnedCount"] == 0
    assert result["offset"] == 1
    assert result["limit"] == 1


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class _GatewayClient:
    def __init__(self) -> None:
        self.get_calls: list[tuple[str, dict[str, Any]]] = []

    async def get(self, path: str, params: dict[str, Any]) -> _Response:
        self.get_calls.append((path, params))
        if "/subgraph/" in path:
            size = int(params["limit"])
            edges = [
                {"id": f"edge_{index}", "source": "person_a", "target": f"n{index}"}
                for index in range(size)
            ]
            return _Response({"success": True, "code": 200, "data": {"nodes": [], "edges": edges}})
        return _Response({"success": False, "code": 404, "msg": "not found"})

    async def post(self, path: str, params: dict[str, Any], json: dict[str, Any]) -> _Response:
        if "name_zh" in json:
            items = [
                {"id": "person_1", "properties": {"name_zh": "张三"}},
                {"id": "person_2", "properties": {"name_zh": "张三"}},
            ]
        else:
            items = []
        return _Response(
            {"success": True, "code": 200, "data": {"items": items, "total": len(items)}}
        )


@pytest.mark.asyncio
async def test_gateway_rejects_ambiguous_person_name() -> None:
    gateway = FastAPIGraphSearchGateway(_GatewayClient())  # type: ignore[arg-type]

    with pytest.raises(LookupError, match="多个精确匹配"):
        await gateway.resolve_person("张三", "dev")


@pytest.mark.asyncio
async def test_gateway_subgraph_respects_total_limit() -> None:
    client = _GatewayClient()
    gateway = FastAPIGraphSearchGateway(client)  # type: ignore[arg-type]

    graph = await gateway.subgraph("person_a", depth=1, limit=3, space="dev")

    assert len(graph["edges"]) == 3
    subgraph_calls = [item for item in client.get_calls if "/subgraph/" in item[0]]
    assert len(subgraph_calls) == 1


def test_request_accepts_page_snake_case_fields() -> None:
    request = ExpertColleagueRelationRequest.model_validate(
        {
            "expert_id": "E10001",
            "overlap_period": "2018-2022",
            "team_or_project": " 知识工程项目组 ",
            "min_confidence": 0.6,
        }
    )

    assert request.expertId == "E10001"
    assert request.overlapPeriod == "2018-2022"
    assert request.teamOrProject == "知识工程项目组"
    assert request.minConfidence == 0.6


@pytest.mark.asyncio
async def test_query_filters_min_confidence_and_does_not_invent_work_content() -> None:
    result = await ExpertColleagueRelationService().query(
        FakeGraphSearchGateway(), expert_id="person_a", min_confidence=0.99
    )
    assert result["colleagues"] == []

    result = await ExpertColleagueRelationService().query(
        FakeGraphSearchGateway(), expert_id="person_a", achievement_types=["Patent"]
    )
    assert result["colleagues"][0]["achievements"] == []
    assert result["colleagues"][0]["workContent"] == []


def test_persist_relations_reads_space_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRS_GRAPH_SPACE", "techkg_prod")
    graph = MagicMock()
    graph.get_node_edges.return_value = []
    payload = {
        "expert": {"id": "person_z"},
        "colleagues": [
            {
                "colleague": {"id": "person_a"},
                "commonOrganization": "自动化研究所",
                "commonDepartment": "智能系统实验室",
                "effectivePeriod": "2020-01 至 2022-12",
                "overlapMonths": 36,
                "confidence": 0.8,
                "commonTeamOrProject": ["知识工程项目组"],
                "workContent": [],
                "collaborationScenes": ["同机构任职"],
                "achievements": [],
                "evidence": ["任职时间重叠"],
            }
        ],
    }
    with patch(
        "application.expert_colleague_relation.TRSGraphClient", return_value=graph
    ) as client:
        result = ExpertColleagueRelationApplication._persist_relations(payload)

    assert client.call_args.args[0].space == "techkg_prod"
    graph.create_edge.assert_called_once()
    assert graph.create_edge.call_args.args[:3] == ("person_a", "person_z", "COLLEAGUE")
    assert result == {
        "space": "techkg_prod",
        "edgeType": "COLLEAGUE",
        "created": 1,
        "updated": 0,
        "total": 1,
    }
    graph.close.assert_called_once()


@pytest.mark.asyncio
async def test_application_uses_environment_space_for_query_and_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRS_GRAPH_SPACE", "tenant_graph")
    application = ExpertColleagueRelationApplication()
    data = {"expert": {"id": "person_z"}, "colleagues": []}
    application._service.query = AsyncMock(return_value=data)

    with patch.object(
        application,
        "_persist_relations",
        return_value={"space": "tenant_graph", "total": 0},
    ) as persist:
        result = await application.query(MagicMock(), expert_id="person_z")

    assert application._service.query.await_args.kwargs["space"] == "tenant_graph"
    assert persist.call_args.args[0]["expert"]["id"] == "person_z"
    assert len(persist.call_args.args) == 1
    assert result["persistence"]["space"] == "tenant_graph"
