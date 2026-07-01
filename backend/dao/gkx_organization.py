"""gkx_local 企业数据查询（只读）。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db_model.domestic_organization import DwdOrgRegInfo


class GkxOrganizationDAO:
    """gkx `dwd_org_reg_info` 查询封装（用于挖掘消歧靶库与企业建点）。"""

    def __init__(self, session: Session) -> None:
        self._s = session

    def get_by_id(self, org_id: str) -> DwdOrgRegInfo | None:
        return self._s.execute(
            select(DwdOrgRegInfo).where(DwdOrgRegInfo.org_id == org_id)
        ).scalar_one_or_none()

    def list_name_id(self) -> list[tuple[str, str]]:
        """返回 [(org_id, name_cn), ...]，作为消歧候选集。"""
        rows = self._s.execute(select(DwdOrgRegInfo.org_id, DwdOrgRegInfo.name_cn)).all()
        return [(oid, name) for (oid, name) in rows]
