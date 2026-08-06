"""国内外项目抽取工作流脚本。

封装 ``script.load_project_graph.load_project_graph``，供工作流平台 ``kg.custom.python``
上传后在 Activity 子进程执行。payload 控制批量与模式，返回 ProjectIngestReport 的
JSON 可序列化结果。

注意：stdout 必须只输出最终 JSON（runner 据此解析结果），日志一律走 stderr。
"""

from __future__ import annotations

import logging
import sys
from typing import Any

logger = logging.getLogger("workflow.project_ingest")


def workflow(payload: dict[str, Any]) -> dict[str, Any]:
    """执行项目实体与关系入图。

    payload 字段（均可选）:
      - limit: int — 本批次处理的项目数上限，默认 50（规避 60s 超时，全量靠多次执行）
      - id_prefix: str — 按 project id 前缀过滤
      - dry_run: bool — 只统计不写图
      - nodes_only: bool — 仅灌 Project 节点
      - relations_only: bool — 仅灌关系边
    """
    # 日志走 stderr，避免污染 stdout 的 JSON 结果。
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # 延迟导入：在子进程内执行，复用平台已注入的 PYTHONPATH=backend 与 .env 凭据。
    from script.load_project_graph import load_project_graph

    limit = payload.get("limit")
    limit_int = int(limit) if limit is not None else 50
    logger.info("project_ingest start payload=%s", payload)
    report = load_project_graph(
        id_prefix=payload.get("id_prefix"),
        limit=limit_int,
        nodes_only=bool(payload.get("nodes_only", False)),
        relations_only=bool(payload.get("relations_only", False)),
        dry_run=bool(payload.get("dry_run", False)),
    )
    logger.info("project_ingest done report=%s", report)
    return report
