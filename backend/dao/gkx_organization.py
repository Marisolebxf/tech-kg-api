"""gkx_local 企业数据查询（只读）。

候选企业池合并 `dwd_org_reg_info`（机构注册信息）与 `dwd_org_stock_base`（上市公司），
按 org_id 去重，覆盖注册企业 + 上市公司，提升学者关联企业的命中率。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db_model.domestic_organization import DwdOrgRegInfo, DwdOrgStockBase


class GkxOrganizationDAO:
    """gkx 企业查询封装（用于挖掘消歧靶库与企业建点）。"""

    def __init__(self, session: Session) -> None:
        self._s = session

    def get_by_id(self, org_id: str) -> DwdOrgRegInfo | DwdOrgStockBase | None:
        """先查注册信息表，未命中再查上市公司表。"""
        row = self._s.execute(
            select(DwdOrgRegInfo).where(DwdOrgRegInfo.org_id == org_id)
        ).scalar_one_or_none()
        if row is not None:
            return row
        return self._s.execute(
            select(DwdOrgStockBase).where(DwdOrgStockBase.org_id == org_id)
        ).scalar_one_or_none()

    def list_name_id(self) -> list[tuple[str, str]]:
        """返回 [(org_id, name_cn), ...]，合并注册信息表 + 上市公司表，按 org_id 去重。"""
        by_id: dict[str, str] = {}
        for oid, name in self._s.execute(select(DwdOrgRegInfo.org_id, DwdOrgRegInfo.name_cn)).all():
            if oid and oid not in by_id:
                by_id[oid] = name
        for oid, name in self._s.execute(
            select(DwdOrgStockBase.org_id, DwdOrgStockBase.name_cn)
        ).all():
            if oid and oid not in by_id:
                by_id[oid] = name
        return list(by_id.items())
