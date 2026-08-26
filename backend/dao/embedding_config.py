"""平台 embedding 模型配置 DAO。"""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from dao.base import BaseDAO
from db_model.embedding_config import EmbeddingConfig


class EmbeddingConfigDAO(BaseDAO[EmbeddingConfig]):
    model = EmbeddingConfig

    def __init__(self, session: Session | None = None) -> None:
        super().__init__(session)

    def get_default(self) -> EmbeddingConfig | None:
        session, should_close = self._get_session()
        try:
            stmt = (
                select(EmbeddingConfig)
                .where(
                    EmbeddingConfig.is_default.is_(True),
                    EmbeddingConfig.status == "正常",
                )
                .order_by(EmbeddingConfig.updated_at.desc())
                .limit(1)
            )
            return session.scalars(stmt).first()
        finally:
            if should_close:
                session.close()

    def clear_other_defaults(self, exclude_id: str) -> int:
        session, should_close = self._get_session()
        try:
            stmt = (
                update(EmbeddingConfig)
                .where(
                    EmbeddingConfig.is_default.is_(True),
                    EmbeddingConfig.id != exclude_id,
                )
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
