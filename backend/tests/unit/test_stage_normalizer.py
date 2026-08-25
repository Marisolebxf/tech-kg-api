"""stage_normalizer 单元测试:dict-stages bug 修复的核心覆盖。"""

from __future__ import annotations

from service.stage_normalizer import normalize_stages


def test_none_output_returns_empty() -> None:
    assert normalize_stages(None) == []


def test_non_dict_output_returns_empty() -> None:
    assert normalize_stages("not a dict") == []  # type: ignore[arg-type]
    assert normalize_stages(["list", "not", "dict"]) == []  # type: ignore[arg-type]


def test_output_without_stages_key_returns_empty() -> None:
    assert normalize_stages({"status": "ok", "result": "done"}) == []


def test_dict_stages_with_known_keys_uses_catalog() -> None:
    """project_ingest_workflow 真实形状:schema/load/align/cleanup 都在 catalog 里。"""
    output = {
        "stages": {
            "schema": {"status": "ok"},
            "load": {"status": "ok", "count": "128 条"},
            "align": {"status": "skipped"},
            "cleanup": {"status": "ok"},
        }
    }
    steps = normalize_stages(output)
    assert len(steps) == 4
    by_id = {s["id"]: s for s in steps}
    # catalog 元数据生效
    assert by_id["schema"]["name"] == "Schema 映射"
    assert by_id["schema"]["phase"] == "图谱构建"
    assert by_id["schema"]["description"] == "映射实体、关系与属性 Schema"
    # worker 提供的字段透传
    assert by_id["load"]["count"] == "128 条"
    assert by_id["load"]["status"] == "ok"
    # worker 没提供的字段填 "-",不编造
    assert by_id["schema"]["count"] == "-"
    assert by_id["schema"]["abnormal"] == "-"
    assert by_id["schema"]["duration"] == "-"


def test_dict_stages_missing_fields_use_dash() -> None:
    steps = normalize_stages({"stages": {"schema": {}}})
    assert len(steps) == 1
    step = steps[0]
    assert step["id"] == "schema"
    assert step["status"] == "-"
    assert step["count"] == "-"
    assert step["abnormal"] == "-"
    assert step["duration"] == "-"


def test_dict_stages_unknown_key_preserves_raw_key() -> None:
    """worker 引入新 stage key 时归一化器不崩,用 raw key 作为 id/name。"""
    steps = normalize_stages({"stages": {"custom_stage": {"status": "ok"}}})
    assert len(steps) == 1
    step = steps[0]
    assert step["id"] == "custom_stage"
    assert step["name"] == "custom_stage"
    assert step["phase"] == "图谱构建"
    assert step["description"] == ""
    assert step["status"] == "ok"


def test_dict_stages_skips_non_dict_values() -> None:
    """stages 是 dict 但某些 value 不是 dict(如 worker 写错)时跳过。"""
    steps = normalize_stages(
        {"stages": {"schema": {"status": "ok"}, "bad": "string value", "skip": 42}}
    )
    assert len(steps) == 1
    assert steps[0]["id"] == "schema"


def test_empty_dict_stages_returns_empty() -> None:
    assert normalize_stages({"stages": {}}) == []


def test_list_stages_passes_through() -> None:
    """旧 list 形式(历史兼容):透传已经是 ProcessStep 形状的 dict。"""
    legacy_steps = [
        {"id": "source", "name": "数据接入", "status": "成功", "count": "10 条"},
        {"id": "schema", "name": "Schema 映射", "status": "成功"},
    ]
    steps = normalize_stages({"stages": legacy_steps})
    assert steps == legacy_steps


def test_list_stages_filters_non_dict_items() -> None:
    steps = normalize_stages({"stages": [{"id": "ok"}, "garbage", 42]})
    assert steps == [{"id": "ok"}]


def test_stages_wrong_type_returns_empty() -> None:
    """stages 既不是 list 也不是 dict(如 worker 写成字符串)时返回空。"""
    assert normalize_stages({"stages": "schema,load,align"}) == []
    assert normalize_stages({"stages": 42}) == []
