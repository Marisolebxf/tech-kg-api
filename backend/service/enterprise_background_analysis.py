"""企业背景关联分析服务：MySQL 多维聚合 + LLM 合成结论（带降级）。"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from dao.organization import OrganizationDAO
from dao.patent import PatentDAO
from infra.gkx import get_gkx_session
from infra.llm import get_llm_client
from service.base_module import KGModuleScaffoldService

logger = logging.getLogger(__name__)


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class EnterpriseBackgroundAnalysisService(KGModuleScaffoldService):
    module_code = "enterprise_background_analysis"

    def analyze(self, payload: dict[str, Any], session: Session | None = None) -> dict[str, Any]:
        enterprise_id = payload.get("enterpriseId", "")
        dimensions = payload.get("analysisDimensions", []) or []
        patent_cpc = payload.get("patentCPC", []) or []

        own_session = session is None
        if own_session:
            session = get_gkx_session()
        try:
            org_dao = OrganizationDAO(session)
            pat_dao = PatentDAO(session)
            org = org_dao.get_by_id(enterprise_id)
            if org is None:
                raise KeyError(f"企业不存在: {enterprise_id}")
            name = org.name_cn

            facts: dict[str, dict[str, Any]] = {}
            # 各维度独立容错：gkx 表结构与模型可能存在列漂移，单维度查询失败时降级为
            # available=False，不应导致整个 analyze 抛系统异常（标书：无数据返回空结果）。
            dim_calls: dict[str, Any] = {}
            if "industry_status" in dimensions:
                dim_calls["industry_status"] = lambda: self._industry_status(
                    org, org_dao, enterprise_id
                )
            if "core_tech" in dimensions:
                dim_calls["core_tech"] = lambda: self._core_tech(
                    org_dao, pat_dao, enterprise_id, name, patent_cpc
                )
            if "financial" in dimensions:
                dim_calls["financial"] = lambda: self._financial(org_dao, enterprise_id)
            for dim, fn in dim_calls.items():
                try:
                    facts[dim] = fn()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("analyze dimension %s failed: %s", dim, exc)
                    facts[dim] = {"available": False, "summary": "暂无数据"}

            patent_dist = self._patent_distribution(pat_dao, name)
        finally:
            if own_session:
                session.close()

        llm = get_llm_client()
        conclusions: dict[str, str] = self._synthesize_dimensions(llm, facts) if llm else {}
        core_layout = (
            self._synthesize_core_layout(llm, facts) if llm else ""
        ) or self._template_core_layout(facts)

        for dim, data in facts.items():
            if not data.get("available"):
                continue
            data["conclusion"] = conclusions.get(dim) or self._template_conclusion(dim, data)

        return {
            "status": "success",
            "enterpriseId": enterprise_id,
            "enterpriseName": name,
            "dimensions": facts,
            "patentDistribution": patent_dist,
            "coreTechLayout": core_layout,
        }

    # ----- 维度聚合 -----

    def _industry_status(self, org: Any, org_dao: OrganizationDAO, org_id: str) -> dict[str, Any]:
        if org is None:
            return {"available": False, "summary": "暂无数据"}
        facts = {
            "orgType": getattr(org, "org_type", None),
            "listingStatus": org.listing_status,
            "registeredCapital": _num(org.registered_capital_value),
            "province": org.province,
            "city": org.city,
            "incorporationYear": org.incorporation_year,
            "tags": [{"tag": t.org_tag, "level": t.tag_level} for t in org_dao.get_tags(org_id)],
            "industryChains": [
                {"chain": c.chain_name, "score": _num(c.chain_score)}
                for c in org_dao.get_industry_chain(org_id)
            ],
            "chainProducts": [p.tech_product for p in org_dao.get_chain_products(org_id)],
        }
        return {"available": True, "facts": facts}

    def _core_tech(
        self,
        org_dao: OrganizationDAO,
        pat_dao: PatentDAO,
        org_id: str,
        name_cn: str,
        cpc_prefixes: list[str],
    ) -> dict[str, Any]:
        prod = org_dao.get_products(org_id)
        try:
            patents = pat_dao.list_by_assignee(name_cn, cpc_prefixes)
        except Exception as exc:  # noqa: BLE001  gkx 无 dwd_patent 表等
            logger.warning("patent list failed: %s", exc)
            patents = []
        if prod is None and not patents:
            return {"available": False, "summary": "暂无数据"}
        facts = {
            "industryClass": prod.industry_class if prod else None,
            "mainActivities": prod.main_activities if prod else None,
            "mainProducts": prod.main_prod if prod else None,
            "patentCount": len(patents),
            "patents": [
                {"id": p.patent_id, "applicant": p.first_current_assignee_name}
                for p in patents[:20]
            ],
        }
        return {"available": True, "facts": facts}

    def _financial(self, org_dao: OrganizationDAO, org_id: str) -> dict[str, Any]:
        stock = org_dao.get_stock_finance(org_id)
        if stock:
            f = stock[0]
            return {
                "available": True,
                "facts": {
                    "source": "stock",
                    "period": f.occur_period,
                    "operatingRevenue": _num(f.operating_revenue),
                    "pureProfit": _num(f.pure_profit),
                    "totalAssets": _num(f.total_assets),
                    "rdAmount": _num(f.research_development_amount),
                    "employees": f.employees_number,
                },
            }
        annual = org_dao.get_annual_finance(org_id)
        if annual:
            f = annual[0]
            return {
                "available": True,
                "facts": {
                    "source": "annual",
                    "period": f.year,
                    "operatingRevenue": _num(f.operating_revenue),
                    "pureProfit": _num(f.pure_profit),
                    "totalAssets": _num(f.total_assets),
                    "employees": f.employees_number,
                },
            }
        return {"available": False, "summary": "暂无数据"}

    def _patent_distribution(self, pat_dao: PatentDAO, name_cn: str) -> list[dict[str, object]]:
        try:
            return pat_dao.count_by_cpc_section(name_cn)
        except Exception as exc:  # noqa: BLE001
            logger.warning("patent distribution failed: %s", exc)
            return []

    # ----- LLM 合成 + 降级 -----

    def _available_facts(self, facts: dict[str, dict[str, Any]]) -> dict[str, Any]:
        return {k: v.get("facts") for k, v in facts.items() if v.get("available")}

    def _synthesize_dimensions(self, llm: Any, facts: dict[str, dict[str, Any]]) -> dict[str, str]:
        avail = self._available_facts(facts)
        if not avail:
            return {}
        prompt = (
            "你是产业分析助手。根据以下企业背景结构化数据，为每个维度生成一句中文分析结论。"
            "只输出 JSON，键为维度名，值为结论字符串。\n"
            + json.dumps(avail, ensure_ascii=False, default=str)
        )
        text = llm.synthesize(prompt)
        if not text:
            return {}
        try:
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                data = json.loads(text[start : end + 1])
                return {k: str(v) for k, v in data.items()}
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("LLM conclusion parse failed: %s", exc)
        return {}

    def _synthesize_core_layout(self, llm: Any, facts: dict[str, dict[str, Any]]) -> str:
        avail = self._available_facts(facts)
        if not avail:
            return ""
        prompt = (
            "根据以下企业背景数据，用一段中文总结该企业的核心技术布局（不超过100字）。\n"
            + json.dumps(avail, ensure_ascii=False, default=str)
        )
        return llm.synthesize(prompt) or ""

    def _template_conclusion(self, dim: str, data: dict[str, Any]) -> str:
        f = data.get("facts", {}) or {}
        if dim == "industry_status":
            return f"{f.get('province') or ''}{f.get('city') or ''}企业，上市状态：{f.get('listingStatus') or '未知'}。"
        if dim == "core_tech":
            return f"主营产品：{f.get('mainProducts') or '未知'}，相关专利 {f.get('patentCount', 0)} 项。"
        if dim == "financial":
            return f"最近一期营业收入：{f.get('operatingRevenue') or '未知'}。"
        return ""

    def _template_core_layout(self, facts: dict[str, dict[str, Any]]) -> str:
        parts: list[str] = []
        ct = facts.get("core_tech")
        if ct and ct.get("available"):
            f = ct.get("facts", {}) or {}
            parts.append(
                f"核心技术围绕{f.get('mainProducts') or '主营产品'}，相关专利 {f.get('patentCount', 0)} 项"
            )
        return "；".join(parts) + "。" if parts else ""
