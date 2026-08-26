# backend/tests/unit/test_expert_cooperation_achievement.py
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from infra.graph_db import GraphConnectionError
from service.expert_cooperation_achievement import ExpertCooperationAchievementService, clear_caches


@pytest.fixture(autouse=True)
def _isolate_caches():
    """每条用例前后清空进程内 TTL 缓存，避免用例间串味。"""
    clear_caches()
    yield
    clear_caches()


@pytest.fixture(autouse=True)
def _disable_llm_by_default(monkeypatch):
    """默认不打真实 LLM，避免单测依赖外网/密钥。"""
    monkeypatch.setattr(
        "service.expert_cooperation_achievement.get_llm_client",
        lambda: None,
    )


def _node(nid: str, props: dict | None = None, labels: list[str] | None = None):
    return SimpleNamespace(id=nid, properties=props or {}, labels=labels or ["Person"])


def _edge(etype: str, source: str, target: str):
    return SimpleNamespace(
        id=f"{source}->{target}@0",
        type=etype,
        source_id=source,
        target_id=target,
        properties={},
    )


def _svc(graph) -> ExpertCooperationAchievementService:
    svc = ExpertCooperationAchievementService()
    svc._client = MagicMock(return_value=graph)  # type: ignore[method-assign]
    return svc


def test_query_shared_papers_and_patent_with_awards():
    p1 = _node(
        "P1",
        {
            "title": "论文A",
            "year": "2020",
            "keywords": "图谱,AI",
            "award": "优秀论文",
            "source_table": "dwd_paper_test",
            "source_field": "paper_source_id",
        },
    )
    p2 = _node("P2", {"title": "论文B", "year": "2021"})
    pt1 = _node(
        "PT1",
        {
            "title": "专利X",
            "year": "2022",
            "awards": [{"name": "中国专利奖", "level": "国家级", "year": 2022}],
        },
    )
    nodes = {
        "S1": _node(
            "S1",
            {
                "name_zh": "甲",
                "source_table": "dwd_scholar_test",
                "source_field": "scholar_source_id",
            },
        ),
        "S2": _node("S2", {"name_zh": "乙"}),
        "P1": p1,
        "P2": p2,
        "PT1": pt1,
    }
    edges = {
        "S1": [
            _edge("AUTHORED_BY", "P1", "S1"),
            _edge("AUTHORED_BY", "P2", "S1"),
            _edge("INVENTED_BY", "PT1", "S1"),
        ],
        "S2": [
            _edge("AUTHORED_BY", "P1", "S2"),
            _edge("INVENTED_BY", "PT1", "S2"),
        ],
    }
    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: nodes.get(str(nid)))
    graph.get_node_edges = MagicMock(side_effect=lambda nid, **kw: edges.get(str(nid), []))
    graph._settings = SimpleNamespace(space="dev")

    resp = _svc(graph).query(source_expert_id="S1", target_expert_id="S2")

    assert resp["summary"]["papers"] == 1
    assert resp["summary"]["patents"] == 1
    assert resp["summary"]["projects"] == 0
    assert resp["summary"]["awards"] >= 1
    types = {i["type"] for i in resp["items"]}
    assert types == {"paper", "patent"}
    paper = next(i for i in resp["items"] if i["type"] == "paper")
    assert paper["title"] == "论文A"
    assert "图谱" in paper["fields"]
    assert resp["coreContribution"]  # has patent + paper
    assert "共同专利产出" in resp["coreContribution"]
    assert resp["cooperationMode"] in {
        "多类型合作",
        "长期稳定型科研合作",
        "单类型合作（论文）",
        "单类型合作（专利）",
        "单类型合作（项目）",
    }
    assert resp["summaryRows"]
    labels = [row["label"] for row in resp["summaryRows"]]
    assert "成果1" in labels
    assert labels.count("完成时间") >= 1
    assert labels.count("所属领域") >= 1
    assert labels.count("奖项/评价") >= 1
    assert next(row for row in resp["summaryRows"] if row["label"] == "成果1")["value"] == "论文A"
    # 成果1 块：名称后紧跟完成时间/所属领域/奖项/评价
    idx = labels.index("成果1")
    assert labels[idx : idx + 4] == ["成果1", "完成时间", "所属领域", "奖项/评价"]
    assert resp["summaryRows"][idx + 1]["value"] == "2020"
    assert "图谱" in resp["summaryRows"][idx + 2]["value"]
    assert "优秀论文" in resp["summaryRows"][idx + 3]["value"]

    svc = ExpertCooperationAchievementService()
    assert svc._coerce_field_values('["异构图", "实体关联"]') == ["异构图", "实体关联"]
    assert svc._normalize_time_label("20220901") == "2022-09-01"
    assert resp["graph"]["nodes"]
    assert resp["rules"]
    assert resp["provenance"]["evidences"]
    source_evidence = resp["provenance"]["evidences"][0]
    assert source_evidence["technicalTable"] == "dwd_scholar_test"
    assert source_evidence["sourceField"] == "scholar_source_id"
    assert source_evidence["graphVid"] == "S1"
    paper_evidence = next(
        evidence for evidence in resp["provenance"]["evidences"] if evidence["graphVid"] == "P1"
    )
    assert paper_evidence["technicalTable"] == "dwd_paper_test"
    assert paper_evidence["sourceField"] == "paper_source_id"

    target_evidence = resp["provenance"]["evidences"][1]
    assert target_evidence["technicalTable"] == "-"
    assert target_evidence["sourceField"] == "-"


def test_query_same_id_raises():
    graph = MagicMock()
    with pytest.raises(ValueError, match="不能相同"):
        _svc(graph).query(source_expert_id="S1", target_expert_id="S1")


def test_query_missing_expert_raises():
    graph = MagicMock()
    graph.get_node = MagicMock(return_value=None)
    with pytest.raises(KeyError, match="未找到专家"):
        _svc(graph).query(source_expert_id="NO", target_expert_id="S2")


def test_query_propagates_graph_connection_error():
    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=GraphConnectionError("not connected"))

    with pytest.raises(GraphConnectionError, match="not connected"):
        _svc(graph).query(source_expert_id="S1", target_expert_id="S2")


def test_service_does_not_cache_replaced_process_client():
    first = MagicMock()
    second = MagicMock()
    service = ExpertCooperationAchievementService()

    with patch(
        "service.expert_cooperation_achievement.get_trs_graph_client",
        side_effect=[first, second],
    ):
        assert service._client() is first  # noqa: SLF001
        assert service._client() is second  # noqa: SLF001


def test_query_empty_shared_achievements():
    nodes = {
        "S1": _node("S1", {"name_zh": "甲"}),
        "S2": _node("S2", {"name_zh": "乙"}),
    }
    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: nodes.get(str(nid)))
    graph.get_node_edges = MagicMock(return_value=[])
    graph._settings = SimpleNamespace(space="dev")

    resp = _svc(graph).query(source_expert_id="S1", target_expert_id="S2")

    assert resp["summary"] == {"papers": 0, "patents": 0, "projects": 0, "awards": 0}
    assert resp["items"] == []
    assert resp["coreContribution"] == "暂无结构化共同成果"
    assert resp["cooperationMode"] == "暂无合作模式"


def test_cooperation_mode_long_term():
    nodes = {
        "S1": _node("S1", {"name_zh": "甲"}),
        "S2": _node("S2", {"name_zh": "乙"}),
        "P1": _node("P1", {"title": "a", "year": "2018"}),
        "P2": _node("P2", {"title": "b", "year": "2020"}),
        "P3": _node("P3", {"title": "c", "year": "2022"}),
    }
    edges = {
        "S1": [
            _edge("AUTHORED_BY", "P1", "S1"),
            _edge("AUTHORED_BY", "P2", "S1"),
            _edge("AUTHORED_BY", "P3", "S1"),
        ],
        "S2": [
            _edge("AUTHORED_BY", "P1", "S2"),
            _edge("AUTHORED_BY", "P2", "S2"),
            _edge("AUTHORED_BY", "P3", "S2"),
        ],
    }
    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: nodes.get(str(nid)))
    graph.get_node_edges = MagicMock(side_effect=lambda nid, **kw: edges.get(str(nid), []))
    graph._settings = SimpleNamespace(space="dev")

    resp = _svc(graph).query(source_expert_id="S1", target_expert_id="S2")
    assert resp["cooperationMode"] == "长期稳定型科研合作"
    assert resp["coreContribution"] == "共同论文产出"


def test_does_not_treat_project_level_as_award():
    nodes = {
        "S1": _node("S1", {"name_zh": "甲"}),
        "S2": _node("S2", {"name_zh": "乙"}),
        "PR1": _node("PR1", {"title": "项目", "year": "2021", "project_level": "国家级"}),
    }
    edges = {
        "S1": [_edge("HAS_PARTICIPANT", "PR1", "S1")],
        "S2": [_edge("LEADS", "PR1", "S2")],
    }
    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: nodes.get(str(nid)))
    graph.get_node_edges = MagicMock(side_effect=lambda nid, **kw: edges.get(str(nid), []))
    graph._settings = SimpleNamespace(space="dev")

    resp = _svc(graph).query(source_expert_id="S1", target_expert_id="S2")
    assert resp["summary"]["projects"] == 1
    assert resp["summary"]["awards"] == 0
    assert resp["items"][0]["awards"] == []


def test_enrich_fields_with_strict_llm_json(monkeypatch):
    nodes = {
        "S1": _node("S1", {"name_zh": "甲"}),
        "S2": _node("S2", {"name_zh": "乙"}),
        "P1": _node("P1", {"title": "异构图对齐方法", "year": "2022", "keywords": "旧关键词"}),
    }
    edges = {
        "S1": [_edge("AUTHORED_BY", "P1", "S1")],
        "S2": [_edge("AUTHORED_BY", "P1", "S2")],
    }
    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: nodes.get(str(nid)))
    graph.get_node_edges = MagicMock(side_effect=lambda nid, **kw: edges.get(str(nid), []))
    graph._settings = SimpleNamespace(space="dev")

    llm = MagicMock()
    llm.synthesize_json.return_value = '{"items":[{"id":"P1","fields":["异构图","实体关联"]}]}'
    monkeypatch.setattr(
        "service.expert_cooperation_achievement.get_llm_client",
        lambda: llm,
    )

    resp = _svc(graph).query(source_expert_id="S1", target_expert_id="S2")
    assert resp["items"][0]["fields"] == ["异构图", "实体关联"]
    domain_row = next(row for row in resp["summaryRows"] if row["label"] == "所属领域")
    assert domain_row["value"] == "异构图、实体关联"
    llm.synthesize_json.assert_called_once()
    kwargs = llm.synthesize_json.call_args.kwargs
    assert kwargs["schema_name"] == "cooperation_achievement_domains"
    assert kwargs["schema"]["required"] == ["items"]
    prompt = llm.synthesize_json.call_args.args[0]
    assert "P1" in prompt
    assert "技术领域" in prompt


def test_enrich_fields_keeps_graph_when_llm_json_invalid(monkeypatch):
    nodes = {
        "S1": _node("S1", {"name_zh": "甲"}),
        "S2": _node("S2", {"name_zh": "乙"}),
        "P1": _node("P1", {"title": "论文A", "year": "2020", "keywords": "图谱,AI"}),
    }
    edges = {
        "S1": [_edge("AUTHORED_BY", "P1", "S1")],
        "S2": [_edge("AUTHORED_BY", "P1", "S2")],
    }
    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: nodes.get(str(nid)))
    graph.get_node_edges = MagicMock(side_effect=lambda nid, **kw: edges.get(str(nid), []))
    graph._settings = SimpleNamespace(space="dev")

    llm = MagicMock()
    llm.synthesize_json.return_value = "所属领域是人工智能"  # 非严格 JSON
    monkeypatch.setattr(
        "service.expert_cooperation_achievement.get_llm_client",
        lambda: llm,
    )

    resp = _svc(graph).query(source_expert_id="S1", target_expert_id="S2")
    assert "图谱" in resp["items"][0]["fields"]
    assert "AI" in resp["items"][0]["fields"]


def test_parse_domain_llm_json_rejects_non_object():
    svc = ExpertCooperationAchievementService()
    assert svc._parse_domain_llm_json('[{"id":"P1","fields":["AI"]}]') is None
    assert svc._parse_domain_llm_json('{"items":[{"id":"P1","fields":["AI"]}]}') == [
        {"id": "P1", "fields": ["AI"]}
    ]


def test_parse_domain_llm_json_tolerates_trailing_junk():
    svc = ExpertCooperationAchievementService()
    raw = '{"items":[{"id":"P1","fields":["风电","数据定价"]}]} }'
    assert svc._parse_domain_llm_json(raw) == [{"id": "P1", "fields": ["风电", "数据定价"]}]
