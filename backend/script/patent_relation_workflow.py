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


def workflow(payload: dict) -> dict:
    """主分支工作流入口：抽取并写入专利相关事实关系。

    payload（默认值与 ``load`` 签名一致）:
      apply (bool, 默认 False) —— False 只分析不写图；True 实际写入 dev。
      replace (bool, 默认 False) —— True 先删除既有受管边再重写（需 apply=True）。
      use_llm (bool, 默认 False) —— 是否用 LLM 扩展机构别名。
      llm_limit (int|None, 默认 None)
      llm_batch_size (int, 默认 10)
      llm_auto_threshold (float, 默认 0.75)
      llm_workers (int, 默认 4)
      review_output (str|None, 默认 None) —— ReviewRecord JSONL 输出路径。
      llm_cache (str|None, 默认 None) —— LLM 别名缓存路径。
    """
    if not isinstance(payload, dict):
        raise ValueError(f"payload 必须是 dict，收到: {type(payload).__name__}")

    review_output = payload.get("review_output")
    llm_cache = payload.get("llm_cache")
    kwargs = {
        "apply": bool(payload.get("apply", False)),
        "replace": bool(payload.get("replace", False)),
        "review_output": Path(review_output) if review_output else None,
        "use_llm": bool(payload.get("use_llm", False)),
        "llm_limit": payload.get("llm_limit"),
        "llm_batch_size": int(payload.get("llm_batch_size", 10)),
        "llm_auto_threshold": float(payload.get("llm_auto_threshold", 0.75)),
        "llm_workers": int(payload.get("llm_workers", 4)),
        "llm_cache": Path(llm_cache) if llm_cache else None,
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
