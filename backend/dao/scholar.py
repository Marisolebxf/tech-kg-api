"""专家/人才数据查询（MySQL）。"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from db_model.scholar import DwdScholar


class ScholarDAO:
    """dwd_scholar 查询封装。"""

    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, scholar_id: str) -> DwdScholar | None:
        return self._s.get(DwdScholar, scholar_id)

    def list(self, *, limit: int = 100, offset: int = 0) -> Sequence[DwdScholar]:
        return list(self._s.execute(select(DwdScholar).limit(limit).offset(offset)).scalars())
