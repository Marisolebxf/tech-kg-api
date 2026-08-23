from script.load_scholar_entities import render_person_insert


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
