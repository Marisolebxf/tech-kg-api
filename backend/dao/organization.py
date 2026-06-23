"""机构/企业数据查询（MySQL）。"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from db_model.industry_chain import (
    DwdOrgIndustryChainDtl,
    DwdOrgIndustryChainProdDtl,
)
from db_model.organization import (
    DwdOrgAnnualFinancialInfo,
    DwdOrgOrgProductInfo,
    DwdOrgRegInfo,
    DwdOrgStockFinanceInfo,
    DwdOrgTagInfo,
)


class OrganizationDAO:
    """企业多维查询封装。"""

    def __init__(self, session: Session) -> None:
        self._s = session

    def get_by_id(self, org_id: str) -> DwdOrgRegInfo | None:
        return self._s.get(DwdOrgRegInfo, org_id)

    def get_by_name(self, name_cn: str) -> DwdOrgRegInfo | None:
        stmt = select(DwdOrgRegInfo).where(DwdOrgRegInfo.name_cn == name_cn).limit(1)
        return self._s.execute(stmt).scalar_one_or_none()

    def list(self, *, limit: int = 100, offset: int = 0) -> Sequence[DwdOrgRegInfo]:
        return list(self._s.execute(select(DwdOrgRegInfo).limit(limit).offset(offset)).scalars())

    def get_products(self, org_id: str) -> DwdOrgOrgProductInfo | None:
        return self._s.get(DwdOrgOrgProductInfo, org_id)

    def get_tags(self, org_id: str) -> list[DwdOrgTagInfo]:
        stmt = select(DwdOrgTagInfo).where(DwdOrgTagInfo.org_id == org_id)
        return list(self._s.execute(stmt).scalars())

    def get_industry_chain(self, org_id: str) -> list[DwdOrgIndustryChainDtl]:
        stmt = select(DwdOrgIndustryChainDtl).where(DwdOrgIndustryChainDtl.antitypic == org_id)
        return list(self._s.execute(stmt).scalars())

    def get_chain_products(self, org_id: str) -> list[DwdOrgIndustryChainProdDtl]:
        stmt = select(DwdOrgIndustryChainProdDtl).where(
            DwdOrgIndustryChainProdDtl.antitypic == org_id
        )
        return list(self._s.execute(stmt).scalars())

    def get_stock_finance(self, org_id: str) -> list[DwdOrgStockFinanceInfo]:
        stmt = (
            select(DwdOrgStockFinanceInfo)
            .where(DwdOrgStockFinanceInfo.org_id == org_id)
            .order_by(DwdOrgStockFinanceInfo.occur_period.desc())
        )
        return list(self._s.execute(stmt).scalars())

    def get_annual_finance(self, org_id: str) -> list[DwdOrgAnnualFinancialInfo]:
        stmt = (
            select(DwdOrgAnnualFinancialInfo)
            .where(DwdOrgAnnualFinancialInfo.org_id == org_id)
            .order_by(DwdOrgAnnualFinancialInfo.year.desc())
        )
        return list(self._s.execute(stmt).scalars())
