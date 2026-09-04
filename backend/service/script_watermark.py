"""脚本水位 service：读上次成功水位 / 写本次水位。供 activity 在子进程外调用。

watermark 是领域 ETL 游标（类比 Kafka offset），非 Temporal workflow step 状态缓存。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from dao.script_watermark import ScriptWatermarkDAO

logger = logging.getLogger(__name__)


class ScriptWatermarkService:
    def __init__(self) -> None:
        self._dao = ScriptWatermarkDAO()

    def read(self, definition_id: str, step_id: str) -> dict[str, Any] | None:
        row = self._dao.get(definition_id, step_id)
        if row is None:
            return None
        return {
            "watermark": row.watermark.strftime("%Y-%m-%dT%H:%M:%S"),
            "checkpoint": row.checkpoint,
        }

    def write(
        self,
        definition_id: str,
        step_id: str,
        watermark: datetime | None = None,
        checkpoint: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ts = watermark or datetime.now(UTC)
        row = self._dao.upsert(definition_id, step_id, ts, checkpoint)
        return {
            "definitionId": definition_id,
            "stepId": step_id,
            "watermark": row.watermark.strftime("%Y-%m-%dT%H:%M:%S"),
        }

    def clear_source_watermarks(self, definition_id: str) -> int:
        return self._dao.delete_source_watermarks(definition_id)


def read_watermark(definition_id: str | None, step_id: str) -> dict[str, Any] | None:
    """供 activity 解析：独立短连接读水位。definition_id 为空返回 None。"""
    if not definition_id:
        return None
    try:
        return ScriptWatermarkService().read(definition_id, step_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("读水位失败 %s/%s: %s", definition_id, step_id, exc)
        return None


def clear_watermarks(definition_ids: list[str]) -> int:
    """删除这批 definition 的全部 ``source:{id}`` 水位（回填前重置增量游标）。

    失败抛出（与读写的 best-effort 不同：清水位失败时回填只是增量续跑、
    达不到全量重跑目的，应让调用方感知）。返回总删除行数。
    """
    service = ScriptWatermarkService()
    cleared = 0
    for definition_id in definition_ids:
        cleared += service.clear_source_watermarks(definition_id)
    return cleared


def write_watermark(
    definition_id: str | None,
    step_id: str,
    watermark: datetime | None = None,
    checkpoint: dict[str, Any] | None = None,
) -> None:
    """供 activity 在 step 成功后调用。失败不阻塞 pipeline——记 warning 继续。"""
    if not definition_id:
        return
    try:
        ScriptWatermarkService().write(definition_id, step_id, watermark, checkpoint)
    except Exception as exc:  # noqa: BLE001
        logger.warning("写水位失败 %s/%s: %s", definition_id, step_id, exc)
