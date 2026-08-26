"""平台 Milvus 配置 DAO。"""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from dao.base import BaseDAO
from db_model.milvus_config import MilvusConfig


class MilvusConfigDAO(BaseDAO[MilvusConfig]):
    model = MilvusConfig

    def __init__(self, session: Session | None = None) -> None:
        super().__init__(session)

    def get_default(self) -> MilvusConfig | None:
        session, should_close = self._get_session()
        try:
            stmt = (
                select(MilvusConfig)
                .where(MilvusConfig.is_default.is_(True), MilvusConfig.status == "正常")
                .order_by(MilvusConfig.updated_at.desc())
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
                update(MilvusConfig)
                .where(MilvusConfig.is_default.is_(True), MilvusConfig.id != exclude_id)
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
