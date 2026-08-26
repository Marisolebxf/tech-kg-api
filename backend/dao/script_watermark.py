"""脚本水位 DAO。复合主键 (definition_id, step_id)，自管 get/upsert。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db_model.script_watermark import ScriptWatermark


class ScriptWatermarkDAO:
    model = ScriptWatermark

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    def _get_session(self) -> tuple[Session, bool]:
        if self._session is not None:
            return self._session, False
        from infra.mysql import create_session

        session = create_session()
        return session, True

    def get(self, definition_id: str, step_id: str) -> ScriptWatermark | None:
        session, should_close = self._get_session()
        try:
            stmt = select(ScriptWatermark).where(
                ScriptWatermark.definition_id == definition_id,
                ScriptWatermark.step_id == step_id,
            )
            return session.scalars(stmt).first()
        finally:
            if should_close:
                session.close()

    def upsert(
        self,
        definition_id: str,
        step_id: str,
        watermark: datetime,
        checkpoint: dict[str, Any] | None = None,
    ) -> ScriptWatermark:
        """插入或更新水位。复合主键冲突时更新 watermark/checkpoint/updated_at。"""
        session, should_close = self._get_session()
        try:
            existing = session.scalars(
                select(ScriptWatermark).where(
                    ScriptWatermark.definition_id == definition_id,
                    ScriptWatermark.step_id == step_id,
                )
            ).first()
            if existing is None:
                row = ScriptWatermark(
                    definition_id=definition_id,
                    step_id=step_id,
                    watermark=watermark,
                    checkpoint=checkpoint,
                    updated_at=datetime.utcnow(),
                )
                session.add(row)
            else:
                existing.watermark = watermark
                existing.checkpoint = checkpoint
                existing.updated_at = datetime.utcnow()
            session.commit()
            return existing if existing is not None else row  # type: ignore[name-defined]
        except Exception:
            session.rollback()
            raise
        finally:
            if should_close:
                session.close()
