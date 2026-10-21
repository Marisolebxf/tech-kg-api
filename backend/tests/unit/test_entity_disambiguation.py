"""实体消歧（写前判定）纯函数单测：评分口径 / 三分支决策 / 平台列排除 / 多路召回。"""

from __future__ import annotations

from typing import Any

import pytest

from service import entity_disambiguation as ed
from service.entity_disambiguation import (
    GRAY_LOW,
    MARGIN,
    MERGE_THRESHOLD,
    decide,
    display_name,
    name_columns_in,
    normalize_display_name,
    recall_candidates,
    score_candidate,
)


def test_name_columns_in_picks_existing_by_priority():
    # vendor ETL 的 Organization 只有 name_cn；schema 管理的 tag 有 name
    assert name_columns_in({"name_cn", "province"}) == ["name_cn"]
    assert name_columns_in({"name", "name_cn"}) == ["name", "name_cn"]
    assert name_columns_in({"name_en", "name_zh"}) == ["name_zh", "name_en"]
    assert name_columns_in({"org_id", "address"}) == []  # 无显示名列 → 召回跳过


def test_display_name_prefers_name_then_localized():
    assert display_name({"name": "A", "name_cn": "B"}) == "A"
    assert display_name({"name_cn": "B"}) == "B"
    assert display_name({"name_en": "C"}) == "C"
    # 中文优先于英文：同英文名的不同学者（王毅/王祎/王翊 都叫 Yi Wang）
    # 不能坍缩成同一显示名，否则批内去重会错并（2026-10-16 一2/一3 根因）
    assert display_name({"name_zh": "王祎", "name_en": "Yi Wang"}) == "王祎"
    assert display_name({"id": "x"}) == ""


def test_normalize_collapses_width_and_whitespace():
    # 全角空格（U+3000）经 NFKC 归一后与半角空白等价
    assert normalize_display_name("  中科院　计算所 ") == normalize_display_name("中科院 计算所")


def test_full_agreement_scores_one():
    score, detail = score_candidate(
        "中科院计算所",
        {"province": "北京", "address": "中关村"},
        "中科院计算所",
        {"province": "北京", "address": "中关村"},
    )
    assert score == 1.0
    assert detail["propsAgree"] == 1.0
    # 证据 v2（gray-gate-v2）：每字段 {key, match, side} 布尔化，不含业务值
    assert detail["comparedProps"] == [
        {"key": "province", "match": True, "side": "both"},
        {"key": "address", "match": True, "side": "both"},
    ]
    assert detail["propCompared"] == 2 and detail["propMatched"] == 2


def test_no_comparable_props_is_neutral_gray():
    # 同名但候选无可比属性：0.6 + 0.4*0.5 = 0.8 → 灰区
    score, _ = score_candidate("同名人", {"org": "A"}, "同名人", {})
    assert GRAY_LOW <= score < MERGE_THRESHOLD


def test_all_conflicting_props_falls_below_gray_low():
    # 同名但可比属性全不一致：0.6 + 0 = 0.6 → 低于灰区下界（同名异体 → 新建）
    score, _ = score_candidate(
        "同名", {"province": "北京", "address": "甲"}, "同名", {"province": "上海", "address": "乙"}
    )
    assert score < GRAY_LOW


def test_meta_columns_do_not_count_as_evidence():
    # 平台溯源列差异不参与评分
    score, _ = score_candidate(
        "X",
        {"create_time": "1", "source_table": "a", "province": "京"},
        "X",
        {"create_time": "2", "source_table": "b", "province": "京"},
    )
    assert score == 1.0


def test_platform_lineage_columns_do_not_count_as_evidence():
    # 摄取/溯源元数据列同源近乎恒定（source_system/ingest_batch）、或与身份无关
    # （match_method/scholar_status 是厂商匹配过程标注）——参与评分会把同名不同人
    # 的属性一致率基线抬高到灰区（2026-10-16 王祎/王翊 实测 ~0.37 → 总分 ~0.74）。
    # 排除后唯一可比业务列 org 不一致 → 属性分 0，同名总分 0.6 低于灰区下界。
    score, detail = score_candidate(
        "王伟",
        {
            "source_system": "gkx",
            "source_record_id": "a1",
            "ingest_batch": "20261016",
            "match_method": "exact",
            "scholar_status": "active",
            "confidence": "0.9",
            "org": "清华大学",
        },
        "王伟",
        {
            "source_system": "gkx",
            "source_record_id": "b2",
            "ingest_batch": "20261016",
            "match_method": "fuzzy",
            "scholar_status": "active",
            "confidence": "0.7",
            "org": "北京大学",
        },
    )
    assert detail["comparedProps"] == [{"key": "org", "match": False, "side": "both"}]
    assert detail["propCompared"] == 1 and detail["propMatched"] == 0
    assert score < GRAY_LOW


def test_decide_no_candidates_is_new():
    assert decide([])["decision"] == "new"


def test_decide_single_high_candidate_merges():
    out = decide([{"vid": "v1", "name": "x", "score": 0.95}])
    assert out["decision"] == "merge"
    assert out["targetVid"] == "v1"
    assert out["margin"] is None  # 单候选视为分差通过


def test_decide_ambiguous_high_pair_goes_gray():
    out = decide(
        [
            {"vid": "v1", "name": "x", "score": 0.95},
            {"vid": "v2", "name": "x", "score": 0.95 - MARGIN + 0.01},
        ]
    )
    assert out["decision"] == "gray"


def test_decide_low_score_is_new():
    out = decide([{"vid": "v1", "name": "x", "score": 0.6}])
    assert out["decision"] == "new"


# ---------------------------------------------------------------------------
# 多路召回：Milvus 近邻路（fail-open）+ 并集去重
# ---------------------------------------------------------------------------


class _FakeMilvus:
    """MilvusClient 高层 search 的最小仿真：返回按查询分组的 dict 型命中。"""

    def __init__(self, per_query_hits: list[list[dict[str, Any]]]) -> None:
        self._per_query = per_query_hits
        self.search_calls: list[dict[str, Any]] = []

    def has_collection(self, name: str) -> bool:
        return True

    def query(self, **kwargs: Any) -> list[dict[str, Any]]:
        return [{"vid": "stub"}]  # _milvus_space_has_rows → True

    def search(self, **kwargs: Any) -> list[list[dict[str, Any]]]:
        self.search_calls.append(kwargs)
        return self._per_query


class _FakeEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(i)] for i, _ in enumerate(texts)]


def _hit(vid: str, name: str, distance: float, props: str = "{}") -> dict[str, Any]:
    return {
        "id": f"dev2::{vid}",
        "distance": distance,
        "entity": {"vid": vid, "name": name, "properties": props},
    }


def test_fuzzy_recall_kill_switch(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENTITY_DISAMBIGUATION_MILVUS_RECALL", "0")
    milvus = _FakeMilvus([[_hit("v9", "无关", 0.99)]])
    # gray-gate-v2：返回 (载荷, routeStatus)——开关关闭属可用性降级 degraded
    out = ed._milvus_fuzzy_recall(
        "Person", ["张三"], "dev2", milvus=milvus, embedder=_FakeEmbedder()
    )
    assert out == ({}, "degraded")
    assert milvus.search_calls == []  # 关闭时不发任何检索


def test_fuzzy_recall_filters_by_min_sim_and_parses_props(monkeypatch: pytest.MonkeyPatch):
    for key in (
        "ENTITY_DISAMBIGUATION_MILVUS_RECALL",
        "ENTITY_DISAMBIGUATION_MILVUS_TOP_K",
        "ENTITY_DISAMBIGUATION_MILVUS_MIN_SIM",
    ):
        monkeypatch.delenv(key, raising=False)
    milvus = _FakeMilvus(
        [
            [
                _hit("v1", "华为技术有限公司", 0.93, '{"province": "广东省"}'),
                _hit("v2", "无关公司", 0.70),  # 低于最小相似度 → 丢弃
                _hit("v3", "华为技术", 0.88, "非JSON"),  # properties 解析失败 → 空 dict
            ]
        ]
    )
    merged, status = ed._milvus_fuzzy_recall(
        "Organization", ["华为技术"], "dev2", milvus=milvus, embedder=_FakeEmbedder()
    )
    assert status == "ok"  # 有命中
    cands = merged["华为技术"]
    assert [c["vid"] for c in cands] == ["v1", "v3"]
    assert cands[0]["props"] == {"province": "广东省"}
    assert cands[1]["props"] == {}
    assert cands[0]["similarity"] == pytest.approx(0.93)


def test_fuzzy_recall_degrades_without_embedder(monkeypatch: pytest.MonkeyPatch):
    # 容器里可能带真实 embedding 配置：钉死 _embedding_client 返回 None
    monkeypatch.setattr("service.entity_search._embedding_client", lambda: None)
    milvus = _FakeMilvus([[_hit("v9", "无关", 0.99)]])
    out = ed._milvus_fuzzy_recall("Person", ["张三"], "dev2", milvus=milvus, embedder=None)
    assert out == ({}, "degraded")  # embedding 未配置=可用性降级
    assert milvus.search_calls == []


def test_fuzzy_recall_degrades_on_milvus_error():
    class _Broken(_FakeMilvus):
        def search(self, **kwargs: Any) -> Any:
            raise RuntimeError("milvus down")

    out = ed._milvus_fuzzy_recall(
        "Person", ["张三"], "dev2", milvus=_Broken([]), embedder=_FakeEmbedder()
    )
    assert out == ({}, "service_error")  # 检索异常≠真空，状态如实区分


class _FakeGraph:
    """图客户端仿真：DESCRIBE 报 name 列；MATCH 命中预置同名候选。"""

    def execute_query(self, q: str) -> Any:
        class _R:
            records = [{"Field": "name"}]

        return _R()

    def execute_read(self, q: str) -> Any:
        class _R:
            records = [
                {"vid": "e1", "props": {"name": "王伟", "province": "北京"}},
                {"vid": "e2", "props": {"name": "王伟", "province": "上海"}},
            ]

        return _R()


def test_recall_candidates_unions_two_roads_dedup_by_vid(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ENTITY_DISAMBIGUATION_MILVUS_RECALL", raising=False)
    # 近邻路：e2 已被同名路召回（去重丢弃），e3 为不同名新候选
    monkeypatch.setattr(
        ed,
        "_milvus_fuzzy_recall",
        lambda tag, names, space, **kw: (
            {
                "王伟": [
                    {"vid": "e2", "name": "王伟", "props": {}, "similarity": 0.9},
                    {"vid": "e3", "name": "汪伟", "props": {"province": "北京"}, "similarity": 0.8},
                ]
            },
            "ok",
        ),
    )
    out = recall_candidates(_FakeGraph(), "Person", ["王伟"], space="dev2")
    vids = [c["vid"] for c in out["王伟"]]
    assert vids == ["e1", "e2", "e3"]  # 同名路在前，近邻路去重后补位


def test_recall_candidates_fuzzy_failure_falls_back_to_exact(monkeypatch: pytest.MonkeyPatch):
    # 近邻路异常（service_error）fail-open：载荷空，仅同名路候选
    monkeypatch.setattr(ed, "_milvus_fuzzy_recall", lambda *a, **kw: ({}, "service_error"))
    out = recall_candidates(_FakeGraph(), "Person", ["王伟"], space="dev2")
    assert [c["vid"] for c in out["王伟"]] == ["e1", "e2"]


def test_name_similarity_varies_for_fuzzy_names():
    # 多路召回的意义：不同名候选的名称相似度是真实变量，不再恒 1.0；
    # 属性全一致时同名候选满分（自动并），近名候选按权重折价后不再轻易过阈值
    score_same, exact = score_candidate(
        "华为技术", {"province": "广东省"}, "华为技术", {"province": "广东省"}
    )
    score_near, fuzzy = score_candidate(
        "华为技术", {"province": "广东省"}, "华为技术有限公司", {"province": "广东省"}
    )
    assert exact["nameSim"] == 1.0
    assert score_same == 1.0
    assert 0.0 < fuzzy["nameSim"] < 1.0
    assert score_near < score_same
