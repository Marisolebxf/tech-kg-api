"""平台 LLM 配置 DAO。"""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from dao.base import BaseDAO
from db_model.llm_config import LlmConfig


class LlmConfigDAO(BaseDAO[LlmConfig]):
    model = LlmConfig

    def __init__(self, session: Session | None = None) -> None:
        super().__init__(session)

    def get_default(self) -> LlmConfig | None:
        """返回当前默认且状态正常的 LLM 配置。"""
        session, should_close = self._get_session()
        try:
            stmt = (
                select(LlmConfig)
                .where(LlmConfig.is_default.is_(True), LlmConfig.status == "正常")
                .order_by(LlmConfig.updated_at.desc())
                .limit(1)
            )
            return session.scalars(stmt).first()
        finally:
            if should_close:
                session.close()

    def clear_other_defaults(self, exclude_id: str) -> int:
        """把除 exclude_id 外的所有 is_default=True 记录置 False。返回受影响行数。"""
        session, should_close = self._get_session()
        try:
            stmt = (
                update(LlmConfig)
                .where(LlmConfig.is_default.is_(True), LlmConfig.id != exclude_id)
                .values(is_default=False)
            )
            result = session.execute(stmt)
            session.commit()
            return result.rowcount or 0
        except Exception:
            session.rollback()
            raise
        finally:
            if should_close:
                session.close()
