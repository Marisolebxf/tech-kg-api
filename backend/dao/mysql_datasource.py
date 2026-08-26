"""平台 MySQL 数据源 DAO。"""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from dao.base import BaseDAO
from db_model.mysql_datasource import MysqlDatasource


class MysqlDatasourceDAO(BaseDAO[MysqlDatasource]):
    model = MysqlDatasource

    def __init__(self, session: Session | None = None) -> None:
        super().__init__(session)

    def get_default(self) -> MysqlDatasource | None:
        """返回当前默认且状态正常的 MySQL 数据源。"""
        session, should_close = self._get_session()
        try:
            stmt = (
                select(MysqlDatasource)
                .where(
                    MysqlDatasource.is_default.is_(True),
                    MysqlDatasource.status == "正常",
                )
                .order_by(MysqlDatasource.updated_at.desc())
                .limit(1)
            )
            return session.scalars(stmt).first()
        finally:
            if should_close:
                session.close()

    def clear_other_defaults(self, exclude_id: str) -> int:
        """把除 exclude_id 外的所有 is_default=True 记录置 False。"""
        session, should_close = self._get_session()
        try:
            stmt = (
                update(MysqlDatasource)
                .where(
                    MysqlDatasource.is_default.is_(True),
                    MysqlDatasource.id != exclude_id,
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
