"""STEPS 多步声明解析单测：接受/拒绝矩阵、上传入口校验、步间透传大小防护。"""

from __future__ import annotations

import ast

import pytest

from service.script_steps import MAX_STEPS, extract_step_list
from service.schema_management import SchemaManagementService, SchemaScriptError
from service.temporal_workflows import (
    _MAX_PREV_OUTPUT_BYTES,
    _MAX_STEP_CHAIN_BYTES,
    _shrink_chain_value,
    _truncate_step_extras,
)

VALID_STEPS_SCRIPT = """
STEPS = [
    {"id": "normalize", "fn": "step_normalize"},
    {"id": "emit", "fn": "step_emit"},
]

def step_normalize(payload):
    return {"cleaned": []}

def step_emit(payload):
    return {"edges": []}
"""


# ---------------------------------------------------------------------------
# extract_step_list 接受 / 拒绝矩阵
# ---------------------------------------------------------------------------


class TestExtractStepList:
    def test_valid_steps(self):
        steps = extract_step_list(VALID_STEPS_SCRIPT)
        assert steps == [
            {"id": "normalize", "fn": "step_normalize"},
            {"id": "emit", "fn": "step_emit"},
        ]

    def test_no_declaration_returns_none(self):
        assert extract_step_list("def transform(payload):\n    return {}\n") is None

    def test_ann_assign_accepted(self):
        source = 'STEPS: list = [{"id": "a", "fn": "fa"}]\n\ndef fa(payload):\n    return {}\n'
        assert extract_step_list(source) == [{"id": "a", "fn": "fa"}]

    def test_last_assignment_wins(self):
        source = (
            'STEPS = [{"id": "a", "fn": "fa"}]\n'
            'STEPS = [{"id": "b", "fn": "fb"}]\n'
            "def fa(payload):\n    return {}\n\n"
            "def fb(payload):\n    return {}\n"
        )
        assert extract_step_list(source) == [{"id": "b", "fn": "fb"}]

    def test_workflow_entry_coexists_with_steps(self):
        """旧 workflow 入口与 STEPS 共存不报错（STEPS 优先生效）。"""
        source = VALID_STEPS_SCRIPT + "\n\ndef workflow(payload):\n    return {}\n"
        assert extract_step_list(source) is not None

    def test_rejects_transform_and_steps_coexistence(self):
        source = VALID_STEPS_SCRIPT + "\n\ndef transform(payload):\n    return {}\n"
        with pytest.raises(ValueError, match="不能同时声明"):
            extract_step_list(source)

    def test_rejects_empty_list(self):
        with pytest.raises(ValueError, match="不能为空"):
            extract_step_list("STEPS = []\n\ndef fa(payload):\n    return {}\n")

    def test_rejects_non_list_literal(self):
        with pytest.raises(ValueError, match="list 字面量"):
            extract_step_list(
                'STEPS = make_steps()\n\ndef make_steps():\n    return []\n'
            )

    def test_rejects_non_dict_item(self):
        with pytest.raises(ValueError, match="第 1 项必须是 dict"):
            extract_step_list('STEPS = ["a"]\n\ndef fa(payload):\n    return {}\n')

    def test_rejects_non_literal_item(self):
        with pytest.raises(ValueError, match="dict 字面量"):
            extract_step_list(
                'STEPS = [make_item()]\n\ndef make_item():\n    return {}\n'
            )

    def test_rejects_missing_id(self):
        source = 'STEPS = [{"fn": "fa"}]\n\ndef fa(payload):\n    return {}\n'
        with pytest.raises(ValueError, match="缺少非空字符串 id"):
            extract_step_list(source)

    def test_rejects_bad_id_charset(self):
        source = 'STEPS = [{"id": "a:b", "fn": "fa"}]\n\ndef fa(payload):\n    return {}\n'
        with pytest.raises(ValueError, match="id 非法"):
            extract_step_list(source)

    def test_rejects_blank_id(self):
        source = 'STEPS = [{"id": "  ", "fn": "fa"}]\n\ndef fa(payload):\n    return {}\n'
        with pytest.raises(ValueError, match="缺少非空字符串 id"):
            extract_step_list(source)

    def test_rejects_duplicate_id(self):
        source = (
            'STEPS = [{"id": "a", "fn": "fa"}, {"id": "a", "fn": "fb"}]\n'
            "def fa(payload):\n    return {}\n\n"
            "def fb(payload):\n    return {}\n"
        )
        with pytest.raises(ValueError, match="id 重复"):
            extract_step_list(source)

    def test_rejects_missing_fn(self):
        source = 'STEPS = [{"id": "a"}]\n\ndef fa(payload):\n    return {}\n'
        with pytest.raises(ValueError, match="缺少非空字符串 fn"):
            extract_step_list(source)

    def test_rejects_unknown_fn(self):
        source = 'STEPS = [{"id": "a", "fn": "missing"}]\n\ndef fa(payload):\n    return {}\n'
        with pytest.raises(ValueError, match="未在脚本顶层定义"):
            extract_step_list(source)

    def test_rejects_too_many_steps(self):
        entries = ", ".join(
            f'{{"id": "s{i}", "fn": "f{i}"}}' for i in range(MAX_STEPS + 1)
        )
        functions = "\n".join(f"def f{i}(payload):\n    return {{}}" for i in range(MAX_STEPS + 1))
        source = f"STEPS = [{entries}]\n\n{functions}\n"
        with pytest.raises(ValueError, match=f"最长 {MAX_STEPS} 步"):
            extract_step_list(source)

    def test_syntax_error_wrapped(self):
        with pytest.raises(ValueError, match="语法错误"):
            extract_step_list("def broken(:\n")


# ---------------------------------------------------------------------------
# _validate_script（上传入口）
# ---------------------------------------------------------------------------


class TestValidateScriptEntry:
    def test_transform_script_unchanged(self):
        assert SchemaManagementService._validate_script("a.py", b"def transform(p):\n    return {}\n") == "transform"

    def test_workflow_script_unchanged(self):
        assert SchemaManagementService._validate_script("a.py", b"def workflow(p):\n    return {}\n") == "workflow"

    def test_no_entry_returns_none(self):
        assert SchemaManagementService._validate_script("a.py", b"x = 1\n") is None

    def test_steps_script_stores_first_fn(self):
        # workflow_function_name 存第一步 fn（展示参考；执行时 plan 重新 ast 解析）
        assert (
            SchemaManagementService._validate_script("a.py", VALID_STEPS_SCRIPT.encode())
            == "step_normalize"
        )

    def test_steps_with_transform_rejected(self):
        source = VALID_STEPS_SCRIPT + "\n\ndef transform(p):\n    return {}\n"
        with pytest.raises(SchemaScriptError, match="不能同时声明"):
            SchemaManagementService._validate_script("a.py", source.encode())

    def test_invalid_steps_rejected_with_reason(self):
        source = 'STEPS = [{"id": "a", "fn": "nope"}]\n\ndef fa(p):\n    return {}\n'
        with pytest.raises(SchemaScriptError, match="未在脚本顶层定义"):
            SchemaManagementService._validate_script("a.py", source.encode())


# ---------------------------------------------------------------------------
# 步间透传大小防护
# ---------------------------------------------------------------------------


class TestStepChainSizeGuards:
    def test_small_value_passthrough(self):
        value = {"cleaned": ["a"]}
        assert _shrink_chain_value(value, budget=_MAX_STEP_CHAIN_BYTES, label="x") is value

    def test_oversized_value_truncated_with_stats(self):
        value = {"cleaned": ["x" * 4096] * 512, "stats": {"cleaned": 512}}
        shrunk = _shrink_chain_value(value, budget=_MAX_PREV_OUTPUT_BYTES, label="x")
        assert shrunk["_truncated"] is True
        assert shrunk["_originalBytes"] > _MAX_PREV_OUTPUT_BYTES
        assert shrunk["stats"] == {"cleaned": 512}
        assert "cleaned" not in shrunk

    def test_oversized_stats_dropped(self):
        value = {"stats": {"blob": "y" * 8192}}
        shrunk = _shrink_chain_value(value, budget=8, label="x")
        assert shrunk["_truncated"] is True
        assert "stats" not in shrunk

    def test_truncate_step_extras_keeps_contract_keys(self):
        output = {
            "entities": [{"id": "E1", "props": {}}],
            "failures": [{"recordId": "r1", "error": "e"}],
            "cleaned": ["z" * 1024] * 1024,
            "stats": {"rows": 1},
        }
        truncated = _truncate_step_extras(output)
        assert truncated["entities"] == output["entities"]
        assert truncated["failures"] == output["failures"]
        assert truncated["stats"] == {"rows": 1}
        assert truncated["_stepExtras"]["_truncated"] is True
        assert "cleaned" not in truncated

    def test_truncate_step_extras_noop_under_budget(self):
        output = {"entities": [], "cleaned": ["a"], "stats": {"n": 1}}
        assert _truncate_step_extras(output) is output

    def test_tree_from_ast_module(self):
        tree = ast.parse(VALID_STEPS_SCRIPT)
        from service.script_steps import step_list_from_tree

        assert step_list_from_tree(tree) is not None
