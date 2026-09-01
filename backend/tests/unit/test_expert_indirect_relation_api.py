import pytest
from pydantic import ValidationError

from biz.schema.expert_indirect_relation import ExpertIndirectRelationRequest
from service.expert_indirect_relation_api import _build_provenance, _build_result, _build_rules


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
    assert result["directNodeCount"] == 1
    assert result["indirectNodeCount"] == 1
    assert result["pathCount"] == 1
    assert result["relationTypeCount"] == {"学术关联": 1}
    assert {path["targetNode"]["name"] for path in result["paths"]} == {"专家丙"}
    assert all(path["depth"] == 2 for path in result["paths"])


def test_relation_type_filter_and_string_normalization():
    body = ExpertIndirectRelationRequest(
        core_node_id="A",
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


def test_core_node_id_rejects_more_than_64_characters():
    body = ExpertIndirectRelationRequest(
        core_node_id="A" * 64,
        relation_types=["学术关联"],
    )
    assert len(body.core_node_id) == 64

    with pytest.raises(ValidationError, match="核心节点 ID 长度不能超过 64 个字符"):
        ExpertIndirectRelationRequest(
            core_node_id="A" * 65,
            relation_types=["学术关联"],
        )


@pytest.mark.parametrize("core_node_id", ["person_a!@#￥%&", "person a", " person_a"])
def test_core_node_id_rejects_abnormal_characters(core_node_id: str):
    with pytest.raises(ValidationError, match="异常字符"):
        ExpertIndirectRelationRequest(
            core_node_id=core_node_id,
            relation_types=["学术关联"],
        )


def test_rules_describe_the_actual_indirect_path_algorithm():
    body = ExpertIndirectRelationRequest(
        core_node_id="A",
        relation_types=["学术关联"],
        path_depth=2,
        min_strength=0.65,
    )
    rules = _build_rules(_build_result(_core_node(), _subgraph(), body))

    assert [rule["name"] for rule in rules] == [
        "路径分析与关系传递算法",
        "间接关系分类规则",
        "路径强度计算与排序规则",
    ]
    assert "0.92" in rules[2]["logic"]
    assert "本次 0.65" in rules[2]["threshold"]
    assert all("人工复核" not in rule["audit"] for rule in rules)


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


def test_direct_nodes_are_empty_when_no_filtered_path_matches():
    body = ExpertIndirectRelationRequest(
        core_node_id="A",
        relation_types=["项目关联"],
        path_depth=2,
        min_strength=1.0,
    )

    result = _build_result(_core_node(), _subgraph(), body)

    assert result["pathCount"] == 0
    assert result["directNodeCount"] == 0
    assert result["directNodes"] == []
    assert result["indirectNodeCount"] == 0
    assert result["indirectNodes"] == []


def test_builds_provenance_from_real_graph_metadata():
    core_node = _core_node()
    core_node["properties"].update(
        {
            "source_system": "gkx_element",
            "source_table": "dwd_scholar",
            "source_record_id": "A",
            "ingest_batch": "BATCH_PERSON",
            "ingest_time": "2026-08-23 09:21:28",
        }
    )
    subgraph = _subgraph()
    subgraph["nodes"][0] = core_node
    subgraph["edges"][0]["properties"].update(
        {
            "source_table": "dwd_scholar_coauthor",
            "source_record_id": "A_B",
            "ingest_batch": "BATCH_EDGE",
            "ingest_time": "2026-08-23 16:20:30",
        }
    )
    body = ExpertIndirectRelationRequest(
        core_node_id="A",
        relation_types=["学术关联"],
        path_depth=2,
        min_strength=0.65,
    )

    provenance = _build_provenance(_build_result(core_node, subgraph, body))

    assert provenance["sourceDatabase"].startswith("trs-graph / space=")
    assert provenance["summary"].startswith("命中 1 条间接路径")
    core_evidence = next(item for item in provenance["evidences"] if item["graphVid"] == "person_A")
    assert core_evidence == {
        "title": "实体 · 专家甲",
        "sourceTable": "dwd_scholar",
        "sourceField": "scholar_id",
        "graphVid": "person_A",
    }
    assert all(not item["title"].startswith("关系 ·") for item in provenance["evidences"])


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
