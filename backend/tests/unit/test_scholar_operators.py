"""学者领域算子包装器的单元测试。

只验证 operator(data, ctx) 契约：ctx 参数被正确解析、脚本 run() 的返回值被
封装为 list[dict]、异常被兜住并返回 error 结构。不触发真实 MySQL/Graph/Milvus。
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

_OP_DIR = Path(__file__).resolve().parents[2] / "operators" / "scholar"


def _load_operator(module_stem: str) -> Callable[[list[dict], dict], list[dict]]:
    """把 operators/scholar/xxx.py 当模块加载，返回其 operator 函数。"""
    source_path = _OP_DIR / f"{module_stem}.py"
    module_name = f"scholar_operator_{module_stem.replace('.', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, source_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module.operator  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("op_stem", "script_module", "expected_params"),
    [
        (
            "user.scholar.load_entities",
            "script.load_scholar_entities",
            {"database": "gkx_element", "dry_run": True},
        ),
        (
            "user.scholar.load_relations",
            "script.load_scholar_relations",
            {
                "database": "gkx_element",
                "dry_run": True,
                "include_authored_by_fallback": False,
            },
        ),
        (
            "user.scholar.build_milvus_index",
            "script.build_scholar_milvus_index",
            {"dry_run": True, "drop_existing": False, "preview": 5},
        ),
        (
            "user.scholar.align_affiliations",
            "script.align_scholar_affiliations",
            {"dry_run": True, "top_k": 5, "min_score": 0.65, "preview": 5},
        ),
    ],
)
def test_operator_success_wraps_run_return(
    monkeypatch: pytest.MonkeyPatch,
    op_stem: str,
    script_module: str,
    expected_params: dict[str, Any],
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"total": 42, "kwargs": kwargs}

    monkeypatch.setitem(sys.modules, script_module, type(sys)("stub"))
    sys.modules[script_module].run = fake_run  # type: ignore[attr-defined]

    operator = _load_operator(op_stem)
    result = operator([], {})

    assert isinstance(result, list)
    assert len(result) == 1
    entry = result[0]
    assert entry["operator"] == op_stem
    assert entry["status"] == "ok"
    assert entry["stats"] == {"total": 42, "kwargs": expected_params}
    assert entry["params"] == expected_params
    # ctx 默认值应传给底层 run
    assert captured == expected_params


def test_dedupe_operator_success_wraps_run_return(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"pairs": 3}

    monkeypatch.setitem(sys.modules, "script.dedupe_scholar_persons", type(sys)("stub"))
    sys.modules["script.dedupe_scholar_persons"].run = fake_run  # type: ignore[attr-defined]

    operator = _load_operator("user.scholar.dedupe_persons")
    result = operator([], {"write": True, "high_threshold": 0.8})

    assert result[0]["status"] == "ok"
    assert result[0]["stats"] == {"pairs": 3}
    assert captured["dry_run"] is True
    assert captured["write"] is True
    assert captured["high_threshold"] == 0.8
    # 未传的 ctx 字段使用默认值
    assert captured["top_k"] == 5
    assert captured["mid_threshold"] == 0.55
    assert captured["preview"] == 8
    assert captured["report_path"] is None


def test_operator_wraps_exception_as_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(**_: Any) -> dict[str, Any]:
        raise RuntimeError("mysql down")

    monkeypatch.setitem(sys.modules, "script.load_scholar_entities", type(sys)("stub"))
    sys.modules["script.load_scholar_entities"].run = boom  # type: ignore[attr-defined]

    operator = _load_operator("user.scholar.load_entities")
    result = operator([], {"database": "test_db"})

    assert result[0]["status"] == "error"
    assert result[0]["error"] == "mysql down"
    assert result[0]["error_type"] == "RuntimeError"
    assert result[0]["params"]["database"] == "test_db"


def test_operator_result_is_json_serializable() -> None:
    """算子返回值必须可 JSON 序列化——注册表在 invoke 后会强制校验。"""
    import json

    for stem in (
        "user.scholar.load_entities",
        "user.scholar.load_relations",
        "user.scholar.build_milvus_index",
        "user.scholar.align_affiliations",
        "user.scholar.dedupe_persons",
    ):
        operator = _load_operator(stem)
        # 强制走异常路径：script 模块不存在 → ImportError 被捕获成 error dict
        # 通过删除模块缓存里的假 stub 保证异常
        for module_key in list(sys.modules):
            if module_key.startswith("script."):
                sys.modules.pop(module_key, None)
        # 让 import 真的失败：monkeypatch sys.path 无法覆盖，改为 mock 一个抛异常的 stub
        stub = type(sys)("stub")

        def _raise(**_: Any) -> None:
            raise ImportError("simulated missing")

        stub.run = _raise  # type: ignore[attr-defined]
        module_name = {
            "user.scholar.load_entities": "script.load_scholar_entities",
            "user.scholar.load_relations": "script.load_scholar_relations",
            "user.scholar.build_milvus_index": "script.build_scholar_milvus_index",
            "user.scholar.align_affiliations": "script.align_scholar_affiliations",
            "user.scholar.dedupe_persons": "script.dedupe_scholar_persons",
        }[stem]
        sys.modules[module_name] = stub

        result = operator([], {})
        # 契约：list[dict] 且完整 JSON 可序列化
        assert isinstance(result, list)
        assert all(isinstance(item, dict) for item in result)
        json.dumps(result, ensure_ascii=False)
