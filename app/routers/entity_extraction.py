"""实体抽取 HTTP 接口"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.schemas.entity_extraction import (
    ExtractRequest,
    ExtractResponse,
    ExtractionTaskStatusResponse,
)
from app.services.entity_extractor import extract, FOCUS_TYPES
from app.services.entity_extraction_writer import persist_extraction_job
from app.services.extraction_job_runner import enqueue_entity_extraction_job
from app.services.extraction_task_store import task_store

router = APIRouter(prefix="/entity", tags=["实体抽取"])

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _set_task(record_id: str, **fields) -> None:
    fields.pop("task_id", None)
    task_store().upsert(record_id, **fields)


def _get_task(task_id: str) -> dict:
    return task_store().get(task_id)


def _run_persist_task(task_id: str, source_type: str, text: str, entities: list[dict]) -> None:
    _set_task(task_id, status="running", started_at=_utc_now(), error="")
    try:
        result = persist_extraction_job(
            task_id=task_id,
            source_type=source_type,
            source_text=text,
            entities=entities,
        )
        _set_task(
            task_id,
            status="succeeded",
            finished_at=result.get("finished_at", _utc_now()),
            written_entities=int(result.get("entity_written", 0)),
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
            error=str(exc),
            storage_backend="redis_or_memory",
        )


@router.post("/extraction")
def run_extraction(body: ExtractRequest) -> ExtractResponse:
    """
    从非结构化文本中抽取知识图谱实体。

    - **text**: 待抽取的文本，如工作经历、教育背景、摘要等
    - **source_type**: 文本类型，决定重点识别哪些实体
      - `work`      工作经历 → 机构、职位、时间段
      - `education` 教育背景 → 学校、学位、专业、时间段
      - `abstract`  摘要文本 → 技术领域、机构、基金
      - `general`   通用模式 → 所有实体类型
    """
    if not body.text or not body.text.strip():
        raise HTTPException(status_code=400, detail="text 不能为空")

    if body.source_type not in FOCUS_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"source_type 不合法，可选值：{list(FOCUS_TYPES.keys())}"
        )

    entities = extract(body.text, body.source_type)
    task_id = uuid4().hex
    _set_task(
        task_id,
        task_kind="entity_extraction",
        task_id=task_id,
        status="queued",
        source_type=body.source_type,
        entity_count=len(entities),
        written_entities=0,
        job_node_id="",
        queued_at=_utc_now(),
        started_at="",
        finished_at="",
        source_hash="",
        storage_backend="redis_or_memory",
        execution_backend="scheduled_worker",
        error="",
    )
    enqueue_entity_extraction_job(
        task_id=task_id,
        source_type=body.source_type,
        text=body.text,
        entities=entities,
    )

    return ExtractResponse(
        source_type=body.source_type,
        entity_count=len(entities),
        entities=entities,
        task_id=task_id,
        task_status="queued",
        persist_to_graph=True,
    )


@router.get("/extraction/tasks/{task_id}", response_model=ExtractionTaskStatusResponse)
def get_extraction_task(task_id: str) -> ExtractionTaskStatusResponse:
    record = _get_task(task_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"task_id 不存在: {task_id}")
    return ExtractionTaskStatusResponse(
        task_id=task_id,
        task_kind=str(record.get("task_kind", "")),
        status=str(record.get("status", "unknown")),
        source_type=str(record.get("source_type", "")),
        entity_count=int(record.get("entity_count", 0) or 0),
        written_entities=int(record.get("written_entities", 0) or 0),
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
