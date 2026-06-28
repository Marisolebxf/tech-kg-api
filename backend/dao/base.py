from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from db_model.base import Base
from infra.mysql import create_session

ModelT = TypeVar("ModelT", bound=Base)


class BaseDAO(Generic[ModelT]):
    """Reusable SQLAlchemy CRUD helper.

    Business services should depend on DAO methods instead of operating ORM models directly.
    """

    model: type[ModelT]

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    def _create_session(self) -> Session:
        return create_session()

    def _get_session(self) -> tuple[Session, bool]:
        if self._session is not None:
            return self._session, False
        return self._create_session(), True

    def get(self, pk: Any) -> ModelT | None:
        session, should_close = self._get_session()
        try:
            return session.get(self.model, pk)
        finally:
            if should_close:
                session.close()

    def list(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: Any | None = None,
    ) -> list[ModelT]:
        statement = select(self.model).offset(offset).limit(limit)
        if order_by is not None:
            statement = statement.order_by(order_by)
        return self.list_by_statement(statement)

    def list_by_statement(self, statement: Select[tuple[ModelT]]) -> list[ModelT]:
        session, should_close = self._get_session()
        try:
            return list(session.scalars(statement).all())
        finally:
            if should_close:
                session.close()

    def first_by_statement(self, statement: Select[tuple[ModelT]]) -> ModelT | None:
        session, should_close = self._get_session()
        try:
            return session.scalars(statement).first()
        finally:
            if should_close:
                session.close()

    def count(self) -> int:
        session, should_close = self._get_session()
        try:
            statement = select(func.count()).select_from(self.model)
            return int(session.scalar(statement) or 0)
        finally:
            if should_close:
                session.close()

    def create(self, **values: Any) -> ModelT:
        session, should_close = self._get_session()
        instance = self.model(**values)
        try:
            session.add(instance)
            session.commit()
            session.refresh(instance)
            return instance
        except Exception:
            session.rollback()
            raise
        finally:
            if should_close:
                session.close()

    def update(self, pk: Any, **values: Any) -> ModelT | None:
        session, should_close = self._get_session()
        try:
            instance = session.get(self.model, pk)
            if instance is None:
                return None
            for key, value in values.items():
                setattr(instance, key, value)
            session.commit()
            session.refresh(instance)
            return instance
        except Exception:
            session.rollback()
            raise
        finally:
            if should_close:
                session.close()

    def delete(self, pk: Any) -> bool:
        session, should_close = self._get_session()
        try:
            instance = session.get(self.model, pk)
            if instance is None:
                return False
            session.delete(instance)
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            if should_close:
                session.close()

    def bulk_create(self, rows: Sequence[dict[str, Any]]) -> list[ModelT]:
        session, should_close = self._get_session()
        instances = [self.model(**row) for row in rows]
        try:
            session.add_all(instances)
            session.commit()
            for instance in instances:
                session.refresh(instance)
            return instances
        except Exception:
            session.rollback()
            raise
        finally:
            if should_close:
                session.close()
