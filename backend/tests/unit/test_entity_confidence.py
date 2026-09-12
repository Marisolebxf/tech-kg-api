"""实体置信度：已有值优先、规则计算、默认兜底、尽力写回图。"""

from __future__ import annotations

from types import SimpleNamespace

import service.entity_confidence as mod
from service.entity_confidence import (
    DEFAULT_ENTITY_CONFIDENCE,
    compute_entity_confidence,
    fill_entity_confidence,
    parse_confidence,
    persist_entity_confidence,
    resolve_entity_confidence,
)


class FakeGraph:
    def __init__(self, fail_first: bool = False) -> None:
        self.writes: list[str] = []
        self.fail_first = fail_first

    def execute_write(self, query: str):
        self.writes.append(query)
        if self.fail_first and "ALTER TAG" not in query and len(self.writes) == 1:
            raise RuntimeError("Unknown column confidence")
        return SimpleNamespace(records=[])


def setup_function() -> None:
    mod.reset_persist_state()


def test_parse_confidence_rejects_blank_and_nan() -> None:
    assert parse_confidence(None) is None
    assert parse_confidence("") is None
    assert parse_confidence("x") is None
    assert parse_confidence(float("nan")) is None
    assert parse_confidence(0.81) == 0.81
    assert parse_confidence("0.9") == 0.9


def test_compute_matches_dwd_evidence_rule() -> None:
    score = compute_entity_confidence(
        {
            "source_table": "dwd_scholar",
            "source_record_id": "s1",
            "name_cn": "张三",
        }
    )
    assert score == 0.8
    assert compute_entity_confidence({}) is None


def test_resolve_prefers_existing_then_rule_then_default() -> None:
    assert resolve_entity_confidence({"confidence": 0.92}) == 0.92
    assert (
        resolve_entity_confidence(
            {"source_table": "dwd_org_base_info", "organization_id": "o1", "name_cn": "甲"}
        )
        == 0.8
    )
    assert resolve_entity_confidence({}) == DEFAULT_ENTITY_CONFIDENCE


def test_fill_writes_back_when_missing() -> None:
    graph = FakeGraph()
    props = {"source_table": "dwd_scholar", "source_record_id": "s1", "name_zh": "李四"}
    value = fill_entity_confidence(props, {"Person"}, vid="person_s1", client=graph)
    assert value == 0.8
    assert props["confidence"] == 0.8
    assert any("UPDATE VERTEX ON `Person`" in q and "person_s1" in q for q in graph.writes)


def test_fill_skips_write_when_already_present() -> None:
    graph = FakeGraph()
    props = {"confidence": 0.88, "name_cn": "甲"}
    value = fill_entity_confidence(props, {"Organization"}, vid="org_a", client=graph)
    assert value == 0.88
    assert graph.writes == []


def test_persist_alters_tag_then_retries() -> None:
    graph = FakeGraph(fail_first=True)
    assert persist_entity_confidence(graph, "node_x", "IndustryNode", 0.8)
    assert any("ALTER TAG `IndustryNode`" in q for q in graph.writes)
    assert graph.writes[-1].startswith("UPDATE VERTEX ON `IndustryNode`")


def test_fill_survives_persist_failure() -> None:
    class Boom:
        def execute_write(self, query: str) -> None:
            raise RuntimeError("graph down")

    props: dict = {}
    value = fill_entity_confidence(props, {"Organization"}, vid="org_z", client=Boom())
    assert value == DEFAULT_ENTITY_CONFIDENCE
    assert props["confidence"] == DEFAULT_ENTITY_CONFIDENCE
