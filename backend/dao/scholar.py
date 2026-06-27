from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from dao.base import BaseDAO
from db_model.scholar import DwdScholar


class ScholarDAO(BaseDAO[DwdScholar]):
    """专家/人才数据查询封装。"""

    model = DwdScholar

    def __init__(self, session: Session | None = None) -> None:
        super().__init__(session=session)

    def get_by_id(self, scholar_pk: int) -> DwdScholar | None:
        return self.get(scholar_pk)

    def get_by_scholar_id(self, scholar_id: str) -> DwdScholar | None:
        statement = select(DwdScholar).where(DwdScholar.scholar_id == scholar_id)
        return self.first_by_statement(statement)

    def search_by_name(
        self,
        keyword: str,
        *,
        offset: int = 0,
        limit: int = 20,
        only_active: bool = True,
    ) -> list[DwdScholar]:
        keyword = keyword.strip()
        if not keyword:
            return []

        like_keyword = f"%{keyword}%"
        statement = (
            select(DwdScholar)
            .where(
                or_(DwdScholar.name_zh.like(like_keyword), DwdScholar.name_en.like(like_keyword))
            )
            .offset(offset)
            .limit(limit)
        )
        if only_active:
            statement = statement.where(DwdScholar.status == 1)
        return self.list_by_statement(statement)
