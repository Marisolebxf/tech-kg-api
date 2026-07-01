from __future__ import annotations

from unittest.mock import MagicMock

from service.enterprise_mining_extractor import extract_relations

PROFILE = {
    "name_zh": "吴边",
    "scholar_org_name_zh": "中国科学院微生物研究所",
    "bio_zh": "该学者从事合成生物学研究，曾与某生物科技公司合作开发酶工程。",
    "work_experience_zh": "2014-至今 中国科学院微生物研究所 研究员",
    "education_background_zh": "",
}


def test_extract_parses_llm_json():
    llm = MagicMock()
    llm.synthesize.return_value = (
        "```json\n"
        '[{"enterprise_name":"某生物科技公司","relation_type":"tech_cooperation",'
        '"role":"technical_advisor","tech_field":"酶工程",'
        '"period_start":"2018-01-01","period_end":"","evidence":"曾与...合作"}]\n'
        "```"
    )
    items, degraded = extract_relations(llm, PROFILE)
    assert degraded is False
    assert len(items) == 1
    assert items[0]["enterprise_name"] == "某生物科技公司"
    assert items[0]["relation_type"] == "tech_cooperation"
    assert items[0]["role"] == "technical_advisor"
    assert items[0]["period_start"] == "2018-01-01"


def test_extract_invalid_relation_type_defaults():
    llm = MagicMock()
    llm.synthesize.return_value = (
        '[{"enterprise_name":"X公司","relation_type":"bogus","role":"bogus"}]'
    )
    items, degraded = extract_relations(llm, PROFILE)
    assert degraded is False
    assert items[0]["relation_type"] == "tech_cooperation"  # 非法 → 默认
    assert items[0]["role"] == "engineer"


def test_extract_llm_none_falls_back_to_regex():
    items, degraded = extract_relations(None, PROFILE)
    assert degraded is True
    names = [i["enterprise_name"] for i in items]
    assert any("公司" in n for n in names)
    assert all(i["relation_type"] == "employment" for i in items)


def test_extract_llm_nonjson_falls_back():
    llm = MagicMock()
    llm.synthesize.return_value = "这不是JSON"
    items, degraded = extract_relations(llm, PROFILE)
    assert degraded is True


def test_extract_llm_returns_empty_array_not_degraded():
    """LLM 正确返回 []（无企业）时不应降级，degraded=False。"""
    llm = MagicMock()
    llm.synthesize.return_value = "[]"
    items, degraded = extract_relations(llm, PROFILE)
    assert degraded is False
    assert items == []
