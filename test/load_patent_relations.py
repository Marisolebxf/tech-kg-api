"""从科技要素库抽取专利出发的有向关系并写入配置的TRSGraph图空间。"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pymysql
from pymysql.cursors import DictCursor
from dotenv import load_dotenv

TEST_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = TEST_DIR.parent / "backend"
load_dotenv(BACKEND_ROOT / ".env")
load_dotenv(TEST_DIR / "config.env", override=True)
GRAPH_SPACE = os.getenv("TRS_GRAPH_SPACE", "test").strip() or "test"

from infra.graph_db import get_trs_graph_client
from infra.milvus import OrganizationMilvusStore
from service.organization_entity_alignment import (
    BM25SparseEncoder,
    HashingDenseEncoder,
    OrganizationAlignmentContext,
    OrganizationHybridMatcher,
)

logger = logging.getLogger(__name__)
DDL_FILE = BACKEND_ROOT / "schemas" / "ddl" / "patent_relation_ddl.ngql"
NAME_CLEAN_RE = re.compile(r"[^0-9a-z\u4e00-\u9fff]+")
IDENTIFIER_CLEAN_RE = re.compile(r"[^0-9a-z]+")
CN_APPLICATION_RE = re.compile(r"^(?:cn|zl)?(\d{12})(?:[a-z]|\d)?$")
PERSON_EDGE_TYPES = {"INVENTED_BY", "APPLIED_BY", "OWNED_BY"}
ALL_EDGE_TYPES = ("INVENTED_BY", "APPLIED_BY", "OWNED_BY", "CITES", "OUTPUT_OF")
DEFAULT_VECTOR_STATE_DIR = Path(".cache/organization_milvus")
DEFAULT_VECTOR_THRESHOLD = 0.88
DEFAULT_VECTOR_MARGIN = 0.08
DEFAULT_VECTOR_TOP_K = 20

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

SHARED_EDGE_PROPERTIES = {
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
    "OUTPUT_OF": {
        "source_table": "string",
        "source_record_id": "string",
        "confidence": "double",
        "match_method": "string",
        "match_evidence": "string",
    },
}


@dataclass(frozen=True)
class EdgeRecord:
    edge_type: str
    source_vid: str
    target_vid: str
    rank: int
    properties: tuple[tuple[str, Any], ...]


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


def ngql_string(value: Any) -> str:
    text = "" if value is None else str(value)
    escaped = (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def ngql_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return ngql_string(value)


def mysql_connection() -> pymysql.Connection:
    password = os.getenv("PATENT_MYSQL_PASSWORD") or os.getenv("MYSQL_PASSWORD")
    if password is None:
        raise RuntimeError("缺少 PATENT_MYSQL_PASSWORD 环境变量")
    return pymysql.connect(
        host=os.getenv("PATENT_MYSQL_HOST") or os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("PATENT_MYSQL_PORT") or os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("PATENT_MYSQL_USERNAME") or os.getenv("MYSQL_USERNAME", "root"),
        password=password,
        database=os.getenv("PATENT_MYSQL_DATABASE") or os.getenv("MYSQL_DATABASE", "gkx_element"),
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=True,
    )


def graph_catalog(
    graph: Any, tag: str, fields: Iterable[str], *, optional: bool = False
) -> list[dict[str, Any]]:
    projections = ["id(v) AS vid", *(f"v.{tag}.{field} AS {field}" for field in fields)]
    try:
        return list(
            graph.execute_read(f"MATCH (v:{tag}) RETURN {','.join(projections)}").records
        )
    except Exception as exc:
        if optional and "Unknown tag" in str(getattr(exc, "body", "")):
            logger.info("可选图实体 %s 不存在，按空目录处理", tag)
            return []
        raise


def fetch_all(connection: pymysql.Connection, sql: str) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(sql)
        return list(cursor.fetchall())


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


def edge_statement(edge_type: str, rows: list[EdgeRecord]) -> str:
    if not rows:
        return ""
    names = [name for name, _ in rows[0].properties]
    values = []
    for row in rows:
        props = ",".join(ngql_value(value) for _, value in row.properties)
        values.append(
            f"{ngql_string(row.source_vid)}->{ngql_string(row.target_vid)}@{row.rank}:({props})"
        )
    return f"INSERT EDGE {edge_type}({','.join(names)}) VALUES {','.join(values)};"


def execute_batched(
    graph: Any, rows: list[Any], builder: Callable[[list[Any]], str], batch_size: int = 50
) -> None:
    def write_batch(batch: list[Any]) -> None:
        statement = builder(batch)
        if not statement:
            return
        try:
            graph.execute_write(statement)
        except Exception:
            if len(batch) == 1:
                raise
            middle = len(batch) // 2
            write_batch(batch[:middle])
            write_batch(batch[middle:])

    for start in range(0, len(rows), batch_size):
        write_batch(rows[start : start + batch_size])


def ensure_schema(graph: Any) -> None:
    ddl = DDL_FILE.read_text(encoding="utf-8")
    for statement in re.findall(r"CREATE\s+EDGE\b.*?;", ddl, flags=re.I | re.S):
        graph.execute_write(statement)
    # 全新图空间可能没有 dev 中预先存在的共享边。
    for edge_type, properties in SHARED_EDGE_PROPERTIES.items():
        fields = ",".join(f"{name} {kind}" for name, kind in properties.items())
        graph.execute_write(f"CREATE EDGE IF NOT EXISTS {edge_type} ({fields});")
    time.sleep(2)
    for edge_type, wanted in SHARED_EDGE_PROPERTIES.items():
        existing = {
            str(row["Field"]) for row in graph.execute_read(f"DESCRIBE EDGE {edge_type}").records
        }
        missing = [(name, kind) for name, kind in wanted.items() if name not in existing]
        if missing:
            graph.execute_write(
                f"ALTER EDGE {edge_type} ADD ({','.join(f'{n} {k}' for n, k in missing)});"
            )
    for edge_type in ALL_EDGE_TYPES:
        wanted = set(SHARED_EDGE_PROPERTIES.get(edge_type, {}))
        for attempt in range(15):
            try:
                visible = {
                    str(row["Field"])
                    for row in graph.execute_read(f"DESCRIBE EDGE {edge_type}").records
                }
                if wanted <= visible:
                    break
            except Exception:
                if attempt == 14:
                    raise
            if attempt == 14:
                raise RuntimeError(f"{edge_type}新属性未在TRSGraph中生效")
            time.sleep(1)


def canonical_entities(
    graph: Any, connection: pymysql.Connection
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
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
        connection,
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


def project_context(
    graph: Any, connection: pymysql.Connection, patent_index: dict[str, list[str]]
) -> tuple[dict[str, set[str]], list[EdgeRecord], Counter[str]]:
    graph_projects = graph_catalog(
        graph, "Project", ("source_table", "source_record_id"), optional=True
    )
    project_vid_by_source = {
        (
            str(row.get("source_table") or ""),
            str(row.get("source_record_id") or ""),
        ): str(row["vid"])
        for row in graph_projects
        if row.get("source_table") and row.get("source_record_id") not in (None, "")
    }
    context: dict[str, set[str]] = defaultdict(set)
    edges: list[EdgeRecord] = []
    stats: Counter[str] = Counter()
    for main_table, output_table in (
        ("dwd_zh_project", "dwd_zh_project_output"),
        ("dwd_en_project", "dwd_en_project_output"),
    ):
        rows = fetch_all(
            connection,
            f"""
            SELECT p.id,p.project_host,p.participants,p.funded_institution,p.participating_institution,o.output_patents
            FROM {main_table} p JOIN {output_table} o ON o.id=p.id
            WHERE o.output_patents IS NOT NULL
        """,
        )
        for row in rows:
            project_vid = project_vid_by_source.get((main_table, str(row["id"])))
            if not project_vid:
                stats["OUTPUT_OF:missing_project"] += 1
                continue
            evidence_names = set()
            for field in (
                "project_host",
                "participants",
                "funded_institution",
                "participating_institution",
            ):
                evidence_names.update(names_from(row.get(field)))
            for sequence, item in enumerate(parse_json(row.get("output_patents"), []), start=1):
                if not isinstance(item, dict):
                    continue
                identifier = str(
                    item.get("patent_number") or item.get("publication_number") or ""
                ).strip()
                candidates = patent_candidates(patent_index, identifier)
                if len(candidates) != 1:
                    stats["OUTPUT_OF:unmatched_or_ambiguous_patent"] += 1
                    continue
                patent_vid = candidates[0]
                context[patent_vid].update(evidence_names)
                edges.append(
                    EdgeRecord(
                        "OUTPUT_OF",
                        patent_vid,
                        project_vid,
                        sequence,
                        (
                            ("source_table", output_table),
                            ("source_record_id", f"{row['id']}:output_patents:{sequence}"),
                            ("confidence", 1.0),
                            ("match_method", "exact_patent_identifier_and_project_id"),
                            (
                                "match_evidence",
                                "项目产出专利号与现有Patent唯一匹配，项目ID对应现有Project",
                            ),
                        ),
                    )
                )
                stats["OUTPUT_OF:exact"] += 1
    return context, edges, stats


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


def review(
    patent_id: str,
    relation: str,
    source_name: str,
    reason: str,
    confidence: float | None,
    candidates: list[dict[str, Any]],
    evidence: list[str],
    **context: Any,
) -> ReviewRecord:
    return ReviewRecord(
        patent_id, relation, source_name, reason, confidence, candidates, evidence, **context
    )


def common_party_properties(
    sequence: int,
    role: str,
    source_name: str,
    confidence: float,
    subject_type: str,
    method: str,
    evidence: str,
    source_id: str,
    current: bool | None = None,
) -> tuple[tuple[str, Any], ...]:
    props: list[tuple[str, Any]] = [("sequence", sequence), ("role", role)]
    if current is not None:
        props.append(("is_current", current))
    props.extend(
        (
            ("source_name", source_name),
            ("confidence", confidence),
            ("subject_type", subject_type),
            ("resolution_status", "automatic"),
            ("match_method", method),
            ("match_evidence", evidence),
            ("source_table", "dwd_patent"),
            ("source_record_id", source_id),
        )
    )
    return tuple(props)


def build_relations(
    graph: Any, connection: pymysql.Connection
) -> tuple[list[EdgeRecord], list[ReviewRecord], Counter[str]]:
    patents = graph_catalog(
        graph, "Patent", ("patent_id", "publication_number", "application_number", "granted_number")
    )
    source_patent_ids = {
        str(row["patent_id"]) for row in fetch_all(connection, "SELECT patent_id FROM dwd_patent")
    }
    patents = [row for row in patents if str(row.get("patent_id") or "") in source_patent_ids]
    patent_vid_by_id = {str(row["patent_id"]): str(row["vid"]) for row in patents}
    patent_index = identifier_index(patents)
    patent_vids = {str(row["vid"]) for row in patents}
    people, organizations = canonical_entities(graph, connection)
    person_index = make_index(people, ("name_zh", "name_en"))
    org_index = make_index(organizations, ("name_cn", "name_en", "name_alias"))
    project_evidence, output_edges, stats = project_context(graph, connection, patent_index)
    edges = list(output_edges)
    reviews: list[ReviewRecord] = []

    rows = fetch_all(
        connection, "SELECT id,patent_id,inventors,applicants,assignees FROM dwd_patent"
    )
    for row in rows:
        patent_vid = patent_vid_by_id.get(str(row["patent_id"]))
        if not patent_vid or patent_vid not in patent_vids:
            stats["party:missing_patent"] += 1
            continue
        confirmed_org_names: set[str] = set()
        party_cache: dict[tuple[str, int], tuple[str, dict[str, Any]] | None] = {}
        for column in ("applicants", "assignees"):
            for item in party_items(row.get(column)):
                name = str(item["name"]).strip()
                sequence = int(item.get("sequence") or 0)
                org_candidates = org_index.get(normalize_name(name), [])
                if len(org_candidates) == 1:
                    party_cache[(column, sequence)] = ("Organization", org_candidates[0])
                    confirmed_org_names.update(names_from(name))
                elif len(org_candidates) > 1:
                    party_cache[(column, sequence)] = None
                    reviews.append(
                        review(
                            str(row["patent_id"]),
                            "APPLIED_BY" if column == "applicants" else "OWNED_BY",
                            name,
                            "机构名称命中多个已有机构",
                            None,
                            [candidate_view(c, "Organization") for c in org_candidates],
                            ["机构名称精确匹配但不唯一"],
                            patent_vid=patent_vid,
                            sequence=sequence,
                            role="applicant" if column == "applicants" else "assignee",
                            is_current=True if column == "assignees" else None,
                            source_record_id=f"{row['id']}:{column}:{sequence}",
                        )
                    )
                else:
                    person_candidates = person_index.get(normalize_name(name), [])
                    party_cache[(column, sequence)] = None
                    reason = (
                        "名称可能是个人，但只有姓名证据"
                        if person_candidates
                        else "名称未精确命中已有机构或人才"
                    )
                    reviews.append(
                        review(
                            str(row["patent_id"]),
                            "APPLIED_BY" if column == "applicants" else "OWNED_BY",
                            name,
                            reason,
                            0.60 if len(person_candidates) == 1 else None,
                            [candidate_view(c, "Person") for c in person_candidates],
                            ["申请人/权利人源字段只有sequence和name"],
                            patent_vid=patent_vid,
                            sequence=sequence,
                            role="applicant" if column == "applicants" else "assignee",
                            is_current=True if column == "assignees" else None,
                            source_record_id=f"{row['id']}:{column}:{sequence}",
                        )
                    )

        for item in party_items(row.get("inventors")):
            name = str(item["name"]).strip()
            sequence = int(item.get("sequence") or 0)
            candidates = person_index.get(normalize_name(name), [])
            scored: list[tuple[dict[str, Any], bool, bool]] = []
            for candidate in candidates:
                org_hit = bool(confirmed_org_names & person_org_names(candidate))
                project_hit = normalize_name(name) in project_evidence.get(
                    patent_vid, set()
                ) or bool(person_org_names(candidate) & project_evidence.get(patent_vid, set()))
                scored.append((candidate, org_hit, project_hit))
            strong = [item_ for item_ in scored if item_[1]]
            if len(strong) == 1:
                candidate, _, project_hit = strong[0]
                confidence = 0.90 if project_hit else 0.80
                evidence = (
                    "姓名和任职机构精确一致，且项目人员/机构信息一致"
                    if project_hit
                    else "姓名和任职机构精确一致且候选唯一"
                )
                edges.append(
                    EdgeRecord(
                        "INVENTED_BY",
                        patent_vid,
                        str(candidate["vid"]),
                        sequence,
                        (
                            ("sequence", sequence),
                            ("source_name", name),
                            ("confidence", confidence),
                            ("subject_type", "Person"),
                            ("resolution_status", "automatic"),
                            (
                                "match_method",
                                "exact_name_org_project" if project_hit else "exact_name_org",
                            ),
                            ("match_evidence", evidence),
                            ("source_table", "dwd_patent"),
                            ("source_record_id", f"{row['id']}:inventors:{sequence}"),
                        ),
                    )
                )
                stats[f"INVENTED_BY:{confidence:.2f}"] += 1
            else:
                reason = (
                    "同名候选仍有多个"
                    if len(candidates) > 1
                    else "只有姓名证据"
                    if len(candidates) == 1
                    else "人才表未找到同名人员"
                )
                reviews.append(
                    review(
                        str(row["patent_id"]),
                        "INVENTED_BY",
                        name,
                        reason,
                        0.60 if len(candidates) == 1 else None,
                        [candidate_view(c, "Person") for c in candidates],
                        ["姓名精确匹配", "申请/权利机构和项目证据未能唯一确认"]
                        if candidates
                        else ["无姓名精确候选"],
                        patent_vid=patent_vid,
                        sequence=sequence,
                        role="inventor",
                        source_record_id=f"{row['id']}:inventors:{sequence}",
                    )
                )
                stats["INVENTED_BY:review"] += 1

        for column, edge_type, role, current in (
            ("applicants", "APPLIED_BY", "applicant", None),
            ("assignees", "OWNED_BY", "assignee", True),
        ):
            for item in party_items(row.get(column)):
                sequence = int(item.get("sequence") or 0)
                cached = party_cache.get((column, sequence))
                if not cached:
                    stats[f"{edge_type}:review"] += 1
                    continue
                subject_type, candidate = cached
                name = str(item["name"]).strip()
                edges.append(
                    EdgeRecord(
                        edge_type,
                        patent_vid,
                        str(candidate["vid"]),
                        sequence,
                        common_party_properties(
                            sequence,
                            role,
                            name,
                            0.98,
                            subject_type,
                            "exact_unique_organization_name",
                            "机构名称或别名与dev已有Organization精确匹配且候选唯一",
                            f"{row['id']}:{column}:{sequence}",
                            current,
                        ),
                    )
                )
                stats[f"{edge_type}:0.98"] += 1

    cited_rows = fetch_all(
        connection, "SELECT id,patent_id,patent_citations,cited_by FROM dwd_patent_cited"
    )
    for row in cited_rows:
        current = patent_candidates(patent_index, row["patent_id"])
        if len(current) != 1:
            stats["CITES:missing_source"] += 1
            continue
        for column in ("patent_citations", "cited_by"):
            for sequence, identifier in enumerate(parse_json(row.get(column), []), start=1):
                candidates = patent_candidates(patent_index, identifier)
                if len(candidates) != 1:
                    stats["CITES:unmatched_target"] += 1
                    continue
                source_vid, target_vid = (
                    (current[0], candidates[0])
                    if column == "patent_citations"
                    else (candidates[0], current[0])
                )
                if source_vid == target_vid:
                    continue
                edges.append(
                    EdgeRecord(
                        "CITES",
                        source_vid,
                        target_vid,
                        sequence,
                        (
                            ("reference_identifier", str(identifier)),
                            ("sequence", sequence),
                            ("confidence", 1.0),
                            ("match_method", "exact_patent_identifier"),
                            ("match_evidence", "引用专利号与现有Patent唯一精确匹配"),
                            ("source_table", "dwd_patent_cited"),
                            ("source_record_id", f"{row['id']}:{column}:{sequence}"),
                        ),
                    )
                )
                stats["CITES:exact"] += 1
    return edges, reviews, stats


def _json_object(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def promote_vector_organization_matches(
    reviews: list[ReviewRecord],
    *,
    threshold: float = DEFAULT_VECTOR_THRESHOLD,
    margin: float = DEFAULT_VECTOR_MARGIN,
    top_k: int = DEFAULT_VECTOR_TOP_K,
    state_dir: Path | None = None,
    store: OrganizationMilvusStore | None = None,
    valid_organization_vids: set[str] | None = None,
) -> tuple[list[EdgeRecord], list[ReviewRecord]]:
    """Promote only unique threshold-and-margin-qualified Milvus matches."""

    def eligible(item: ReviewRecord) -> bool:
        if item.relation_type not in {"APPLIED_BY", "OWNED_BY"}:
            return False
        candidate_types = {str(candidate.get("type")) for candidate in item.candidates}
        if candidate_types and candidate_types <= {"Person"}:
            item.reason = "申请人/权利人匹配到人才候选，禁止使用机构向量索引跨类型自动建边"
            if "entity_type_guard=Person" not in item.evidence:
                item.evidence.append("entity_type_guard=Person")
            return False
        return not candidate_types or not candidate_types <= {"Person"}

    if not any(eligible(item) for item in reviews):
        return [], reviews
    vector_store = store or OrganizationMilvusStore()
    owns_store = store is None
    try:
        if not vector_store.has_collection("Organization"):
            raise RuntimeError(
                "Organization Milvus index is missing; run "
                "python -m script.organization_milvus_index --entity Organization --write"
            )
        resolved_state = Path(
            state_dir or os.getenv("ORG_MILVUS_STATE_DIR") or DEFAULT_VECTOR_STATE_DIR
        ).resolve()
        model_path = resolved_state / f"{vector_store.collection_name('Organization')}.bm25.json"
        if not model_path.exists():
            raise RuntimeError(f"Organization BM25 state is missing: {model_path}")
        matcher = OrganizationHybridMatcher(
            vector_store,
            BM25SparseEncoder.load(model_path),
            HashingDenseEncoder(384),
            threshold=threshold,
            margin=margin,
            top_k=top_k,
        )
        promoted: list[EdgeRecord] = []
        remaining: list[ReviewRecord] = []
        decision_cache: dict[str, Any] = {}
        for item in reviews:
            if not eligible(item):
                remaining.append(item)
                continue
            cache_key = normalize_name(item.source_name)
            decision = decision_cache.get(cache_key)
            if decision is None:
                decision = matcher.align(
                    OrganizationAlignmentContext(
                        name=item.source_name,
                        source_table="dwd_patent",
                        source_record_id=item.source_record_id,
                    )
                )
                decision_cache[cache_key] = decision
            item.candidates = [
                {
                    "vid": candidate.vid,
                    "type": "Organization",
                    "name": candidate.canonical_name,
                    "vector_score": round(candidate.score, 4),
                    "retrieval_score": round(candidate.retrieval_score, 4),
                    "evidence": list(candidate.evidence),
                }
                for candidate in decision.candidates
            ]
            item.evidence.append(
                f"milvus_status={decision.status};score={decision.score:.4f};"
                f"margin={decision.margin:.4f};reason={decision.reason}"
            )
            if decision.status != "matched" or not decision.selected_vid:
                item.reason = "Milvus candidate failed score, uniqueness, or margin policy"
                item.confidence = decision.score or None
                remaining.append(item)
                continue
            if (
                valid_organization_vids is not None
                and decision.selected_vid not in valid_organization_vids
            ):
                item.reason = "Milvus候选VID不在当前图空间，禁止跨图空间写边"
                item.confidence = decision.score or None
                item.evidence.append("target_endpoint_missing_in_current_graph_space")
                remaining.append(item)
                continue
            confidence = round(decision.score, 4)
            promoted.append(
                EdgeRecord(
                    item.relation_type,
                    item.patent_vid,
                    decision.selected_vid,
                    item.sequence,
                    common_party_properties(
                        item.sequence,
                        item.role,
                        item.source_name,
                        confidence,
                        "Organization",
                        "milvus_bm25_dense_hybrid",
                        f"score={decision.score:.4f};margin={decision.margin:.4f};{decision.reason}",
                        item.source_record_id,
                        item.is_current,
                    ),
                )
            )
        return promoted, remaining
    finally:
        if owns_store:
            vector_store.close()


def deduplicate_edges(rows: list[EdgeRecord]) -> tuple[list[EdgeRecord], int]:
    """按逻辑关系去重；引用和项目产出不因来源数组序号重复建边。"""
    selected: dict[tuple[str, str, str, int], EdgeRecord] = {}
    for row in rows:
        logical_rank = 0 if row.edge_type in {"CITES", "OUTPUT_OF"} else row.rank
        key = (row.edge_type, row.source_vid, row.target_vid, logical_rank)
        previous = selected.get(key)
        if previous is None:
            selected[key] = (
                row
                if logical_rank == row.rank
                else EdgeRecord(
                    row.edge_type, row.source_vid, row.target_vid, logical_rank, row.properties
                )
            )
            continue
        previous_confidence = float(dict(previous.properties).get("confidence") or 0)
        current_confidence = float(dict(row.properties).get("confidence") or 0)
        if current_confidence > previous_confidence:
            selected[key] = EdgeRecord(
                row.edge_type, row.source_vid, row.target_vid, logical_rank, row.properties
            )
    return list(selected.values()), len(rows) - len(selected)


def write_reviews(path: Path, reviews: list[ReviewRecord]) -> None:
    path.write_text(
        "".join(json.dumps(asdict(item), ensure_ascii=False) + "\n" for item in reviews),
        encoding="utf-8",
    )


def existing_edge_keys(graph: Any, edge_type: str) -> list[tuple[str, str, int]]:
    query = f"MATCH (s:Patent)-[e:{edge_type}]->(t) RETURN id(s) AS src,id(t) AS dst,rank(e) AS edge_rank"
    return [
        (str(r["src"]), str(r["dst"]), int(r["edge_rank"]))
        for r in graph.execute_read(query).records
    ]


def replace_existing_edges(graph: Any) -> Counter[str]:
    stats: Counter[str] = Counter()
    for edge_type in ALL_EDGE_TYPES:
        rows = existing_edge_keys(graph, edge_type)
        for start in range(0, len(rows), 10):
            values = ",".join(
                f"{ngql_string(src)}->{ngql_string(dst)}@{rank}"
                for src, dst, rank in rows[start : start + 10]
            )
            if values:
                graph.execute_write(f"DELETE EDGE {edge_type} {values};")
        stats[f"{edge_type}:replaced"] = len(rows)
    return stats


def load(
    apply: bool,
    replace: bool = False,
    review_output: Path | None = None,
    use_vector: bool = True,
    vector_threshold: float = DEFAULT_VECTOR_THRESHOLD,
    vector_margin: float = DEFAULT_VECTOR_MARGIN,
    vector_top_k: int = DEFAULT_VECTOR_TOP_K,
    vector_state_dir: Path | None = None,
) -> Counter[str]:
    if replace and not apply:
        raise ValueError("replace=True 必须同时设置 apply=True")
    if not 0 <= vector_threshold <= 1:
        raise ValueError("vector_threshold 必须在 0 到 1 之间")
    if not 0 <= vector_margin <= 1:
        raise ValueError("vector_margin 必须在 0 到 1 之间")
    if vector_top_k < 2:
        raise ValueError("vector_top_k 必须大于等于 2")
    os.environ["TRS_GRAPH_SPACE"] = GRAPH_SPACE
    graph = get_trs_graph_client()
    connection = mysql_connection()
    try:
        edges, reviews, stats = build_relations(graph, connection)
        if use_vector and reviews:
            valid_organization_vids = {
                str(row["vid"]) for row in graph_catalog(graph, "Organization", ())
            }
            vector_edges, reviews = promote_vector_organization_matches(
                reviews,
                threshold=vector_threshold,
                margin=vector_margin,
                top_k=vector_top_k,
                state_dir=vector_state_dir,
                valid_organization_vids=valid_organization_vids,
            )
            edges.extend(vector_edges)
            stats["milvus_hybrid_auto_edges"] = len(vector_edges)
        edges, duplicate_count = deduplicate_edges(edges)
        stats["duplicate_edges_removed"] = duplicate_count
        stats["review_records"] = len(reviews)
        if review_output:
            write_reviews(review_output, reviews)
        if not apply:
            return stats
        ensure_schema(graph)
        if replace:
            stats.update(replace_existing_edges(graph))
        grouped: dict[str, list[EdgeRecord]] = defaultdict(list)
        for edge in edges:
            grouped[edge.edge_type].append(edge)
        for edge_type, records in grouped.items():
            execute_batched(
                graph, records, lambda batch, kind=edge_type: edge_statement(kind, batch)
            )
            stats[f"{edge_type}:loaded"] = len(records)
        return stats
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="抽取并装载专利领域出发的有向关系")
    parser.add_argument(
        "--apply",
        action="store_true",
        help=f"实际写入{GRAPH_SPACE}；默认只分析",
    )
    parser.add_argument("--replace", action="store_true", help="写入前替换本加载器管理的旧关系")
    parser.add_argument("--review-output", type=Path, help="可选：输出待人工审核JSONL")
    parser.add_argument("--no-vector", action="store_true", help="仅用于诊断：跳过Milvus候选召回")
    parser.add_argument(
        "--vector-threshold",
        type=float,
        default=DEFAULT_VECTOR_THRESHOLD,
        help="Milvus候选自动建边最低综合分，默认0.88",
    )
    parser.add_argument(
        "--vector-margin",
        type=float,
        default=DEFAULT_VECTOR_MARGIN,
        help="第一与第二候选最低分差，默认0.08",
    )
    parser.add_argument(
        "--vector-top-k",
        type=int,
        default=DEFAULT_VECTOR_TOP_K,
        help="Milvus候选召回数量，默认20",
    )
    parser.add_argument("--vector-state-dir", type=Path, help="Organization BM25状态目录")
    args = parser.parse_args()
    if args.replace and not args.apply:
        parser.error("--replace必须与--apply一起使用")
    if not 0 <= args.vector_threshold <= 1:
        parser.error("--vector-threshold必须在0到1之间")
    if not 0 <= args.vector_margin <= 1:
        parser.error("--vector-margin必须在0到1之间")
    if args.vector_top_k < 2:
        parser.error("--vector-top-k必须大于等于2")
    logging.basicConfig(level=logging.INFO)
    for key, value in sorted(
        load(
            args.apply,
            args.replace,
            args.review_output,
            not args.no_vector,
            args.vector_threshold,
            args.vector_margin,
            args.vector_top_k,
            args.vector_state_dir,
        ).items()
    ):
        logger.info("%s=%d", key, value)


if __name__ == "__main__":
    main()
