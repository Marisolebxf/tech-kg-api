"""机构域关系目录（复刻旧 organization_etl_common.RELATION_SPECS 的 32 条活跃 spec）。

与旧目录的差异（拆分设计文档声明的决策）：

- 不迁移 6 条永不执行的死配置：dwd_zh/en_project 的 PARTICIPATES_IN/FUNDED_BY
  （source_table 不在机构域表目录中）、dwd_org_industry_chain_dtl 的
  BELONGS_TO_NODE 与 dwd_org_industry_chain_prod_dtl 的 PRODUCES
  （产业链边由产业链域脚本承接）。
- person 端点 VID 统一为实体侧公式（见 resolvers.person_vid_for_row），
  修复旧关系侧 shareholder/executive 分支与实体点的分叉。
"""

from __future__ import annotations

from dataclasses import dataclass

EDGE_PROVENANCE: tuple[str, ...] = (
    "organization_id",
    "confidence",
    "source_table",
    "source_record_id",
    "ingest_batch",
    "ingest_time",
)


@dataclass(frozen=True)
class RelationEdgeSpec:
    key: str
    source_table: str
    edge_type: str
    target_tag: str
    scope: str
    extractor: str
    required_columns: tuple[str, ...]
    edge_properties: tuple[str, ...]
    numeric_properties: frozenset[str] = frozenset()
    source_record_fields: tuple[str, ...] = ()
    source_tags: tuple[str, ...] = ("Organization",)


RELATION_EDGE_SPECS: tuple[RelationEdgeSpec, ...] = (
    # --- LEGAL_REP_OF（3 表） ---
    RelationEdgeSpec(
        "legal_representative",
        "dwd_org_base_info",
        "LEGAL_REP_OF",
        "Organization",
        "domestic",
        "legal_representative",
        ("org_id", "lerep"),
        ("extra_json", *EDGE_PROVENANCE),
        source_record_fields=("org_id", "lerep"),
        source_tags=("Person",),
    ),
    RelationEdgeSpec(
        "legal_representative",
        "dwd_research_institute_base_info",
        "LEGAL_REP_OF",
        "Organization",
        "domestic",
        "legal_representative",
        ("org_id", "lerep"),
        ("extra_json", *EDGE_PROVENANCE),
        source_record_fields=("org_id", "lerep"),
        source_tags=("Person",),
    ),
    RelationEdgeSpec(
        "legal_representative",
        "dwd_special_taiwan_company",
        "LEGAL_REP_OF",
        "Organization",
        "domestic",
        "legal_representative",
        ("org_id", "legal_person"),
        ("extra_json", *EDGE_PROVENANCE),
        source_record_fields=("org_id", "legal_person"),
        source_tags=("Person",),
    ),
    # --- SHAREHOLDER_OF（2 表） ---
    RelationEdgeSpec(
        "shareholder",
        "dwd_org_shareholder_info",
        "SHAREHOLDER_OF",
        "Organization",
        "domestic",
        "domestic_shareholder",
        ("org_id", "inv_org_id", "owners_type", "ownership_percentage"),
        ("ownership_percentage", "extra_json", *EDGE_PROVENANCE),
        frozenset({"ownership_percentage"}),
        ("inv_org_id", "org_id", "owners_type"),
        ("Person", "Organization"),
    ),
    RelationEdgeSpec(
        "shareholder",
        "dwd_forg_shareholder_info",
        "SHAREHOLDER_OF",
        "Organization",
        "foreign",
        "foreign_shareholder",
        ("org_id", "owners_name", "ownership_percentage"),
        ("ownership_percentage", "extra_json", *EDGE_PROVENANCE),
        frozenset({"ownership_percentage"}),
        ("owners_name", "org_id"),
        ("Person", "Organization"),
    ),
    # --- EXECUTIVE_OF（2 表） ---
    RelationEdgeSpec(
        "executive",
        "dwd_org_executive_info",
        "EXECUTIVE_OF",
        "Organization",
        "domestic",
        "executive",
        ("org_id", "executives_name", "executives_position"),
        ("position", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("org_id", "executives_name", "executives_position"),
        source_tags=("Person",),
    ),
    RelationEdgeSpec(
        "executive",
        "dwd_forg_executive_info",
        "EXECUTIVE_OF",
        "Organization",
        "foreign",
        "executive",
        ("org_id", "executives_name", "executives_position"),
        ("position", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("org_id", "executives_name", "dm_birthdate"),
        source_tags=("Person",),
    ),
    # --- BENEFICIAL_OWNER_OF ---
    RelationEdgeSpec(
        "beneficial_owner",
        "dwd_forg_beneficiary_info",
        "BENEFICIAL_OWNER_OF",
        "Organization",
        "foreign",
        "beneficial_owner",
        ("org_id", "bo_name", "direct_percent", "indirect_percent", "total_percent"),
        (
            "direct_percent",
            "indirect_percent",
            "total_percent",
            "extra_json",
            *EDGE_PROVENANCE,
        ),
        frozenset({"direct_percent", "indirect_percent", "total_percent"}),
        ("org_id", "bo_name", "bo_birthdate"),
        ("Person",),
    ),
    # --- ACTUAL_CONTROLLER_OF ---
    RelationEdgeSpec(
        "actual_controller",
        "dwd_forg_act_contro_info",
        "ACTUAL_CONTROLLER_OF",
        "Organization",
        "foreign",
        "actual_controller",
        ("org_id", "entity_name", "entity_type", "direct_pct", "total_pct"),
        ("direct_pct", "total_pct", "extra_json", *EDGE_PROVENANCE),
        frozenset({"direct_pct", "total_pct"}),
        ("org_id", "entity_eid", "entity_name"),
        ("Person", "Organization"),
    ),
    # --- INVESTS_IN ---
    RelationEdgeSpec(
        "investment",
        "dwd_org_invest_info",
        "INVESTS_IN",
        "Organization",
        "domestic",
        "investment",
        ("org_id", "inv_org_id", "investment_amount", "investment_ratio"),
        ("investment_amount", "investment_ratio", "extra_json", *EDGE_PROVENANCE),
        frozenset({"investment_amount", "investment_ratio"}),
        ("org_id", "inv_org_id"),
    ),
    # --- ACQUIRES ---
    RelationEdgeSpec(
        "acquisition",
        "dwd_org_merger_acquisition_info",
        "ACQUIRES",
        "Organization",
        "domestic",
        "acquisition",
        ("acquiring_org_id", "acquired_org_id", "ma_amount", "currency_code"),
        ("ma_amount", "currency_code", "extra_json", *EDGE_PROVENANCE),
        frozenset({"ma_amount"}),
        ("acquiring_org_id", "acquired_org_id"),
    ),
    # --- SUBSIDIARY_OF ---
    RelationEdgeSpec(
        "subsidiary",
        "dwd_forg_subsidiary_info",
        "SUBSIDIARY_OF",
        "Organization",
        "foreign",
        "subsidiary",
        ("org_id", "affiliate", "affiliates_company_id", "affiliates_name"),
        ("extra_json", *EDGE_PROVENANCE),
        source_record_fields=("org_id", "affiliate", "affiliates_company_id", "affiliates_name"),
    ),
    # --- HAS_NEWS ---
    RelationEdgeSpec(
        "news",
        "dwd_org_important_news_info",
        "HAS_NEWS",
        "News",
        "domestic",
        "news",
        ("org_id", "news_title", "news_date", "news_content"),
        ("extra_json", *EDGE_PROVENANCE),
    ),
    # --- INVOLVED_IN（17 表，4 种 extractor） ---
    RelationEdgeSpec(
        "event",
        "dwd_org_annual_financial_info",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "event",
        ("org_id", "year"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("org_id", "year"),
    ),
    RelationEdgeSpec(
        "event",
        "dwd_org_stock_finance_info",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "event",
        ("org_id", "occur_period"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("org_id", "occur_period"),
    ),
    RelationEdgeSpec(
        "event",
        "dwd_forg_stock_fin_info",
        "INVOLVED_IN",
        "Event",
        "foreign",
        "event",
        ("org_id", "occur_period"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("org_id", "occur_period"),
    ),
    RelationEdgeSpec(
        "event",
        "dwd_org_changerecord_info",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "event",
        ("org_id", "update_date", "update_content"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("org_id", "update_date", "update_content"),
    ),
    RelationEdgeSpec(
        "event",
        "dwd_org_financing_info",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "event",
        ("org_id", "completion_date", "funding_round"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("org_id", "completion_date", "funding_round"),
    ),
    RelationEdgeSpec(
        "event",
        "dwd_org_recruit_info",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "event",
        ("org_id", "release_date", "job_title"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("org_id", "release_date", "job_title"),
    ),
    RelationEdgeSpec(
        "event",
        "dwd_org_company_abnormal",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "event",
        ("org_id", "abnormal_id"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("abnormal_id",),
    ),
    RelationEdgeSpec(
        "event",
        "dwd_org_company_punish",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "event",
        ("org_id", "penalty_id"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("penalty_id",),
    ),
    RelationEdgeSpec(
        "event",
        "dwd_org_company_illegal",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "event",
        ("org_id", "sv_id"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("sv_id",),
    ),
    RelationEdgeSpec(
        "event",
        "dwd_org_risk_tax_punish",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "event",
        ("org_id", "tax_vio_id"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("tax_vio_id",),
    ),
    RelationEdgeSpec(
        "event",
        "dwd_org_opt_judicial_case",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "event",
        ("org_id", "case_id"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("case_id",),
    ),
    RelationEdgeSpec(
        "event",
        "dwd_org_risk_shixin",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "event",
        ("org_id", "dishonest_id"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("dishonest_id",),
    ),
    RelationEdgeSpec(
        "event",
        "dwd_org_risk_zhixing",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "event",
        ("org_id", "exec_person_id"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("exec_person_id",),
    ),
    RelationEdgeSpec(
        "event",
        "dwd_org_bankruptcy_public_cases_list",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "bankruptcy_party",
        ("org_id", "case_no", "bankruptcy_party_id"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("bankruptcy_party_id",),
    ),
    RelationEdgeSpec(
        "event",
        "dwd_org_bankruptcy_public_cases",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "bankruptcy_admin",
        ("case_no", "admin_org"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("case_no", "admin_org_id", "admin_org"),
    ),
    RelationEdgeSpec(
        "event",
        "dwd_bid_win_candidate_out",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "bid_party",
        ("u_id", "org_id", "relate_type"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("u_id", "org_id", "ranking"),
    ),
    RelationEdgeSpec(
        "event",
        "dwd_bid_purchase_agency_out",
        "INVOLVED_IN",
        "Event",
        "domestic",
        "bid_party",
        ("u_id", "company_id", "relate_type"),
        ("role", "extra_json", *EDGE_PROVENANCE),
        source_record_fields=("u_id", "company_id", "relate_type"),
    ),
    # --- PRODUCES（活跃 2 条，经营信息表） ---
    RelationEdgeSpec(
        "product",
        "dwd_org_org_product_info",
        "PRODUCES",
        "Product",
        "domestic",
        "organization_product",
        ("org_id", "main_prod"),
        ("extra_json", *EDGE_PROVENANCE),
        source_record_fields=("org_id", "main_prod"),
    ),
    RelationEdgeSpec(
        "product",
        "dwd_forg_product_info",
        "PRODUCES",
        "Product",
        "foreign",
        "organization_product",
        ("org_id", "main_products"),
        ("extra_json", *EDGE_PROVENANCE),
        source_record_fields=("org_id", "main_products"),
    ),
)

assert len(RELATION_EDGE_SPECS) == 32

SPECS_BY_KEY: dict[str, tuple[RelationEdgeSpec, ...]] = {}
for _spec in RELATION_EDGE_SPECS:
    SPECS_BY_KEY[_spec.key] = SPECS_BY_KEY.get(_spec.key, ()) + (_spec,)

RELATION_KEYS: tuple[str, ...] = tuple(SPECS_BY_KEY)
