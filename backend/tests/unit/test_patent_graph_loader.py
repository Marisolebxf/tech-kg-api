import re
from datetime import datetime
from pathlib import Path

from script.load_patent_graph import (
    PATENT_PROPERTIES,
    SELECT_SQL,
    SQL_FILE,
    family_statements,
    keyword_statements,
    keyword_values,
    patent_payload,
    patent_statement,
)


def patent_row():
    return {
        "patent_id": "CN1A",
        "publication_number": "CN-1-A",
        "application_number": "CN-APP-1",
        "application_kind": "A",
        "country_code": "CN",
        "country": "China",
        "publication_date": 20210101,
        "application_date": 20200101,
        "granted_number": "CN1B",
        "grant_date": "2022-01-01",
        "status": "Granted",
        "anticipated_expiration": 20400101,
        "titles": '[{"lang":"zh","text":"原文标题"}]',
        "title_en": "English title",
        "title_zh": "中文标题",
        "abstract_zh": "中文摘要",
        "language": '["zh"]',
        "main_ipcr": "G06F",
        "further_ipcr": '["G06N"]',
        "main_cpc": "G06F",
        "further_cpc": '["G06N"]',
        "keywords": '[{"zhName":"知识图谱","enName":"knowledge graph"}, " AI ", "ai"]',
        "citation_nums": 2,
        "cited_by_nums": 3,
        "patent_value": 100,
        "simple_family_number": "F1",
        "db_source": "ods_patent",
        "create_time": datetime(2026, 7, 21, 10, 0),
        "update_time": datetime(2026, 7, 22, 10, 0),
    }


def test_patent_preserves_raw_identifiers_and_only_maps_source_properties():
    vid, values = patent_payload(patent_row())
    mapped = dict(zip(PATENT_PROPERTIES, values, strict=True))
    assert len(PATENT_PROPERTIES) == 29
    assert vid == "patent_CN1A"
    assert mapped["publication_date"] == "20210101"
    assert mapped["anticipated_expiration"] == "20400101"
    assert mapped["db_source"] == '"ods_patent"'
    assert mapped["title_original"] == '"原文标题"'
    assert mapped["publication_number"] == '"CN-1-A"'
    assert mapped["application_number"] == '"CN-APP-1"'
    assert not any(name.endswith("_match_key") for name in PATENT_PROPERTIES)
    assert "INSERT VERTEX Patent" in patent_statement([(vid, values)])


def test_keyword_vertices_are_normalized_deduplicated_and_linked():
    row = patent_row()
    assert keyword_values(row["keywords"]) == ["知识图谱", "AI"]
    vertex_ngql, edge_ngql = keyword_statements([row])
    assert vertex_ngql.count("keyword_") == 2
    assert "INSERT VERTEX Keyword(keyword)" in vertex_ngql
    assert "INSERT EDGE HAS_KEYWORD(confidence,source_table,source_record_id)" in edge_ngql
    assert edge_ngql.count("patent_CN1A") == 2


def test_family_vertex_and_edge_use_source_family_number():
    vertex_ngql, edge_ngql = family_statements([patent_row()])
    assert 'patent_family_F1' in vertex_ngql
    assert '"patent_CN1A"->"patent_family_F1"' in edge_ngql
    assert 'confidence,match_method,match_evidence,source_table,source_record_id' in edge_ngql


def test_ddl_matches_loader_schema():
    ddl_path = Path(__file__).parents[2] / "schemas" / "ddl" / "patent_ddl.ngql"
    ddl = ddl_path.read_text(encoding="utf-8")
    patent_block = re.search(r"CREATE TAG IF NOT EXISTS Patent \((.*?)\);", ddl, re.S)
    assert patent_block is not None
    ddl_properties = tuple(
        line.strip().split()[0].rstrip(",")
        for line in patent_block.group(1).splitlines()
        if line.strip()
    )
    assert ddl_properties == PATENT_PROPERTIES
    assert "CREATE TAG IF NOT EXISTS Keyword" in ddl
    assert "CREATE TAG IF NOT EXISTS PatentFamily" in ddl
    assert "CREATE EDGE IF NOT EXISTS HAS_KEYWORD" in ddl
    assert "CREATE EDGE IF NOT EXISTS MEMBER_OF_FAMILY" in ddl


def test_entity_sql_is_external_and_complete():
    assert SQL_FILE.name == "patent_entity_extract.sql"
    assert SELECT_SQL == SQL_FILE.read_text(encoding="utf-8")
    assert "FROM dwd_patent p" in SELECT_SQL
    assert SELECT_SQL.count("LEFT JOIN dwd_patent_") == 5
    assert "LIMIT %s OFFSET %s" in SELECT_SQL
