from script.load_scholar_entities import _scholar_sql


def test_full_no_since_paginated():
    sql = _scholar_sql("NULL AS scholar_org_id", None, None, None)
    assert "WHERE status = 1" in sql
    assert "update_time >" not in sql
    assert "scholar_id = :sid" not in sql
    assert "LIMIT :limit OFFSET :offset" in sql  # 分页


def test_incremental_adds_since():
    sql = _scholar_sql("scholar_org_id", "2026-01-01 00:00:00", None, None)
    assert "AND update_time > :since" in sql
    assert "LIMIT :limit OFFSET :offset" in sql


def test_scholar_id_filter():
    sql = _scholar_sql("NULL AS scholar_org_id", None, "855924f1", None)
    assert "AND scholar_id = :sid" in sql


def test_incremental_plus_scholar_id():
    sql = _scholar_sql("NULL AS scholar_org_id", "2026-01-01 00:00:00", "855924f1", None)
    assert "AND update_time > :since" in sql
    assert "AND scholar_id = :sid" in sql


def test_limit_cap_no_offset():
    sql = _scholar_sql("NULL AS scholar_org_id", None, None, 100)
    assert "LIMIT :cap" in sql
    assert "OFFSET" not in sql
