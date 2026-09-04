"""Schema 平台喂数抽取：触发 / 重跑 kg.schema.extract 工作流。

模式：平台按来源表绑定分批读行（水位或 pk keyset 游标）→ 行 JSON 经
``payload["rows"]`` 传给脚本入口（``transform(payload)``，脚本只做转换）→
平台并发写图、同名冲突检测（消歧）、实体重建 Milvus 索引、推进游标；
逐行解析失败落 T_EXTRACT_FAIL 审核 case，人工点击重跑（本模块
``rerun_failed_records``，新执行 triggerSource=RERUN，与常规执行同列展示）。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy.orm import Session

from service.schema_management import (
    SchemaConflictError,
    SchemaManagementService,
    _stale_behind,
)

logger = logging.getLogger(__name__)

EXTRACT_WORKFLOW_TYPE = "kg.schema.extract"
DEFAULT_BATCH_SIZE = 500
MAX_BATCH_SIZE = 5000


def extract_watermark_definition_ids(schema_key: str) -> list[str]:
    """该 schema 抽取水位的 definition_id 候选（回填清水位用）。

    抽取工作流按 ``schema-extract-{schema_key}``（原始 key）推水位，而执行记录
    落库用的是 sanitized 变体（``extract_definition_id``）——两个都清，兜住
    schema_key 含大写/特殊字符时的错位。
    """
    return sorted({f"schema-extract-{schema_key}", extract_definition_id(schema_key)})


def extract_definition_id(schema_key: str) -> str:
    """平台喂数抽取的合成 definition id（execution/task 行引用它）。"""
    from service.schema_management import _workflow_definition_id

    return f"schema-extract-{_workflow_definition_id(schema_key).removeprefix('schema-')}"


def build_extract_definition(definition: Any) -> dict[str, Any]:
    """由 schema 定义构造 kg.schema.extract 的合成工作流定义。

    脚本本体由 worker 端 ``load_schema_extract_plan`` activity 从 S3 下载到
    临时文件（独立 worker 进程也能取到），此处只带元数据。
    ``sourceKind="extract"``：temporal_runtime 对该类定义不包装
    ``{definitionId, payload}``（kg.schema.extract 收扁平 request），Schedule
    只把 ``_scheduleId`` merge 进扁平 payload。
    """
    if isinstance(definition, dict):
        schema_key = definition["schema_key"]
        label = definition.get("label") or definition["schema_key"]
    else:
        schema_key = definition.schema_key
        label = definition.label
    return {
        "id": extract_definition_id(schema_key),
        "workflowType": EXTRACT_WORKFLOW_TYPE,
        "name": f"{label} 平台喂数抽取",
        "category": "extract",
        "sourceKind": "extract",
        "active": True,
        "steps": ["extract"],
        "timeoutSeconds": int(os.getenv("SCHEMA_WORKFLOW_TIMEOUT_SECONDS", "3600")),
    }


def persist_extract_definition(definition: dict[str, Any]) -> dict[str, Any]:
    """把合成定义幂等落库。

    ``register_scheduled_execution``（周期触发落 execution 行）与
    ``trigger_job``（任务触发取定义）都按 definitionId 查控制库——不落库则
    周期运行无处留痕、任务触发直接报定义丢失。merge 时刷新名称/超时。
    """
    from service.workflow_repository import repository

    existing = repository.get_definition(definition["id"])
    if existing is None:
        repository.save_definition(definition)
        return definition
    merged = {
        **existing,
        "name": definition["name"],
        "workflowType": definition["workflowType"],
        "category": "extract",
        "sourceKind": "extract",
        "active": True,
        "steps": ["extract"],
        "timeoutSeconds": definition["timeoutSeconds"],
    }
    repository.save_definition(merged)
    return merged


def load_extract_schema(schema_id: str, *, session: Session | None = None) -> dict[str, Any]:
    """校验 schema 可抽取（已传脚本且 ≥1 来源绑定），返回构造定义所需字段。

    ``session`` 可传入已绑定控制库的会话（如 SchemaExtractionService 的
    service 层会话/测试 sqlite）；缺省自建控制库短会话。
    """
    from sqlalchemy.orm import Session as OrmSession

    from db_model.schema_management import GraphSchemaDefinition
    from infra.workflow_mysql import get_workflow_engine

    def _load(row_session):
        row = row_session.get(GraphSchemaDefinition, schema_id)
        if row is None or row.is_deleted:
            raise SchemaConflictError(f"Schema 不存在: {schema_id}")
        has_script = row.script is not None
        has_sources = len(row.sources) > 0
        info = {
            "id": row.id,
            "schema_key": row.schema_key,
            "kind": row.kind,
            "name": row.name,
            "label": row.label,
            "graph_space": row.graph_space,
            "property_revision": row.property_revision,
            "captured_revision": row.script.captured_revision if row.script else None,
        }
        return has_script, has_sources, info

    if session is not None:
        has_script, has_sources, info = _load(session)
    else:
        with OrmSession(get_workflow_engine()) as control_session:
            has_script, has_sources, info = _load(control_session)
    if not has_script:
        raise SchemaConflictError("请先上传抽取脚本后再触发抽取")
    if not has_sources:
        raise SchemaConflictError("请先绑定至少一张来源表后再触发抽取")
    return info


class SchemaExtractionService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._schema_service = SchemaManagementService(session)

    async def trigger_extraction(
        self,
        *,
        schema_id: str,
        user_id: str,
        is_platform_admin: bool = False,
        graph_space: str | None = None,
        batch_size: int | None = None,
    ) -> dict[str, Any]:
        """触发平台喂数抽取。要求已上传脚本且 ≥1 来源表绑定，否则 409。"""
        self._schema_service.assert_mutable(
            schema_id,
            user_id,
            is_platform_admin=is_platform_admin,
            denied_system_message="只有 Schema 管理员可以触发系统 Schema 抽取",
            denied_owner_message="只能触发自己创建的 Schema 抽取",
        )
        info = load_extract_schema(schema_id, session=self._session)

        from service.workflow_operations import workflow_operations_service

        payload = {
            "schemaId": schema_id,
            # 空间优先级：显式传参 > Schema 目录登记的归属空间 > env 默认
            "graphSpace": graph_space
            or info.get("graph_space")
            or os.getenv("TRS_GRAPH_SPACE", "techkg"),
            "batchSize": min(max(int(batch_size or DEFAULT_BATCH_SIZE), 1), MAX_BATCH_SIZE),
            "triggerSource": "MANUAL",
        }
        definition = persist_extract_definition(build_extract_definition(info))
        execution = await workflow_operations_service.execute_definition(
            definition, payload, persist_task=True
        )
        result = {
            "executionId": execution["id"],
            "workflowId": execution["workflowId"],
            "status": execution["status"],
        }
        # 下发检查：脚本落后于 Schema → 提示但放行（旧脚本永远跑不挂：
        # 删掉的属性被 activeProps 过滤、新属性只是没人产出留 NULL）
        stale_behind = _stale_behind(info.get("property_revision"), info.get("captured_revision"))
        if stale_behind:
            result["staleScript"] = True
            result["staleBehind"] = stale_behind
        return result

    async def backfill(
        self,
        *,
        schema_id: str,
        user_id: str,
        is_platform_admin: bool = False,
        force: bool = False,
        graph_space: str | None = None,
        batch_size: int | None = None,
    ) -> dict[str, Any]:
        """回填历史数据：清空该 Schema 全部来源水位后全量重跑抽取。

        merge_node/INSERT VERTEX 是 UPSERT：回填用源表当前值覆盖既有属性；
        失败可直接重跑（清水位幂等）。脚本落后于 Schema 时回填可能无效
        （脚本不产出新增属性，重跑完新列还是 NULL）——未带 ``force`` 时 409。
        """
        self._schema_service.assert_mutable(
            schema_id,
            user_id,
            is_platform_admin=is_platform_admin,
            denied_system_message="只有 Schema 管理员可以回填系统 Schema",
            denied_owner_message="只能回填自己创建的 Schema",
        )
        info = load_extract_schema(schema_id, session=self._session)
        stale_behind = _stale_behind(info.get("property_revision"), info.get("captured_revision"))
        if stale_behind and not force:
            raise SchemaConflictError(
                f"当前脚本未覆盖最新属性（落后 {stale_behind} 版），"
                "回填可能无效，请先更新脚本后再回填"
            )

        from service.script_watermark import clear_watermarks

        cleared = clear_watermarks(extract_watermark_definition_ids(info["schema_key"]))
        result = await self.trigger_extraction(
            schema_id=schema_id,
            user_id=user_id,
            is_platform_admin=is_platform_admin,
            graph_space=graph_space,
            batch_size=batch_size,
        )
        return {
            **result,
            "watermarksCleared": cleared,
            "forced": bool(force and stale_behind),
        }


async def rerun_failed_records(
    *,
    case_ids: list[str] | None = None,
    execution_id: str | None = None,
    batch_size: int | None = None,
) -> dict[str, Any]:
    """按审核 case 重跑失败记录（单条/批量勾选共用）。

    同一 schema 的所选 case 合并为**一个**新执行（triggerSource=RERUN），
    只读失败记录 id；先标 RERUNNING 再触发（防执行先完成的竞态），触发失败
    回滚为 OPEN。仍失败的记录由 workflow 结尾的 resolve 重建 case（attempt+1）。
    """
    from service.manual_review_production import manual_review_service
    from service.workflow_operations import workflow_operations_service
    from service.workflow_repository import repository

    cases = manual_review_service.list_extract_fail_cases(
        case_ids=case_ids, execution_id=execution_id
    )
    if not cases:
        raise SchemaConflictError("没有可重跑的抽取失败记录（case 可能已重跑或已关闭）")

    groups: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        schema_id = case.get("schemaId")
        if not schema_id:
            continue
        groups.setdefault(schema_id, []).append(case)

    executions: list[dict[str, Any]] = []
    total_cases = 0
    for schema_id, group in groups.items():
        info = load_extract_schema(schema_id)
        definition = persist_extract_definition(build_extract_definition(info))
        record_ids_by_source: dict[str, list[str]] = {}
        for case in group:
            binding = case.get("sourceBindingId") or ""
            if binding:
                ids = record_ids_by_source.setdefault(binding, [])
                if case["recordId"] not in ids:
                    ids.append(case["recordId"])
        if not record_ids_by_source:
            raise SchemaConflictError(f"所选 case 缺少来源绑定信息，无法重跑: {schema_id}")
        group_case_ids = [case["caseId"] for case in group]
        original = (
            repository.get_execution(group[0]["executionId"])
            if group[0].get("executionId")
            else None
        )
        orig_payload = (original or {}).get("payload") or {}
        graph_space = (
            orig_payload.get("graphSpace") or orig_payload.get("graph_space")
        ) or os.getenv("TRS_GRAPH_SPACE", "techkg")
        job_id = (original or {}).get("jobId") or group[0].get("jobId")

        payload: dict[str, Any] = {
            "schemaId": schema_id,
            "graphSpace": graph_space,
            "batchSize": min(max(int(batch_size or DEFAULT_BATCH_SIZE), 1), MAX_BATCH_SIZE),
            "recordIdsBySource": record_ids_by_source,
            "rerunCaseIds": group_case_ids,
            "rerunOfExecutionId": group[0].get("executionId"),
            "triggerSource": "RERUN",
            "buildIndex": False,  # 重跑只补写少量记录，不重建全量索引
        }
        if job_id:
            payload["jobId"] = job_id

        manual_review_service.mark_extract_rerun(group_case_ids)
        try:
            execution = await workflow_operations_service.execute_definition(
                definition, payload, persist_task=True
            )
        except Exception:
            manual_review_service.revert_extract_rerun(group_case_ids, reason="触发重跑执行失败")
            raise
        manual_review_service.attach_rerun_execution(group_case_ids, execution["id"])
        record_count = sum(len(v) for v in record_ids_by_source.values())
        executions.append(
            {
                "executionId": execution["id"],
                "schemaId": schema_id,
                "records": record_count,
                "cases": len(group_case_ids),
            }
        )
        total_cases += len(group_case_ids)
    return {"executions": executions, "cases": total_cases}
