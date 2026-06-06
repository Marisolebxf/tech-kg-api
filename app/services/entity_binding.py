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
from datetime import datetime, timezone
from typing import Any, Optional

from dotenv import load_dotenv

from app.schemas.entity_binding import (
    BindingGraphResponse,
    BindingPairDetail,
    BindingResult,
    BindingStatsResponse,
    ClearResponse,
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

# ---------------------------------------------------------------------------
# nGQL constants for edge types and indexes
# ---------------------------------------------------------------------------

# Valid property names per NebulaGraph tag (from DESCRIBE TAG)
VALID_TAG_PROPS: dict[str, set[str]] = {
    "talent": {
        "scholar_id", "name_en", "name_zh", "avatar", "scholar_org_name_en",
        "scholar_org_name_zh", "bio", "bio_zh", "work_experience_en",
        "work_experience_zh", "education_background_en", "education_background_zh",
        "paper_nums", "citation_nums", "h_index", "status", "create_time",
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

    # ------------------------------------------------------------------
    # Init test data
    # ------------------------------------------------------------------

    def init_data(self) -> InitDataResponse:
        """Initialize edge types, indexes, and insert test data nodes."""
        edge_types_created: list[str] = []
        indexes_created: list[str] = []
        nodes_inserted: dict[str, int] = {}

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
        talent_count = 0
        for t in TALENT_DATA:
            try:
                vid = t.get("scholar_id", t.get("id", ""))
                self.db.merge_node(
                    labels=["talent"],
                    identity_props={"vid": vid},
                    properties=_filter_props("talent", dict(t)),
                )
                talent_count += 1
            except Exception as e:
                logger.warning("Failed to insert talent %s: %s", t.get("scholar_id", t.get("id", "")), e)
        nodes_inserted["talent"] = talent_count

        # Insert paper nodes
        paper_count = 0
        for p in PAPER_DATA:
            try:
                vid = p.get("paper_id", p.get("id", ""))
                self.db.merge_node(
                    labels=["cn_paper"],
                    identity_props={"vid": vid},
                    properties=_filter_props("cn_paper", dict(p)),
                )
                paper_count += 1
            except Exception as e:
                logger.warning("Failed to insert paper %s: %s", p.get("paper_id", p.get("id", "")), e)
        nodes_inserted["cn_paper"] = paper_count

        # Insert patent nodes
        patent_count = 0
        for p in PATENT_DATA:
            try:
                vid = p.get("patent_id", "")
                self.db.merge_node(
                    labels=["patent"],
                    identity_props={"vid": vid},
                    properties=_filter_props("patent", dict(p)),
                )
                patent_count += 1
            except Exception as e:
                logger.warning("Failed to insert patent %s: %s", p.get("patent_id"), e)
        nodes_inserted["patent"] = patent_count

        # Insert organization nodes
        org_count = 0
        for o in ORG_DATA:
            try:
                vid = o.get("org_id", "")
                self.db.merge_node(
                    labels=["cn_organization"],
                    identity_props={"vid": vid},
                    properties=_filter_props("cn_organization", dict(o)),
                )
                org_count += 1
            except Exception as e:
                logger.warning("Failed to insert org %s: %s", o.get("org_id"), e)
        nodes_inserted["cn_organization"] = org_count

        self._seed_initial_candidate_edges()

        msg = (
            f"初始化完成: 创建边类型{len(edge_types_created)}个, "
            f"索引{len(indexes_created)}个, "
            f"插入节点{sum(nodes_inserted.values())}个"
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

        for detail in details:
            try:
                self.db.create_edge(
                    source_id=detail.source_id,
                    target_id=detail.target_id,
                    edge_type=edge_type,
                    properties={
                        "confidence": detail.confidence,
                        "method": detail.method,
                        "bound_at": datetime.now(timezone.utc).isoformat(),
                        "rule_score": detail.rule_score,
                        "llm_score": detail.llm_score,
                        "status": detail.status,
                    },
                )
            except Exception as exc:
                logger.warning("Failed to replace binding edge %s->%s: %s", detail.source_id, detail.target_id, exc)

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
