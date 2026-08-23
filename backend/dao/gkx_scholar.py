"""gkx_local 学者数据查询（只读）。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db_model.scholar import DwdScholar, DwdScholarResearchDirection


class GkxScholarDAO:
    """gkx `dwd_scholar` / `dwd_scholar_research_direction` 查询封装。"""

    def __init__(self, session: Session) -> None:
        self._s = session

    def get_by_id(self, scholar_id: str) -> DwdScholar | None:
        return self._s.execute(
            select(DwdScholar).where(DwdScholar.scholar_id == scholar_id)
        ).scalar_one_or_none()

    def get_research_directions(self, scholar_id: str) -> list[str]:
        rows = self._s.execute(
            select(DwdScholarResearchDirection.fields).where(
                DwdScholarResearchDirection.scholar_id == scholar_id
            )
        ).all()
        dirs: list[str] = []
        for (fields,) in rows:
            if not fields:
                continue
            dirs.extend(f.strip() for f in fields.split(",") if f.strip())
        return dirs
