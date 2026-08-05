import pytest

from biz.schema.expert_paper_cooperation import ExpertPaperCooperationDemoRequest
from service.expert_paper_cooperation_api import _build_structured_result


class FakeGraphSearchApi:
    async def get_node(self, node_id: str, *, space: str):
        nodes = {
            "person_A": {
                "id": "person_A",
                "labels": ["Person"],
                "properties": {
                    "name_zh": "专家甲",
                    "scholar_org": "甲单位",
                    "research_fields": "医学影像;人工智能",
                },
            },
            "person_B": {
                "id": "person_B",
                "labels": ["Person"],
                "properties": {
                    "name_zh": "专家乙",
                    "scholar_org": "乙单位",
                    "research_fields": "医学影像;知识图谱",
                },
            },
        }
        return nodes[node_id]

    async def search_paths(self, body: dict):
        edge_type = body["steps"][0]["edgeType"]
        if edge_type == "AUTHORED_BY":
            return {"items": [], "total": 0}
        if len(body["steps"]) == 1:
            return {
                "items": [
                    {
                        "nodes": [{"id": "person_A"}, {"id": "person_B"}],
                        "edges": [
                            {
                                "type": "COAUTHOR_WITH",
                                "properties": {"co_paper_count": 35},
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


@pytest.mark.asyncio
async def test_coauthor_edge_fallback_keeps_unproven_fields_empty():
    body = ExpertPaperCooperationDemoRequest(
        dataSource="knowledge_graph",
        expertAId="A",
        expertBId="B",
    )

    result = await _build_structured_result(FakeGraphSearchApi(), body)

    assert result["authorList"] == ["专家甲", "专家乙"]
    assert result["cooperationPaperCount"] == 35
    assert result["cooperationFrequency"] == 35
    assert result["paperTopics"][0] == "医学影像"
    assert result["coreCollaborators"] == ["共同作者丙"]
    assert result["stableTeamMembers"] == []
    assert result["cooperationTimeRange"]["displayText"] == ""
    assert result["journalLevelCount"] == {}
    assert result["conferenceLevelCount"] == {}
    assert result["citation"] == {"total": 0, "max": 0}
