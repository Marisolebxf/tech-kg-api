"""机构域源表目录（复刻旧 organization_etl_common.DOMAIN_TABLE_SPECS）。

新脚本按"一实体一脚本"组织，但机构域各实体共享这份表目录：表名、中文名、
实体类型、语义 kind、复合稳定键（raw_id_fields）与旧脚本逐一对应。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OrgTableSpec:
    name: str
    cn_name: str
    scope: str  # domestic / foreign
    entity_tag: str | None  # Organization / Person / Event / News / None
    entity_kind: str
    raw_id_fields: tuple[str, ...] = ()


ORG_TABLE_SPECS: tuple[OrgTableSpec, ...] = (
    OrgTableSpec("dwd_org_base_info", "机构基本信息", "domestic", "Organization", "organization"),
    OrgTableSpec(
        "dwd_org_shareholder_info", "国内机构股东信息", "domestic", "Person", "shareholder"
    ),
    OrgTableSpec("dwd_org_executive_info", "国内机构高管信息", "domestic", "Person", "executive"),
    OrgTableSpec(
        "dwd_org_org_product_info",
        "国内机构经营信息",
        "domestic",
        "Organization",
        "organization_enrichment",
    ),
    OrgTableSpec(
        "dwd_org_annual_financial_info",
        "年报财务信息",
        "domestic",
        "Event",
        "annual_finance",
        ("org_id", "year"),
    ),
    OrgTableSpec("dwd_org_important_news_info", "重点资讯", "domestic", "News", "news"),
    OrgTableSpec(
        "dwd_org_changerecord_info",
        "工商变更",
        "domestic",
        "Event",
        "change_record",
        ("org_id", "update_date", "update_content"),
    ),
    OrgTableSpec("dwd_org_merger_acquisition_info", "并购事件", "domestic", None, "relation"),
    OrgTableSpec(
        "dwd_org_financing_info",
        "融资事件",
        "domestic",
        "Event",
        "financing",
        ("org_id", "completion_date", "funding_round"),
    ),
    OrgTableSpec("dwd_org_invest_info", "投资事件", "domestic", None, "relation"),
    OrgTableSpec(
        "dwd_org_recruit_info",
        "招聘信息",
        "domestic",
        "Event",
        "recruit",
        ("org_id", "release_date", "job_title"),
    ),
    OrgTableSpec("dwd_org_heis_info", "高校基本信息", "domestic", "Organization", "organization"),
    OrgTableSpec(
        "dwd_org_stock_base",
        "上市企业基本信息",
        "domestic",
        "Organization",
        "organization_enrichment",
    ),
    OrgTableSpec(
        "dwd_org_stock_finance_info",
        "上市企业财务信息",
        "domestic",
        "Event",
        "stock_finance",
        ("org_id", "occur_period"),
    ),
    OrgTableSpec(
        "dwd_org_company_abnormal", "经营异常", "domestic", "Event", "abnormal", ("abnormal_id",)
    ),
    OrgTableSpec(
        "dwd_org_company_punish", "行政处罚", "domestic", "Event", "punish", ("penalty_id",)
    ),
    OrgTableSpec("dwd_org_company_illegal", "严重违法", "domestic", "Event", "illegal", ("sv_id",)),
    OrgTableSpec(
        "dwd_org_risk_tax_punish", "税收违法", "domestic", "Event", "tax_punish", ("tax_vio_id",)
    ),
    OrgTableSpec(
        "dwd_org_opt_judicial_case", "司法案件", "domestic", "Event", "judicial_case", ("case_id",)
    ),
    OrgTableSpec(
        "dwd_org_risk_shixin", "失信被执行人", "domestic", "Event", "shixin", ("dishonest_id",)
    ),
    OrgTableSpec(
        "dwd_org_risk_zhixing", "被执行人", "domestic", "Event", "zhixing", ("exec_person_id",)
    ),
    OrgTableSpec(
        "dwd_org_bankruptcy_public_cases",
        "破产案件",
        "domestic",
        "Event",
        "bankruptcy",
        ("case_no",),
    ),
    OrgTableSpec(
        "dwd_org_bankruptcy_public_cases_list", "破产案件当事人", "domestic", None, "relation"
    ),
    OrgTableSpec(
        "dwd_special_hongkong_company", "香港企业", "domestic", "Organization", "organization"
    ),
    OrgTableSpec(
        "dwd_special_taiwan_company", "台湾企业", "domestic", "Organization", "organization"
    ),
    OrgTableSpec(
        "dwd_special_aomen_company", "澳门企业", "domestic", "Organization", "organization"
    ),
    OrgTableSpec("dwd_bid_base_out", "招投标公告", "domestic", "Event", "bid", ("u_id",)),
    OrgTableSpec("dwd_bid_win_candidate_out", "中标候选人", "domestic", None, "relation"),
    OrgTableSpec("dwd_bid_purchase_agency_out", "采购代理", "domestic", None, "relation"),
    OrgTableSpec(
        "dwd_bid_target_item_out",
        "招投标标的物",
        "domestic",
        "Event",
        "bid_item",
        ("u_id", "target_item_name", "bid_section_number"),
    ),
    OrgTableSpec(
        "dwd_research_institute_base_info",
        "科研机构基本信息",
        "domestic",
        "Organization",
        "organization",
    ),
    OrgTableSpec(
        "dwd_forg_base_info", "海外机构基本信息", "foreign", "Organization", "organization"
    ),
    OrgTableSpec("dwd_forg_shareholder_info", "海外机构股东信息", "foreign", None, "relation"),
    OrgTableSpec("dwd_forg_subsidiary_info", "海外机构子公司", "foreign", None, "relation"),
    OrgTableSpec("dwd_forg_executive_info", "海外机构高管信息", "foreign", "Person", "executive"),
    OrgTableSpec(
        "dwd_forg_product_info",
        "海外机构经营信息",
        "foreign",
        "Organization",
        "organization_enrichment",
    ),
    OrgTableSpec(
        "dwd_forg_beneficiary_info", "海外机构受益人", "foreign", "Person", "beneficial_owner"
    ),
    OrgTableSpec(
        "dwd_forg_act_contro_info", "海外机构实际控制人", "foreign", "Person", "actual_controller"
    ),
    OrgTableSpec(
        "dwd_forg_stock_fin_info",
        "海外上市企业财务信息",
        "foreign",
        "Event",
        "stock_finance",
        ("org_id", "occur_period"),
    ),
)

SPEC_BY_NAME: dict[str, OrgTableSpec] = {spec.name: spec for spec in ORG_TABLE_SPECS}

TABLE_CN_NAMES: dict[str, str] = {spec.name: spec.cn_name for spec in ORG_TABLE_SPECS}
assert len(TABLE_CN_NAMES) == 39

ORGANIZATION_TABLES: tuple[str, ...] = tuple(
    spec.name for spec in ORG_TABLE_SPECS if spec.entity_tag == "Organization"
)
PERSON_TABLES: tuple[str, ...] = tuple(
    spec.name for spec in ORG_TABLE_SPECS if spec.entity_tag == "Person"
)
EVENT_TABLES: tuple[str, ...] = tuple(
    spec.name for spec in ORG_TABLE_SPECS if spec.entity_tag == "Event"
)
NEWS_TABLES: tuple[str, ...] = tuple(
    spec.name for spec in ORG_TABLE_SPECS if spec.entity_tag == "News"
)

# 复刻旧 organization_kind：org_kind 语义枚举按来源表映射。
ORGANIZATION_KIND_BY_TABLE: dict[str, str] = {
    "dwd_org_heis_info": "domestic_university",
    "dwd_research_institute_base_info": "domestic_research_institute",
    "dwd_special_hongkong_company": "hong_kong_company",
    "dwd_special_taiwan_company": "taiwan_company",
    "dwd_special_aomen_company": "macao_company",
    "dwd_forg_base_info": "foreign_organization",
    "dwd_forg_product_info": "foreign_organization",
}


def organization_kind(table: str) -> str:
    return ORGANIZATION_KIND_BY_TABLE.get(table, "domestic_organization")
