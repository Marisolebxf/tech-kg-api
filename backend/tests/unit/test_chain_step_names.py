"""chain 任务详情步骤补名：``schema:<id>`` 环渲染为「{Schema 中文名} 平台喂数抽取」。

背景：环 RUNNING/FAILED 阶段 workflow 的 chain_steps 不带 name，前端按
name||id 渲染会露出裸 ``schema:<uuid>``。读取侧统一装饰（实时 get_steps 的
dict 形状 + 落库 pipeline_steps 的 list 形状），查不到/异常保持原样。
"""

from __future__ import annotations

import pytest

from service import schema_extraction
from service.workflow_operations import _decorate_chain_step_names


def _patch_names(monkeypatch: pytest.MonkeyPatch, mapping: dict[str, str]) -> None:
    monkeypatch.setattr(schema_extraction, "schema_display_name_map", lambda ids: mapping)


def test_dict_shape_running_ring_gets_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """实时 get_steps 形状：id 在键上，RUNNING 环补名。"""
    _patch_names(monkeypatch, {"sch-1": "审测挂件"})
    steps = {
        "schema:sch-1": {"status": "RUNNING", "schemaId": "sch-1", "position": 1},
    }
    _decorate_chain_step_names(steps)
    assert steps["schema:sch-1"]["name"] == "审测挂件 平台喂数抽取"


def test_list_shape_persisted_steps_unified(monkeypatch: pytest.MonkeyPatch) -> None:
    """落库 pipeline_steps 形状：id 在条目上，已完成环的裸 label 统一成完整口径。"""
    _patch_names(monkeypatch, {"sch-1": "论文", "sch-2": "学者"})
    steps = [
        {"id": "schema:sch-1", "status": "COMPLETED", "name": "论文", "position": 1},
        {"id": "schema:sch-2", "status": "FAILED", "position": 2},
    ]
    _decorate_chain_step_names(steps)
    assert steps[0]["name"] == "论文 平台喂数抽取"
    assert steps[1]["name"] == "学者 平台喂数抽取"


def test_unresolved_id_kept_as_is(monkeypatch: pytest.MonkeyPatch) -> None:
    """查不到的 schema id 不动（已删除/测试库不存在），普通脚本步不碰。"""
    _patch_names(monkeypatch, {})
    steps = {
        "schema:missing": {"status": "RUNNING"},
        "normalize": {"status": "COMPLETED", "name": "标准化"},
    }
    _decorate_chain_step_names(steps)
    assert "name" not in steps["schema:missing"]
    assert steps["normalize"]["name"] == "标准化"


def test_lookup_failure_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """展示名解析抛异常时吞掉，不拖垮任务详情。"""

    def _boom(ids: list[str]) -> dict[str, str]:
        raise RuntimeError("db down")

    monkeypatch.setattr(schema_extraction, "schema_display_name_map", _boom)
    steps = {"schema:sch-1": {"status": "RUNNING"}}
    _decorate_chain_step_names(steps)
    assert "name" not in steps["schema:sch-1"]


def test_non_step_payloads_ignored() -> None:
    """空/异形载荷直接返回，不抛错。"""
    _decorate_chain_step_names(None)
    _decorate_chain_step_names({})
    _decorate_chain_step_names("not-steps")
