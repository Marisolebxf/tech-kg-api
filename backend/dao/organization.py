"""机构/企业数据查询（MySQL）。"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from db_model.organization import DwdOrgRegInfo


class OrganizationDAO:
    """dwd_org_reg_info 查询封装。"""

    def __init__(self, session: Session) -> None:
        self._s = session

    def get_by_id(self, org_id: str) -> DwdOrgRegInfo | None:
        return self._s.get(DwdOrgRegInfo, org_id)

    def get_by_name(self, name_cn: str) -> DwdOrgRegInfo | None:
        stmt = select(DwdOrgRegInfo).where(DwdOrgRegInfo.name_cn == name_cn).limit(1)
        return self._s.execute(stmt).scalar_one_or_none()

    def list(self, *, limit: int = 100, offset: int = 0) -> Sequence[DwdOrgRegInfo]:
        return list(self._s.execute(select(DwdOrgRegInfo).limit(limit).offset(offset)).scalars())
