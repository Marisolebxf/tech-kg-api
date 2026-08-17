"""国内外项目抽取工作流脚本。

流水线：ensure_schema → load_project_graph → align_project_relations → cleanup_project_stubs。
供工作流平台 ``kg.custom.python`` 上传后在 Activity 子进程执行；也可由
``kg.entity.project`` 的 Activity 直接 import 调用。

注意：stdout 必须只输出最终 JSON（runner 据此解析结果），日志一律走 stderr。
"""

from __future__ import annotations

import logging
import sys
from typing import Any

logger = logging.getLogger("workflow.project_ingest")


def workflow(payload: dict[str, Any]) -> dict[str, Any]:
    """执行项目实体与关系入图流水线。

    payload 字段（均可选）:
      - limit: int — 本批次处理的项目数上限，默认 50（规避超时，全量靠多次执行）
      - id_prefix / project_id: str — 过滤
      - dry_run: bool — 只统计不写图
      - nodes_only / relations_only: bool — 仅灌点或仅灌边（传给 load）
      - skip_align / skip_cleanup / skip_schema: bool — 跳过阶段
      - ingest_batch: str — 批次号
    """
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    from script.align_project_relations import align_project_relations
    from script.cleanup_project_stubs import cleanup_project_stubs
    from script.load_project_graph import get_dev_graph_client, load_project_graph
    from script.project_edge_schema import (
        ensure_alignment_edge_schema,
        ensure_project_tag_confidence,
    )

    limit = payload.get("limit")
    limit_int = int(limit) if limit is not None else 50
    dry_run = bool(payload.get("dry_run", False))
    skip_align = bool(payload.get("skip_align", False))
    skip_cleanup = bool(payload.get("skip_cleanup", False))
    skip_schema = bool(payload.get("skip_schema", False))
    nodes_only = bool(payload.get("nodes_only", False))
    relations_only = bool(payload.get("relations_only", False))
    backfill_confidence = bool(payload.get("backfill_confidence", False))

    logger.info("project_ingest start payload=%s", payload)
    stages: dict[str, Any] = {}

    if not skip_schema and not dry_run:
        graph = get_dev_graph_client()
        try:
            ensure_alignment_edge_schema(graph)
            ensure_project_tag_confidence(graph)
            stages["schema"] = {"status": "ok"}
        finally:
            from infra.graph_db import close_trs_graph_client

            close_trs_graph_client()
    else:
        stages["schema"] = {"status": "skipped"}

    if backfill_confidence:
        # 仅回填现有 Project 节点 confidence，跳过灌点/对齐/清理（可幂等重跑）
        from script.load_project_graph import backfill_project_confidence, get_dev_graph_client

        graph = get_dev_graph_client()
        try:
            stages["backfill_confidence"] = backfill_project_confidence(graph, dry_run=dry_run)
        finally:
            from infra.graph_db import close_trs_graph_client

            close_trs_graph_client()
        stages.setdefault("load", {"status": "skipped"})
        stages.setdefault("align", {"status": "skipped"})
        stages.setdefault("cleanup", {"status": "skipped"})
        result = {"status": "completed", "stages": stages}
        logger.info("project_ingest backfill done")
        return result

    load_report = load_project_graph(
        project_id=payload.get("project_id"),
        id_prefix=payload.get("id_prefix"),
        limit=limit_int,
        ingest_batch=payload.get("ingest_batch"),
        nodes_only=nodes_only,
        relations_only=relations_only,
        dry_run=dry_run,
    )
    stages["load"] = load_report

    if skip_align or nodes_only:
        stages["align"] = {"status": "skipped"}
    else:
        stages["align"] = align_project_relations(
            project_id=payload.get("project_id"),
            id_prefix=payload.get("id_prefix"),
            limit=limit_int,
            ingest_batch=payload.get("ingest_batch"),
            dry_run=dry_run,
        )

    if skip_cleanup:
        stages["cleanup"] = {"status": "skipped"}
    else:
        stages["cleanup"] = cleanup_project_stubs(dry_run=dry_run)

    result = {"status": "completed", "stages": stages}
    logger.info("project_ingest done keys=%s", list(stages))
    return result
