"""项目数据查询封装。"""

from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from dao.base import BaseDAO
from db_model.base import Base
from db_model.domestic_project import OdsZhProject, OdsZhProjectOutput
from db_model.foreign_project import OdsEnProject, OdsEnProjectOutput

ModelT = TypeVar("ModelT", bound=Base)


class ProjectDAO:
    """国内外项目及其产出分页查询。"""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session
        self._zh = _ZhProjectDAO(session=session)
        self._en = _EnProjectDAO(session=session)
        self._zh_output = _ZhProjectOutputDAO(session=session)
        self._en_output = _EnProjectOutputDAO(session=session)

    def list_zh(
        self, *, offset: int = 0, limit: int = 100, id_prefix: str | None = None
    ) -> list[OdsZhProject]:
        return self._zh.list_filtered(offset=offset, limit=limit, id_prefix=id_prefix)

    def list_en(
        self, *, offset: int = 0, limit: int = 100, id_prefix: str | None = None
    ) -> list[OdsEnProject]:
        return self._en.list_filtered(offset=offset, limit=limit, id_prefix=id_prefix)

    def list_zh_output(
        self, *, offset: int = 0, limit: int = 100, id_prefix: str | None = None
    ) -> list[OdsZhProjectOutput]:
        return self._zh_output.list_filtered(offset=offset, limit=limit, id_prefix=id_prefix)

    def list_en_output(
        self, *, offset: int = 0, limit: int = 100, id_prefix: str | None = None
    ) -> list[OdsEnProjectOutput]:
        return self._en_output.list_filtered(offset=offset, limit=limit, id_prefix=id_prefix)

    def get_zh(self, project_id: str) -> OdsZhProject | None:
        return self._zh.get(project_id)

    def get_en(self, project_id: str) -> OdsEnProject | None:
        return self._en.get(project_id)


class _FilteredIdDAO(BaseDAO[ModelT], Generic[ModelT]):
    """按主键 id 前缀过滤的列表辅助。"""

    def list_filtered(
        self, *, offset: int = 0, limit: int = 100, id_prefix: str | None = None
    ) -> list[ModelT]:
        statement = select(self.model)
        if id_prefix:
            statement = statement.where(self.model.id.like(f"{id_prefix}%"))
        statement = statement.order_by(self.model.id).offset(offset).limit(limit)
        return self.list_by_statement(statement)


class _ZhProjectDAO(_FilteredIdDAO[OdsZhProject]):
    model = OdsZhProject


class _EnProjectDAO(_FilteredIdDAO[OdsEnProject]):
    model = OdsEnProject


class _ZhProjectOutputDAO(_FilteredIdDAO[OdsZhProjectOutput]):
    model = OdsZhProjectOutput


class _EnProjectOutputDAO(_FilteredIdDAO[OdsEnProjectOutput]):
    model = OdsEnProjectOutput
