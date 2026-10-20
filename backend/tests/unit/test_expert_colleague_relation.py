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


def test_entity_provenance_prefers_explicit_mysql_source():
    entity = node(
        "person_a",
        ["Person"],
        source_table="dwd_scholar",
        source_field="scholar_id",
        source_record_id="a",
        organization_base="dwd_org_stock_base",
    )
    provenance = ExpertColleagueRelationService()._entity_data(entity, {})["provenance"]
    assert provenance["sourceTable"] == "dwd_scholar"
    assert provenance["sourceField"] == "scholar_id"
    entity["properties"]["source_field"] = "external_scholar_id"
    assert (
        ExpertColleagueRelationService()._entity_data(entity, {})["provenance"]["sourceField"]
        == "external_scholar_id"
    )


@pytest.mark.parametrize(
    "table,field,vid",
    [
        ("dwd_scholar", "scholar_id", "person_99a94795"),
        ("dwd_org_stock_base", "org_id", "org_047583dfefe252480e530d15c0d436df"),
    ],
)
def test_legacy_entity_provenance_uses_mysql_column(table, field, vid):
    entity = node(
        vid,
        ["Person" if table == "dwd_scholar" else "Organization"],
        source_table=table,
        source_record_id=vid,
    )
    provenance = ExpertColleagueRelationService()._entity_data(entity, {})["provenance"]
    assert provenance["sourceTable"] == table
    assert provenance["sourceField"] == field


class FakeGraphSearchGateway:
    def __init__(self) -> None:
        self.api_calls: list[dict[str, Any]] = []
        # 可注入的 /paths/search 返回值（默认空：共同论文走上下文子图交集）
        self.path_search_result: dict[str, Any] = {"items": [], "total": 0}
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

    async def search_paths(self, body: dict[str, Any], *, space: str | None) -> dict[str, Any]:
        self.api_calls.append(
            {"method": "POST", "path": "/api/v1/graph-search/paths/search", "body": body}
        )
        return self.path_search_result

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
async def test_query_uses_affiliation_org_not_person_scholar_org() -> None:
    gateway = FakeGraphSearchGateway()
    gateway.expert = node(
        "person_a",
        ["Person"],
        name_zh="张明远",
        scholar_org="错误的展示机构",
    )
    gateway.colleague = node(
        "person_b",
        ["Person"],
        name_zh="李佳宁",
        scholar_org="另一个错误机构",
    )
    result = await ExpertColleagueRelationService().query(gateway, expert_id="person_a")

    assert result["expert"]["organization"] == "中国科学院自动化研究所"
    assert result["colleagues"][0]["colleague"]["organization"] == "中国科学院自动化研究所"
    assert result["summary"]["coreExpertOrganization"] == "中国科学院自动化研究所"


@pytest.mark.asyncio
async def test_parent_and_subsidiary_orgs_are_not_colleagues() -> None:
    gateway = FakeGraphSearchGateway()
    parent = node("org_parent", ["Organization"], name_zh="某集团")
    child = node("org_child", ["Organization"], name_zh="某子公司")
    gateway.org = child
    gateway.expert_aff_edge = edge(
        "person_a",
        "org_child",
        "AFFILIATED_WITH",
        affiliation_name="某子公司",
        work_experience_date="2018-2023",
        work_experience_department_zh="研发部",
    )
    gateway.colleague_aff_edge = edge(
        "person_b",
        "org_parent",
        "AFFILIATED_WITH",
        affiliation_name="某集团",
        work_experience_date="2020-2025",
        work_experience_department_zh="研发部",
    )
    hierarchy = edge("org_child", "org_parent", "SUBSIDIARY_OF")

    async def subgraph(
        node_id: str,
        *,
        depth: int,
        limit: int,
        direction: str = "both",
        edge_type: str | None = None,
        space: str | None = None,
    ) -> dict[str, Any]:
        gateway.api_calls.append(
            {
                "method": "GET",
                "path": f"/api/v1/graph-search/subgraph/{node_id}",
                "params": {"depth": depth, "direction": direction, "edge_type": edge_type},
            }
        )
        if node_id == "person_a" and edge_type == "AFFILIATED_WITH":
            return {"nodes": [gateway.expert, child], "edges": [gateway.expert_aff_edge]}
        if node_id == "org_child":
            return {
                "nodes": [child, parent, gateway.expert],
                "edges": [gateway.expert_aff_edge, hierarchy],
            }
        if node_id == "org_parent":
            return {
                "nodes": [parent, gateway.colleague],
                "edges": [gateway.colleague_aff_edge],
            }
        if edge_type == "COAUTHOR_WITH":
            return {"nodes": [gateway.expert], "edges": []}
        return {"nodes": [gateway.expert, child], "edges": [gateway.expert_aff_edge]}

    gateway.subgraph = subgraph  # type: ignore[method-assign]
    result = await ExpertColleagueRelationService().query(gateway, expert_id="person_a")
    assert result["total"] == 0
    assert result["colleagues"] == []


@pytest.mark.asyncio
async def test_query_time_window_filters_without_clipping_employment_overlap() -> None:
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
    assert relation["effectivePeriod"] == "2020-01 至 2023-12"
    assert relation["overlapMonths"] == 48
    assert relation["overlapYears"] == 4.0
    assert result["summary"]["effectivePeriod"] == "2020-01 至 2023-12"
    assert result["summary"]["overlapDuration"] == "48个月"
    assert relation["reviewRequired"] is False
    assert relation["achievements"][0]["id"] == "paper_1"
    assert "论文合作" in relation["collaborationScenes"]
    assert all(call["path"].startswith("/api/v1/graph-search/") for call in result["apiCalls"])


@pytest.mark.asyncio
async def test_query_time_window_outside_employment_overlap_excludes_colleague() -> None:
    result = await ExpertColleagueRelationService().query(
        FakeGraphSearchGateway(),
        expert_id="person_a",
        overlap_period="2024-2025",
    )

    assert result["total"] == 0
    assert result["colleagues"] == []


@pytest.mark.asyncio
async def test_joint_papers_refetched_via_path_search_when_subgraph_truncated() -> None:
    """上下文子图取数被截断（高产专家论文边刷屏）时，共同论文改由
    服务端路径搜索补齐，期间内成果不再整批丢成 0 项。"""
    gateway = FakeGraphSearchGateway()
    original_subgraph = gateway.subgraph

    async def truncated_subgraph(
        node_id: str,
        *,
        depth: int,
        limit: int,
        direction: str = "both",
        edge_type: str | None = None,
        space: str | None = None,
    ) -> dict[str, Any]:
        graph = await original_subgraph(
            node_id,
            depth=depth,
            limit=limit,
            direction=direction,
            edge_type=edge_type,
            space=space,
        )
        # 只截断专家的上下文子图（无 edge_type 分支）：共同论文整体丢失
        if node_id == "person_a" and edge_type is None:
            return {"nodes": [gateway.expert, gateway.org], "edges": [gateway.expert_aff_edge]}
        return graph

    gateway.subgraph = truncated_subgraph  # type: ignore[method-assign]
    gateway.path_search_result = {
        "items": [
            {
                "nodes": [
                    gateway.expert,
                    node("paper_1", ["Paper"], title="科技知识图谱关系推理", year="2022"),
                    gateway.colleague,
                ],
                "edges": [
                    edge("paper_1", "person_a", "AUTHORED_BY"),
                    edge("paper_1", "person_b", "AUTHORED_BY"),
                ],
            }
        ],
        "total": 1,
    }

    result = await ExpertColleagueRelationService().query(gateway, expert_id="person_a")

    relation = result["colleagues"][0]
    assert relation["colleague"]["id"] == "person_b"
    # 2022 在共事期间（2020-2023）内：成果须由路径搜索补齐，不能是 0 项
    assert [item["id"] for item in relation["achievements"]] == ["paper_1"]
    assert relation["workContent"] == ["科技知识图谱关系推理"]
    path_calls = [c for c in result["apiCalls"] if "paths/search" in c["path"]]
    assert path_calls, "共同论文应改走 /paths/search 服务端路径搜索"


@pytest.mark.asyncio
async def test_achievement_year_reads_publication_year_property() -> None:
    """图上 Paper 的年份属性是 publication_year：缺该键时期间内成果会被整批滤成 0。"""
    gateway = FakeGraphSearchGateway()
    gateway.paper = node(
        "paper_1",
        ["Paper"],
        title="科技知识图谱关系推理",
        publication_year="2022",
    )

    original_subgraph = gateway.subgraph

    async def subgraph_with_new_paper(
        node_id: str,
        *,
        depth: int,
        limit: int,
        direction: str = "both",
        edge_type: str | None = None,
        space: str | None = None,
    ) -> dict[str, Any]:
        graph = await original_subgraph(
            node_id,
            depth=depth,
            limit=limit,
            direction=direction,
            edge_type=edge_type,
            space=space,
        )
        if node_id == "person_a" and edge_type is None:
            return {
                "nodes": [gateway.expert, gateway.colleague, gateway.org, gateway.paper],
                "edges": [
                    gateway.expert_aff_edge,
                    gateway.colleague_aff_edge,
                    edge("paper_1", "person_a", "AUTHORED_BY"),
                    edge("paper_1", "person_b", "AUTHORED_BY"),
                ],
            }
        return graph

    gateway.subgraph = subgraph_with_new_paper  # type: ignore[method-assign]

    result = await ExpertColleagueRelationService().query(gateway, expert_id="person_a")

    relation = result["colleagues"][0]
    assert [item["id"] for item in relation["achievements"]] == ["paper_1"]


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
async def test_query_reports_all_missing_experts() -> None:
    gateway = FakeGraphSearchGateway()
    gateway.resolve_person = AsyncMock(return_value=None)

    with pytest.raises(LookupError, match="未找到专家: 2、3"):
        await ExpertColleagueRelationService().query(
            gateway,
            expert_id="2",
            target_expert_id="3",
        )


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
    # 摘要机构须与共同机构（即图谱预览展示的机构）一致，即使专家节点自带其他 scholar_org
    assert summary["coreExpertOrganization"] == "中国科学院自动化研究所"
    assert summary["relationConfidence"] == result["colleagues"][0]["confidence"]
    expert_edges = [
        edge
        for edge in result["graph"]["edges"]
        if {edge["source"], edge["target"]} == {"person_a", "person_b"}
    ]
    assert [edge["label"] for edge in expert_edges] == ["同事关系"]
    assert result["colleagues"][0]["coauthorEdge"]  # 合著仍作为证据保留
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


def test_request_accepts_only_page_fields_and_requires_expert_b() -> None:
    request = ExpertColleagueRelationRequest(
        expert_a_id="person_a",
        expert_b_id="person_b",
        start_time="2021-01",
        end_time="2022-12",
    )
    assert request.expertId == "person_a"
    assert request.targetExpertId == "person_b"
    assert request.startTime == "2021-01"
    assert request.endTime == "2022-12"

    with pytest.raises(ValidationError):
        ExpertColleagueRelationRequest(expert_a_id="person_a")
    with pytest.raises(ValidationError):
        ExpertColleagueRelationRequest(
            expert_a_id="person_a", expert_b_id="person_b", start_time="2022-01"
        )
    with pytest.raises(ValidationError):
        ExpertColleagueRelationRequest(
            expert_a_id="person_a",
            expert_b_id="person_b",
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
        self.post_calls: list[tuple[str, dict[str, Any], dict[str, Any]]] = []

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
        self.post_calls.append((path, params, json))
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


@pytest.mark.asyncio
async def test_gateway_search_paths_carries_space_in_body() -> None:
    """paths/search 端点从请求体读 space（与其余 GET 端点不同），适配层须并入 body。"""
    client = _GatewayClient()
    gateway = FastAPIGraphSearchGateway(client)  # type: ignore[arg-type]

    result = await gateway.search_paths({"sourceId": "a", "targetId": "b"}, space="dev")

    path, _params, body = client.post_calls[-1]
    assert path == "/api/v1/graph-search/paths/search"
    assert body["space"] == "dev"
    assert body["sourceId"] == "a"
    assert result == {"items": [], "total": 0}


@pytest.mark.parametrize(
    "extra_field",
    [
        "organization",
        "department",
        "team_or_project",
        "achievement_types",
        "min_confidence",
        "limit",
        "offset",
        "overlap_period",
    ],
)
def test_request_rejects_removed_parameters(extra_field: str) -> None:
    payload = {
        "expert_a_id": "E10001",
        "expert_b_id": "E10002",
        extra_field: "unused",
    }
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ExpertColleagueRelationRequest.model_validate(payload)


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
    writable_graph_request,
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


@pytest.fixture
def writable_graph_request():
    from service.graph_space_context import request_can_write

    token = request_can_write.set(True)
    try:
        yield
    finally:
        request_can_write.reset(token)


def _persist_payload() -> dict[str, Any]:
    return {
        "expert": {"id": "person_a"},
        "colleagues": [
            {
                "colleague": {"id": "person_z"},
                "commonOrganization": "某某大学",
                "commonDepartment": "计算机学院",
                "effectivePeriod": "2018-01 ~ 2024-06",
                "overlapMonths": 77,
                "confidence": 0.8,
                "commonTeamOrProject": ["某某实验室"],
                "workContent": ["联合研发"],
                "collaborationScenes": ["项目合作"],
                "achievements": [{"id": "paper_1"}],
                "evidence": ["任职重叠"],
            }
        ],
    }


def test_persist_relations_creates_edge_in_vid_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRS_GRAPH_SPACE", "tenant_graph")
    monkeypatch.delenv("TRS_GRAPH_BUSINESS_BASE_URL", raising=False)
    graph = MagicMock()
    graph.get_node_edges.return_value = []
    with patch(
        "application.expert_colleague_relation.TRSGraphClient", return_value=graph
    ) as client:
        result = ExpertColleagueRelationApplication._persist_relations(_persist_payload())

    assert client.call_args.args[0].space == "tenant_graph"
    graph.create_edge.assert_called_once()
    assert graph.create_edge.call_args.args[:3] == ("person_a", "person_z", "COLLEAGUE")
    props = graph.create_edge.call_args.args[3]
    assert props["organization"] == "某某大学"
    assert props["overlap_months"] == 77
    assert props["source"] == "expert_colleague_relation_service"
    assert result == {
        "space": "tenant_graph",
        "edgeType": "COLLEAGUE",
        "created": 1,
        "updated": 0,
        "total": 1,
    }
    graph.close.assert_called_once()


def test_persist_relations_failure_does_not_block_query(monkeypatch: pytest.MonkeyPatch) -> None:
    """落盘被图库拒绝（如 schema 冲突）时只记日志，不能拖垮已算好的查询结果。"""
    monkeypatch.setenv("TRS_GRAPH_SPACE", "dev2")
    monkeypatch.delenv("TRS_GRAPH_BUSINESS_BASE_URL", raising=False)
    graph = MagicMock()
    graph.get_node_edges.return_value = []
    graph.create_edge.side_effect = RuntimeError("Unknown column `organization' in schema")
    with patch("application.expert_colleague_relation.TRSGraphClient", return_value=graph):
        result = ExpertColleagueRelationApplication._persist_relations(_persist_payload())

    assert result == {
        "space": "dev2",
        "edgeType": "COLLEAGUE",
        "created": 0,
        "updated": 0,
        "total": 0,
    }
    graph.close.assert_called_once()


def test_persist_relations_follows_business_plane(monkeypatch: pytest.MonkeyPatch) -> None:
    """业务面请求落盘跟随 TRS_GRAPH_BUSINESS_*：读写同库同空间。"""
    from service.graph_space_context import business_data_plane, selected_graph_space

    monkeypatch.setenv("TRS_GRAPH_SPACE", "tenant_graph")
    monkeypatch.setenv("TRS_GRAPH_BUSINESS_BASE_URL", "http://bridge:8190")
    monkeypatch.setenv("TRS_GRAPH_BUSINESS_SPACE", "dev")
    graph = MagicMock()
    graph.get_node_edges.return_value = []
    space_token = selected_graph_space.set("dev2")
    plane_token = business_data_plane.set(True)
    try:
        with patch(
            "application.expert_colleague_relation.TRSGraphClient", return_value=graph
        ) as client:
            result = ExpertColleagueRelationApplication._persist_relations(_persist_payload())
    finally:
        business_data_plane.reset(plane_token)
        selected_graph_space.reset(space_token)

    settings = client.call_args.args[0]
    assert settings.base_url == "http://bridge:8190"
    assert settings.space == "dev"
    graph.create_edge.assert_called_once()
    assert result["space"] == "dev"


def test_persist_relations_ignores_business_env_off_business_plane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非业务面调用（业务面未置位）即便容器里有业务 env，也保持平台连接。"""
    monkeypatch.setenv("TRS_GRAPH_BASE_URL", "http://platform:8090")
    monkeypatch.setenv("TRS_GRAPH_SPACE", "tenant_graph")
    monkeypatch.setenv("TRS_GRAPH_BUSINESS_BASE_URL", "http://bridge:8190")
    monkeypatch.setenv("TRS_GRAPH_BUSINESS_SPACE", "dev")
    graph = MagicMock()
    graph.get_node_edges.return_value = []
    with patch(
        "application.expert_colleague_relation.TRSGraphClient", return_value=graph
    ) as client:
        result = ExpertColleagueRelationApplication._persist_relations(_persist_payload())

    settings = client.call_args.args[0]
    assert settings.base_url == "http://platform:8090"
    assert settings.space == "tenant_graph"
    assert result["space"] == "tenant_graph"
