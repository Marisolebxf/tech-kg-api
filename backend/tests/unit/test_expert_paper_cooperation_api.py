import asyncio

import pytest

from biz.schema.expert_paper_cooperation import ExpertPaperCooperationDemoRequest
from service.expert_paper_cooperation_api import (
    _build_rules,
    _build_structured_result,
    _fetch_paper_context,
    _year_filters,
)


class FakeGraphSearchApi:
    def __init__(self):
        self.path_requests = []

    async def get_node(self, node_id: str, *, space: str):
        # 同时接受带/不带 person_ 前缀的 ID，兼容 dev/techkg 两种图空间
        normalized = node_id.removeprefix("person_")
        nodes = {
            "A": {
                "id": "person_A",
                "labels": ["Person"],
                "properties": {
                    "name_zh": "专家甲",
                    "scholar_org": "甲单位",
                    "research_fields": "医学影像;人工智能",
                    "source_system": "gkx_element",
                    "source_table": "dwd_scholar",
                    "source_record_id": "A",
                    "ingest_batch": "BATCH_PERSON",
                    "ingest_time": "2026-08-23 09:21:28",
                },
            },
            "B": {
                "id": "person_B",
                "labels": ["Person"],
                "properties": {
                    "name_zh": "专家乙",
                    "scholar_org": "乙单位",
                    "research_fields": "医学影像;知识图谱",
                },
            },
        }
        return nodes[normalized]

    async def search_paths(self, body: dict):
        self.path_requests.append(body)
        edge_type = body["steps"][0]["edgeType"]
        # 无论文路径：AUTHORED（techkg）或 AUTHORED_BY（dev）均返回空
        if edge_type in ("AUTHORED", "AUTHORED_BY"):
            return {"items": [], "total": 0}
        if len(body["steps"]) == 1:
            return {
                "items": [
                    {
                        "nodes": [{"id": "person_A"}, {"id": "person_B"}],
                        "edges": [
                            {
                                "id": "person_A->person_B@0",
                                "type": "COAUTHOR_WITH",
                                "source": "person_A",
                                "target": "person_B",
                                "properties": {
                                    "co_paper_count": 35,
                                    "source_table": "dwd_scholar_coauthor",
                                    "source_record_id": "A_B",
                                    "ingest_batch": "BATCH_EDGE",
                                    "ingest_time": "2026-08-23 16:20:30",
                                },
                            }
                        ],
                    }
                ],
                "total": 1,
            }
        return {
            "items": [
                {
                    "nodes": [
                        {"id": "person_A"},
                        {
                            "id": "person_C",
                            "properties": {"name_zh": "共同作者丙"},
                        },
                        {"id": "person_B"},
                    ],
                    "edges": [
                        {"properties": {"co_paper_count": 12}},
                        {"properties": {"co_paper_count": 4}},
                    ],
                }
            ],
            "total": 1,
        }

    async def get_subgraph(self, *args, **kwargs):
        raise AssertionError("无逐篇论文路径时不应查询论文子图")


def test_request_schema_does_not_expose_data_source():
    schema = ExpertPaperCooperationDemoRequest.model_json_schema()

    assert "dataSource" not in schema["properties"]



@pytest.mark.parametrize(
    ("expert_a_id", "expert_b_id"),
    [
        ("专家甲", "专家乙"),
        ("person_A.1", "person_B-2"),
        ("专家·甲", "专家·乙"),
    ],
)
def test_expert_ids_accept_the_same_characters_as_colleague_relation(
    expert_a_id: str, expert_b_id: str
):
    body = ExpertPaperCooperationDemoRequest(
        expertAId=expert_a_id,
        expertBId=expert_b_id,
    )

    assert body.expertAId == expert_a_id
    assert body.expertBId == expert_b_id


@pytest.mark.parametrize("field", ["expertAId", "expertBId"])
@pytest.mark.parametrize("invalid_id", ["person A", "person@A", " person_A", "person_A\n"])
def test_expert_ids_reject_whitespace_and_abnormal_characters(
    field: str, invalid_id: str
):
    payload = {"expertAId": "person_A", "expertBId": "person_B"}
    payload[field] = invalid_id

    with pytest.raises(ValueError, match="异常字符"):
        ExpertPaperCooperationDemoRequest(**payload)


def test_year_filters_use_string_publication_year():
    body = ExpertPaperCooperationDemoRequest(
        expertAId="A",
        expertBId="B",
        startTime="2021-01-01",
        endTime="2026-08-31",
    )

    assert _year_filters(body) == [
        {"property": "publication_year", "operator": "gte", "value": "2021"},
        {"property": "publication_year", "operator": "lte", "value": "2026"},
    ]


def test_rules_describe_the_actual_paper_cooperation_algorithm():
    rules = _build_rules(
        {
            "cooperationPaperCount": 6,
            "stableTeamMembers": ["共同作者丙"],
            "academicImpactScore": 57.8,
        }
    )

    assert [rule["name"] for rule in rules] == [
        "作者关联与合作频次算法",
        "论文指标与合作成员统计规则",
        "学术影响力与共同贡献计算规则",
    ]
    assert "仅取" in rules[0]["logic"] and "年份" in rules[0]["logic"]
    assert "未配置 status=1" in rules[0]["threshold"]
    assert "至少覆盖 2 个不同发表年份" in rules[1]["threshold"]
    assert "论文数×6.5" in rules[2]["logic"]


@pytest.mark.asyncio
async def test_coauthor_edge_fallback_keeps_unproven_fields_empty():
    body = ExpertPaperCooperationDemoRequest(
        expertAId="A",
        expertBId="B",
    )

    graph_api = FakeGraphSearchApi()
    result = await _build_structured_result(graph_api, body)

    assert result["authorList"] == ["专家甲", "专家乙"]
    assert result["cooperationPaperCount"] == 35
    assert result["cooperationFrequency"] == 35
    shared_path_request = graph_api.path_requests[0]
    assert shared_path_request["sourceId"] == "person_A"
    assert shared_path_request["targetId"] == "person_B"
    assert shared_path_request["steps"][0]["direction"] == "in"
    assert shared_path_request["steps"][1]["direction"] == "out"
    assert result["paperTopics"][0] == "医学影像"
    assert result["coreCollaborators"] == ["共同作者丙"]
    assert result["stableTeamMembers"] == []
    assert result["cooperationTimeRange"]["displayText"] == ""
    assert result["journalLevelCount"] == {}
    assert result["conferenceLevelCount"] == {}
    assert result["citation"] == {"total": 0, "max": 0}
    provenance = result["_provenance"]
    assert provenance["sourceDatabase"].startswith("trs-graph / space=")
    expert_evidence = next(
        item for item in provenance["evidences"] if item["graphVid"] == "person_A"
    )
    assert expert_evidence == {
        "title": "实体 · 专家甲",
        "sourceTable": "dwd_scholar",
        "sourceField": "scholar_id",
        "graphVid": "person_A",
    }
    assert all(not item["title"].startswith("关系 ·") for item in provenance["evidences"])


@pytest.mark.asyncio
async def test_paper_context_uses_dev_keyword_and_citation_edges():
    class FakeContextGraphApi:
        def __init__(self):
            self.calls = []

        async def get_subgraph(self, node_id, **kwargs):
            self.calls.append((kwargs["edge_type"], kwargs["direction"]))
            return {"nodes": [{"id": node_id}], "edges": []}

    graph_api = FakeContextGraphApi()
    await _fetch_paper_context(
        graph_api,
        {"id": "paper_1", "properties": {}},
        space="dev",
        semaphore=asyncio.Semaphore(1),
    )

    assert ("HAS_KEYWORD", "out") in graph_api.calls
    assert ("CITED_BY", "out") in graph_api.calls
