"""专利域匹配类边共享原语（复刻旧 load_patent_relations.py 的匹配逻辑）。

不 import 旧 ETL 入口模块本身；``normalize_name``/``normalize_identifier``/
``application_number_key``/``identifier_index``/``patent_candidates``/
``canonical_entities``/``project_evidence_context`` 等匹配器与索引构建逻辑
逐行移植自旧脚本，保证 CITES/INVENTED_BY/APPLIED_BY/OWNED_BY 数据口径不变。

旧脚本的 Milvus 向量提升（``promote_vector_organization_matches``）为可选的
对齐修正步骤，不在本包边脚本内迁移（见包 README「对齐修正配套」）。
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from infra.graph_db import TRSGraphClient
from script.relation_extractors_one_relation.common import EdgeRecord

NAME_CLEAN_RE = re.compile(r"[^0-9a-z\u4e00-\u9fff]+")
IDENTIFIER_CLEAN_RE = re.compile(r"[^0-9a-z]+")
CN_APPLICATION_RE = re.compile(r"^(?:cn|zl)?(\d{12})(?:[a-z]|\d)?$")

# 只有机构数据域的正式来源可以作为专利关系目标。人才、项目等领域为了
# 保存原始机构文本而临时创建的 Organization 不参与匹配。
CANONICAL_ORGANIZATION_SOURCE_TABLES = frozenset(
    {
        "dwd_org_base_info",
        "dwd_org_heis_info",
        "dwd_research_institute_base_info",
        "dwd_forg_base_info",
        "dwd_special_hongkong_company",
        "dwd_special_aomen_company",
        "dwd_special_taiwan_company",
    }
)

# 旧 ensure_schema 补齐的边属性（类型与旧 SHARED_EDGE_PROPERTIES 一致）。
EDGE_PROPERTY_SCHEMAS: dict[str, dict[str, str]] = {
    "INVENTED_BY": {
        "sequence": "int64",
        "source_name": "string",
        "confidence": "double",
        "subject_type": "string",
        "resolution_status": "string",
        "match_method": "string",
        "match_evidence": "string",
        "source_table": "string",
        "source_record_id": "string",
    },
    "APPLIED_BY": {
        "sequence": "int64",
        "role": "string",
        "source_name": "string",
        "confidence": "double",
        "subject_type": "string",
        "resolution_status": "string",
        "match_method": "string",
        "match_evidence": "string",
        "source_table": "string",
        "source_record_id": "string",
    },
    "OWNED_BY": {
        "sequence": "int64",
        "role": "string",
        "is_current": "bool",
        "source_name": "string",
        "confidence": "double",
        "subject_type": "string",
        "resolution_status": "string",
        "match_method": "string",
        "match_evidence": "string",
        "source_table": "string",
        "source_record_id": "string",
    },
    "CITES": {
        "reference_identifier": "string",
        "sequence": "int64",
        "confidence": "double",
        "match_method": "string",
        "match_evidence": "string",
        "source_table": "string",
        "source_record_id": "string",
    },
}


@dataclass
class ReviewRecord:
    patent_id: str
    relation_type: str
    source_name: str
    reason: str
    confidence: float | None
    candidates: list[dict[str, Any]]
    evidence: list[str]
    patent_vid: str = ""
    sequence: int = 0
    role: str = ""
    is_current: bool | None = None
    source_record_id: str = ""


def normalize_name(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return NAME_CLEAN_RE.sub("", text)


def normalize_identifier(value: Any) -> str:
    """关系识别时临时规范化编号，不写入Patent属性。"""
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return IDENTIFIER_CLEAN_RE.sub("", text)


def application_number_key(value: Any) -> str:
    """关系识别时统一中国申请号的供应商格式。"""
    key = normalize_identifier(value)
    matched = CN_APPLICATION_RE.fullmatch(key)
    return f"cn{matched.group(1)}" if matched else key


def parse_json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def fetch_all(
    engine: Engine, sql: str, params: Mapping[str, Any] | None = None
) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(text(sql), dict(params or {})).mappings().all()
        return [dict(row) for row in rows]


def graph_catalog(graph: TRSGraphClient, tag: str, fields: Iterable[str]) -> list[dict[str, Any]]:
    projections = ["id(v) AS vid", *(f"v.{tag}.{field} AS {field}" for field in fields)]
    return list(graph.execute_read(f"MATCH (v:{tag}) RETURN {','.join(projections)}").records)


def names_from(value: Any) -> set[str]:
    parsed = parse_json(value, value)
    values: list[Any]
    if isinstance(parsed, list):
        values = parsed
    else:
        values = re.split(r"[;,；，|/]", str(parsed or ""))
    result = set()
    for item in values:
        if isinstance(item, dict):
            item = item.get("name") or item.get("institution") or item.get("org_name") or ""
        key = normalize_name(item)
        if key:
            result.add(key)
    return result


def party_items(value: Any) -> list[dict[str, Any]]:
    parsed = parse_json(value, [])
    return [
        item for item in parsed if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]


def make_index(
    rows: list[dict[str, Any]], fields: Iterable[str]
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        seen = set()
        for field in fields:
            keys = (
                names_from(row.get(field))
                if field == "name_alias"
                else {normalize_name(row.get(field))}
            )
            for key in keys:
                if key and key not in seen:
                    result[key].append(row)
                    seen.add(key)
    return result


def identifier_index(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        for field in ("patent_id", "publication_number", "application_number", "granted_number"):
            key = (
                application_number_key(row.get(field))
                if field == "application_number"
                else normalize_identifier(row.get(field))
            )
            if key and str(row["vid"]) not in result[key]:
                result[key].append(str(row["vid"]))
    return result


def patent_candidates(index: dict[str, list[str]], value: Any) -> list[str]:
    """同时按通用编号和申请号格式查找，并对候选VID去重。"""
    keys = {normalize_identifier(value), application_number_key(value)} - {""}
    return list(dict.fromkeys(vid for key in keys for vid in index.get(key, [])))


def is_canonical_organization(row: dict[str, Any]) -> bool:
    """只按节点来源判断是否为机构领域正式节点。"""
    return str(row.get("source_table") or "") in CANONICAL_ORGANIZATION_SOURCE_TABLES


def patent_indexes(
    graph: TRSGraphClient, engine: Engine
) -> tuple[dict[str, str], dict[str, list[str]]]:
    """旧 build_relations 的专利侧索引：图内 Patent 限定在 dwd_patent.patent_id 集合内。"""
    patents = graph_catalog(
        graph, "Patent", ("patent_id", "publication_number", "application_number", "granted_number")
    )
    source_patent_ids = {
        str(row["patent_id"]) for row in fetch_all(engine, "SELECT patent_id FROM dwd_patent")
    }
    patents = [row for row in patents if str(row.get("patent_id") or "") in source_patent_ids]
    vid_by_id = {str(row["patent_id"]): str(row["vid"]) for row in patents}
    return vid_by_id, identifier_index(patents)


def canonical_entities(
    graph: TRSGraphClient, engine: Engine
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """图内 Person（限 source_table=dwd_scholar，dwd_scholar 行补充机构经历）
    与正式机构域 Organization 候选（含真实 VID）。"""
    graph_people = graph_catalog(
        graph,
        "Person",
        (
            "name_zh",
            "name_en",
            "scholar_org",
            "source_table",
            "source_record_id",
            "organization_base",
            "organization_id",
        ),
    )
    graph_orgs = graph_catalog(
        graph,
        "Organization",
        (
            "name_cn",
            "name_en",
            "name_alias",
            "source_system",
            "source_table",
            "source_record_id",
            "org_id",
            "organization_base",
            "organization_id",
        ),
    )
    people = fetch_all(
        engine,
        """
        SELECT scholar_id,name_zh,name_en,scholar_org_name_zh,scholar_org_name_en,
               work_experience_institution_zh,work_experience_institution_en
        FROM dwd_scholar
    """,
    )
    people_by_id = {str(row["scholar_id"]): row for row in people}
    resolved_people = []
    for node in graph_people:
        if str(node.get("source_table") or "") != "dwd_scholar":
            continue
        # Person是否进入候选只由其正式来源和图中姓名决定。source_record_id
        # 仅在恰好能定位同源学者记录时补充机构经历，不能作为过滤条件。
        source = people_by_id.get(str(node.get("source_record_id") or ""), {})
        person = dict(
            source,
            vid=str(node["vid"]),
            name_zh=node.get("name_zh") or source.get("name_zh"),
            name_en=node.get("name_en") or source.get("name_en"),
            scholar_org=node.get("scholar_org"),
            source_table=node.get("source_table"),
            source_record_id=node.get("source_record_id"),
            organization_base=node.get("organization_base"),
            organization_id=node.get("organization_id"),
        )
        if person.get("name_zh") or person.get("name_en"):
            resolved_people.append(person)
    # 专利侧只有名称，不能拿 source_record_id、org_id 等ID做跨域匹配。
    # source_table 仅用于排除其他数据域创建的临时机构；名称用于识别，
    # 图查询返回的真实VID仅在最终写边时使用。
    resolved_orgs = [
        {
            "vid": str(node["vid"]),
            "name_cn": node.get("name_cn"),
            "name_en": node.get("name_en"),
            "name_alias": node.get("name_alias"),
            "source_system": node.get("source_system"),
            "source_table": node.get("source_table"),
            "source_record_id": node.get("source_record_id"),
            "org_id": node.get("org_id"),
            "organization_base": node.get("organization_base"),
            "organization_id": node.get("organization_id"),
        }
        for node in graph_orgs
        if is_canonical_organization(node)
    ]
    return resolved_people, resolved_orgs


def project_evidence_context(
    graph: TRSGraphClient, engine: Engine, patent_index: dict[str, list[str]]
) -> dict[str, set[str]]:
    """旧 project_context 的证据部分：patent_vid → 项目 host/参与机构名集合。

    只为图内已有 Project 的产出行累积证据（项目缺失整行跳过，与旧一致）；
    OUTPUT_OF 边本身由项目域脚本承接，不在本函数产出。
    """
    graph_projects = graph_catalog(graph, "Project", ("source_table", "source_record_id"))
    project_vid_by_source = {
        (
            str(row.get("source_table") or ""),
            str(row.get("source_record_id") or ""),
        ): str(row["vid"])
        for row in graph_projects
        if row.get("source_table") and row.get("source_record_id") not in (None, "")
    }
    context: dict[str, set[str]] = defaultdict(set)
    for main_table, output_table in (
        ("dwd_zh_project", "dwd_zh_project_output"),
        ("dwd_en_project", "dwd_en_project_output"),
    ):
        rows = fetch_all(
            engine,
            f"""
            SELECT p.id,p.project_host,p.participants,p.funded_institution,p.participating_institution,o.output_patents
            FROM {main_table} p JOIN {output_table} o ON o.id=p.id
            WHERE o.output_patents IS NOT NULL
        """,
        )
        for row in rows:
            project_vid = project_vid_by_source.get((main_table, str(row["id"])))
            if not project_vid:
                continue
            evidence_names = set()
            for field in (
                "project_host",
                "participants",
                "funded_institution",
                "participating_institution",
            ):
                evidence_names.update(names_from(row.get(field)))
            for item in parse_json(row.get("output_patents"), []):
                if not isinstance(item, dict):
                    continue
                identifier = str(
                    item.get("patent_number") or item.get("publication_number") or ""
                ).strip()
                candidates = patent_candidates(patent_index, identifier)
                if len(candidates) != 1:
                    continue
                context[candidates[0]].update(evidence_names)
    return context


def candidate_view(row: dict[str, Any], entity_type: str) -> dict[str, Any]:
    if entity_type == "Person":
        return {
            "vid": row["vid"],
            "type": entity_type,
            "name_zh": row.get("name_zh"),
            "name_en": row.get("name_en"),
            "organization": row.get("scholar_org_name_zh") or row.get("scholar_org_name_en"),
        }
    return {
        "vid": row["vid"],
        "type": entity_type,
        "name": row.get("name_cn") or row.get("name_en"),
        "alias": row.get("name_alias"),
        "organization_base": row.get("organization_base"),
        "organization_id": row.get("organization_id"),
    }


def person_org_names(row: dict[str, Any]) -> set[str]:
    result = set()
    for field in (
        "scholar_org_name_zh",
        "scholar_org_name_en",
        "work_experience_institution_zh",
        "work_experience_institution_en",
        "scholar_org",
    ):
        result.update(names_from(row.get(field)))
    return result


def party_properties(
    sequence: int,
    role: str,
    source_name: str,
    confidence: float,
    subject_type: str,
    method: str,
    evidence: str,
    source_id: str,
    current: bool | None = None,
) -> dict[str, Any]:
    """旧 common_party_properties（元组顺序改为 dict 顺序）。"""
    props: dict[str, Any] = {"sequence": sequence, "role": role}
    if current is not None:
        props["is_current"] = current
    props.update(
        {
            "source_name": source_name,
            "confidence": confidence,
            "subject_type": subject_type,
            "resolution_status": "automatic",
            "match_method": method,
            "match_evidence": evidence,
            "source_table": "dwd_patent",
            "source_record_id": source_id,
        }
    )
    return props


def make_edge_deduper():
    """旧 deduplicate_edges 的流式等价：按 (edge,src,dst,rank) 记录最高置信度。

    首条胜出（与旧口径一致）；后续更高置信度的同键记录再次写入，rank 模式
    INSERT EDGE @rank 覆盖更新后图内最终状态与旧去重结果一致。
    """
    best: dict[tuple[str, str, str, int], float] = {}

    def accept(record: EdgeRecord) -> EdgeRecord | None:
        key = (record.edge_type, record.source_vid, record.target_vid, record.rank)
        confidence = float(record.properties.get("confidence") or 0)
        if key in best and confidence <= best[key]:
            return None
        best[key] = confidence
        return record

    return accept


def write_reviews(path: Path, reviews: list[ReviewRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(asdict(item), ensure_ascii=False) + "\n" for item in reviews),
        encoding="utf-8",
    )
