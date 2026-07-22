from datetime import datetime

from script.load_patent_graph import (
    PATENT_PROPERTIES,
    SELECT_SQL,
    first_localized_text,
    insert_statement,
    localized_text,
    normalized_language,
    patent_payload,
)


def _row():
    return {
        "patent_id": "CN1A",
        "publication_number": "CN-1-A",
        "application_kind": "A",
        "country_code": "CN",
        "country": "China",
        "publication_kind": "A",
        "publication_date": "2021-01-01",
        "publication_year": 2021,
        "publication_month": "2021-01",
        "application_number": "CN-APP-1",
        "application_country": "CN",
        "application_date": "2020-01-01",
        "application_year": 2020,
        "application_month": "2020-01",
        "pct_application_number": "PCT/CN/1",
        "pct_application_date": "2020-01-01",
        "pct_national_stage_date": "2022-01-01",
        "pct_publication_number": "WO1",
        "pct_publication_date": "2021-01-01",
        "titles": '{"zh":"原文标题"}',
        "title_localized": '{"en":"English title"}',
        "title_zh": "中文标题",
        "abstracts": '{"zh":"原文摘要"}',
        "abstract_localized": '{"en":"English abstract"}',
        "abstract_zh": "中文摘要",
        "language": '["zh"]',
        "granted_number": "CN1B",
        "main_ipcr": "G06F",
        "further_ipcr": '["G06N"]',
        "main_cpc": "G06F",
        "further_cpc": '["G06N"]',
        "keywords": '["知识图谱"]',
        "status": "已授权（Granted）",
        "grant_date": "2022-01-01",
        "grant_year": 2022,
        "grant_month": "2022-01",
        "anticipated_expiration": "2040-01-01",
        "expiration_year": 2040,
        "citation_nums": 2,
        "cited_by_nums": 3,
        "non_patent_citation_nums": 1,
        "patent_value": 100,
        "simple_family_number": "F1",
        "update_time": datetime(2026, 7, 22, 10, 0, 0),
    }


def test_localized_helpers():
    assert localized_text('{"zh":"中文标题"}', "zh") == "中文标题"
    assert localized_text('[{"text":"English","language":"en"}]', "en") == "English"
    assert first_localized_text('{"en":"English"}') == "English"
    assert normalized_language('["zh", "en"]') == "zh,en"


def test_select_sql_uses_confirmed_json_columns():
    for path in ("$.apdt", "$.pbdt", "$.kind", "$.date"):
        assert path in SELECT_SQL
    for obsolete in ("application_reference_3", "publication_reference_2"):
        assert obsolete not in SELECT_SQL
    assert "dwd_patent_family" in SELECT_SQL


def test_patent_payload_matches_schema():
    vid, values = patent_payload(_row(), "BATCH", datetime(2026, 7, 22, 11, 0, 0))
    assert vid == "patent_CN1A"
    assert len(values) == len(PATENT_PROPERTIES)
    mapped = dict(zip(PATENT_PROPERTIES, values, strict=True))
    assert mapped["patent_id"] == '"CN1A"'
    assert mapped["title_zh"] == '"中文标题"'
    assert mapped["abstract_en"] == '"English abstract"'
    assert mapped["language"] == '"zh"'
    statement = insert_statement([(vid, values)])
    assert "INSERT VERTEX Patent" in statement
    assert '"patent_CN1A"' in statement
    assert "CREATE EDGE" not in statement
