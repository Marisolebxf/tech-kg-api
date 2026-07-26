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
from dataclasses import asdict, dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from infra.graph_db import get_trs_graph_client
from infra.llm import get_llm_client
from script.patent_identifiers import application_number_key, identifier_key

logger = logging.getLogger(__name__)
DDL_FILE = Path(__file__).resolve().parents[1] / "schemas" / "ddl" / "patent_relation_ddl.ngql"
NAME_CLEAN_RE = re.compile(r"[^0-9a-z\u4e00-\u9fff]+")
PERSON_EDGE_TYPES = {"INVENTED_BY", "APPLIED_BY", "OWNED_BY"}
ALL_EDGE_TYPES = ("INVENTED_BY", "APPLIED_BY", "OWNED_BY", "CITES", "OUTPUT_OF")

SHARED_EDGE_PROPERTIES = {
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


def normalize_name(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return NAME_CLEAN_RE.sub("", text)


def normalize_identifier(value: Any) -> str:
    return identifier_key(value)


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
            for key in names_from(row.get(field)):
                if key not in seen:
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
    graph: Any, rows: list[Any], builder: Callable[[list[Any]], str], batch_size: int = 20
) -> None:
    for start in range(0, len(rows), batch_size):
        statement = builder(rows[start : start + batch_size])
        if statement:
            graph.execute_write(statement)


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
        for attempt in range(15):
            try:
                graph.execute_read(f"DESCRIBE EDGE {edge_type}")
                break
            except Exception:
                if attempt == 14:
                    raise
                time.sleep(1)


def canonical_entities(
    graph: Any, connection: pymysql.Connection
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    graph_people = graph_catalog(
        graph, "Person",
        ("name_zh", "name_en", "scholar_org", "source_table", "source_record_id"),
    )
    graph_orgs = graph_catalog(
        graph, "Organization",
        ("name_cn", "name_en", "name_alias", "source_table", "source_record_id"),
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
        source = people_by_id.get(str(node.get("source_record_id") or ""))
        if source:
            resolved_people.append(dict(source, vid=str(node["vid"])))
    domestic = [
        dict(row, source_table="dwd_org_base_info")
        for row in fetch_all(connection, "SELECT org_id,name_cn FROM dwd_org_base_info")
    ]
    foreign = [
        dict(row, source_table="dwd_forg_base_info")
        for row in fetch_all(
            connection, "SELECT org_id,name_en,name_alias FROM dwd_forg_base_info"
        )
    ]
    orgs_by_source = {
        (str(row["source_table"]), str(row["org_id"])): row
        for row in domestic + foreign
    }
    resolved_orgs = []
    for node in graph_orgs:
        key = (
            str(node.get("source_table") or ""),
            str(node.get("source_record_id") or ""),
        )
        source = orgs_by_source.get(key)
        if source:
            resolved_orgs.append(dict(source, vid=str(node["vid"])))
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
                candidates = patent_index.get(application_number_key(identifier), [])
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
) -> ReviewRecord:
    return ReviewRecord(patent_id, relation, source_name, reason, confidence, candidates, evidence)


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
        str(row["patent_id"])
        for row in fetch_all(connection, "SELECT patent_id FROM dwd_patent")
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
                            "机构法定名或别名精确匹配且候选唯一",
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
        current = patent_index.get(normalize_identifier(row["patent_id"]), [])
        if len(current) != 1:
            stats["CITES:missing_source"] += 1
            continue
        for column in ("patent_citations", "cited_by"):
            for sequence, identifier in enumerate(parse_json(row.get(column), []), start=1):
                candidates = patent_index.get(normalize_identifier(identifier), [])
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


def _candidate_shortlist(
    name: str, people: list[dict[str, Any]], organizations: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """只把现有实体作为大模型候选，模型不能编造VID。"""
    key = normalize_name(name)
    ranked: list[tuple[float, dict[str, Any]]] = []
    for entity_type, rows, fields in (
        ("Organization", organizations, ("name_cn", "name_en", "name_alias")),
        ("Person", people, ("name_zh", "name_en")),
    ):
        for row in rows:
            names = set()
            for name_field in fields:
                names.update(names_from(row.get(name_field)))
            score = max(
                (difflib.SequenceMatcher(None, key, candidate).ratio() for candidate in names),
                default=0.0,
            )
            ranked.append((score, candidate_view(row, entity_type)))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [
        dict(candidate, lexical_score=round(score, 4))
        for score, candidate in ranked[:8]
        if score > 0
    ]


def enrich_reviews_with_llm(
    reviews: list[ReviewRecord],
    graph: Any,
    connection: pymysql.Connection,
    limit: int | None = None,
    batch_size: int = 10,
) -> int:
    """辅助判断类型、别名和已有候选；不评分、不自动选定、不写边。"""
    llm = get_llm_client()
    if llm is None:
        logger.warning("未配置公共大模型能力，跳过主体类型和别名分析")
        return 0
    people, organizations = canonical_entities(graph, connection)
    related: dict[str, set[str]] = defaultdict(set)
    for item in reviews:
        related[item.patent_id].add(item.source_name)
    unique: dict[str, list[ReviewRecord]] = defaultdict(list)
    for item in reviews:
        unique[item.source_name].append(item)
    names = list(unique)
    if limit is not None:
        names = names[:limit]
    processed = 0
    for start in range(0, len(names), batch_size):
        batch_names = names[start : start + batch_size]
        inputs = []
        allowed: dict[str, dict[str, dict[str, Any]]] = {}
        for name in batch_names:
            sample = unique[name][0]
            candidates = _candidate_shortlist(name, people, organizations)
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
            "识别可能的中英文名、简称和机构别名；只能从existing_candidates选择candidate_vids。"
            "禁止计算置信度，禁止决定最终实体。same_patent_names仅作申请人、权利人、发明人的上下文。"
            '严格返回JSON对象：{"results":[{"source_name":"","subject_type":"Person|Organization|Unknown",'
            '"aliases":[],"candidate_vids":[],"reason":""}]}。输入：'
            + json.dumps(inputs, ensure_ascii=False)
        )
        raw = llm.synthesize(prompt, max_tokens=min(4096, 600 + 300 * len(inputs)))
        payload = _json_object(raw or "")
        results = payload.get("results", []) if payload else []
        for result in results:
            if not isinstance(result, dict) or result.get("source_name") not in allowed:
                continue
            name = str(result["source_name"])
            subject_type = str(result.get("subject_type") or "Unknown")
            if subject_type not in {"Person", "Organization", "Unknown"}:
                subject_type = "Unknown"
            aliases = [
                str(value).strip() for value in result.get("aliases", []) if str(value).strip()
            ][:8]
            selected = [
                allowed[name][str(vid)]
                for vid in result.get("candidate_vids", [])
                if str(vid) in allowed[name]
            ]
            reason = str(result.get("reason") or "")
            for item in unique[name]:
                item.llm_subject_type = subject_type
                item.llm_aliases = aliases
                item.llm_candidate_entities = selected
                item.llm_summary = reason
            processed += 1
    return processed


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
) -> Counter[str]:
    os.environ["TRS_GRAPH_SPACE"] = "dev"
    graph = get_trs_graph_client()
    connection = mysql_connection()
    try:
        edges, reviews, stats = build_relations(graph, connection)
        stats["review_records"] = len(reviews)
        if use_llm and reviews:
            stats["llm_reviewed_names"] = enrich_reviews_with_llm(
                reviews, graph, connection, llm_limit, llm_batch_size
            )
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
    args = parser.parse_args()
    if args.replace and not args.apply:
        parser.error("--replace必须与--apply一起使用")
    logging.basicConfig(level=logging.INFO)
    for key, value in sorted(
        load(
            args.apply,
            args.replace,
            args.review_output,
            args.use_llm,
            args.llm_limit,
            args.llm_batch_size,
        ).items()
    ):
        logger.info("%s=%d", key, value)


if __name__ == "__main__":
    main()
