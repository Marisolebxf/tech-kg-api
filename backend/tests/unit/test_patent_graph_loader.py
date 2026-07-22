from datetime import datetime

from script.load_patent_graph import (
    PATENT_PROPERTIES,
    insert_statement,
    localized_text,
    patent_payload,
)


def test_localized_text_supports_object_and_legacy_array():
    assert localized_text('{"zh":"中文标题"}', "zh") == "中文标题"
    assert localized_text('[{"text":"English","language":"en"}]', "en") == "English"


def test_patent_payload_matches_original_schema():
    row = {
        "patent_id": "CN1A",
        "publication_number": "CN-1-A",
        "application_kind": "A",
        "country_code": "CN",
        "country": "China",
        "title_localized": '{"zh":"标题"}',
        "abstract_localized": '{"zh":"摘要"}',
        "language": "中文（zh）",
        "status": "已授权（Granted）",
        "granted_number": "CN1B",
        "application_date": "2020-01-01",
        "publication_date": "2021-01-01",
        "anticipated_expiration": "2040-01-01",
        "citation_nums": 2,
        "cited_by_nums": 3,
        "update_time": datetime(2026, 7, 22, 10, 0, 0),
    }
    vid, values = patent_payload(row, "BATCH", datetime(2026, 7, 22, 11, 0, 0))
    assert vid == "patent_CN1A"
    assert len(values) == len(PATENT_PROPERTIES)
    statement = insert_statement([(vid, values)])
    assert "INSERT VERTEX Patent" in statement
    assert '"patent_CN1A"' in statement
    assert "CREATE EDGE" not in statement
