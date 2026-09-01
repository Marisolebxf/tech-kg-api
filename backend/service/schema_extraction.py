"""Schema 平台喂数抽取：触发 kg.schema.extract 工作流。

模式：平台按来源表绑定分批读行（update_time 水位）→ 把行 JSON 通过
``payload["rows"]`` 传给脚本入口（复用现有 ``workflow(payload)`` 约定）→
脚本只做转换返回实体/关系 → 平台 merge 写图并推进水位。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy.orm import Session

from service.schema_management import (
    SchemaConflictError,
    SchemaManagementService,
)

logger = logging.getLogger(__name__)

EXTRACT_WORKFLOW_TYPE = "kg.schema.extract"
DEFAULT_BATCH_SIZE = 500
MAX_BATCH_SIZE = 5000


def extract_definition_id(schema_key: str) -> str:
    """平台喂数抽取的合成 definition id（execution/task 行引用它）。"""
    from service.schema_management import _workflow_definition_id

    return f"schema-extract-{_workflow_definition_id(schema_key).removeprefix('schema-')}"


def build_extract_definition(definition) -> dict[str, Any]:
    """由 schema 定义构造 kg.schema.extract 的合成工作流定义。

    脚本本体由 worker 端 ``load_schema_extract_plan`` activity 从 S3 下载到
    临时文件（独立 worker 进程也能取到），此处只带元数据。
    """
    return {
        "id": extract_definition_id(definition.schema_key),
        "workflowType": EXTRACT_WORKFLOW_TYPE,
        "name": f"{definition.label} 平台喂数抽取",
        "timeoutSeconds": int(os.getenv("SCHEMA_WORKFLOW_TIMEOUT_SECONDS", "3600")),
    }


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
        definition = self._schema_service.assert_mutable(
            schema_id,
            user_id,
            is_platform_admin=is_platform_admin,
            denied_system_message="只有 Schema 管理员可以触发系统 Schema 抽取",
            denied_owner_message="只能触发自己创建的 Schema 抽取",
        )
        if definition.script is None:
            raise SchemaConflictError("请先上传抽取脚本后再触发抽取")
        active_sources = [item for item in definition.sources]
        if not active_sources:
            raise SchemaConflictError("请先绑定至少一张来源表后再触发抽取")

        from service.workflow_operations import workflow_operations_service

        payload = {
            "schemaId": schema_id,
            "graphSpace": graph_space or os.getenv("TRS_GRAPH_SPACE", "techkg"),
            "batchSize": min(max(int(batch_size or DEFAULT_BATCH_SIZE), 1), MAX_BATCH_SIZE),
        }
        extract_definition = build_extract_definition(definition)
        execution = await workflow_operations_service.execute_definition(
            extract_definition, payload, persist_task=True
        )
        return {
            "executionId": execution["id"],
            "workflowId": execution["workflowId"],
            "status": execution["status"],
        }
