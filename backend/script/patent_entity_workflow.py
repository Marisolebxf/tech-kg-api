"""专利实体抽取薄包装：把 ``load_patent_graph.load_patents`` 封装为主分支 Python
工作流接口可调用的 ``workflow(payload)``，供“标准实体 → Patent → 上传脚本”使用。

主分支工作流接口（``POST /workflow-system/definitions/python``）要求脚本定义
``workflow(payload)`` 函数；Temporal ``kg.custom.python`` 经 ``execute_python_script``
activity 以子进程方式执行本脚本。子进程的 ``PYTHONPATH`` 只含脚本所在目录
（``WORKFLOW_SCRIPT_DIR``，通常是 /tmp），不含 backend 根，因此本脚本需自举
``sys.path`` 才能 ``from script.load_patent_graph import load_patents``。

本脚本只做入口适配、参数传递、结果 JSON 化；不复制/不修改实体抽取与建图逻辑。
执行失败时向上抛出异常，让 Temporal 识别 FAILED 并按平台策略重试。
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def _backend_root() -> Path:
    """定位 backend 根目录（含 ``script/load_patent_graph.py``）。"""
    env_root = os.getenv("TECH_KG_BACKEND_ROOT")
    if env_root and Path(env_root, "script", "load_patent_graph.py").is_file():
        return Path(env_root)
    here = Path(__file__).resolve()
    for parent in (here.parent, *here.parents):
        if (parent / "script" / "load_patent_graph.py").is_file():
            return parent
    # 兜底：假设 worker 从 backend 根启动。
    return Path.cwd()


_BACKEND_ROOT = _backend_root()
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def workflow(payload: dict) -> dict:
    """主分支工作流入口：写入 Patent 实体及其属性。

    payload:
      batch_size (int, 默认 50) —— MySQL 分页大小，透传给 ``load_patents``。

    图数据库连接和图空间只读取 ``TRS_GRAPH_*`` 环境变量，不接受 payload 覆盖。
    """
    if not isinstance(payload, dict):
        raise ValueError(f"payload 必须是 dict，收到: {type(payload).__name__}")

    batch_size = int(payload.get("batch_size", 50))
    try:
        from script.load_patent_graph import load_patents

        loaded, keyword_count, edge_count = load_patents(batch_size)
    except Exception as exc:  # noqa: BLE001
        print(
            f"[patent_entity_workflow] failed (batch_size={batch_size}): {exc!r}",
            file=sys.stderr,
        )
        traceback.print_exc(file=sys.stderr)
        raise

    return {
        "ok": True,
        "stats": {
            "patents": int(loaded),
            "keywordRefs": int(keyword_count),
            "hasKeywordEdges": int(edge_count),
        },
    }
