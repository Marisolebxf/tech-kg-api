"""实体消歧（写前判定）纯函数单测：评分口径 / 三分支决策 / 平台列排除。"""

from __future__ import annotations

from service.entity_disambiguation import (
    GRAY_LOW,
    MARGIN,
    MERGE_THRESHOLD,
    decide,
    display_name,
    normalize_display_name,
    score_candidate,
)


def test_display_name_prefers_name_then_localized():
    assert display_name({"name": "A", "name_cn": "B"}) == "A"
    assert display_name({"name_cn": "B"}) == "B"
    assert display_name({"name_en": "C"}) == "C"
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
    assert detail["comparedProps"] == ["province", "address"]


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
