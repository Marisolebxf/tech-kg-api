# backend/tests/unit/test_expert_cooperation_achievement.py
from __future__ import annotations

import json
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


def test_in_time_range_respects_month_and_day_bounds():
    svc = ExpertCooperationAchievementService()
    # 结束月 2022-08（前端会传 2022-08-31）：9 月成果应被滤掉
    assert svc._in_time_range("2022-09-01", None, "2022-08") is False
    assert svc._in_time_range("2022-09-01", None, "2022-08-31") is False
    assert svc._in_time_range("20220901", None, "2022-08") is False
    # 同月内应保留
    assert svc._in_time_range("2022-08-15", None, "2022-08") is True
    assert svc._in_time_range("2022-08-31", None, "2022-08-31") is True
    # 开始月 2022-09：8 月成果应被滤掉
    assert svc._in_time_range("2022-08-01", "2022-09", None) is False
    assert svc._in_time_range("2022-09-01", "2022-09", None) is True
    # 仅年份的成果：仍按年比较（与旧行为一致）
    assert svc._in_time_range("2022", None, "2022-08") is True
    assert svc._in_time_range("2023", None, "2022-08") is False
    # 有时间筛选时：无法解析/缺失完成时间一律排除
    assert svc._in_time_range(None, None, "2022-08") is False
    assert svc._in_time_range("unknown", None, "2022-08") is False
    assert svc._in_time_range(None, "2022-01", None) is False
    # 未设置时间筛选：缺失时间仍保留
    assert svc._in_time_range(None, None, None) is True
    assert svc._in_time_range("unknown", None, None) is True


def test_query_filters_items_after_time_range_end():
    nodes = {
        "S1": _node("S1", {"name_zh": "甲"}),
        "S2": _node("S2", {"name_zh": "乙"}),
        "P1": _node("P1", {"title": "八月论文", "year": "2022-08-01"}),
        "P2": _node(
            "P2",
            {"title": "一种基于异构图的科技实体关联方法", "publication_date": "20220901"},
        ),
    }
    edges = {
        "S1": [_edge("AUTHORED_BY", "P1", "S1"), _edge("AUTHORED_BY", "P2", "S1")],
        "S2": [_edge("AUTHORED_BY", "P1", "S2"), _edge("AUTHORED_BY", "P2", "S2")],
    }
    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: nodes.get(str(nid)))
    graph.get_node_edges = MagicMock(side_effect=lambda nid, **kw: edges.get(str(nid), []))
    graph._settings = SimpleNamespace(space="dev")

    resp = _svc(graph).query(
        source_expert_id="S1",
        target_expert_id="S2",
        time_range_end="2022-08-31",
    )
    titles = [i["title"] for i in resp["items"]]
    assert "八月论文" in titles
    assert "一种基于异构图的科技实体关联方法" not in titles
    assert resp["summary"]["papers"] == 1


def test_query_excludes_items_without_time_when_range_set():
    nodes = {
        "S1": _node("S1", {"name_zh": "甲"}),
        "S2": _node("S2", {"name_zh": "乙"}),
        "P1": _node("P1", {"title": "有时间专利", "publication_date": "20230901"}),
        "PJ1": _node("PJ1", {"title": "无时间项目"}),
    }
    edges = {
        "S1": [
            _edge("INVENTED_BY", "P1", "S1"),
            _edge("LEADS", "PJ1", "S1"),
        ],
        "S2": [
            _edge("INVENTED_BY", "P1", "S2"),
            _edge("HAS_PARTICIPANT", "PJ1", "S2"),
        ],
    }
    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: nodes.get(str(nid)))
    graph.get_node_edges = MagicMock(side_effect=lambda nid, **kw: edges.get(str(nid), []))
    graph._settings = SimpleNamespace(space="dev")

    resp = _svc(graph).query(
        source_expert_id="S1",
        target_expert_id="S2",
        time_range_start="2023-02-01",
    )
    titles = [i["title"] for i in resp["items"]]
    assert "有时间专利" in titles
    assert "无时间项目" not in titles
    assert resp["summary"]["patents"] == 1
    assert resp["summary"]["projects"] == 0


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


def test_project_awards_from_output_awards_prop():
    """项目奖项/评价读 Project.output_awards（对应 dwd_zh_project_output.output_awards）。"""
    awards_json = json.dumps(
        [{"year": 2020, "title": "数字科技应用示范奖", "authors": ["甲", "乙"]}],
        ensure_ascii=False,
    )
    nodes = {
        "S1": _node("S1", {"name_zh": "甲"}),
        "S2": _node("S2", {"name_zh": "乙"}),
        "PR1": _node(
            "PR1",
            {
                "title": "知识图谱关键项目",
                "approval_year": "2024",
                "output_awards": awards_json,
                "awards_count": 1,
            },
        ),
    }
    edges = {
        "S1": [_edge("LEADS", "PR1", "S1")],
        "S2": [_edge("HAS_PARTICIPANT", "PR1", "S2")],
    }
    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: nodes.get(str(nid)))
    graph.get_node_edges = MagicMock(side_effect=lambda nid, **kw: edges.get(str(nid), []))
    graph._settings = SimpleNamespace(space="dev")

    resp = _svc(graph).query(source_expert_id="S1", target_expert_id="S2")
    assert resp["summary"]["projects"] == 1
    assert resp["summary"]["awards"] == 1
    item = resp["items"][0]
    assert item["type"] == "project"
    assert item["awards"][0]["name"] == "数字科技应用示范奖"
    assert item["awards"][0]["year"] == 2020
    award_row = next(r for r in resp["summaryRows"] if r["label"] == "奖项/评价")
    assert "数字科技应用示范奖" in award_row["value"]


def test_fields_from_has_keyword_edges():
    """所属领域优先走 HAS_KEYWORD→Keyword.keyword。"""
    nodes = {
        "S1": _node("S1", {"name_zh": "甲"}),
        "S2": _node("S2", {"name_zh": "乙"}),
        "P1": _node("P1", {"title": "异构图对齐方法", "year": "2022"}),
        "K1": _node("K1", {"keyword": "异构图"}, labels=["Keyword"]),
        "K2": _node("K2", {"keyword": "实体关联"}, labels=["Keyword"]),
    }
    edges = {
        "S1": [_edge("AUTHORED_BY", "P1", "S1")],
        "S2": [_edge("AUTHORED_BY", "P1", "S2")],
        "P1": [
            _edge("HAS_KEYWORD", "P1", "K1"),
            _edge("HAS_KEYWORD", "P1", "K2"),
        ],
    }
    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: nodes.get(str(nid)))
    graph.get_node_edges = MagicMock(side_effect=lambda nid, **kw: edges.get(str(nid), []))
    graph._settings = SimpleNamespace(space="dev")

    resp = _svc(graph).query(source_expert_id="S1", target_expert_id="S2")
    assert resp["items"][0]["fields"] == ["异构图", "实体关联"]
    domain_row = next(row for row in resp["summaryRows"] if row["label"] == "所属领域")
    assert domain_row["value"] == "异构图、实体关联"


def test_fields_fallback_to_node_keywords_when_no_has_keyword():
    """无 HAS_KEYWORD 时回退成果节点 keywords 属性（专利双写场景）。"""
    nodes = {
        "S1": _node("S1", {"name_zh": "甲"}),
        "S2": _node("S2", {"name_zh": "乙"}),
        "PT1": _node(
            "PT1",
            {
                "title_zh": "一种图谱方法",
                "year": "2022",
                "keywords": [{"zhName": "知识图谱", "enName": "KG"}, {"zhName": "推理"}],
            },
        ),
    }
    edges = {
        "S1": [_edge("INVENTED_BY", "PT1", "S1")],
        "S2": [_edge("INVENTED_BY", "PT1", "S2")],
    }
    graph = MagicMock()
    graph.get_node = MagicMock(side_effect=lambda nid: nodes.get(str(nid)))
    graph.get_node_edges = MagicMock(side_effect=lambda nid, **kw: edges.get(str(nid), []))
    graph._settings = SimpleNamespace(space="dev")

    resp = _svc(graph).query(source_expert_id="S1", target_expert_id="S2")
    assert resp["items"][0]["type"] == "patent"
    assert "知识图谱" in resp["items"][0]["fields"]
    assert "推理" in resp["items"][0]["fields"]
