"""脚本 needsRun（已更新待重跑 / 从未运行）序列化判定单测。

与 staleness（captured_revision 版本号比较）是两个独立维度：
stale 提示"更新脚本"，needsRun 在更新后接力提示"重跑"，直到抽取收尾回写
last_run_at 晚于 uploaded_at 才消除。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from db_model.schema_management import GraphSchemaDefinition, GraphSchemaScript
from service.schema_management import SchemaManagementService

NOW = datetime(2026, 9, 17, 12, 0, 0)


def _definition(revision: int = 1) -> GraphSchemaDefinition:
    return GraphSchemaDefinition(id="schema-1", property_revision=revision)


def _script(
    *, uploaded_at: datetime, last_run_at: datetime | None, captured_revision: int = 1
) -> GraphSchemaScript:
    return GraphSchemaScript(
        schema_id="schema-1",
        bucket="b",
        object_key="k",
        original_filename="w.py",
        content_type="text/x-python",
        size_bytes=1,
        sha256="x" * 64,
        uploaded_by="u",
        captured_revision=captured_revision,
        uploaded_at=uploaded_at,
        last_run_at=last_run_at,
    )


def _serialize(script: GraphSchemaScript | None, definition: GraphSchemaDefinition):
    return SchemaManagementService._serialize_script(script, definition)


def test_needs_run_true_when_never_ran():
    result = _serialize(_script(uploaded_at=NOW, last_run_at=None), _definition())
    assert result is not None
    assert result["needsRun"] is True
    assert result["lastRunAt"] is None


def test_needs_run_true_when_uploaded_after_last_run():
    script = _script(uploaded_at=NOW, last_run_at=NOW - timedelta(hours=1))
    result = _serialize(script, _definition())
    assert result is not None
    assert result["needsRun"] is True
    assert result["lastRunAt"] is not None


def test_needs_run_false_when_ran_after_upload():
    script = _script(uploaded_at=NOW - timedelta(hours=1), last_run_at=NOW)
    result = _serialize(script, _definition())
    assert result is not None
    assert result["needsRun"] is False


def test_stale_and_needs_run_are_independent():
    # 脚本已更新到最新版本（不 stale）但尚未重跑：只有 needsRun 亮
    script = _script(uploaded_at=NOW, last_run_at=NOW - timedelta(hours=1), captured_revision=3)
    result = _serialize(script, _definition(revision=3))
    assert result is not None
    assert result["stale"] is False
    assert result["needsRun"] is True

    # 脚本落后（stale）且旧脚本跑过：只有 stale 亮，待重跑在更新后再接管
    script = _script(uploaded_at=NOW - timedelta(hours=2), last_run_at=NOW - timedelta(hours=1))
    result = _serialize(script, _definition(revision=3))
    assert result is not None
    assert result["stale"] is True
    assert result["needsRun"] is False


def test_no_script_returns_none():
    assert _serialize(None, _definition()) is None
