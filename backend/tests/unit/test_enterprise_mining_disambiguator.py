from __future__ import annotations

from service.enterprise_mining_disambiguator import disambiguate, merge_matches


def test_disambiguate_exact_match():
    candidates = [
        ("id1", "上海微创医疗机器人(集团)股份有限公司"),
        ("id2", "浙江菜鸟供应链管理有限公司"),
    ]
    m = disambiguate("上海微创医疗机器人(集团)股份有限公司", candidates)
    assert m == {"org_id": "id1", "name_cn": "上海微创医疗机器人(集团)股份有限公司", "score": 100.0}


def test_disambiguate_fuzzy_partial():
    candidates = [("id1", "上海微创医疗机器人(集团)股份有限公司")]
    m = disambiguate("上海微创医疗", candidates)
    assert m is not None
    assert m["org_id"] == "id1"
    assert m["score"] >= 70


def test_disambiguate_below_threshold_returns_none():
    candidates = [("id1", "上海微创医疗机器人(集团)股份有限公司")]
    assert disambiguate("完全不相关的名字XYZ", candidates) is None


def test_disambiguate_rejects_common_suffix_false_positive():
    """共有'股份有限公司'后缀不应把不相关公司误匹配（菲鹏生物 vs 上海微创）。"""
    candidates = [("id1", "上海微创医疗机器人(集团)股份有限公司")]
    assert disambiguate("菲鹏生物股份有限公司", candidates) is None


def test_disambiguate_rejects_suffix_only_fragment():
    """抽取名剥后缀后过短（如'科技有限公司'→'科技'）应拒绝，不误匹配垃圾名。"""
    candidates = [("id1", "科技有限公司"), ("id2", "福建帝视信息科技有限公司")]
    assert disambiguate("科技有限公司", candidates) is None


def test_disambiguate_empty_candidates():
    assert disambiguate("某公司", []) is None


def test_merge_matches_dedups_by_org_id_and_unions_relation_types():
    matches = [
        {
            "org_id": "id1",
            "name_cn": "A公司",
            "score": 80.0,
            "relation_type": "employment",
            "role": "engineer",
            "tech_field": "",
            "period_start": "",
            "period_end": "",
            "evidence": "",
        },
        {
            "org_id": "id1",
            "name_cn": "A公司",
            "score": 85.0,
            "relation_type": "tech_cooperation",
            "role": "technical_advisor",
            "tech_field": "酶",
            "period_start": "",
            "period_end": "",
            "evidence": "",
        },
        {
            "org_id": "id2",
            "name_cn": "B公司",
            "score": 70.0,
            "relation_type": "advisor",
            "role": "engineer",
            "tech_field": "",
            "period_start": "",
            "period_end": "",
            "evidence": "",
        },
    ]
    merged = merge_matches(matches)
    assert len(merged) == 2
    a = next(m for m in merged if m["org_id"] == "id1")
    assert a["score"] == 85.0  # 取最高分
    assert a["relation_types"] == ["employment", "tech_cooperation"]
