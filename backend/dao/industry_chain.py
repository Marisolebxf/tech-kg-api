from __future__ import annotations

from typing import Any

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from db_model.industry_chain import (
    DwdIndustryChainInfo,
    DwdIndustryChainNewsInfo,
    DwdOrgIndustryChainDtl,
    DwdOrgIndustryChainPatDtl,
    DwdOrgIndustryChainProdDtl,
)
from infra.mysql import create_session


class IndustryChainDAO:
    """Read-only queries for industry-chain panorama and event ranking."""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    def _session_pair(self) -> tuple[Session, bool]:
        return (self._session, False) if self._session is not None else (create_session(), True)

    def _rows(self, statement: Select[Any]) -> list[dict[str, Any]]:
        session, close = self._session_pair()
        try:
            return [dict(row) for row in session.execute(statement).mappings().all()]
        finally:
            if close:
                session.close()

    @staticmethod
    def _chain_filter(model: Any, chain_code: str | None, keyword: str | None) -> Any:
        conditions = []
        if chain_code:
            conditions.append(model.chain_code == chain_code)
        if keyword:
            like = f"%{keyword.strip()}%"
            conditions.append(or_(model.chain_name.like(like), model.chain_code.like(like)))
        return or_(*conditions) if conditions else True

    def list_nodes(
        self, *, chain_code: str | None, keyword: str | None, limit: int = 500
    ) -> list[dict[str, Any]]:
        model = DwdIndustryChainInfo
        return self._rows(
            select(
                model.chain_code,
                model.chain_name,
                model.node_id,
                model.node_name,
                model.node_type,
                model.level,
                model.node_seq,
                model.parent_id,
                model.parent_name,
                model.node_imp_level,
                model.node_stage,
                model.node_path,
            )
            .where(self._chain_filter(model, chain_code, keyword))
            .order_by(model.level, model.node_seq, model.node_id)
            .limit(max(1, min(limit, 2000)))
        )

    def list_news(
        self,
        *,
        chain_code: str | None,
        keyword: str | None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        model = DwdIndustryChainNewsInfo
        statement = select(
            model.chain_code,
            model.chain_name,
            model.news_id,
            model.title,
            model.relaese_date,
            model.summary,
            model.source,
            model.updated_time,
        ).where(self._chain_filter(model, chain_code, keyword))
        if since:
            statement = statement.where(model.relaese_date >= since)
        if until:
            statement = statement.where(model.relaese_date <= until)
        return self._rows(
            statement.order_by(model.relaese_date.desc(), model.news_id).limit(
                max(1, min(limit, 1000))
            )
        )

    def list_organizations(
        self, *, chain_code: str | None, keyword: str | None, limit: int = 300
    ) -> list[dict[str, Any]]:
        model = DwdOrgIndustryChainDtl
        return self._rows(
            select(
                model.chain_code,
                model.chain_name,
                model.node_id,
                model.node_name,
                model.antitypic,
                model.credit_code,
                model.chain_score,
            )
            .where(self._chain_filter(model, chain_code, keyword))
            .order_by(model.chain_score.desc(), model.antitypic)
            .limit(max(1, min(limit, 1000)))
        )

    def list_patents(
        self, *, chain_code: str | None, keyword: str | None, limit: int = 300
    ) -> list[dict[str, Any]]:
        model = DwdOrgIndustryChainPatDtl
        return self._rows(
            select(
                model.chain_code,
                model.chain_name,
                model.node_id,
                model.node_name,
                model.apno,
                model.pat_name,
                model.current_assign,
                model.inventors,
                model.pbdt,
            )
            .where(self._chain_filter(model, chain_code, keyword))
            .order_by(model.pbdt.desc(), model.apno)
            .limit(max(1, min(limit, 1000)))
        )

    def list_products(
        self, *, chain_code: str | None, keyword: str | None, limit: int = 300
    ) -> list[dict[str, Any]]:
        model = DwdOrgIndustryChainProdDtl
        return self._rows(
            select(
                model.chain_code,
                model.chain_name,
                model.antitypic,
                model.company_name,
                model.credit_code,
                model.tech_product,
                model.tech_product_s,
            )
            .where(self._chain_filter(model, chain_code, keyword))
            .order_by(model.tech_product_s, model.antitypic)
            .limit(max(1, min(limit, 1000)))
        )
