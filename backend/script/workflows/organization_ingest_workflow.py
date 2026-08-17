"""国内外机构实体与关系抽取工作流入口。

脚本上传到工作流平台后，由 ``workflow(payload)`` 调用。stdout 由平台保留给
最终 JSON 结果，运行日志统一写入 stderr。
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("workflow.organization_ingest")


def _positive_int(payload: dict[str, Any], name: str, default: int) -> int:
    value = int(payload.get(name, default))
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _optional_positive_int(payload: dict[str, Any], name: str) -> int | None:
    value = payload.get(name)
    if value is None or value == "":
        return None
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"{name} must be positive or null for a full run")
    return parsed


def _boolean(payload: dict[str, Any], name: str, default: bool) -> bool:
    value = payload.get(name, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    raise ValueError(f"{name} must be a JSON boolean")


def workflow(payload: dict[str, Any]) -> dict[str, Any]:
    """按范围执行机构实体、关系抽取。

    payload 字段：
      - stage: all/entity/relation，默认 all
      - scope: all/domestic/foreign，默认 all
      - table: 实体来源表，默认 all
      - relation: 关系类型，默认 all
      - max_records: 正整数为抽样条数；null/省略表示全量
      - entity_batch_size / relation_batch_size: 批大小
      - dry_run: 默认 true；设为 false 才实际写图
      - alignment_mode: exact/hybrid，默认 exact
      - ingest_batch: 可选的批次标识
      - space: 图空间，当前机构本体仅支持 dev
    """
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    stage = str(payload.get("stage", "all")).strip().lower()
    scope = str(payload.get("scope", "all")).strip().lower()
    space = str(payload.get("space", "dev")).strip()
    if stage not in {"all", "entity", "relation"}:
        raise ValueError("stage must be all, entity or relation")
    if scope not in {"all", "domestic", "foreign"}:
        raise ValueError("scope must be all, domestic or foreign")
    if space != "dev":
        raise ValueError("organization workflow currently supports only the dev graph space")
    os.environ["TRS_GRAPH_SPACE"] = space

    from infra.graph_db.client import TRSGraphClient
    from infra.graph_db.config import TRSGraphSettings
    from script.organization_acceptance import collect_graph_snapshot, write_acceptance_report
    from script.organization_entity_etl import initialize_schema
    from script.organization_entity_etl import run_etl as run_entity_etl
    from script.organization_etl_common import exclusive_etl_lock
    from script.organization_relation_etl import run_etl as run_relation_etl

    dry_run = _boolean(payload, "dry_run", True)
    report_enabled = _boolean(payload, "report", True)
    max_records = _optional_positive_int(payload, "max_records")
    entity_batch_size = _positive_int(payload, "entity_batch_size", 100)
    relation_batch_size = _positive_int(payload, "relation_batch_size", 500)
    domestic_only = scope == "domestic"
    foreign_only = scope == "foreign"
    batch_timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    ingest_batch = payload.get("ingest_batch") or f"ORG_WORKFLOW_{batch_timestamp}"

    result: dict[str, Any] = {
        "stage": stage,
        "scope": scope,
        "space": space,
        "dryRun": dry_run,
        "ingestBatch": ingest_batch,
    }
    logger.info("organization_ingest start payload=%s", payload)
    with exclusive_etl_lock("organization_ingest_workflow", str(ingest_batch)):
        settings = TRSGraphSettings.from_env().model_copy(update={"space": space})
        graph = TRSGraphClient(settings)
        graph.connect()
        if not dry_run:
            initialize_schema(graph)
        before = collect_graph_snapshot(graph) if report_enabled else {}
        if stage in {"all", "entity"}:
            entity_result = run_entity_etl(
                table=str(payload.get("table", "all")),
                full=True,
                batch_size=entity_batch_size,
                max_records=max_records,
                dry_run=dry_run,
                domestic_only=domestic_only,
                foreign_only=foreign_only,
                ingest_batch=str(ingest_batch),
                graph=graph,
            )
            result["entities"] = {name: asdict(stats) for name, stats in entity_result.items()}

        if stage in {"all", "relation"}:
            relation_result = run_relation_etl(
                relation=str(payload.get("relation", "all")),
                batch_size=relation_batch_size,
                max_records=max_records,
                dry_run=dry_run,
                domestic_only=domestic_only,
                foreign_only=foreign_only,
                ingest_batch=str(ingest_batch),
                alignment_mode=str(payload.get("alignment_mode", "exact")),
                graph=graph,
            )
            result["relations"] = {name: asdict(stats) for name, stats in relation_result.items()}

        if report_enabled:
            after = collect_graph_snapshot(graph)
            result["acceptance"] = {
                "before": before,
                "after": after,
                "artifacts": write_acceptance_report(
                    batch=str(ingest_batch),
                    workflow_result=result,
                    before=before,
                    after=after,
                    output_dir=payload.get("report_output_dir"),
                ),
            }

    logger.info("organization_ingest done result=%s", result)
    return result
