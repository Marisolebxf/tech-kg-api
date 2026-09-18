"""步声明解析单测：@step 装饰器（唯一合法形态）的接受/拒绝矩阵、上传入口校验、步间透传大小防护。"""

from __future__ import annotations

import pytest

from service.schema_management import SchemaManagementService, SchemaScriptError
from service.script_steps import MAX_STEPS, extract_declared_steps
from service.temporal_workflows import (
    _MAX_PREV_OUTPUT_BYTES,
    _MAX_STEP_CHAIN_BYTES,
    _shrink_chain_value,
    _truncate_step_extras,
)

VALID_DECORATED_SCRIPT = """
from kg_sdk import step

@step
def normalize(payload):
    return {"cleaned": []}

def _helper(x):
    return x

@step("emit-rows")
def do_emit(payload):
    return {"edges": []}
"""


# ---------------------------------------------------------------------------
# extract_declared_steps 接受 / 拒绝矩阵
# ---------------------------------------------------------------------------


class TestExtractDeclaredSteps:
    def test_valid_decorators_in_source_order(self):
        """顺序 = 源码出现顺序；未标注的辅助函数不进清单。"""
        assert extract_declared_steps(VALID_DECORATED_SCRIPT) == [
            {"id": "normalize", "fn": "normalize"},
            {"id": "emit-rows", "fn": "do_emit"},
        ]

    def test_bare_decorator_id_defaults_to_function_name(self):
        source = "from kg_sdk import step\n\n@step\ndef clean(payload):\n    return {}\n"
        assert extract_declared_steps(source) == [{"id": "clean", "fn": "clean"}]

    def test_keyword_id_accepted(self):
        source = (
            'from kg_sdk import step\n\n@step(id="emit")\ndef do_emit(payload):\n    return {}\n'
        )
        assert extract_declared_steps(source) == [{"id": "emit", "fn": "do_emit"}]

    def test_empty_call_defaults_to_function_name(self):
        source = "from kg_sdk import step\n\n@step()\ndef clean(payload):\n    return {}\n"
        assert extract_declared_steps(source) == [{"id": "clean", "fn": "clean"}]

    def test_dotted_kg_sdk_step_accepted(self):
        """import kg_sdk 后的 @kg_sdk.step 点式写法同样识别（裸与带参都认）。"""
        source = (
            "import kg_sdk\n"
            "\n"
            "@kg_sdk.step\n"
            "def clean(payload):\n"
            "    return {}\n"
            "\n"
            '@kg_sdk.step("emit")\n'
            "def do_emit(payload):\n"
            "    return {}\n"
        )
        assert extract_declared_steps(source) == [
            {"id": "clean", "fn": "clean"},
            {"id": "emit", "fn": "do_emit"},
        ]

    def test_async_function_accepted(self):
        source = "from kg_sdk import step\n\n@step\nasync def clean(payload):\n    return {}\n"
        assert extract_declared_steps(source) == [{"id": "clean", "fn": "clean"}]

    def test_rejects_legacy_transform_entry(self):
        source = "def transform(payload):\n    return {}\n"
        with pytest.raises(ValueError, match="已下线"):
            extract_declared_steps(source)

    def test_rejects_legacy_workflow_entry(self):
        source = "def workflow(payload):\n    return {}\n"
        with pytest.raises(ValueError, match="已下线"):
            extract_declared_steps(source)

    def test_rejects_steps_literal(self):
        source = 'STEPS = [{"id": "a", "fn": "fa"}]\n\ndef fa(payload):\n    return {}\n'
        with pytest.raises(ValueError, match="STEPS 清单声明已下线"):
            extract_declared_steps(source)

    def test_rejects_transform_and_decorators_coexistence(self):
        source = VALID_DECORATED_SCRIPT + "\n\ndef transform(p):\n    return {}\n"
        with pytest.raises(ValueError, match="不能同时声明"):
            extract_declared_steps(source)

    def test_rejects_no_step_declaration(self):
        with pytest.raises(ValueError, match="缺少抽取步声明"):
            extract_declared_steps("x = 1\n")

    def test_rejects_non_constant_decorator_arg(self):
        source = "from kg_sdk import step\n\n@step(name)\ndef clean(payload):\n    return {}\n"
        with pytest.raises(ValueError, match="只接受一个可选的 step id 字符串常量"):
            extract_declared_steps(source)

    def test_rejects_non_string_decorator_arg(self):
        source = "from kg_sdk import step\n\n@step(1)\ndef clean(payload):\n    return {}\n"
        with pytest.raises(ValueError, match="只接受一个可选的 step id 字符串常量"):
            extract_declared_steps(source)

    def test_rejects_bad_id_charset(self):
        source = 'from kg_sdk import step\n\n@step("a:b")\ndef clean(payload):\n    return {}\n'
        with pytest.raises(ValueError, match="id 非法"):
            extract_declared_steps(source)

    def test_rejects_blank_explicit_id(self):
        source = 'from kg_sdk import step\n\n@step("  ")\ndef clean(payload):\n    return {}\n'
        with pytest.raises(ValueError, match="不能为空白字符串"):
            extract_declared_steps(source)

    def test_rejects_non_ascii_function_name_default_id(self):
        """中文函数名不匹配 id 字符集：报错并提示显式传 ASCII id。"""
        source = "from kg_sdk import step\n\n@step\ndef 清洗(payload):\n    return {}\n"
        with pytest.raises(ValueError, match="显式指定"):
            extract_declared_steps(source)

    def test_rejects_duplicate_ids(self):
        source = (
            "from kg_sdk import step\n"
            "\n"
            "@step\n"
            "def clean(payload):\n"
            "    return {}\n"
            "\n"
            '@step("clean")\n'
            "def other(payload):\n"
            "    return {}\n"
        )
        with pytest.raises(ValueError, match="id 重复"):
            extract_declared_steps(source)

    def test_rejects_double_decoration(self):
        source = "from kg_sdk import step\n\n@step\n@step\ndef clean(payload):\n    return {}\n"
        with pytest.raises(ValueError, match="重复标注"):
            extract_declared_steps(source)

    def test_rejects_decorator_on_class(self):
        source = "from kg_sdk import step\n\n@step\nclass Cleaner:\n    pass\n"
        with pytest.raises(ValueError, match="只能标注在函数上"):
            extract_declared_steps(source)

    def test_rejects_too_many_steps(self):
        functions = "\n\n".join(
            f"@step\ndef f{i}(payload):\n    return {{}}" for i in range(MAX_STEPS + 1)
        )
        source = f"from kg_sdk import step\n\n{functions}\n"
        with pytest.raises(ValueError, match=f"最长 {MAX_STEPS} 步"):
            extract_declared_steps(source)

    def test_syntax_error_wrapped(self):
        with pytest.raises(ValueError, match="语法错误"):
            extract_declared_steps("def broken(:\n")


# ---------------------------------------------------------------------------
# _validate_script（上传入口）
# ---------------------------------------------------------------------------


class TestValidateScriptEntry:
    def test_decorated_script_stores_first_fn(self):
        # workflow_function_name 存第一步 fn（展示参考；执行时 plan 重新 ast 解析）
        assert (
            SchemaManagementService._validate_script("a.py", VALID_DECORATED_SCRIPT.encode())
            == "normalize"
        )

    def test_transform_script_rejected(self):
        with pytest.raises(SchemaScriptError, match="已下线"):
            SchemaManagementService._validate_script("a.py", b"def transform(p):\n    return {}\n")

    def test_workflow_script_rejected(self):
        with pytest.raises(SchemaScriptError, match="已下线"):
            SchemaManagementService._validate_script("a.py", b"def workflow(p):\n    return {}\n")

    def test_steps_script_rejected(self):
        source = 'STEPS = [{"id": "a", "fn": "fa"}]\n\ndef fa(p):\n    return {}\n'
        with pytest.raises(SchemaScriptError, match="STEPS 清单声明已下线"):
            SchemaManagementService._validate_script("a.py", source.encode())

    def test_no_entry_rejected(self):
        with pytest.raises(SchemaScriptError, match="缺少抽取步声明"):
            SchemaManagementService._validate_script("a.py", b"x = 1\n")

    def test_invalid_decorator_rejected_with_reason(self):
        source = "from kg_sdk import step\n\n@step(1)\ndef clean(p):\n    return {}\n"
        with pytest.raises(SchemaScriptError, match="只接受一个可选的 step id 字符串常量"):
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
