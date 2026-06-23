"""关系抽取 HTTP 接口。"""

import os
from datetime import datetime, timezone
from uuid import uuid4
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException

from app.schemas.relation_extraction import (
    BatchRelationExtractionRequest,
    RelationExtractionRequest,
    RelationExtractionResponse,
    RelationExtractionTaskStatusResponse,
)
from app.services.relation_extraction import (
    batch_extract_relations,
    extract_relations,
)
from app.services.relation_extraction_writer import persist_relation_extraction_job
from app.services.extraction_job_runner import enqueue_relation_extraction_job
from app.services.extraction_task_store import task_store

router = APIRouter(prefix="/relation", tags=["关系抽取"])

_LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
_LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
_LLM_MODEL = os.environ.get("LLM_MODEL", "glm-4-flash")

_EXTRACTION_OPENAPI_EXAMPLES = {
    "rule_create": {
        "summary": "规则抽取 - 创立关系",
        "description": "使用规则模式抽取「创立」关系。",
        "value": {
            "text": "马云创立了阿里巴巴集团，阿里巴巴集团位于浙江省杭州市。",
            "method": "rule",
        },
    },
    "rule_multi": {
        "summary": "规则抽取 - 多关系",
        "description": "一段包含多种关系的文本，规则模式可同时抽取。",
        "value": {
            "text": (
                "任正非创立了华为技术有限公司，华为技术有限公司位于广东省深圳市。"
                "孟晚舟担任华为技术有限公司的CFO。"
                "华为技术有限公司推出了鸿蒙操作系统产品。"
            ),
            "method": "rule",
        },
    },
    "hybrid": {
        "summary": "混合抽取（需要 LLM_API_KEY）",
        "description": "规则 + LLM 交叉验证，需要设置 LLM_API_KEY 环境变量。",
        "value": {
            "text": "马斯克创立了特斯拉公司，特斯拉公司位于美国得克萨斯州。",
            "method": "hybrid",
        },
    },
}

_BATCH_EXTRACTION_OPENAPI_EXAMPLES = {
    "two_texts": {
        "summary": "批量抽取两条文本",
        "value": {
            "texts": [
                "马云创立了阿里巴巴集团",
                "任正非创立了华为技术有限公司",
            ],
            "method": "rule",
        },
    },
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _set_task(record_id: str, **fields) -> None:
    fields.pop("task_id", None)
    task_store().upsert(record_id, **fields)


def _get_task(task_id: str) -> dict:
    return task_store().get(task_id)


def _run_persist_task(task_id: str, method: str, text: str, entities: list[dict], relations: list[dict]) -> None:
    _set_task(task_id, status="running", started_at=_utc_now(), error="")
    try:
        result = persist_relation_extraction_job(
            task_id=task_id,
            method=method,
            source_text=text,
            entities=entities,
            relations=relations,
        )
        _set_task(
            task_id,
            status="succeeded",
            finished_at=result.get("finished_at", _utc_now()),
            written_entities=int(result.get("entity_written", 0)),
            written_relations=int(result.get("relation_written", 0)),
            job_node_id=str(result.get("job_node_id", "")),
            source_hash=str(result.get("source_hash", "")),
            storage_backend="redis_or_memory",
            error="",
        )
    except Exception as exc:  # pragma: no cover - background task failure path
        _set_task(
            task_id,
            status="failed",
            finished_at=_utc_now(),
            storage_backend="redis_or_memory",
            error=str(exc),
        )


@router.post("/extraction")
def run_extraction(
    body: Annotated[
        RelationExtractionRequest,
        Body(openapi_examples=_EXTRACTION_OPENAPI_EXAMPLES),
    ],
) -> RelationExtractionResponse:
    """
    从文本中抽取实体与关系三元组。
    支持三种抽取方法：rule（规则匹配）、llm（大模型）、hybrid（混合）。
    """
    result = extract_relations(
        text=body.text,
        method=body.method,
        llm_api_key=_LLM_API_KEY or None,
        llm_base_url=_LLM_BASE_URL,
        llm_model=_LLM_MODEL,
    )
    task_id = uuid4().hex
    _set_task(
        task_id,
        task_kind="relation_extraction",
        task_id=task_id,
        status="queued",
        method=str(result.get("method", body.method)),
        entity_count=len(result.get("entities", [])),
        relation_count=len(result.get("relations", [])),
        written_entities=0,
        written_relations=0,
        job_node_id="",
        source_hash="",
        storage_backend="redis_or_memory",
        execution_backend="scheduled_worker",
        queued_at=_utc_now(),
        started_at="",
        finished_at="",
        error="",
    )
    enqueue_relation_extraction_job(
        task_id=task_id,
        method=str(result.get("method", body.method)),
        text=body.text,
        entities=list(result.get("entities", [])),
        relations=list(result.get("relations", [])),
    )
    return RelationExtractionResponse(
        **result,
        task_id=task_id,
        task_status="queued",
        persist_to_graph=True,
    )


@router.post("/extraction/batch")
def run_batch_extraction(
    body: Annotated[
        BatchRelationExtractionRequest,
        Body(openapi_examples=_BATCH_EXTRACTION_OPENAPI_EXAMPLES),
    ],
) -> dict:
    """
    批量从多个文本中抽取实体与关系三元组，合并去重后返回。
    """
    result = batch_extract_relations(
        texts=body.texts,
        method=body.method,
        llm_api_key=_LLM_API_KEY or None,
        llm_base_url=_LLM_BASE_URL,
        llm_model=_LLM_MODEL,
    )
    task_id = uuid4().hex
    _set_task(
        task_id,
        task_kind="relation_extraction",
        task_id=task_id,
        status="queued",
        method=body.method,
        entity_count=int(result.get("entity_count", 0) or 0),
        relation_count=int(result.get("relation_count", 0) or 0),
        written_entities=0,
        written_relations=0,
        job_node_id="",
        queued_at=_utc_now(),
        started_at="",
        finished_at="",
        source_hash="",
        storage_backend="redis_or_memory",
        execution_backend="scheduled_worker",
        error="",
    )
    enqueue_relation_extraction_job(
        task_id=task_id,
        method=body.method,
        text="\n".join(body.texts),
        entities=list(result.get("merged_entities", [])),
        relations=list(result.get("merged_relations", [])),
    )
    result["task_id"] = task_id
    result["task_status"] = "queued"
    result["persist_to_graph"] = True
    return result


@router.get("/extraction/tasks/{task_id}", response_model=RelationExtractionTaskStatusResponse)
def get_extraction_task(task_id: str) -> RelationExtractionTaskStatusResponse:
    record = _get_task(task_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"task_id 不存在: {task_id}")
    return RelationExtractionTaskStatusResponse(
        task_id=task_id,
        task_kind=str(record.get("task_kind", "")),
        status=str(record.get("status", "unknown")),
        method=str(record.get("method", "")),
        entity_count=int(record.get("entity_count", 0) or 0),
        relation_count=int(record.get("relation_count", 0) or 0),
        written_entities=int(record.get("written_entities", 0) or 0),
        written_relations=int(record.get("written_relations", 0) or 0),
        job_node_id=str(record.get("job_node_id", "")),
        source_hash=str(record.get("source_hash", "")),
        storage_backend=str(record.get("storage_backend", "")),
        execution_backend=str(record.get("execution_backend", "")),
        error=str(record.get("error", "")),
        queued_at=str(record.get("queued_at", "")),
        started_at=str(record.get("started_at", "")),
        finished_at=str(record.get("finished_at", "")),
        updated_at=str(record.get("updated_at", "")),
    )


@router.get("/examples")
def get_examples() -> list[dict]:
    """获取示例文本列表。"""
    from app.services.relation_extraction import EXAMPLE_TEXTS
    return EXAMPLE_TEXTS
