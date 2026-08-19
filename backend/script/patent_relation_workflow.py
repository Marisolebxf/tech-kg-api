"""专利关系抽取薄包装：把 ``load_patent_relations.load`` 封装为主分支 Python
工作流接口可调用的 ``workflow(payload)``，供“事实关系 → 专利关系 → 上传脚本”使用。

一次执行原脚本现有的全部专利关系：``INVENTED_BY``、``APPLIED_BY``、``OWNED_BY``、
``CITES``、``OUTPUT_OF``。不拆分、不过滤、不改抽取逻辑。

主分支工作流接口（``POST /workflow-system/definitions/python``）要求脚本定义
``workflow(payload)`` 函数；Temporal ``kg.custom.python`` 经 ``execute_python_script``
activity 以子进程方式执行本脚本。子进程的 ``PYTHONPATH`` 只含脚本所在目录
（``WORKFLOW_SCRIPT_DIR``，通常是 /tmp），不含 backend 根，因此本脚本需自举
``sys.path`` 才能 ``from script.load_patent_relations import load``。

本脚本只做入口适配、参数传递、结果 JSON 化；不复制/不修改关系抽取与建图逻辑。
执行失败时向上抛出异常，让 Temporal 识别 FAILED 并按平台策略重试。
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def _backend_root() -> Path:
    """定位 backend 根目录（含 ``script/load_patent_relations.py``）。"""
    env_root = os.getenv("TECH_KG_BACKEND_ROOT")
    if env_root and Path(env_root, "script", "load_patent_relations.py").is_file():
        return Path(env_root)
    here = Path(__file__).resolve()
    for parent in (here.parent, *here.parents):
        if (parent / "script" / "load_patent_relations.py").is_file():
            return parent
    # 兜底：假设 worker 从 backend 根启动。
    return Path.cwd()


_BACKEND_ROOT = _backend_root()
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def _boolean(payload: dict, key: str, default: bool) -> bool:
    value = payload.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} 必须是 JSON boolean，不能使用字符串或数字")
    return value


def _number(payload: dict, key: str, default: float) -> float:
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} 必须是数字")
    return float(value)


def workflow(payload: dict) -> dict:
    """主分支工作流入口：抽取并写入专利相关事实关系。

    payload（默认值与 ``load`` 签名一致）:
      apply (bool, 默认 False) —— False 只分析不写图；True 实际写入 dev。
      replace (bool, 默认 False) —— True 先删除既有受管边再重写（需 apply=True）。
      use_vector (bool, 默认 True) —— 精确规则未命中时使用Milvus混合召回。
      vector_threshold (float, 默认 0.88)
      vector_margin (float, 默认 0.08)
      vector_top_k (int, 默认 20)
      vector_state_dir (str|None, 默认 None) —— Organization BM25状态目录。
    """
    if not isinstance(payload, dict):
        raise ValueError(f"payload 必须是 dict，收到: {type(payload).__name__}")

    review_output = payload.get("review_output")
    vector_state_dir = payload.get("vector_state_dir")
    apply = _boolean(payload, "apply", False)
    replace = _boolean(payload, "replace", False)
    use_vector = _boolean(payload, "use_vector", True)
    threshold = _number(payload, "vector_threshold", 0.88)
    margin = _number(payload, "vector_margin", 0.08)
    top_k_value = payload.get("vector_top_k", 20)
    if isinstance(top_k_value, bool) or not isinstance(top_k_value, int):
        raise ValueError("vector_top_k 必须是整数")
    if replace and not apply:
        raise ValueError("replace=true 必须同时设置 apply=true")
    if not 0 <= threshold <= 1 or not 0 <= margin <= 1:
        raise ValueError("vector_threshold 和 vector_margin 必须在 0 到 1 之间")
    if top_k_value < 2:
        raise ValueError("vector_top_k 必须大于等于 2")
    kwargs = {
        "apply": apply,
        "replace": replace,
        "review_output": Path(review_output) if review_output else None,
        "use_vector": use_vector,
        "vector_threshold": threshold,
        "vector_margin": margin,
        "vector_top_k": top_k_value,
        "vector_state_dir": Path(vector_state_dir) if vector_state_dir else None,
    }

    try:
        from script.load_patent_relations import load

        stats = load(**kwargs)
    except Exception as exc:  # noqa: BLE001
        print(
            f"[patent_relation_workflow] failed (kwargs={kwargs}): {exc!r}",
            file=sys.stderr,
        )
        traceback.print_exc(file=sys.stderr)
        raise

    return {"ok": True, "stats": dict(stats)}
