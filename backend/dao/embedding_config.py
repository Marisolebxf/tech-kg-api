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

    def clear_other_defaults(self, exclude_id: str, owner: str | None = None) -> int:
        """把除 exclude_id 外的 is_default=True 记录置 False。传 owner 时仅影响该用户。"""
        session, should_close = self._get_session()
        try:
            conditions = [EmbeddingConfig.is_default.is_(True), EmbeddingConfig.id != exclude_id]
            if owner is not None:
                conditions.append(EmbeddingConfig.owner == owner)
            stmt = update(EmbeddingConfig).where(*conditions).values(is_default=False)
            result = session.execute(stmt)
            session.commit()
            return result.rowcount or 0
        except Exception:
            session.rollback()
            raise
        finally:
            if should_close:
                session.close()
