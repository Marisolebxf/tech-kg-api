"""从科技要素库抽取专利出发的有向关系并通过公共能力写入TRSGraph dev。"""

from __future__ import annotations

import argparse
import difflib
import json
import logging
import os
import re
import time
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from infra.graph_db import get_trs_graph_client
from infra.llm import get_llm_client

logger = logging.getLogger(__name__)
DDL_FILE = Path(__file__).resolve().parents[1] / "schemas" / "ddl" / "patent_relation_ddl.ngql"
NAME_CLEAN_RE = re.compile(r"[^0-9a-z\u4e00-\u9fff]+")
IDENTIFIER_CLEAN_RE = re.compile(r"[^0-9a-z]+")
CN_APPLICATION_RE = re.compile(r"^(?:cn|zl)?(\d{12})(?:[a-z]|\d)?$")
PERSON_EDGE_TYPES = {"INVENTED_BY", "APPLIED_BY", "OWNED_BY"}
ALL_EDGE_TYPES = ("INVENTED_BY", "APPLIED_BY", "OWNED_BY", "CITES", "OUTPUT_OF")
LLM_CACHE_VERSION = "patent-org-alias-v1"

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
    llm_summary: str = ""
    llm_subject_type: str = ""
    llm_aliases: list[str] = dataclass_field(default_factory=list)
    llm_candidate_entities: list[dict[str, Any]] = dataclass_field(default_factory=list)
    llm_alias_matched_entities: list[dict[str, Any]] = dataclass_field(default_factory=list)
    llm_same_entity: bool = False
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


def graph_catalog(graph: Any, tag: str, fields: Iterable[str]) -> list[dict[str, Any]]:
    projections = ["id(v) AS vid", *(f"v.{tag}.{field} AS {field}" for field in fields)]
    return list(graph.execute_read(f"MATCH (v:{tag}) RETURN {','.join(projections)}").records)


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
        ("name_zh", "name_en", "scholar_org", "source_table", "source_record_id"),
    )
    graph_orgs = graph_catalog(
        graph,
        "Organization",
        ("name_cn", "name_en", "name_alias", "source_system", "source_table"),
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
        }
        for node in graph_orgs
        if is_canonical_organization(node)
    ]
    return resolved_people, resolved_orgs


def project_context(
    graph: Any, connection: pymysql.Connection, patent_index: dict[str, list[str]]
) -> tuple[dict[str, set[str]], list[EdgeRecord], Counter[str]]:
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
                            0.80,
                            subject_type,
                            "exact_unique_organization_name",
                            "机构名称或别名与dev已有Organization精确匹配且候选唯一",
                            f"{row['id']}:{column}:{sequence}",
                            current,
                        ),
                    )
                )
                stats[f"{edge_type}:0.80"] += 1

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


def _name_grams(value: str) -> set[str]:
    """字符与二元组索引兼顾中文简称、英文缩写和格式变化。"""
    if not value:
        return set()
    grams = {f"u:{char}" for char in value}
    grams.update(f"b:{value[index : index + 2]}" for index in range(len(value) - 1))
    return grams


class CandidateSearchIndex:
    """预计算实体名称倒排索引，避免每个源名称遍历全部实体。"""

    def __init__(self, people: list[dict[str, Any]], organizations: list[dict[str, Any]]) -> None:
        self.entries: list[tuple[set[str], dict[str, Any]]] = []
        self.postings: dict[str, list[int]] = defaultdict(list)
        for entity_type, rows, fields in (
            ("Organization", organizations, ("name_cn", "name_en", "name_alias")),
            ("Person", people, ("name_zh", "name_en")),
        ):
            for row in rows:
                variants = set()
                for field in fields:
                    variants.update(names_from(row.get(field)))
                if not variants:
                    continue
                entry_id = len(self.entries)
                self.entries.append((variants, candidate_view(row, entity_type)))
                for gram in set().union(*(_name_grams(name) for name in variants)):
                    self.postings[gram].append(entry_id)

    def shortlist(self, name: str, limit: int = 8, prefilter: int = 50) -> list[dict[str, Any]]:
        key = normalize_name(name)
        overlap: Counter[int] = Counter()
        for gram in _name_grams(key):
            overlap.update(self.postings.get(gram, ()))
        entry_ids = [entry_id for entry_id, _ in overlap.most_common(prefilter)]
        ranked: list[tuple[float, dict[str, Any]]] = []
        for entry_id in entry_ids:
            variants, candidate = self.entries[entry_id]
            score = max(difflib.SequenceMatcher(None, key, variant).ratio() for variant in variants)
            if score > 0:
                ranked.append((score, candidate))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [
            dict(candidate, lexical_score=round(score, 4)) for score, candidate in ranked[:limit]
        ]


def enrich_reviews_with_llm(
    reviews: list[ReviewRecord],
    graph: Any,
    connection: pymysql.Connection,
    limit: int | None = None,
    batch_size: int = 10,
    workers: int = 4,
    cache_path: Path | None = None,
) -> int:
    """规则未命中后补充别名并反查正式机构，是否写边由后续阈值决定。"""
    people, organizations = canonical_entities(graph, connection)
    organization_name_index = make_index(organizations, ("name_cn", "name_en", "name_alias"))
    llm_reviews = [item for item in reviews if item.relation_type in {"APPLIED_BY", "OWNED_BY"}]
    related: dict[str, set[str]] = defaultdict(set)
    for item in llm_reviews:
        related[item.patent_id].add(item.source_name)
    unique: dict[str, list[ReviewRecord]] = defaultdict(list)
    for item in llm_reviews:
        unique[item.source_name].append(item)
    names = list(unique)
    if limit is not None:
        names = names[:limit]
    cache = read_llm_cache(cache_path)
    cached_names = []
    for name in names:
        cached = cache.get(normalize_name(name))
        if not cached:
            continue
        result = dict(cached, source_name=name)
        _apply_llm_results([result], {name: {}}, unique, organization_name_index)
        cached_names.append(name)
    if cached_names:
        logger.info("复用大模型名称缓存=%d", len(cached_names))
    cached_name_set = set(cached_names)
    names = [name for name in names if name not in cached_name_set]
    if not names:
        return len(cached_names)

    llm = get_llm_client()
    if llm is None:
        logger.warning("未配置公共大模型能力，仅复用已有名称缓存")
        return len(cached_names)

    search_index = CandidateSearchIndex(people, organizations)
    prepared: list[tuple[dict[str, dict[str, dict[str, Any]]], str]] = []
    for start in range(0, len(names), batch_size):
        batch_names = names[start : start + batch_size]
        inputs = []
        allowed: dict[str, dict[str, dict[str, Any]]] = {}
        for name in batch_names:
            sample = unique[name][0]
            candidates = search_index.shortlist(name)
            allowed[name] = {str(candidate["vid"]): candidate for candidate in candidates}
            inputs.append(
                {
                    "source_name": name,
                    "relation_type": sample.relation_type,
                    "same_patent_names": sorted(related[sample.patent_id] - {name}),
                    "existing_candidates": candidates,
                }
            )
        prompt = (
            "你是专利关系人工审核助手。判断每个源名称更可能是Person、Organization或Unknown；"
            "如果可能是机构，补充其可能的正式中文名、正式英文名、简称或历史名称到aliases；"
            "same_legal_entity仅当源名称与补充名称代表同一机构主体时返回true；"
            "院系与高校、分支机构与总公司、子公司与母公司不属于同一机构主体，必须返回false；"
            "candidate_vids只能从existing_candidates选择，但aliases可以用于程序再次检索已有正式机构。"
            "禁止计算置信度，禁止决定最终实体。same_patent_names仅作申请人、权利人、发明人的上下文。"
            '严格返回JSON对象：{"results":[{"source_name":"","subject_type":"Person|Organization|Unknown",'
            '"same_legal_entity":false,"aliases":[],"candidate_vids":[],"reason":""}]}。输入：'
            + json.dumps(inputs, ensure_ascii=False)
        )
        prepared.append((allowed, prompt))

    processed = 0
    completed = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {
            executor.submit(
                llm.synthesize,
                prompt,
                max_tokens=min(4096, 600 + 300 * len(allowed)),
            ): allowed
            for allowed, prompt in prepared
        }
        for future in as_completed(futures):
            allowed = futures[future]
            try:
                raw = future.result()
            except Exception:
                logger.exception("大模型批次调用异常，保留人工审核")
                raw = ""
            completed += 1
            logger.info("大模型批次进度=%d/%d", completed, len(prepared))
            payload = _json_object(raw or "")
            results = payload.get("results", []) if payload else []
            for result in results:
                if not isinstance(result, dict) or result.get("source_name") not in allowed:
                    continue
                cache[normalize_name(result["source_name"])] = {
                    "subject_type": result.get("subject_type") or "Unknown",
                    "same_legal_entity": result.get("same_legal_entity") is True,
                    "aliases": result.get("aliases") or [],
                    "candidate_vids": [],
                    "reason": result.get("reason") or "",
                }
            processed += _apply_llm_results(results, allowed, unique, organization_name_index)
    write_llm_cache(cache_path, cache)
    return processed + len(cached_names)


def read_llm_cache(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None or not path.exists():
        return {}
    result: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(item, dict)
            and item.get("version") == LLM_CACHE_VERSION
            and item.get("key")
            and isinstance(item.get("result"), dict)
        ):
            result[str(item["key"])] = item["result"]
    return result


def write_llm_cache(path: Path | None, cache: dict[str, dict[str, Any]]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(
                {"version": LLM_CACHE_VERSION, "key": key, "result": result},
                ensure_ascii=False,
            )
            + "\n"
            for key, result in sorted(cache.items())
        ),
        encoding="utf-8",
    )


def _apply_llm_results(
    results: list[Any],
    allowed: dict[str, dict[str, dict[str, Any]]],
    reviews_by_name: dict[str, list[ReviewRecord]],
    organization_name_index: dict[str, list[dict[str, Any]]],
) -> int:
    processed = 0
    for result in results:
        if not isinstance(result, dict) or result.get("source_name") not in allowed:
            continue
        name = str(result["source_name"])
        subject_type = str(result.get("subject_type") or "Unknown")
        if subject_type not in {"Person", "Organization", "Unknown"}:
            subject_type = "Unknown"
        aliases = [str(value).strip() for value in result.get("aliases", []) if str(value).strip()][
            :8
        ]
        selected = [
            allowed[name][str(vid)]
            for vid in result.get("candidate_vids", [])
            if str(vid) in allowed[name]
        ]
        alias_matched: list[dict[str, Any]] = []
        if subject_type == "Organization":
            for alias in aliases:
                for candidate in organization_name_index.get(normalize_name(alias), []):
                    view = candidate_view(candidate, "Organization")
                    selected.append(view)
                    alias_matched.append(view)
        selected = list({str(candidate["vid"]): candidate for candidate in selected}.values())
        alias_matched = list(
            {str(candidate["vid"]): candidate for candidate in alias_matched}.values()
        )
        same_entity = result.get("same_legal_entity") is True
        reason = str(result.get("reason") or "")
        for item in reviews_by_name[name]:
            item.llm_subject_type = subject_type
            item.llm_aliases = aliases
            item.llm_candidate_entities = selected
            item.llm_alias_matched_entities = alias_matched
            item.llm_same_entity = same_entity
            item.llm_summary = reason
        processed += 1
    return processed


def promote_llm_organization_matches(
    reviews: list[ReviewRecord], threshold: float = 0.75
) -> tuple[list[EdgeRecord], list[ReviewRecord]]:
    """把满足严格条件的大模型别名唯一匹配提升为0.75关系边。"""
    confidence = 0.75
    promoted: list[EdgeRecord] = []
    remaining: list[ReviewRecord] = []
    for item in reviews:
        existing_org_candidates = [
            candidate for candidate in item.candidates if candidate.get("type") == "Organization"
        ]
        candidates = item.llm_alias_matched_entities
        eligible = (
            item.relation_type in {"APPLIED_BY", "OWNED_BY"}
            and item.llm_subject_type == "Organization"
            and item.llm_same_entity
            and len(candidates) == 1
            and not existing_org_candidates
            and bool(item.patent_vid)
            and confidence >= threshold
        )
        if not eligible:
            remaining.append(item)
            continue
        candidate = candidates[0]
        evidence = (
            f"大模型判断原名称与正式机构为同一主体；补充名称={item.llm_aliases}；"
            f"在dev正式机构中唯一命中；理由={item.llm_summary}"
        )
        promoted.append(
            EdgeRecord(
                item.relation_type,
                item.patent_vid,
                str(candidate["vid"]),
                item.sequence,
                common_party_properties(
                    item.sequence,
                    item.role,
                    item.source_name,
                    confidence,
                    "Organization",
                    "llm_alias_unique",
                    evidence,
                    item.source_record_id,
                    item.is_current,
                ),
            )
        )
    return promoted, remaining


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
    use_llm: bool = False,
    llm_limit: int | None = None,
    llm_batch_size: int = 10,
    llm_auto_threshold: float = 0.75,
    llm_workers: int = 4,
    llm_cache: Path | None = None,
) -> Counter[str]:
    os.environ["TRS_GRAPH_SPACE"] = "dev"
    graph = get_trs_graph_client()
    connection = mysql_connection()
    try:
        edges, reviews, stats = build_relations(graph, connection)
        if use_llm and reviews:
            stats["llm_reviewed_names"] = enrich_reviews_with_llm(
                reviews,
                graph,
                connection,
                llm_limit,
                llm_batch_size,
                llm_workers,
                llm_cache,
            )
            llm_edges, reviews = promote_llm_organization_matches(reviews, llm_auto_threshold)
            edges.extend(llm_edges)
            stats["llm_alias_auto_edges"] = len(llm_edges)
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
    parser.add_argument("--apply", action="store_true", help="实际写入dev；默认只分析")
    parser.add_argument("--replace", action="store_true", help="写入前替换本加载器管理的旧关系")
    parser.add_argument("--review-output", type=Path, help="可选：输出待人工审核JSONL")
    parser.add_argument(
        "--use-llm", action="store_true", help="用公共大模型辅助判断主体类型、别名和审核候选"
    )
    parser.add_argument("--llm-limit", type=int, help="可选：限制本次大模型分析的去重名称数量")
    parser.add_argument(
        "--llm-batch-size", type=int, default=10, help="每次大模型请求分析的名称数量"
    )
    parser.add_argument(
        "--llm-auto-threshold",
        type=float,
        default=0.75,
        help="大模型别名唯一匹配自动建边阈值，默认0.75；设为更高值可只保留审核候选",
    )
    parser.add_argument("--llm-workers", type=int, default=4, help="大模型并发批次数，默认4")
    parser.add_argument(
        "--llm-cache",
        type=Path,
        default=Path("/tmp/patent_relation_llm_cache.jsonl"),
        help="大模型名称识别缓存，默认写入/tmp；生产环境可指定持久卷路径",
    )
    args = parser.parse_args()
    if args.replace and not args.apply:
        parser.error("--replace必须与--apply一起使用")
    if not 0 <= args.llm_auto_threshold <= 1:
        parser.error("--llm-auto-threshold必须在0到1之间")
    if args.llm_workers < 1:
        parser.error("--llm-workers必须大于等于1")
    logging.basicConfig(level=logging.INFO)
    for key, value in sorted(
        load(
            args.apply,
            args.replace,
            args.review_output,
            args.use_llm,
            args.llm_limit,
            args.llm_batch_size,
            args.llm_auto_threshold,
            args.llm_workers,
            args.llm_cache,
        ).items()
    ):
        logger.info("%s=%d", key, value)


if __name__ == "__main__":
    main()
