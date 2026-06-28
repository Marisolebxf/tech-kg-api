from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dao.organization import OrganizationDAO
from db_model.base import Base
from db_model.domestic_organization import (
    DwdOrgAnnualFinancialInfo,
    DwdOrgOrgProductInfo,
    DwdOrgRegInfo,
    DwdOrgStockFinanceInfo,
    DwdOrgTagInfo,
)
from db_model.industry_chain import DwdOrgIndustryChainDtl, DwdOrgIndustryChainProdDtl

_NOW = datetime(2024, 1, 1)


def _session() -> Session:
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        eng,
        tables=[
            DwdOrgRegInfo.__table__,
            DwdOrgTagInfo.__table__,
            DwdOrgStockFinanceInfo.__table__,
            DwdOrgAnnualFinancialInfo.__table__,
            DwdOrgOrgProductInfo.__table__,
            DwdOrgIndustryChainDtl.__table__,
            DwdOrgIndustryChainProdDtl.__table__,
        ],
    )
    return Session(eng)


def _dao(session):
    return OrganizationDAO(session)


def test_get_by_name_and_id():
    with _session() as s:
        now = datetime(2024, 1, 1)
        s.add(
            DwdOrgRegInfo(
                org_id="O1",
                name_cn="清华大学",
                province="北京市",
                data_source="t",
                created_time=now,
                updated_time=now,
            )
        )
        s.commit()
        dao = OrganizationDAO(s)
        assert dao.get_by_id("O1").name_cn == "清华大学"
        assert dao.get_by_name("清华大学").org_id == "O1"
        assert dao.get_by_name("不存在") is None
        assert len(dao.list(limit=10)) == 1


def test_get_tags_filters_by_org_id():
    with _session() as s:
        for tag in ("A", "B"):
            s.add(
                DwdOrgTagInfo(
                    org_id="ORG1",
                    name_cn="公司一",
                    org_tag=tag,
                    tag_level="L1",
                    data_source="t",
                    created_time=_NOW,
                    updated_time=_NOW,
                )
            )
        s.add(
            DwdOrgTagInfo(
                org_id="ORG2",
                name_cn="公司二",
                org_tag="C",
                tag_level="L1",
                data_source="t",
                created_time=_NOW,
                updated_time=_NOW,
            )
        )
        s.commit()
        rows = _dao(s).get_tags("ORG1")
        assert len(rows) == 2
        assert {r.org_id for r in rows} == {"ORG1"}


def test_get_stock_finance_orders_by_period_desc():
    with _session() as s:
        for period in ("2022", "2024", "2023"):
            s.add(
                DwdOrgStockFinanceInfo(
                    org_id="ORG1",
                    name_cn="公司一",
                    stock_code="600001",
                    occur_period=period,
                    data_source="t",
                    created_time=_NOW,
                    updated_time=_NOW,
                )
            )
        s.add(
            DwdOrgStockFinanceInfo(
                org_id="ORG2",
                name_cn="公司二",
                stock_code="600002",
                occur_period="2023",
                data_source="t",
                created_time=_NOW,
                updated_time=_NOW,
            )
        )
        s.commit()
        rows = _dao(s).get_stock_finance("ORG1")
        assert [r.occur_period for r in rows] == ["2024", "2023", "2022"]
        assert {r.org_id for r in rows} == {"ORG1"}


def test_get_annual_finance_orders_by_year_desc():
    with _session() as s:
        for year in (2020, 2022, 2021):
            s.add(
                DwdOrgAnnualFinancialInfo(
                    org_id="ORG1",
                    name_cn="公司一",
                    year=year,
                    data_source="t",
                    created_time=_NOW,
                    updated_time=_NOW,
                )
            )
        s.commit()
        rows = _dao(s).get_annual_finance("ORG1")
        assert [r.year for r in rows] == [2022, 2021, 2020]


def test_get_products_returns_row_and_none_when_absent():
    with _session() as s:
        s.add(
            DwdOrgOrgProductInfo(
                org_id="ORG1",
                name_cn="公司一",
                industry_class="半导体",
                main_prod="芯片",
                data_source="t",
                created_time=_NOW,
                updated_time=_NOW,
            )
        )
        s.commit()
        dao = _dao(s)
        got = dao.get_products("ORG1")
        assert got is not None
        assert got.main_prod == "芯片"
        assert dao.get_products("MISSING") is None


def test_get_industry_chain_filters_by_antitypic():
    with _session() as s:
        for node_id in ("N1", "N2"):
            s.add(
                DwdOrgIndustryChainDtl(
                    chain_code="C1",
                    chain_name="芯片产业链",
                    node_id=node_id,
                    node_name="节点",
                    antitypic="ORG1",
                    data_source="t",
                    created_time=_NOW,
                    updated_time=_NOW,
                )
            )
        s.add(
            DwdOrgIndustryChainDtl(
                chain_code="C1",
                chain_name="芯片产业链",
                node_id="N3",
                node_name="节点",
                antitypic="ORG2",
                data_source="t",
                created_time=_NOW,
                updated_time=_NOW,
            )
        )
        s.commit()
        rows = _dao(s).get_industry_chain("ORG1")
        assert len(rows) == 2
        assert {r.antitypic for r in rows} == {"ORG1"}


def test_get_chain_products_filters_by_antitypic():
    with _session() as s:
        for prod in ("P1", "P2"):
            s.add(
                DwdOrgIndustryChainProdDtl(
                    chain_code="C1",
                    chain_name="芯片产业链",
                    antitypic="ORG1",
                    tech_product=prod,
                    data_source="t",
                    created_time=_NOW,
                    updated_time=_NOW,
                )
            )
        s.add(
            DwdOrgIndustryChainProdDtl(
                chain_code="C1",
                chain_name="芯片产业链",
                antitypic="ORG2",
                tech_product="P3",
                data_source="t",
                created_time=_NOW,
                updated_time=_NOW,
            )
        )
        s.commit()
        rows = _dao(s).get_chain_products("ORG1")
        assert len(rows) == 2
        assert {r.antitypic for r in rows} == {"ORG1"}
