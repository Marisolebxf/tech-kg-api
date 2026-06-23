"""Entity binding service — data recall → rule matching → LLM refinement → write binding edges.

Orchestrates the full entity binding pipeline using:
- BindingMatcher for rule-based candidate recall
- ZhipuAI GLM for LLM-based refinement / verification
- GraphDatabase for reading source nodes and writing binding edges
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

from dotenv import load_dotenv

from app.schemas.entity_binding import (
    BindingGraphResponse,
    BindingPairDetail,
    BindingResult,
    BindingStatsResponse,
    ClearResponse,
    ExpertRelationDemoResponse,
    ExpertRelationGraph,
    ExpertRelationGraphEdge,
    ExpertRelationGraphNode,
    ExpertRelationScenario,
    InitDataResponse,
)
from app.services.binding_matcher import BindingMatcher
from app.services.semantic_matcher import SemanticMatcher
from graph_db.base import GraphDatabase

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM setup — same pattern as entity_extractor.py
# ---------------------------------------------------------------------------

try:
    from zai import ZhipuAiClient
except ImportError:  # pragma: no cover - SDK may be absent
    ZhipuAiClient = None

load_dotenv()

_API_KEY = os.getenv("ZHIPUAI_API_KEY", "")
_BINDING_MODEL = os.getenv("BINDING_MODEL", "glm-4-flash")

_llm_client = ZhipuAiClient(api_key=_API_KEY) if ZhipuAiClient and _API_KEY else None

# ---------------------------------------------------------------------------
# Test data constants
# ---------------------------------------------------------------------------

TALENT_DATA: list[dict[str, Any]] = [
    {
        "id": "talent_001",
        "scholar_id": "talent_001",
        "name_zh": "张伟",
        "name_en": "Wei Zhang",
        "scholar_org_name_zh": "清华大学",
        "scholar_org_name_en": "Tsinghua University",
        "fields": "知识图谱",
        "paper_nums": 35,
        "citation_nums": 1200,
        "h_index": 12,
        "status": 1,
    },
    {
        "id": "talent_002",
        "scholar_id": "talent_002",
        "name_zh": "李明",
        "name_en": "Ming Li",
        "scholar_org_name_zh": "北京大学",
        "scholar_org_name_en": "Peking University",
        "fields": "自然语言处理",
        "paper_nums": 28,
        "citation_nums": 890,
        "h_index": 10,
        "status": 1,
    },
    {
        "id": "talent_003",
        "scholar_id": "talent_003",
        "name_zh": "王芳",
        "name_en": "Fang Wang",
        "scholar_org_name_zh": "浙江大学",
        "scholar_org_name_en": "Zhejiang University",
        "fields": "计算机视觉",
        "paper_nums": 22,
        "citation_nums": 560,
        "h_index": 8,
        "status": 1,
    },
    {
        "id": "talent_004",
        "scholar_id": "talent_004",
        "name_zh": "刘洋",
        "name_en": "Yang Liu",
        "scholar_org_name_zh": "清华大学",
        "scholar_org_name_en": "Tsinghua University",
        "fields": "机器学习",
        "paper_nums": 40,
        "citation_nums": 2100,
        "h_index": 15,
        "status": 1,
    },
    {
        "id": "talent_005",
        "scholar_id": "talent_005",
        "name_zh": "陈静",
        "name_en": "Jing Chen",
        "scholar_org_name_zh": "复旦大学",
        "scholar_org_name_en": "Fudan University",
        "fields": "数据挖掘",
        "paper_nums": 18,
        "citation_nums": 430,
        "h_index": 7,
        "status": 1,
    },
    {
        "id": "talent_006",
        "scholar_id": "talent_006",
        "name_zh": "赵晨",
        "name_en": "Chen Zhao",
        "scholar_org_name_zh": "清华大学",
        "scholar_org_name_en": "Tsinghua University",
        "fields": "知识图谱",
        "paper_nums": 26,
        "citation_nums": 760,
        "h_index": 9,
        "status": 1,
    },
    {
        "id": "talent_007",
        "scholar_id": "talent_007",
        "name_zh": "孙睿",
        "name_en": "Rui Sun",
        "scholar_org_name_zh": "北京大学",
        "scholar_org_name_en": "Peking University",
        "fields": "自然语言处理",
        "paper_nums": 24,
        "citation_nums": 680,
        "h_index": 9,
        "status": 1,
    },
    {
        "id": "talent_008",
        "scholar_id": "talent_008",
        "name_zh": "高原",
        "name_en": "Yuan Gao",
        "scholar_org_name_zh": "浙江大学",
        "scholar_org_name_en": "Zhejiang University",
        "fields": "计算机视觉",
        "paper_nums": 21,
        "citation_nums": 540,
        "h_index": 8,
        "status": 1,
    },
    {
        "id": "talent_009",
        "scholar_id": "talent_009",
        "name_zh": "何涛",
        "name_en": "Tao He",
        "scholar_org_name_zh": "清华大学",
        "scholar_org_name_en": "Tsinghua University",
        "fields": "机器学习",
        "paper_nums": 31,
        "citation_nums": 990,
        "h_index": 11,
        "status": 1,
    },
]

PAPER_DATA: list[dict[str, Any]] = [
    {
        "id": "paper_001",
        "paper_id": "paper_001",
        "zh_name": "基于知识图谱的实体对齐方法研究",
        "en_name": "Entity Alignment in Knowledge Graphs",
        "authors": "张伟",
        "author_id": "auth_001",
        "institution": "清华大学",
        "cover_date_start": "2024-03-15",
        "keywords": "知识图谱;实体对齐",
        "doi": "10.1234/kg001",
    },
    {
        "id": "paper_002",
        "paper_id": "paper_002",
        "zh_name": "NLP前沿技术综述",
        "en_name": "Advances in NLP",
        "authors": "李明",
        "author_id": "auth_002",
        "institution": "北京大学",
        "cover_date_start": "2024-05-20",
        "keywords": "自然语言处理;深度学习",
        "doi": "10.1234/nlp002",
    },
    {
        "id": "paper_003",
        "paper_id": "paper_003",
        "zh_name": "深度学习在CV中的应用",
        "en_name": "Deep Learning for Computer Vision",
        "authors": "王芳",
        "author_id": "auth_003",
        "institution": "浙大",
        "cover_date_start": "2024-01-10",
        "keywords": "计算机视觉;深度学习",
        "doi": "10.1234/cv003",
    },
    {
        "id": "paper_004",
        "paper_id": "paper_004",
        "zh_name": "机器学习优化方法研究",
        "en_name": "Optimization Methods in ML",
        "authors": "刘洋",
        "author_id": "auth_004",
        "institution": "清华大学计算机系",
        "cover_date_start": "2023-11-08",
        "keywords": "机器学习;优化算法",
        "doi": "10.1234/ml004",
    },
    {
        "id": "paper_005",
        "paper_id": "paper_005",
        "zh_name": "知识图谱构建技术研究",
        "en_name": "Knowledge Graph Construction",
        "authors": "张伟",
        "author_id": "auth_005",
        "institution": "Tsinghua University",
        "cover_date_start": "2024-06-01",
        "keywords": "知识图谱;图构建",
        "doi": "10.1234/kg005",
    },
    {
        "id": "paper_006",
        "paper_id": "paper_006",
        "zh_name": "数据挖掘方法综述",
        "en_name": "Data Mining Survey",
        "authors": "陈静",
        "author_id": "auth_006",
        "institution": "复旦大学",
        "cover_date_start": "2023-09-15",
        "keywords": "数据挖掘;机器学习",
        "doi": "10.1234/dm006",
    },
    {
        "id": "paper_007",
        "paper_id": "paper_007",
        "zh_name": "知识图谱推理方法研究",
        "en_name": "Knowledge Graph Reasoning Methods",
        "authors": "赵晨",
        "author_id": "auth_007",
        "institution": "清华大学",
        "cover_date_start": "2024-02-18",
        "keywords": "知识图谱;推理",
        "doi": "10.1234/kg007",
    },
    {
        "id": "paper_008",
        "paper_id": "paper_008",
        "zh_name": "大模型驱动的自然语言处理应用",
        "en_name": "LLM for NLP Applications",
        "authors": "孙睿",
        "author_id": "auth_008",
        "institution": "北京大学",
        "cover_date_start": "2024-04-12",
        "keywords": "自然语言处理;大模型",
        "doi": "10.1234/nlp008",
    },
    {
        "id": "paper_009",
        "paper_id": "paper_009",
        "zh_name": "多模态视觉理解综述",
        "en_name": "Multimodal Vision Understanding",
        "authors": "高原",
        "author_id": "auth_009",
        "institution": "浙江大学",
        "cover_date_start": "2024-03-26",
        "keywords": "计算机视觉;多模态",
        "doi": "10.1234/cv009",
    },
    {
        "id": "paper_010",
        "paper_id": "paper_010",
        "zh_name": "机器学习系统优化实践",
        "en_name": "Machine Learning System Optimization",
        "authors": "何涛",
        "author_id": "auth_010",
        "institution": "清华大学",
        "cover_date_start": "2024-05-30",
        "keywords": "机器学习;系统优化",
        "doi": "10.1234/ml010",
    },
]

PATENT_DATA: list[dict[str, Any]] = [
    {
        "patent_id": "patent_001",
        "title_zh": "知识图谱构建方法",
        "first_inventor_name": "张伟",
        "first_applicant_name": "清华大学",
        "country": "CN",
        "classification_ipcr": "G06F16.36",
        "keywords": "知识图谱;图数据库",
    },
    {
        "patent_id": "patent_002",
        "title_zh": "自然语言处理装置",
        "first_inventor_name": "李明",
        "first_applicant_name": "北京大学",
        "country": "CN",
        "classification_ipcr": "G06F40.30",
        "keywords": "自然语言处理;语义分析",
    },
    {
        "patent_id": "patent_003",
        "title_zh": "图像识别系统",
        "first_inventor_name": "王芳",
        "first_applicant_name": "浙江大学",
        "country": "CN",
        "classification_ipcr": "G06V10.00",
        "keywords": "计算机视觉;图像识别",
    },
    {
        "patent_id": "patent_004",
        "title_zh": "智能推荐算法",
        "first_inventor_name": "赵磊",
        "first_applicant_name": "中科院",
        "country": "CN",
        "classification_ipcr": "G06F16.95",
        "keywords": "推荐系统;协同过滤",
    },
    {
        "patent_id": "patent_005",
        "title_zh": "知识图谱推理系统",
        "first_inventor_name": "赵晨",
        "first_applicant_name": "清华大学",
        "country": "CN",
        "classification_ipcr": "G06F16.35",
        "keywords": "知识图谱;推理",
    },
    {
        "patent_id": "patent_006",
        "title_zh": "自然语言处理训练装置",
        "first_inventor_name": "孙睿",
        "first_applicant_name": "北京大学",
        "country": "CN",
        "classification_ipcr": "G06F40.20",
        "keywords": "自然语言处理;大模型",
    },
    {
        "patent_id": "patent_007",
        "title_zh": "视觉分析方法",
        "first_inventor_name": "高原",
        "first_applicant_name": "浙江大学",
        "country": "CN",
        "classification_ipcr": "G06V20.10",
        "keywords": "计算机视觉;视觉分析",
    },
    {
        "patent_id": "patent_008",
        "title_zh": "机器学习训练平台",
        "first_inventor_name": "何涛",
        "first_applicant_name": "清华大学",
        "country": "CN",
        "classification_ipcr": "G06N20.00",
        "keywords": "机器学习;训练平台",
    },
]

ORG_DATA: list[dict[str, Any]] = [
    {
        "org_id": "org_001",
        "name_cn": "清华大学",
        "province": "北京市",
        "city": "北京",
        "org_type": "高等院校",
    },
    {
        "org_id": "org_002",
        "name_cn": "北京大学",
        "province": "北京市",
        "city": "北京",
        "org_type": "高等院校",
    },
    {
        "org_id": "org_003",
        "name_cn": "浙江大学",
        "province": "浙江省",
        "city": "杭州",
        "org_type": "高等院校",
    },
    {
        "org_id": "org_004",
        "name_cn": "清华大学计算机系",
        "province": "北京市",
        "city": "北京",
        "org_type": "院系",
    },
]

EXPERT_DIRECT_RELATION_FALLBACK_DATA: list[dict[str, Any]] = [
    {
        "key": "expert-fallback-01",
        "label": "科技专家直接关系（张明远 / 李佳宁）",
        "last_test_time": "2026-07-23 11:00:00",
        "expert_a": {"id": "fallback_zhangmingyuan", "name": "张明远", "title": "研究员"},
        "expert_b": {"id": "fallback_lijianing", "name": "李佳宁", "title": "副研究员"},
        "relation_type": "直接关系",
        "institution": "中国科学院自动化研究所",
        "directions": ["知识图谱", "机器学习"],
        "duration": "",
        "achievements": [],
        "api_example": {
            "relation_type": "expert_direct_relation",
            "relation_subtype": "direct",
            "expert_a": {"name": "张明远", "title": "研究员"},
            "expert_b": {"name": "李佳宁", "title": "副研究员"},
            "institution": "中国科学院自动化研究所",
            "reasons": ["同机构", "共论文"],
            "relation_strength": 82,
            "relation_summary": "同机构 + 共论文",
        },
    },
    {
        "key": "expert-fallback-02",
        "label": "科技专家直接关系（李佳宁 / 周欣怡）",
        "last_test_time": "2026-07-23 11:10:00",
        "expert_a": {"id": "fallback_lijianing", "name": "李佳宁", "title": "副研究员"},
        "expert_b": {"id": "fallback_zhouxinyi", "name": "周欣怡", "title": "教授"},
        "relation_type": "直接关系",
        "institution": "智能决策联合实验室",
        "directions": ["智能决策", "知识工程"],
        "duration": "",
        "achievements": [],
        "api_example": {
            "relation_type": "expert_direct_relation",
            "relation_subtype": "direct",
            "expert_a": {"name": "李佳宁", "title": "副研究员"},
            "expert_b": {"name": "周欣怡", "title": "教授"},
            "institution": "智能决策联合实验室",
            "reasons": ["共项目", "Co-Author"],
            "relation_strength": 79,
            "relation_summary": "共项目 + Co-Author",
        },
    },
    {
        "key": "expert-fallback-03",
        "label": "科技专家直接关系（周欣怡 / 赵文博）",
        "last_test_time": "2026-08-01 15:40:00",
        "expert_a": {"id": "fallback_zhouxinyi", "name": "周欣怡", "title": "教授"},
        "expert_b": {"id": "fallback_zhaowenbo", "name": "赵文博", "title": "副教授"},
        "relation_type": "直接关系",
        "institution": "北京航空航天大学计算机学院",
        "directions": ["智能决策", "大模型"],
        "duration": "",
        "achievements": [],
        "api_example": {
            "relation_type": "expert_direct_relation",
            "relation_subtype": "direct",
            "expert_a": {"name": "周欣怡", "title": "教授"},
            "expert_b": {"name": "赵文博", "title": "副教授"},
            "institution": "北京航空航天大学计算机学院",
            "reasons": ["同机构", "共专利", "共论文"],
            "relation_strength": 91,
            "relation_summary": "同机构 + 共专利 + 共论文",
        },
    },
    {
        "key": "expert-fallback-04",
        "label": "科技专家直接关系（赵文博 / 陈星宇）",
        "last_test_time": "2026-08-05 10:20:00",
        "expert_a": {"id": "fallback_zhaowenbo", "name": "赵文博", "title": "副教授"},
        "expert_b": {"id": "fallback_chenxingyu", "name": "陈星宇", "title": "研究员"},
        "relation_type": "直接关系",
        "institution": "清华大学智能产业研究院",
        "directions": ["大模型", "产业智能"],
        "duration": "",
        "achievements": [],
        "api_example": {
            "relation_type": "expert_direct_relation",
            "relation_subtype": "direct",
            "expert_a": {"name": "赵文博", "title": "副教授"},
            "expert_b": {"name": "陈星宇", "title": "研究员"},
            "institution": "清华大学智能产业研究院",
            "reasons": ["共项目", "共论文"],
            "relation_strength": 84,
            "relation_summary": "共项目 + 共论文",
        },
    },
    {
        "key": "expert-fallback-05",
        "label": "科技专家直接关系（陈星宇 / 刘成）",
        "last_test_time": "2026-08-09 09:15:00",
        "expert_a": {"id": "fallback_chenxingyu", "name": "陈星宇", "title": "研究员"},
        "expert_b": {"id": "fallback_liucheng", "name": "刘成", "title": "高级工程师"},
        "relation_type": "直接关系",
        "institution": "国家智能计算实验室",
        "directions": ["算力调度", "智能计算"],
        "duration": "",
        "achievements": [],
        "api_example": {
            "relation_type": "expert_direct_relation",
            "relation_subtype": "direct",
            "expert_a": {"name": "陈星宇", "title": "研究员"},
            "expert_b": {"name": "刘成", "title": "高级工程师"},
            "institution": "国家智能计算实验室",
            "reasons": ["Co-Author", "共专利"],
            "relation_strength": 80,
            "relation_summary": "Co-Author + 共专利",
        },
    },
    {
        "key": "expert-fallback-06",
        "label": "科技专家直接关系（刘成 / 张明远）",
        "last_test_time": "2026-08-12 14:00:00",
        "expert_a": {"id": "fallback_liucheng", "name": "刘成", "title": "高级工程师"},
        "expert_b": {"id": "fallback_zhangmingyuan", "name": "张明远", "title": "研究员"},
        "relation_type": "直接关系",
        "institution": "国家智能计算实验室",
        "directions": ["智能计算", "知识图谱"],
        "duration": "",
        "achievements": [],
        "api_example": {
            "relation_type": "expert_direct_relation",
            "relation_subtype": "direct",
            "expert_a": {"name": "刘成", "title": "高级工程师"},
            "expert_b": {"name": "张明远", "title": "研究员"},
            "institution": "国家智能计算实验室",
            "reasons": ["共项目", "同机构"],
            "relation_strength": 78,
            "relation_summary": "共项目 + 同机构",
        },
    },
]

# ---------------------------------------------------------------------------
# nGQL constants for edge types and indexes
# ---------------------------------------------------------------------------

# Valid property names per NebulaGraph tag (from DESCRIBE TAG)
VALID_TAG_PROPS: dict[str, set[str]] = {
    "talent": {
        "scholar_id", "name_en", "name_zh", "avatar", "scholar_org_name_en",
        "scholar_org_name_zh", "bio", "bio_zh", "work_experience_en",
        "work_experience_zh", "education_background_en", "education_background_zh",
        "paper_nums", "citation_nums", "h_index", "status", "title", "create_time",
        "update_time", "academician", "fields",
        # Paper-related fields embedded in talent TAG
        "paper_id", "year", "citations", "publish_time", "publication_id",
        "related_paper_id", "zh_name", "en_name", "authors", "paper_url",
        "cover_date_start", "zh_abstract", "en_abstract", "doi",
        "publication_en_name",
        # Co-author fields
        "co_scholar_id", "co_scholar_name_en", "co_scholar_name_zh",
        "co_scholar_avatar", "co_scholar_org_name_en", "co_scholar_org_name_zh",
        "co_paper_count",
    },
    "cn_paper": {
        "id", "doi", "en_name", "zh_name", "publication_id", "paper_type",
        "publication_type", "publication_zh_name", "issn", "volume", "issue",
        "first_page", "last_page", "cover_year_start", "cover_date_start",
        "language_classify", "abstract_available", "open_access", "paper_url",
        "data_source", "created_time", "updated_time", "logic_id",
        "title_sequence", "language_code", "language", "original_title",
        "abstract_sequence", "original_abstract", "en_abstract", "zh_abstract",
        "paper_id", "author_sequence", "author_id", "email", "correspond",
        "institution", "affiliation", "country", "name_abbr", "iscn",
        "eissn", "founding_time", "jn_official", "zh_description", "format",
        "postal_code", "chief_editor", "organizer", "publisher_place",
        "award", "cite_nums", "annual_publication", "review", "impact_factor",
        "sub_quartile", "classify_list", "warning", "is_sci",
        "publication_cycle", "paper_nums", "scope", "scope_zone", "keywords",
        "relevant", "authors",
    },
    "patent": {
        "id", "patent_id", "publication_number", "application_kind",
        "country_code", "country", "publication_reference",
        "application_reference", "pct_or_regional_filing_data",
        "pct_or_regional_publishing_data", "priority_filings", "applicants",
        "assignees", "inventors", "first_applicant_name",
        "first_current_assignee_name", "first_inventor_name",
        "classification_ipcr", "classification_cpc", "keywords",
        "claims_localized", "description_localized", "figures", "language",
        "granted_number", "spif_application_number", "spif_publication_number",
        "prior_art_year", "prior_art_date", "relevants", "db_source",
        "create_time", "update_time", "reference_cited", "cited_by_nums",
        "cited_by", "patent_citations", "non_patent_citations",
        "title_localized", "title_zh", "abstract_localized", "abstract_zh",
        "dates_of_public_availability", "status", "legal_events",
        "patent_legal_prs_data", "anticipated_expiration", "expiration_year",
        "transfer_effective_date", "transferor_sequence", "transferor_name",
        "transferee_sequence", "transferee_name", "simple_family",
        "family_citations", "cited_by_family", "other_versions", "worldwides",
    },
    "cn_organization": {
        "org_id", "name_cn", "external_id", "province", "city", "address",
        "addr_lng", "addr_lat", "postal_code", "phone", "email", "lerep",
        "org_type", "org_size", "registration_org", "incorporation_year",
        "incorporation_date", "start_date", "end_date", "listing_status",
        "listing_date", "registered_capital_value", "capital_currency_code",
        "data_source", "created_time", "updated_time", "inv_org_id",
        "owners_name", "owners_type", "ownership_percentage",
        "executives_name", "executives_position", "industry_class",
        "main_activities", "description", "main_prod", "year", "total_assets",
        "total_liabilities", "operating_revenue", "main_business_revenue",
        "total_profit", "pure_profit", "total_tax_paid", "owners_equity",
        "employees_number", "news_title", "news_date", "news_content",
        "original_textlink", "update_content", "current_name", "update_name",
        "update_date", "acquiring_org_id", "acquiring_name",
        "acquired_org_id", "acquired_name", "ma_amount", "currency_code",
        "funding_round", "funding_amount", "funding_currency_code",
        "post_valuation", "completion_date", "investors_name",
        "org_name", "org_name_en", "org_desc", "est_year", "univ_type",
        "web_link", "contact_number", "fax_number", "org_tag", "tag_level",
        "stock_code", "stock_noun", "stock_type", "listed_date",
        "listed_status", "status",
    },
}


def _filter_props(tag: str, props: dict[str, Any]) -> dict[str, Any]:
    """Return only properties that exist in the NebulaGraph tag schema."""
    valid = VALID_TAG_PROPS.get(tag, set())
    if not valid:
        return props
    return {k: v for k, v in props.items() if k in valid}

EDGE_NGQLS: dict[str, str] = {
    "bind_talent_paper_author": (
        "CREATE EDGE IF NOT EXISTS bind_talent_paper_author"
        "(confidence double, method string, bound_at string, rule_score double, llm_score double, status string)"
    ),
    "bind_talent_patent_inventor": (
        "CREATE EDGE IF NOT EXISTS bind_talent_patent_inventor"
        "(confidence double, method string, bound_at string, rule_score double, llm_score double, status string)"
    ),
    "bind_org_org": (
        "CREATE EDGE IF NOT EXISTS bind_org_org"
        "(confidence double, method string, bound_at string, rule_score double, llm_score double, status string)"
    ),
}

INDEX_NGQLS: list[str] = []  # Index creation handled via Java service createIndex API

# nGQL to add missing demo fields to existing tags
ALTER_TAG_NGQLS: list[str] = [
    "ALTER TAG talent ADD (title string DEFAULT \"\")",
    "ALTER TAG cn_paper ADD (authors string DEFAULT \"\")",
]

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _summarize_entity(entity: dict[str, Any], label: str) -> str:
    """Create a human-readable description of an entity for LLM prompt."""
    parts = [f"类型: {label}"]
    for key, val in entity.items():
        if val is not None and str(val).strip():
            parts.append(f"{key}: {val}")
    return "; ".join(parts)


def _llm_judge(
    entity_a_desc: str,
    entity_b_desc: str,
    source_db: str = "学者库",
    target_db: str = "论文库",
) -> Optional[dict[str, Any]]:
    """Ask LLM to judge whether two entity descriptions refer to the same real-world entity.

    Returns {"is_same": bool, "confidence": float, "reason": str} or None on failure.
    """
    if _llm_client is None:
        return None

    prompt = f"""你是实体对齐专家。请判断以下两个来自不同数据源的实体是否指向同一个现实世界实体。

【数据源A】{source_db}
{entity_a_desc}

【数据源B】{target_db}
{entity_b_desc}

请严格按照以下JSON格式输出，不要输出任何其他内容：
{{"is_same": true/false, "confidence": 0.0-1.0, "reason": "判断理由"}}

判断要点：
1. 姓名是否完全一致或为同一人的不同拼写
2. 所属机构是否相同或存在包含关系
3. 研究领域是否高度重叠
4. 注意机构名称的简称/全称差异（如"浙大"="浙江大学"）
5. confidence范围0-1，1表示完全确信"""

    try:
        resp = _llm_client.chat.completions.create(
            model=_BINDING_MODEL,
            messages=[
                {"role": "system", "content": "你是实体对齐专家，只输出JSON，不输出任何解释。"},
                {"role": "user", "content": prompt},
            ],
        )
        raw = resp.choices[0].message.content.strip()
        # Remove possible markdown code block wrapping
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        result = json.loads(raw)

        # Validate required keys
        if "is_same" in result and "confidence" in result:
            return {
                "is_same": bool(result["is_same"]),
                "confidence": float(result["confidence"]),
                "reason": str(result.get("reason", "")),
            }
        return None

    except json.JSONDecodeError as e:
        logger.warning("LLM judge JSON parse failed: %s", e)
        return None
    except Exception as e:
        logger.warning("LLM judge call failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# EntityBindingService
# ---------------------------------------------------------------------------


def _chunked(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


class EntityBindingService:
    """Core binding service: recall → rule matching → LLM refinement → write edges."""

    TALENT_PAPER_SEMANTIC_FALLBACK = 0.78
    TALENT_PATENT_SEMANTIC_FALLBACK = 0.8
    ORG_ORG_SEMANTIC_FALLBACK = 0.82
    INITIAL_CANDIDATE_CONFIDENCE = 0.35

    BINDING_EDGE_MAP = {
        "talent_paper": "bind_talent_paper_author",
        "talent_patent": "bind_talent_patent_inventor",
        "org_org": "bind_org_org",
    }

    SOURCE_LABEL_MAP = {
        "talent_paper": "talent",
        "talent_patent": "talent",
        "org_org": "cn_organization",
    }

    TARGET_LABEL_MAP = {
        "talent_paper": "cn_paper",
        "talent_patent": "patent",
        "org_org": "cn_organization",
    }

    def __init__(self, db: GraphDatabase):
        self.db = db
        self.matcher = BindingMatcher()
        self.semantic_matcher = SemanticMatcher()

    @staticmethod
    def _graph_batch_size() -> int:
        return max(1, int(os.getenv("GRAPH_BATCH_SIZE", "200")))

    def _batch_create_nodes(self, label: str, nodes: list[dict[str, Any]], vid_getter) -> int:
        if not nodes:
            return 0
        batch_size = self._graph_batch_size()
        written = 0
        for chunk in _chunked(nodes, batch_size):
            try:
                self.db.batch_create_nodes(chunk, [label])
                written += len(chunk)
            except Exception as exc:
                logger.warning("Batch create nodes failed for %s, falling back to merge loop: %s", label, exc)
                for node in chunk:
                    try:
                        vid = str(vid_getter(node))
                        self.db.merge_node(
                            labels=[label],
                            identity_props={"vid": vid},
                            properties=dict(node),
                        )
                        written += 1
                    except Exception as item_exc:
                        logger.warning("Failed to persist %s node %s: %s", label, vid_getter(node), item_exc)
        return written

    def _batch_create_edges(self, edge_type: str, edges: list[dict[str, Any]]) -> int:
        if not edges:
            return 0
        batch_size = self._graph_batch_size()
        written = 0
        for chunk in _chunked(edges, batch_size):
            try:
                self.db.batch_create_edges(chunk, edge_type)
                written += len(chunk)
            except Exception as exc:
                logger.warning("Batch create edges failed for %s, falling back to single writes: %s", edge_type, exc)
                for edge in chunk:
                    try:
                        self.db.create_edge(
                            source_id=edge["source_id"],
                            target_id=edge["target_id"],
                            edge_type=edge_type,
                            properties={k: v for k, v in edge.items() if k not in {"source_id", "target_id"}},
                        )
                        written += 1
                    except Exception as item_exc:
                        logger.warning(
                            "Failed to persist %s edge %s->%s: %s",
                            edge_type,
                            edge["source_id"],
                            edge["target_id"],
                            item_exc,
                        )
        return written

    def _load_init_source_data(self) -> dict[str, list[dict[str, Any]]]:
        """Load graph seed data from MySQL when available, otherwise use demos."""
        mysql_data = self.semantic_matcher.load_mysql_binding_data()
        return {
            "talents": mysql_data.get("talents") or TALENT_DATA,
            "papers": mysql_data.get("papers") or PAPER_DATA,
            "patents": PATENT_DATA,
            "orgs": mysql_data.get("orgs") or ORG_DATA,
            "source": mysql_data.get("source") or "demo",
        }

    # ------------------------------------------------------------------
    # Init test data
    # ------------------------------------------------------------------

    def init_data(self) -> InitDataResponse:
        """Initialize edge types, indexes, and insert test data nodes."""
        edge_types_created: list[str] = []
        indexes_created: list[str] = []
        nodes_inserted: dict[str, int] = {}
        source_data = self._load_init_source_data()
        talents = source_data["talents"]
        papers = source_data["papers"]
        patents = source_data["patents"]
        orgs = source_data["orgs"]

        # Create edge types via nGQL
        for edge_name, ngql in EDGE_NGQLS.items():
            try:
                self.db.execute_write(ngql)
                edge_types_created.append(edge_name)
                logger.info("Created edge type: %s", edge_name)
            except Exception as e:
                logger.warning("Failed to create edge type %s: %s", edge_name, e)

        # Create indexes via nGQL
        for ngql in INDEX_NGQLS:
            # Extract index name for tracking
            idx_name = ngql.split("idx_")[1].split(" ")[0] if "idx_" in ngql else ngql
            try:
                self.db.execute_write(ngql)
                indexes_created.append(idx_name)
                logger.info("Created index: %s", idx_name)
            except Exception as e:
                logger.warning("Failed to create index %s: %s", idx_name, e)

        # Add missing demo fields to existing tags
        for ngql in ALTER_TAG_NGQLS:
            try:
                self.db.execute_write(ngql)
                logger.info("Altered tag: %s", ngql)
            except Exception as e:
                logger.warning("Failed to alter tag: %s", e)

        # Insert talent nodes
        talent_nodes = []
        for t in talents:
            vid = str(t.get("scholar_id", t.get("id", "")))
            props = _filter_props("talent", dict(t))
            props["vid"] = vid
            talent_nodes.append(props)
        talent_count = self._batch_create_nodes("talent", talent_nodes, lambda item: item.get("vid", ""))
        nodes_inserted["talent"] = talent_count

        # Insert paper nodes
        paper_nodes = []
        for p in papers:
            vid = str(p.get("paper_id", p.get("id", "")))
            props = _filter_props("cn_paper", dict(p))
            props["vid"] = vid
            paper_nodes.append(props)
        paper_count = self._batch_create_nodes("cn_paper", paper_nodes, lambda item: item.get("vid", ""))
        nodes_inserted["cn_paper"] = paper_count

        # Insert patent nodes
        patent_nodes = []
        for p in patents:
            vid = str(p.get("patent_id", ""))
            props = _filter_props("patent", dict(p))
            props["vid"] = vid
            patent_nodes.append(props)
        patent_count = self._batch_create_nodes("patent", patent_nodes, lambda item: item.get("vid", ""))
        nodes_inserted["patent"] = patent_count

        # Insert organization nodes
        org_nodes = []
        for o in orgs:
            vid = str(o.get("org_id", ""))
            props = _filter_props("cn_organization", dict(o))
            props["vid"] = vid
            org_nodes.append(props)
        org_count = self._batch_create_nodes("cn_organization", org_nodes, lambda item: item.get("vid", ""))
        nodes_inserted["cn_organization"] = org_count

        try:
            self.semantic_matcher.prewarm_binding_indexes(source_data)
        except Exception as exc:
            logger.warning("Failed to prewarm semantic indexes during init data: %s", exc)

        self._seed_initial_candidate_edges()

        source_label = "MySQL" if source_data.get("source") == "mysql" else "demo"
        msg = (
            f"初始化完成: 创建边类型{len(edge_types_created)}个, "
            f"索引{len(indexes_created)}个, "
            f"插入节点{sum(nodes_inserted.values())}个, "
            f"数据源={source_label}"
        )
        return InitDataResponse(
            edge_types_created=edge_types_created,
            indexes_created=indexes_created,
            nodes_inserted=nodes_inserted,
            message=msg,
        )

    # ------------------------------------------------------------------
    # Fetch all nodes of a label (paginated)
    # ------------------------------------------------------------------

    def _fetch_all_nodes(self, label: str) -> list[dict[str, Any]]:
        """Fetch all nodes of a given label using pagination.

        Returns a list of dicts that include both the node VID (as ``id``)
        and all tag properties.
        """
        all_nodes: list[dict[str, Any]] = []
        offset = 0
        page_size = 200

        while True:
            try:
                result = self.db.get_nodes_by_label(label, limit=page_size, offset=offset)
                for node in result.items:
                    props = dict(node.properties)
                    # Ensure the VID is available as "id" for edge creation
                    props["id"] = str(node.id)
                    all_nodes.append(props)
                if not result.page.has_next:
                    break
                offset += page_size
            except Exception as e:
                logger.warning("Error fetching nodes for label %s at offset %d: %s", label, offset, e)
                break

        return all_nodes

    def _replace_binding_edges(
        self,
        edge_type: str,
        details: list[BindingPairDetail],
    ) -> None:
        offset = 0
        page_size = 200
        while True:
            result = self.db.get_edges_by_type(edge_type, limit=page_size, offset=offset)
            if not result.items:
                break
            for edge in result.items:
                try:
                    self.db.delete_edge(edge.id, edge_type=edge.type)
                except Exception as exc:
                    logger.warning("Failed to delete old edge %s: %s", edge.id, exc)
            offset = 0

        batch_edges = [
            {
                "source_id": detail.source_id,
                "target_id": detail.target_id,
                "confidence": detail.confidence,
                "method": detail.method,
                "bound_at": datetime.now(timezone.utc).isoformat(),
                "rule_score": detail.rule_score,
                "llm_score": detail.llm_score,
                "status": detail.status,
            }
            for detail in details
        ]
        self._batch_create_edges(edge_type, batch_edges)

    def _seed_initial_candidate_edges(self) -> None:
        seeders = [
            ("talent_paper", self.matcher.match_talent_paper, "talent", "paper", self.BINDING_EDGE_MAP["talent_paper"]),
            ("talent_patent", self.matcher.match_talent_patent, "talent", "patent", self.BINDING_EDGE_MAP["talent_patent"]),
            ("org_org", lambda orgs, _: self.matcher.match_org_org(orgs, orgs), "org_a", "org_b", self.BINDING_EDGE_MAP["org_org"]),
        ]

        talents = self._fetch_all_nodes("talent")
        papers = self._fetch_all_nodes("cn_paper")
        patents = self._fetch_all_nodes("patent")
        orgs = self._fetch_all_nodes("cn_organization")

        dataset_map = {
            "talent_paper": (talents, papers),
            "talent_patent": (talents, patents),
            "org_org": (orgs, orgs),
        }

        for binding_type, matcher_func, left_key, right_key, edge_type in seeders:
            left_items, right_items = dataset_map[binding_type]
            if not left_items or not right_items:
                continue
            raw_candidates = matcher_func(left_items, right_items)
            details: list[BindingPairDetail] = []
            seen_pairs: set[tuple[str, str]] = set()
            for candidate in raw_candidates:
                left = candidate[left_key]
                right = candidate[right_key]
                source_id = str(left.get("id") or left.get("scholar_id") or left.get("org_id") or "")
                target_id = str(right.get("id") or right.get("paper_id") or right.get("patent_id") or right.get("org_id") or "")
                pair_key = tuple(sorted((source_id, target_id))) if binding_type == "org_org" else (source_id, target_id)
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                source_name = (
                    left.get("name_zh") or left.get("name_cn") or left.get("zh_name") or left.get("title_zh") or left.get("name_en") or source_id
                )
                target_name = (
                    right.get("name_zh") or right.get("name_cn") or right.get("zh_name") or right.get("title_zh") or right.get("name_en") or target_id
                )
                details.append(BindingPairDetail(
                    source_name=str(source_name),
                    source_id=source_id,
                    source_label=self.SOURCE_LABEL_MAP[binding_type],
                    target_name=str(target_name),
                    target_id=target_id,
                    target_label=self.TARGET_LABEL_MAP[binding_type],
                    confidence=self.INITIAL_CANDIDATE_CONFIDENCE,
                    method="rule-init",
                    rule_score=float(candidate.get("rule_score", 0.0)),
                    llm_score=0.0,
                    status="candidate",
                    reason="Initialized from rule recall",
                ))
            self._replace_binding_edges(edge_type, details)

    @staticmethod
    def _merge_candidates(
        rule_candidates: list[dict[str, Any]],
        semantic_candidates: list[dict[str, Any]],
        *,
        left_key: str,
        right_key: str,
        undirected: bool = False,
    ) -> list[dict[str, Any]]:
        merged: dict[tuple[str, str], dict[str, Any]] = {}

        for candidate in rule_candidates:
            left = candidate[left_key]
            right = candidate[right_key]
            left_id = str(left.get("id") or left.get("scholar_id") or left.get("org_id") or "")
            right_id = str(right.get("id") or right.get("paper_id") or right.get("patent_id") or right.get("org_id") or "")
            key = tuple(sorted((left_id, right_id))) if undirected else (left_id, right_id)
            merged[key] = dict(candidate)
            merged[key].setdefault("semantic_score", 0.0)

        for candidate in semantic_candidates:
            left = candidate[left_key]
            right = candidate[right_key]
            left_id = str(left.get("id") or left.get("scholar_id") or left.get("org_id") or "")
            right_id = str(right.get("id") or right.get("paper_id") or right.get("patent_id") or right.get("org_id") or "")
            key = tuple(sorted((left_id, right_id))) if undirected else (left_id, right_id)
            if key in merged:
                merged[key]["semantic_score"] = max(
                    float(merged[key].get("semantic_score", 0.0)),
                    float(candidate.get("semantic_score", 0.0)),
                )
            else:
                merged[key] = dict(candidate)
                merged[key].setdefault("rule_score", 0.0)

        return list(merged.values())

    @staticmethod
    def _resolve_binding_result(
        rule_score: float,
        semantic_score: float,
        fallback_threshold: float,
    ) -> tuple[bool, float, str, str]:
        if semantic_score >= fallback_threshold:
            return True, semantic_score, "semantic-only", "Semantic recall fallback"
        return rule_score >= 0.7, rule_score, "rule-only", "LLM unavailable, rule-based fallback"

    # ------------------------------------------------------------------
    # Bind talent ↔ paper
    # ------------------------------------------------------------------

    def bind_talent_paper(self) -> BindingResult:
        """Execute talent-paper binding pipeline."""
        binding_type = "talent_paper"
        edge_type = self.BINDING_EDGE_MAP[binding_type]
        source_label = self.SOURCE_LABEL_MAP[binding_type]
        target_label = self.TARGET_LABEL_MAP[binding_type]

        # Step 1: Fetch nodes
        talents = self._fetch_all_nodes(source_label)
        papers = self._fetch_all_nodes(target_label)

        if not talents or not papers:
            return BindingResult(binding_type=binding_type)

        # Step 2: Rule-based + semantic matching
        rule_candidates = self.matcher.match_talent_paper(talents, papers)
        semantic_candidates = self.semantic_matcher.match_talent_paper(talents, papers)
        candidates = self._merge_candidates(
            rule_candidates,
            semantic_candidates,
            left_key="talent",
            right_key="paper",
        )

        # Step 3: LLM refinement + write edges
        details: list[BindingPairDetail] = []
        confirmed = 0
        candidate_count = 0
        rejected = 0

        for cand in candidates:
            talent = cand["talent"]
            paper = cand["paper"]
            rule_score = float(cand.get("rule_score", 0.0))
            semantic_score = float(cand.get("semantic_score", 0.0))

            # LLM judge
            talent_desc = _summarize_entity(talent, "学者")
            paper_desc = _summarize_entity(paper, "论文")
            llm_result = _llm_judge(talent_desc, paper_desc, "学者库", "论文库")

            if llm_result is not None:
                is_same = llm_result["is_same"]
                llm_score = llm_result["confidence"]
                reason = llm_result["reason"]
                method = "rule+llm" if rule_score > 0 else "semantic+llm"
            else:
                is_same, llm_score, method, reason = self._resolve_binding_result(
                    rule_score,
                    semantic_score,
                    self.TALENT_PAPER_SEMANTIC_FALLBACK,
                )

            # Status logic
            confidence = llm_score if llm_result is not None else max(rule_score, semantic_score)
            if is_same and confidence >= 0.7:
                status = "confirmed"
                confirmed += 1
            elif is_same and confidence >= 0.5:
                status = "candidate"
                candidate_count += 1
            else:
                status = "rejected"
                rejected += 1

            source_id = str(talent.get("id", "") or talent.get("scholar_id", ""))
            target_id = str(paper.get("id", "") or paper.get("paper_id", ""))
            source_name = talent.get("name_zh", "") or talent.get("name_en", "") or str(talent.get("scholar_id", ""))
            target_name = paper.get("zh_name", "") or paper.get("en_name", "") or str(paper.get("paper_id", ""))
            details.append(BindingPairDetail(
                source_name=source_name,
                source_id=source_id,
                source_label=source_label,
                target_name=target_name,
                target_id=target_id,
                target_label=target_label,
                confidence=confidence,
                method=method,
                rule_score=max(rule_score, semantic_score),
                llm_score=llm_score,
                status=status,
                reason=reason,
            ))

        self._replace_binding_edges(edge_type, [detail for detail in details if detail.status != "rejected"])

        return BindingResult(

            binding_type=binding_type,
            total_candidates=len(candidates),
            confirmed=confirmed,
            candidate=candidate_count,
            rejected=rejected,
            details=details,
        )

    # ------------------------------------------------------------------
    # Bind talent ↔ patent
    # ------------------------------------------------------------------

    def bind_talent_patent(self) -> BindingResult:
        """Execute talent-patent binding pipeline."""
        binding_type = "talent_patent"
        edge_type = self.BINDING_EDGE_MAP[binding_type]
        source_label = self.SOURCE_LABEL_MAP[binding_type]
        target_label = self.TARGET_LABEL_MAP[binding_type]

        # Step 1: Fetch nodes
        talents = self._fetch_all_nodes(source_label)
        patents = self._fetch_all_nodes(target_label)

        if not talents or not patents:
            return BindingResult(binding_type=binding_type)

        # Step 2: Rule-based + semantic matching
        rule_candidates = self.matcher.match_talent_patent(talents, patents)
        semantic_candidates = self.semantic_matcher.match_talent_patent(talents, patents)
        candidates = self._merge_candidates(
            rule_candidates,
            semantic_candidates,
            left_key="talent",
            right_key="patent",
        )

        # Step 3: LLM refinement + write edges
        details: list[BindingPairDetail] = []
        confirmed = 0
        candidate_count = 0
        rejected = 0

        for cand in candidates:
            talent = cand["talent"]
            patent = cand["patent"]
            rule_score = float(cand.get("rule_score", 0.0))
            semantic_score = float(cand.get("semantic_score", 0.0))

            # LLM judge
            talent_desc = _summarize_entity(talent, "学者")
            patent_desc = _summarize_entity(patent, "专利")
            llm_result = _llm_judge(talent_desc, patent_desc, "学者库", "专利库")

            if llm_result is not None:
                is_same = llm_result["is_same"]
                llm_score = llm_result["confidence"]
                reason = llm_result["reason"]
                method = "rule+llm" if rule_score > 0 else "semantic+llm"
            else:
                is_same, llm_score, method, reason = self._resolve_binding_result(
                    rule_score,
                    semantic_score,
                    self.TALENT_PATENT_SEMANTIC_FALLBACK,
                )

            # Status logic
            confidence = llm_score if llm_result is not None else max(rule_score, semantic_score)
            if is_same and confidence >= 0.7:
                status = "confirmed"
                confirmed += 1
            elif is_same and confidence >= 0.5:
                status = "candidate"
                candidate_count += 1
            else:
                status = "rejected"
                rejected += 1

            source_id = str(talent.get("id", "") or talent.get("scholar_id", ""))
            target_id = str(patent.get("patent_id", ""))
            source_name = talent.get("name_zh", "") or talent.get("name_en", "") or str(talent.get("scholar_id", ""))
            target_name = patent.get("title_zh", "") or str(patent.get("patent_id", ""))
            details.append(BindingPairDetail(
                source_name=source_name,
                source_id=source_id,
                source_label=source_label,
                target_name=target_name,
                target_id=target_id,
                target_label=target_label,
                confidence=confidence,
                method=method,
                rule_score=max(rule_score, semantic_score),
                llm_score=llm_score,
                status=status,
                reason=reason,
            ))

        self._replace_binding_edges(edge_type, [detail for detail in details if detail.status != "rejected"])

        return BindingResult(

            binding_type=binding_type,
            total_candidates=len(candidates),
            confirmed=confirmed,
            candidate=candidate_count,
            rejected=rejected,
            details=details,
        )

    # ------------------------------------------------------------------
    # Bind org ↔ org
    # ------------------------------------------------------------------

    def bind_org_org(self) -> BindingResult:
        """Execute org-org binding pipeline."""
        binding_type = "org_org"
        edge_type = self.BINDING_EDGE_MAP[binding_type]
        source_label = self.SOURCE_LABEL_MAP[binding_type]
        target_label = self.TARGET_LABEL_MAP[binding_type]

        # Step 1: Fetch nodes (same label for both sides)
        orgs = self._fetch_all_nodes(source_label)

        if not orgs or len(orgs) < 2:
            return BindingResult(binding_type=binding_type)

        # Step 2: Rule-based + semantic matching (orgs vs orgs)
        rule_candidates = self.matcher.match_org_org(orgs, orgs)
        semantic_candidates = self.semantic_matcher.match_org_org(orgs)
        candidates = self._merge_candidates(
            rule_candidates,
            semantic_candidates,
            left_key="org_a",
            right_key="org_b",
            undirected=True,
        )

        # Step 3: LLM refinement + write edges
        details: list[BindingPairDetail] = []
        confirmed = 0
        candidate_count = 0
        rejected = 0

        for cand in candidates:
            org_a = cand["org_a"]
            org_b = cand["org_b"]
            rule_score = float(cand.get("rule_score", 0.0))
            semantic_score = float(cand.get("semantic_score", 0.0))

            # LLM judge
            org_a_desc = _summarize_entity(org_a, "机构")
            org_b_desc = _summarize_entity(org_b, "机构")
            llm_result = _llm_judge(org_a_desc, org_b_desc, "机构库A", "机构库B")

            if llm_result is not None:
                is_same = llm_result["is_same"]
                llm_score = llm_result["confidence"]
                reason = llm_result["reason"]
                method = "rule+llm" if rule_score > 0 else "semantic+llm"
            else:
                is_same, llm_score, method, reason = self._resolve_binding_result(
                    rule_score,
                    semantic_score,
                    self.ORG_ORG_SEMANTIC_FALLBACK,
                )

            # Status logic
            confidence = llm_score if llm_result is not None else max(rule_score, semantic_score)
            if is_same and confidence >= 0.7:
                status = "confirmed"
                confirmed += 1
            elif is_same and confidence >= 0.5:
                status = "candidate"
                candidate_count += 1
            else:
                status = "rejected"
                rejected += 1

            source_id = str(org_a.get("org_id", ""))
            target_id = str(org_b.get("org_id", ""))
            source_name = org_a.get("name_cn", "") or str(org_a.get("org_id", ""))
            target_name = org_b.get("name_cn", "") or str(org_b.get("org_id", ""))
            details.append(BindingPairDetail(
                source_name=source_name,
                source_id=source_id,
                source_label=source_label,
                target_name=target_name,
                target_id=target_id,
                target_label=target_label,
                confidence=confidence,
                method=method,
                rule_score=max(rule_score, semantic_score),
                llm_score=llm_score,
                status=status,
                reason=reason,
            ))

        self._replace_binding_edges(edge_type, [detail for detail in details if detail.status != "rejected"])

        return BindingResult(

            binding_type=binding_type,
            total_candidates=len(candidates),
            confirmed=confirmed,
            candidate=candidate_count,
            rejected=rejected,
            details=details,
        )

    # ------------------------------------------------------------------
    # Bind all
    # ------------------------------------------------------------------

    def bind_all(self) -> dict[str, Any]:
        """Run all three binding pipelines and return combined results."""
        tp_result = self.bind_talent_paper()
        tpt_result = self.bind_talent_patent()
        oo_result = self.bind_org_org()

        total_confirmed = tp_result.confirmed + tpt_result.confirmed + oo_result.confirmed
        total_candidates = tp_result.total_candidates + tpt_result.total_candidates + oo_result.total_candidates

        return {
            "talent_paper": tp_result,
            "talent_patent": tpt_result,
            "org_org": oo_result,
            "total_confirmed": total_confirmed,
            "total_candidates": total_candidates,
        }

    # ------------------------------------------------------------------
    # Get binding stats
    # ------------------------------------------------------------------

    def get_binding_stats(self) -> BindingStatsResponse:
        """Query binding edges and count by status for each type."""
        stats = BindingStatsResponse()

        for binding_type, edge_type in self.BINDING_EDGE_MAP.items():
            confirmed = 0
            candidate_count = 0
            total = 0

            try:
                # Paginate through all edges of this type
                offset = 0
                page_size = 200
                while True:
                    result = self.db.get_edges_by_type(edge_type, limit=page_size, offset=offset)
                    for edge in result.items:
                        total += 1
                        status = edge.properties.get("status", "")
                        if status == "confirmed":
                            confirmed += 1
                        elif status == "candidate":
                            candidate_count += 1
                    if not result.page.has_next:
                        break
                    offset += page_size
            except Exception as e:
                logger.warning("Error fetching edges for %s: %s", edge_type, e)

            br = BindingResult(
                binding_type=binding_type,
                total_candidates=total,
                confirmed=confirmed,
                candidate=candidate_count,
                rejected=0,
            )

            if binding_type == "talent_paper":
                stats.talent_paper = br
            elif binding_type == "talent_patent":
                stats.talent_patent = br
            elif binding_type == "org_org":
                stats.org_org = br

        stats.total_confirmed = (
            (stats.talent_paper.confirmed if stats.talent_paper else 0)
            + (stats.talent_patent.confirmed if stats.talent_patent else 0)
            + (stats.org_org.confirmed if stats.org_org else 0)
        )
        stats.total_candidates = (
            (stats.talent_paper.total_candidates if stats.talent_paper else 0)
            + (stats.talent_patent.total_candidates if stats.talent_patent else 0)
            + (stats.org_org.total_candidates if stats.org_org else 0)
        )
        stats.total_candidate = (
            (stats.talent_paper.candidate if stats.talent_paper else 0)
            + (stats.talent_patent.candidate if stats.talent_patent else 0)
            + (stats.org_org.candidate if stats.org_org else 0)
        )

        return stats

    # ------------------------------------------------------------------
    # Get binding detail
    # ------------------------------------------------------------------

    def get_binding_detail(self, binding_type: str, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """Get detailed list of binding edges for a specific type."""
        edge_type = self.BINDING_EDGE_MAP.get(binding_type)
        if not edge_type:
            return []

        details: list[dict[str, Any]] = []
        current_offset = offset
        page_size = min(limit, 200)
        remaining = limit
        node_cache: dict[str, dict[str, Any]] = {}

        def _node_summary(node_id: str) -> dict[str, Any]:
            if node_id in node_cache:
                return node_cache[node_id]
            try:
                node = self.db.get_node(node_id)
                if node is None:
                    node_cache[node_id] = {"name": node_id, "label": "unknown"}
                else:
                    name = (
                        node.properties.get("name_zh")
                        or node.properties.get("name_cn")
                        or node.properties.get("zh_name")
                        or node.properties.get("title_zh")
                        or node.properties.get("name_en")
                        or node.properties.get("en_name")
                        or str(node.id)
                    )
                    label = node.labels[0] if node.labels else "unknown"
                    node_cache[node_id] = {"name": name, "label": label}
            except Exception:
                node_cache[node_id] = {"name": node_id, "label": "unknown"}
            return node_cache[node_id]

        while remaining > 0:
            try:
                fetch_size = min(page_size, remaining)
                result = self.db.get_edges_by_type(edge_type, limit=fetch_size, offset=current_offset)
                for edge in result.items:
                    source_id = str(edge.source_id)
                    target_id = str(edge.target_id)
                    source_node = _node_summary(source_id)
                    target_node = _node_summary(target_id)
                    details.append({
                        "edge_id": str(edge.id),
                        "source_id": source_id,
                        "target_id": target_id,
                        "source_name": source_node["name"],
                        "source_label": source_node["label"],
                        "target_name": target_node["name"],
                        "target_label": target_node["label"],
                        "edge_type": edge.type,
                        "confidence": edge.properties.get("confidence", 0),
                        "method": edge.properties.get("method", ""),
                        "rule_score": edge.properties.get("rule_score", 0),
                        "llm_score": edge.properties.get("llm_score", 0),
                        "status": edge.properties.get("status", ""),
                        "reason": edge.properties.get("reason", ""),
                        "properties": edge.properties,
                    })
                    remaining -= 1
                if not result.page.has_next:
                    break
                current_offset += fetch_size
            except Exception as e:
                logger.warning("Error fetching detail for %s: %s", edge_type, e)
                break

        return details

    # ------------------------------------------------------------------
    # Get binding graph (for D3.js visualization)
    # ------------------------------------------------------------------

    def get_binding_graph(self) -> BindingGraphResponse:
        """Fetch current binding edges and build nodes/edges arrays for D3.js visualization."""
        nodes_map: dict[str, dict] = {}
        edges_list: list[dict] = []

        def _ensure_node(node_id: str) -> None:
            if node_id in nodes_map:
                return
            try:
                node = self.db.get_node(node_id)
                if node is not None:
                    name = (
                        node.properties.get("name_zh")
                        or node.properties.get("name_cn")
                        or node.properties.get("zh_name")
                        or node.properties.get("title_zh")
                        or node.properties.get("name_en")
                        or node.properties.get("en_name")
                        or str(node.id)
                    )
                    label = node.labels[0] if node.labels else "unknown"
                    nodes_map[node_id] = {
                        "id": node_id,
                        "name": name,
                        "label": label,
                    }
                    return
            except Exception:
                pass
            nodes_map[node_id] = {"id": node_id, "name": node_id, "label": "unknown"}

        for binding_type, edge_type in self.BINDING_EDGE_MAP.items():
            offset = 0
            page_size = 200

            while True:
                try:
                    result = self.db.get_edges_by_type(edge_type, limit=page_size, offset=offset)
                    for edge in result.items:
                        source_id = str(edge.source_id)
                        target_id = str(edge.target_id)
                        _ensure_node(source_id)
                        _ensure_node(target_id)
                        edges_list.append({
                            "source": source_id,
                            "target": target_id,
                            "type": edge_type,
                            "confidence": edge.properties.get("confidence", 0),
                            "status": edge.properties.get("status", ""),
                            "method": edge.properties.get("method", ""),
                        })

                    if not result.page.has_next:
                        break
                    offset += page_size
                except Exception as e:
                    logger.warning("Error fetching graph for %s: %s", edge_type, e)
                    break

        return BindingGraphResponse(
            nodes=list(nodes_map.values()),
            edges=edges_list,
        )

    def get_expert_direct_relation_demo(
        self,
        data_source: str = "all",
        expert_a_id: str | None = None,
        expert_b_id: str | None = None,
        institution: str | None = None,
        relation_type: str = "direct",
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> ExpertRelationDemoResponse:
        query_params = {
            "dataSource": (data_source or "all").strip().lower(),
            "expertAId": (expert_a_id or "").strip(),
            "expertBId": (expert_b_id or "").strip(),
            "institution": (institution or "").strip(),
            "relationType": (relation_type or "direct").strip(),
            "startTime": (start_time or "").strip(),
            "endTime": (end_time or "").strip(),
        }
        scenarios = self.build_expert_direct_relation_scenarios(
            data_source=query_params["dataSource"],
            relation_type=query_params["relationType"],
        )
        scenarios = self.filter_expert_direct_relation_scenarios(scenarios, query_params)
        for scenario in scenarios:
            scenario.api_example["query_params"] = query_params
        return ExpertRelationDemoResponse(scenarios=scenarios)

    def build_expert_direct_relation_scenarios(
        self,
        data_source: str = "all",
        relation_type: str = "direct",
    ) -> list[ExpertRelationScenario]:
        normalized_source = (data_source or "all").strip().lower()
        normalized_relation = (relation_type or "direct").strip().lower()
        scenarios: list[ExpertRelationScenario] = []
        if normalized_source in {"all", "graph", "real"}:
            try:
                scenarios.extend(self._build_real_expert_relation_scenarios())
            except Exception as exc:
                logger.warning("Build real expert relation scenarios failed, fallback will be used: %s", exc)
        if normalized_source in {"all", "fallback", "demo"} or len(scenarios) < 12:
            fallback_scenarios = self._build_fallback_expert_relation_scenarios()
            existing_keys = {scenario.key for scenario in scenarios}
            for scenario in fallback_scenarios:
                if scenario.key in existing_keys:
                    continue
                scenarios.append(scenario)
                existing_keys.add(scenario.key)
                if normalized_source in {"all", "graph", "real"} and len(scenarios) >= 12:
                    break
        scenarios = self._select_expert_relation_scenarios(scenarios, normalized_relation)
        return [self._scope_relation_reason_for_query(scenario, normalized_relation) for scenario in scenarios]

    @staticmethod
    def _scenario_complexity_score(scenario: ExpertRelationScenario) -> tuple[int, float, str]:
        api_example = scenario.api_example or {}
        reasons = api_example.get("reasons") or []
        if not isinstance(reasons, list):
            reasons = [reasons]
        reason_count = len([reason for reason in reasons if str(reason).strip()])
        relation_strength = float(api_example.get("relation_strength") or 0.0)
        relation_summary = str(api_example.get("relation_summary") or "")
        return reason_count, relation_strength, relation_summary

    def _select_expert_relation_scenarios(
        self,
        scenarios: list[ExpertRelationScenario],
        relation_type: str,
    ) -> list[ExpertRelationScenario]:
        normalized = (relation_type or "direct").strip().lower()
        if normalized not in {"two_hop", "three_hop"} or len(scenarios) <= 1:
            return scenarios

        ranked: list[tuple[float, int, float, int, ExpertRelationScenario]] = []
        for index, scenario in enumerate(scenarios):
            reason_count, relation_strength, _summary = self._scenario_complexity_score(scenario)
            complexity_score = float(reason_count * 10 + relation_strength)
            ranked.append((complexity_score, reason_count, relation_strength, index, scenario))

        ranked.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
        pivot = max(1, len(ranked) // 2)
        if normalized == "two_hop":
            selected = ranked[:pivot]
        else:
            selected = ranked[pivot:]
            if not selected:
                selected = ranked[-pivot:]
        return [item[4] for item in selected]

    @staticmethod
    def filter_expert_direct_relation_scenarios(
        scenarios: list[ExpertRelationScenario],
        query_params: dict[str, str],
    ) -> list[ExpertRelationScenario]:
        expert_a_query = query_params.get("expertAId", "")
        expert_b_query = query_params.get("expertBId", "")
        institution_query = query_params.get("institution", "")
        relation_query = query_params.get("relationType", "direct")
        start_dt = EntityBindingService._parse_query_datetime(query_params.get("startTime", ""))
        end_dt = EntityBindingService._parse_query_datetime(query_params.get("endTime", ""))

        def get_row_value(scenario: ExpertRelationScenario, row_key: str) -> Any:
            for key, value in scenario.detail_rows:
                if key == row_key:
                    return value
            return ""

        def match_expert(scenario: ExpertRelationScenario, side: str, query: str) -> bool:
            if not query or query == "全部":
                return True
            query_text = query.lower()
            expert = scenario.api_example.get("expert_a" if side == "a" else "expert_b", {})
            row_name = str(get_row_value(scenario, "专家 A" if side == "a" else "专家 B"))
            graph_nodes = [node for node in scenario.graph.nodes if node.kind == ("expertA" if side == "a" else "expertB")]
            values = [row_name, str(expert.get("name", "")), str(expert.get("id", ""))]
            values.extend([node.id for node in graph_nodes])
            values.extend([node.subtitle for node in graph_nodes])
            return any(query_text in str(value).lower() for value in values if value)

        def match_institution(scenario: ExpertRelationScenario) -> bool:
            if not institution_query or institution_query == "全部":
                return True
            query_text = institution_query.lower()
            values = [
                str(scenario.api_example.get("institution", "")),
                str(get_row_value(scenario, "直接关系")),
            ]
            values.extend([node.subtitle for node in scenario.graph.nodes if node.kind == "institution"])
            return any(query_text in str(value).lower() for value in values if value)

        def match_relation(scenario: ExpertRelationScenario) -> bool:
            normalized = (relation_query or "direct").strip().lower()
            if normalized in {"", "all", "direct", "two_hop", "three_hop"}:
                return True
            expected = (EntityBindingService._relation_reason_label(normalized) or relation_query).lower()
            reasons = scenario.api_example.get("reasons") or get_row_value(scenario, "判定依据") or []
            if not isinstance(reasons, list):
                reasons = [reasons]
            return any(expected in str(reason).lower() for reason in reasons)

        def match_time(scenario: ExpertRelationScenario) -> bool:
            test_dt = EntityBindingService._parse_query_datetime(scenario.last_test_time)
            if not test_dt:
                return True
            if start_dt and test_dt < start_dt:
                return False
            if end_dt and test_dt > end_dt:
                return False
            return True

        return [
            scenario
            for scenario in scenarios
            if match_expert(scenario, "a", expert_a_query)
            and match_expert(scenario, "b", expert_b_query)
            and match_institution(scenario)
            and match_relation(scenario)
            and match_time(scenario)
        ]

    def _build_real_expert_relation_scenarios(self) -> list[ExpertRelationScenario]:
        talent_result = self.db.get_nodes_by_label("talent", limit=200, offset=0)
        paper_result = self.db.get_nodes_by_label("cn_paper", limit=400, offset=0)
        patent_result = self.db.get_nodes_by_label("patent", limit=400, offset=0)

        talents = [node.properties for node in talent_result.items]
        papers = [node.properties for node in paper_result.items]
        patents = [node.properties for node in patent_result.items]
        if len(talents) < 2:
            return []

        org_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for talent in talents:
            org_name = str(talent.get("scholar_org_name_zh") or talent.get("scholar_org_name_en") or "").strip()
            if org_name:
                org_groups[org_name].append(talent)

        relation_pairs_map: dict[tuple[str, str], dict[str, Any]] = {}
        talent_by_name: dict[str, dict[str, Any]] = {}
        for talent in talents:
            talent_by_name[self._get_talent_display_name(talent)] = talent

        def add_relation_pair(
            expert_a: dict[str, Any],
            expert_b: dict[str, Any],
            relation_reason: str,
            relation_weight: int,
            institution: str = "",
        ) -> None:
            expert_a_id = str(expert_a.get("scholar_id") or self._get_talent_display_name(expert_a))
            expert_b_id = str(expert_b.get("scholar_id") or self._get_talent_display_name(expert_b))
            pair_key = tuple(sorted((expert_a_id, expert_b_id)))
            shared_directions = self._collect_shared_directions(expert_a, expert_b)
            record = relation_pairs_map.setdefault(
                pair_key,
                {
                    "expert_a": expert_a,
                    "expert_b": expert_b,
                    "institution": institution or str(expert_a.get("scholar_org_name_zh") or expert_b.get("scholar_org_name_zh") or "").strip(),
                    "shared_directions": shared_directions,
                    "reasons": [],
                    "weight": 0,
                },
            )
            if relation_reason not in record["reasons"]:
                record["reasons"].append(relation_reason)
            record["weight"] += relation_weight
            if shared_directions:
                record["shared_directions"] = sorted(set(record["shared_directions"]) | set(shared_directions))
            if institution and not record["institution"]:
                record["institution"] = institution

        for institution, members in org_groups.items():
            if len(members) < 2:
                continue
            members = sorted(members, key=lambda item: str(item.get("name_zh") or item.get("name_en") or item.get("scholar_id") or ""))
            for index, expert_a in enumerate(members):
                for expert_b in members[index + 1:]:
                    add_relation_pair(expert_a, expert_b, "同机构", 3, institution)

        for paper in papers:
            authors = self._extract_names_from_text(paper.get("authors"))
            if len(authors) < 2:
                continue
            for index, author_a in enumerate(authors):
                expert_a = talent_by_name.get(author_a)
                if not expert_a:
                    continue
                for author_b in authors[index + 1:]:
                    expert_b = talent_by_name.get(author_b)
                    if not expert_b:
                        continue
                    add_relation_pair(
                        expert_a,
                        expert_b,
                        "共论文",
                        4,
                        str(paper.get("institution") or expert_a.get("scholar_org_name_zh") or expert_b.get("scholar_org_name_zh") or "").strip(),
                    )

        inventor_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for patent in patents:
            applicant = str(patent.get("first_applicant_name") or "").strip()
            inventor_name = str(patent.get("first_inventor_name") or "").strip()
            expert = talent_by_name.get(inventor_name)
            if expert and applicant:
                inventor_groups[applicant].append(expert)
        for applicant, inventors in inventor_groups.items():
            unique_inventors = []
            seen_ids = set()
            for inventor in inventors:
                inventor_id = str(inventor.get("scholar_id") or self._get_talent_display_name(inventor))
                if inventor_id in seen_ids:
                    continue
                seen_ids.add(inventor_id)
                unique_inventors.append(inventor)
            for index, expert_a in enumerate(unique_inventors):
                for expert_b in unique_inventors[index + 1:]:
                    add_relation_pair(expert_a, expert_b, "共专利", 4, applicant)

        for talent in talents:
            co_scholar_names = self._extract_names_from_text(
                talent.get("co_scholar_name_zh") or talent.get("co_scholar_name_en") or talent.get("co_scholar_id")
            )
            for co_name in co_scholar_names:
                co_expert = talent_by_name.get(co_name)
                if not co_expert:
                    continue
                co_paper_count = int(talent.get("co_paper_count") or 1)
                add_relation_pair(
                    talent,
                    co_expert,
                    "Co-Author",
                    max(3, co_paper_count),
                    str(talent.get("co_scholar_org_name_zh") or talent.get("scholar_org_name_zh") or co_expert.get("scholar_org_name_zh") or "").strip(),
                )

        for institution, members in org_groups.items():
            if len(members) < 2:
                continue
            members = sorted(members, key=lambda item: str(item.get("name_zh") or item.get("name_en") or item.get("scholar_id") or ""))
            for index, expert_a in enumerate(members):
                for expert_b in members[index + 1:]:
                    if self._collect_shared_directions(expert_a, expert_b):
                        add_relation_pair(expert_a, expert_b, "共同项目", 2, institution)

        relation_pairs = list(relation_pairs_map.values())
        relation_pairs.sort(
            key=lambda item: (
                item["weight"],
                len(item["reasons"]),
                len(item["shared_directions"]),
                int(item["expert_a"].get("h_index") or 0) + int(item["expert_b"].get("h_index") or 0),
                str(item["expert_a"].get("name_zh") or item["expert_a"].get("name_en") or ""),
                str(item["expert_b"].get("name_zh") or item["expert_b"].get("name_en") or ""),
            ),
            reverse=True,
        )

        scenarios: list[ExpertRelationScenario] = []
        for pair in relation_pairs[:12]:
            expert_a_name = self._get_talent_display_name(pair["expert_a"])
            expert_b_name = self._get_talent_display_name(pair["expert_b"])
            relation_type = "直接关系"
            institution = pair["institution"] or "科研合作网络"
            relation_strength = min(100, 45 + pair["weight"] * 8 + len(pair["reasons"]) * 6)
            api_example = {
                "relation_type": "expert_direct_relation",
                "relation_subtype": "direct",
                "expert_a": {"name": expert_a_name, "title": self._infer_talent_title(pair["expert_a"])},
                "expert_b": {"name": expert_b_name, "title": self._infer_talent_title(pair["expert_b"])},
                "institution": institution,
                "reasons": pair["reasons"],
                "relation_strength": relation_strength,
                "relation_summary": " + ".join(pair["reasons"]),
            }
            scenario_data = {
                "key": f"expert-{pair['expert_a'].get('scholar_id', expert_a_name)}-{pair['expert_b'].get('scholar_id', expert_b_name)}",
                "label": f"科技专家直接关系（{expert_a_name} / {expert_b_name}）",
                "last_test_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "expert_a_id": str(pair["expert_a"].get("scholar_id") or expert_a_name),
                "expert_b_id": str(pair["expert_b"].get("scholar_id") or expert_b_name),
                "expert_a": {"name": expert_a_name, "title": self._infer_talent_title(pair["expert_a"]), "id": str(pair["expert_a"].get("scholar_id") or expert_a_name)},
                "expert_b": {"name": expert_b_name, "title": self._infer_talent_title(pair["expert_b"]), "id": str(pair["expert_b"].get("scholar_id") or expert_b_name)},
                "relation_type": relation_type,
                "institution": institution,
                "directions": pair["shared_directions"],
                "duration": "",
                "achievements": [],
                "api_example": api_example,
            }
            scenarios.append(self._build_expert_relation_scenario(scenario_data))
        return scenarios

    @staticmethod
    def _build_fallback_expert_relation_scenarios() -> list[ExpertRelationScenario]:
        return [EntityBindingService._build_expert_relation_scenario(item) for item in EXPERT_DIRECT_RELATION_FALLBACK_DATA]

    @staticmethod
    def _relation_reason_label(relation_type: str | None) -> str:
        reason_map = {
            "same_institution": "同机构",
            "co_paper": "共论文",
            "co_patent": "共专利",
            "co_author": "Co-Author",
            "co_project": "共同项目",
        }
        normalized = (relation_type or "direct").strip().lower()
        return reason_map.get(normalized, "")

    def _scope_relation_reason_for_query(
        self,
        scenario: ExpertRelationScenario,
        relation_type: str | None,
    ) -> ExpertRelationScenario:
        selected_reason = self._relation_reason_label(relation_type)
        if not selected_reason:
            return scenario
        reasons = scenario.api_example.get("reasons") or []
        if not isinstance(reasons, list):
            reasons = [reasons]
        scoped_reasons = [reason for reason in reasons if selected_reason.lower() == str(reason).lower()]
        if not scoped_reasons:
            scoped_reasons = [selected_reason]
        scenario.api_example["reasons"] = scoped_reasons
        scenario.api_example["relation_summary"] = " + ".join(scoped_reasons)
        scenario.detail_rows = [
            [key, scoped_reasons if key == "判定依据" else (" + ".join(scoped_reasons) if key == "关系摘要" else value)]
            for key, value in scenario.detail_rows
        ]
        return scenario

    @staticmethod
    def _parse_query_datetime(raw_value: str | None) -> datetime | None:
        if not raw_value:
            return None
        value = raw_value.strip()
        if not value:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    @staticmethod
    def _build_expert_relation_scenario(item: dict[str, Any]) -> ExpertRelationScenario:
        graph = EntityBindingService._build_expert_demo_graph(
            item["expert_a"],
            item["expert_b"],
            item["relation_type"],
            item["institution"],
            item["directions"],
            item["duration"],
            item["achievements"],
            expert_a_id=str(item.get("expert_a_id") or item["expert_a"].get("id") or item["expert_a"].get("scholar_id") or item["expert_a"]["name"]),
            expert_b_id=str(item.get("expert_b_id") or item["expert_b"].get("id") or item["expert_b"].get("scholar_id") or item["expert_b"]["name"]),
        )
        detail_rows = [
            ["专家 A", item["expert_a"]["name"]],
            ["专家 A 职称", item["expert_a"]["title"]],
            ["专家 B", item["expert_b"]["name"]],
            ["专家 B 职称", item["expert_b"]["title"]],
            ["关系类型", f"科技专家直接关系 / {item['relation_type']}"],
            ["直接关系", item["institution"]],
            ["判定依据", item.get("api_example", {}).get("reasons", [])],
            ["关系强度", item.get("api_example", {}).get("relation_strength", 0)],
            ["关系摘要", item.get("api_example", {}).get("relation_summary", "")],
        ]
        return ExpertRelationScenario(
            key=item["key"],
            label=item["label"],
            last_test_time=item["last_test_time"],
            graph=graph,
            detail_rows=detail_rows,
            api_example=item["api_example"],
        )

    @staticmethod
    def _get_talent_display_name(talent: dict[str, Any]) -> str:
        return str(talent.get("name_zh") or talent.get("name_en") or talent.get("scholar_id") or "未知专家")

    @staticmethod
    def _infer_talent_title(talent: dict[str, Any]) -> str:
        h_index = int(talent.get("h_index") or 0)
        if h_index >= 12:
            return "研究员"
        if h_index >= 9:
            return "副研究员"
        return "助理研究员"

    @staticmethod
    def _split_text_values(raw_value: Any) -> list[str]:
        text = str(raw_value or "")
        parts = re.split(r"[;,；、|\s]+", text)
        return [part.strip() for part in parts if part.strip()]

    def _extract_names_from_text(self, raw_value: Any) -> list[str]:
        values = self._split_text_values(raw_value)
        result: list[str] = []
        for value in values:
            cleaned = value.strip()
            if not cleaned:
                continue
            if cleaned not in result:
                result.append(cleaned)
        return result

    def _collect_shared_directions(self, expert_a: dict[str, Any], expert_b: dict[str, Any]) -> list[str]:
        fields_a = set(self._split_text_values(expert_a.get("fields")))
        fields_b = set(self._split_text_values(expert_b.get("fields")))
        return sorted(fields_a & fields_b)

    def _merge_direction_values(self, expert_a: dict[str, Any], expert_b: dict[str, Any]) -> list[str]:
        merged: list[str] = []
        for value in self._split_text_values(expert_a.get("fields")) + self._split_text_values(expert_b.get("fields")):
            if value not in merged:
                merged.append(value)
        return merged[:4]

    def _collect_shared_papers(
        self,
        expert_a: dict[str, Any],
        expert_b: dict[str, Any],
        papers: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        expert_names = {self._get_talent_display_name(expert_a), self._get_talent_display_name(expert_b)}
        institution = str(expert_a.get("scholar_org_name_zh") or expert_a.get("scholar_org_name_en") or "").strip()
        shared: list[dict[str, Any]] = []
        for paper in papers:
            authors = str(paper.get("authors") or "")
            if not all(name in authors for name in expert_names):
                continue
            paper_institution = str(paper.get("institution") or "").strip()
            if institution and paper_institution and institution not in paper_institution and paper_institution not in institution:
                continue
            shared.append(paper)
        return shared

    def _collect_shared_patents(
        self,
        expert_a: dict[str, Any],
        expert_b: dict[str, Any],
        patents: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        institution = str(expert_a.get("scholar_org_name_zh") or expert_a.get("scholar_org_name_en") or "").strip()
        expert_names = {self._get_talent_display_name(expert_a), self._get_talent_display_name(expert_b)}
        shared: list[dict[str, Any]] = []
        for patent in patents:
            inventor_name = str(patent.get("first_inventor_name") or "").strip()
            applicant_name = str(patent.get("first_applicant_name") or "").strip()
            if inventor_name not in expert_names:
                continue
            if institution and applicant_name and institution not in applicant_name and applicant_name not in institution:
                continue
            shared.append(patent)
        return shared

    @staticmethod
    def _build_relation_duration(shared_papers: list[dict[str, Any]]) -> str:
        years: list[str] = []
        for paper in shared_papers:
            cover_date = str(paper.get("cover_date_start") or "").strip()
            if cover_date:
                years.append(cover_date[:7])
        if not years:
            return "长期合作"
        years.sort()
        if len(years) == 1:
            return f"{years[0]} - {years[0]}"
        return f"{years[0]} - {years[-1]}"

    @staticmethod
    def _split_duration(duration: str) -> dict[str, str]:
        if " - " in duration:
            start, end = duration.split(" - ", 1)
            return {"start": start, "end": end}
        return {"start": duration, "end": duration}

    @staticmethod
    def _build_expert_demo_graph(
        expert_a: dict[str, str],
        expert_b: dict[str, str],
        relation_type: str,
        institution: str,
        directions: list[str],
        duration: str,
        achievements: list[dict[str, Any]],
        expert_a_id: str = "expertA",
        expert_b_id: str = "expertB",
    ) -> ExpertRelationGraph:
        institution_id = f"institution-{institution}"
        return ExpertRelationGraph(
            width=860,
            height=640,
            nodes=[
                ExpertRelationGraphNode(id=expert_a_id, kind="expertA", x=90, y=140, icon="👤", title=f"专家A：{expert_a['name']}", subtitle=expert_a["title"]),
                ExpertRelationGraphNode(id=expert_b_id, kind="expertB", x=550, y=140, icon="👤", title=f"专家B：{expert_b['name']}", subtitle=expert_b["title"]),
                ExpertRelationGraphNode(id=institution_id, kind="institution", x=270, y=340, icon="🏛", title="直接关系", subtitle=institution),
            ],
            edges=[
                ExpertRelationGraphEdge(type="curve", from_=[276, 196], to=[550, 196], stroke="#a355ec", marker="#a355ec", width=4, label=relation_type, label_x=398, label_y=178, label_color="#8f52db"),
                ExpertRelationGraphEdge(type="curve", from_=[220, 240], c1=[250, 290], c2=[330, 335], to=[402, 392], stroke="#6ca2ff", marker="#6ca2ff", width=4, label="直连", label_x=275, label_y=320, label_color="#6b8fd6"),
                ExpertRelationGraphEdge(type="curve", from_=[640, 240], c1=[620, 290], c2=[540, 335], to=[458, 392], stroke="#6ca2ff", marker="#6ca2ff", width=4, label="直连", label_x=555, label_y=320, label_color="#6b8fd6"),
            ],
        )

    # ------------------------------------------------------------------
    # Clear bindings
    # ------------------------------------------------------------------

    def clear_bindings(self, clear_data: bool = False) -> ClearResponse:
        """Delete all binding edges. If clear_data=True, also delete all source nodes."""
        edges_deleted = 0

        for edge_type in self.BINDING_EDGE_MAP.values():
            offset = 0
            page_size = 200

            while True:
                try:
                    result = self.db.get_edges_by_type(edge_type, limit=page_size, offset=offset)
                    if not result.items:
                        break
                    for edge in result.items:
                        try:
                            self.db.delete_edge(edge.id, edge_type=edge.type)
                            edges_deleted += 1
                        except Exception as e:
                            logger.warning("Failed to delete edge %s: %s", edge.id, e)
                    # After deleting, restart from offset 0 since IDs may have shifted
                    offset = 0
                    # Check if there are still edges
                    check = self.db.get_edges_by_type(edge_type, limit=1, offset=0)
                    if not check.items:
                        break
                except Exception as e:
                    logger.warning("Error clearing edges for %s: %s", edge_type, e)
                    break

        # Optionally clear data nodes
        if clear_data:
            for label in ["talent", "cn_paper", "patent", "cn_organization"]:
                offset = 0
                page_size = 200
                while True:
                    try:
                        result = self.db.get_nodes_by_label(label, limit=page_size, offset=offset)
                        if not result.items:
                            break
                        for node in result.items:
                            try:
                                self.db.delete_node(node.id, detach=True)
                            except Exception as e:
                                logger.warning("Failed to delete node %s: %s", node.id, e)
                        # After deleting, restart from offset 0
                        check = self.db.get_nodes_by_label(label, limit=1, offset=0)
                        if not check.items:
                            break
                    except Exception as e:
                        logger.warning("Error clearing nodes for %s: %s", label, e)
                        break

        msg = f"已清除所有绑定边({edges_deleted}条)"
        if clear_data:
            msg += "，已清除所有测试数据节点"

        return ClearResponse(message=msg, edges_deleted=edges_deleted)
