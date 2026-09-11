from script.load_scholar_entities import _build_person_props, load_persons, render_person_insert


def test_render_writes_only_fields_present_in_tag_and_props():
    # tag 只声明了 name_zh/name_en;props 里多出的 extra 不写
    field_types = {"name_zh": "string", "name_en": "string"}
    props = {"name_zh": "郭佳佳", "name_en": "Guo", "extra": "should_drop"}
    stmt = render_person_insert("person_855924f1", props, field_types)
    assert stmt.startswith("INSERT VERTEX Person(name_zh,name_en) VALUES ")
    assert '"person_855924f1"' in stmt
    assert "郭佳佳" in stmt
    assert "should_drop" not in stmt


def test_render_numeric_fields_unquoted():
    field_types = {"paper_nums": "int64", "h_index": "int64", "name_zh": "string"}
    props = {"paper_nums": 5, "h_index": 3, "name_zh": "郭"}
    stmt = render_person_insert("person_x", props, field_types)
    # 数字不加引号
    assert '(5,3,"郭")' in stmt or '(5, 3, "郭")' in stmt.replace(" ", "")
    assert '"5"' not in stmt  # paper_nums 不该被引号包住


def test_render_none_values_become_null():
    field_types = {"name_zh": "string", "avatar": "string"}
    props = {"name_zh": "郭", "avatar": None}
    stmt = render_person_insert("person_x", props, field_types)
    assert "NULL" in stmt  # None → NULL


def test_render_escapes_quotes():
    field_types = {"name_zh": "string"}
    props = {"name_zh": 'a"b'}
    stmt = render_person_insert("person_x", props, field_types)
    assert '\\"' in stmt


def test_render_drops_fields_not_in_tag():
    # tag 没有 paper_nums → 即使 props 有也不写
    field_types = {"name_zh": "string"}
    props = {"name_zh": "郭", "paper_nums": 5}
    stmt = render_person_insert("person_x", props, field_types)
    assert "paper_nums" not in stmt
    assert "INSERT VERTEX Person(name_zh) VALUES " in stmt


def test_person_props_repair_mojibake_names():
    garbled = "张颖".encode().decode("latin1")
    props = _build_person_props(
        {
            "scholar_id": "abc",
            "name_zh": garbled,
            "scholar_org_name_zh": "清华大学",
        },
        "",
        "",
        "2026-09-10 00:00:00",
    )
    assert props["name_zh"] == "张颖"
    assert props["scholar_org"] == "清华大学"


def test_load_persons_skips_kgtest_and_demo_rows(monkeypatch):
    from unittest.mock import MagicMock

    rows = [
        {"scholar_id": "kgtest_1", "name_zh": "张三", "update_time": "2026-01-01 00:00:00"},
        {
            "scholar_id": "c9915341",
            "name_zh": "向德辉",
            "scholar_org_name_zh": "濠江測試數碼有限公司033",
            "update_time": "2026-01-02 00:00:00",
        },
        {
            "scholar_id": "real1",
            "name_zh": "郭佳佳",
            "scholar_org_name_zh": "新智认知数字科技股份有限公司",
            "update_time": "2026-01-03 00:00:00",
        },
    ]
    monkeypatch.setattr(
        "script.load_scholar_entities._iter_scholars",
        lambda *args, **kwargs: rows,
    )
    monkeypatch.setattr("script.load_scholar_entities._fetch_talent_flags", lambda _s: {})
    monkeypatch.setattr("script.load_scholar_entities._fetch_research_directions", lambda _s: {})
    monkeypatch.setattr(
        "script.load_scholar_entities.describe_tag_field_types",
        lambda _g, _t: {"name_zh": "string"},
    )
    graph = MagicMock()
    stats = load_persons(None, graph, dry_run=False)
    assert stats["written"] == 1
    assert stats["skipped_virtual"] == 2
    assert graph.execute_write.call_count == 1
