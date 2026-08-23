import pytest
from pydantic import ValidationError

from biz.schema.expert_indirect_relation import ExpertIndirectRelationRequest
from service.expert_indirect_relation_api import _build_result


def _core_node():
    return {
        "id": "person_A",
        "labels": ["Person"],
        "properties": {"name_zh": "专家甲"},
    }


def _subgraph():
    return {
        "nodes": [
            _core_node(),
            {
                "id": "person_B",
                "labels": ["Person"],
                "properties": {"name_zh": "专家乙"},
            },
            {
                "id": "person_C",
                "labels": ["Person"],
                "properties": {"name_zh": "专家丙"},
            },
            {
                "id": "project_1",
                "labels": ["Project"],
                "properties": {"name": "项目一"},
            },
            {
                "id": "org_1",
                "labels": ["Organization"],
                "properties": {"name_zh": "机构一"},
            },
        ],
        "edges": [
            {
                "id": "ab",
                "type": "COAUTHOR_WITH",
                "source": "person_A",
                "target": "person_B",
                "properties": {"co_paper_count": 10},
            },
            {
                "id": "ba",
                "type": "COAUTHOR_WITH",
                "source": "person_B",
                "target": "person_A",
                "properties": {"co_paper_count": 10},
            },
            {
                "id": "bc",
                "type": "COAUTHOR_WITH",
                "source": "person_B",
                "target": "person_C",
                "properties": {"co_paper_count": 4},
            },
            {
                "id": "ap",
                "type": "PARTICIPATES_IN",
                "source": "person_A",
                "target": "project_1",
                "properties": {},
            },
            {
                "id": "po",
                "type": "HAS_PARTICIPANT",
                "source": "project_1",
                "target": "org_1",
                "properties": {},
            },
        ],
    }


def test_builds_only_indirect_paths_and_deduplicates_reverse_edges():
    body = ExpertIndirectRelationRequest(
        core_node_id="A",
        relation_types=["学术关联"],
        path_depth=2,
        min_strength=0.65,
    )

    result = _build_result(_core_node(), _subgraph(), body)

    assert result["coreNode"]["name"] == "专家甲"
    assert result["directNodeCount"] == 2
    assert result["indirectNodeCount"] == 1
    assert result["pathCount"] == 1
    assert result["relationTypeCount"] == {"学术关联": 1}
    assert {path["targetNode"]["name"] for path in result["paths"]} == {"专家丙"}
    assert all(path["depth"] == 2 for path in result["paths"])


def test_relation_type_filter_and_string_normalization():
    body = ExpertIndirectRelationRequest(
        core_node_id=" A ",
        relation_types="学术关联",
        path_depth=2,
        min_strength=0.65,
    )
    assert body.core_node_id == "A"
    assert body.relation_types == ["学术关联"]

    body.relation_types = ["学术关联"]
    result = _build_result(_core_node(), _subgraph(), body)

    assert result["pathCount"] == 1
    assert result["paths"][0]["relationType"] == "学术关联"
    assert result["paths"][0]["targetNode"]["name"] == "专家丙"


def test_project_relation_type_returns_only_project_paths():
    body = ExpertIndirectRelationRequest(
        core_node_id="A",
        relation_types=["项目关联"],
        path_depth=2,
        min_strength=0.65,
    )

    result = _build_result(_core_node(), _subgraph(), body)

    assert result["pathCount"] == 1
    assert result["relationTypeCount"] == {"项目关联": 1}
    assert result["paths"][0]["targetNode"]["name"] == "机构一"


def test_relation_type_is_single_choice_from_supported_catalog():
    with pytest.raises(ValidationError):
        ExpertIndirectRelationRequest(
            core_node_id="A",
            relation_types=[],
        )

    with pytest.raises(ValidationError):
        ExpertIndirectRelationRequest(
            core_node_id="A",
            relation_types=["学术关联", "机构关联"],
        )

    with pytest.raises(ValidationError):
        ExpertIndirectRelationRequest(
            core_node_id="A",
            relation_types=["产业关联"],
        )
