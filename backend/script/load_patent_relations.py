"""抽取、对齐并写入五类待补齐专利关系；HAS_KEYWORD由实体装载脚本处理。"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import unicodedata
from collections.abc import Callable
from datetime import datetime
from typing import Any

from dotenv import load_dotenv

from infra.graph_db import get_trs_graph_client
from script.load_patent_graph import mysql_connection, ngql_string, parse_json

logger = logging.getLogger(__name__)
RELATION_SQL = """SELECT p.patent_id,p.inventors,p.applicants,p.assignees,c.patent_citations,c.cited_by FROM dwd_patent p LEFT JOIN dwd_patent_cited c ON c.patent_id=p.patent_id ORDER BY p.id LIMIT %s OFFSET %s"""

# 原始 ``id`` 只能在已经验证为同一数据域的表之间使用。专利数据中的人员、
# 机构和项目/专利引用来自不同数据域，不能把同名 id 字段直接当成 dev VID。
# 只有来源显式声明为 dev 图命名空间的 graph_vid 才允许直连。
TRUSTED_GRAPH_ID_NAMESPACES = {"dev", "trsgraph:dev"}


def normalize_identifier(value: object) -> str:
    return re.sub(r"[^0-9a-z]", "", unicodedata.normalize("NFKC", str(value or "")).casefold())


def array(value: Any) -> list[Any]:
    value = parse_json(value)
    return value if isinstance(value, list) else []


def item_name(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return ""
    return str(
        item.get("name")
        or item.get("fullName")
        or item.get("organizationName")
        or item.get("text")
        or ""
    ).strip()


def item_identifier(item: Any) -> str:
    """提取跨域可比较的专利业务编号，绝不回退到厂商记录 ``id``。"""
    if isinstance(item, str):
        return item
    if not isinstance(item, dict):
        return ""
    return str(
        item.get("patent_id")
        or item.get("publication_number")
        or item.get("publicationNumber")
        or item.get("patent_number")
        or item.get("document_number")
        or item.get("number")
        or ""
    )


def subject_kind(default: str, item: Any) -> str:
    if not isinstance(item, dict):
        return default
    marker = str(
        item.get("type") or item.get("subject_type") or item.get("applicant_type") or ""
    ).casefold()
    if marker in {"person", "individual", "自然人", "个人"}:
        return "Person"
    if marker in {"organization", "organisation", "company", "机构", "企业"}:
        return "Organization"
    return default


def item_sequence(item: Any, index: int) -> int:
    if isinstance(item, dict):
        try:
            return int(item.get("sequence") or item.get("seq") or index + 1)
        except (TypeError, ValueError):
            pass
    return index + 1


def trusted_graph_vid(metadata: dict[str, Any]) -> str | None:
    """返回显式属于 dev 图命名空间的 VID；拒绝未标注数据域的原始 id。"""
    namespace = str(
        metadata.get("id_namespace") or metadata.get("graph_namespace") or ""
    ).strip().casefold()
    vid = str(metadata.get("graph_vid") or "").strip()
    return vid if vid and namespace in TRUSTED_GRAPH_ID_NAMESPACES else None


def edge_statement(
    edge: str,
    src: str,
    dst: str,
    sequence: int | None,
    table: str,
    record_id: str,
    batch: str,
    now: datetime,
    score: float,
    subject_type: str | None = None,
    source_name: str = "",
    reference_identifier: str = "",
) -> str:
    method = "authoritative_id" if score >= 1.0 else "exact_name"
    if edge == "INVENTED_BY":
        if subject_type not in {"Person", "Organization"}:
            raise ValueError(f"{edge} 缺少显式 subject_type")
        names = [
            "sequence",
            "source_name",
            "confidence",
            "match_method",
            "match_evidence",
            "source_table",
            "source_record_id",
            "subject_type",
            "resolution_status",
        ]
        values = [
            str(sequence or 0),
            ngql_string(source_name),
            str(score),
            ngql_string(method),
            ngql_string("unique_match"),
            ngql_string(table),
            ngql_string(record_id),
            ngql_string(subject_type),
            ngql_string("resolved"),
        ]
    elif edge in {"APPLIED_BY", "OWNED_BY"}:
        if subject_type not in {"Person", "Organization"}:
            raise ValueError(f"{edge} 缺少显式 subject_type")
        names = ["sequence", "role"]
        values = [
            str(sequence or 0),
            ngql_string("applicant" if edge == "APPLIED_BY" else "assignee"),
        ]
        if edge == "OWNED_BY":
            names.append("is_current")
            values.append("true")
        names += [
            "source_name",
            "confidence",
            "match_method",
            "match_evidence",
            "source_table",
            "source_record_id",
            "subject_type",
            "resolution_status",
        ]
        values += [
            ngql_string(source_name),
            str(score),
            ngql_string(method),
            ngql_string("unique_match"),
            ngql_string(table),
            ngql_string(record_id),
            ngql_string(subject_type),
            ngql_string("resolved"),
        ]
    elif edge == "CITES":
        names = [
            "reference_identifier",
            "sequence",
            "confidence",
            "match_method",
            "match_evidence",
            "source_table",
            "source_record_id",
        ]
        values = [
            ngql_string(reference_identifier),
            "0",
            str(score),
            ngql_string(method),
            ngql_string("identifier_match"),
            ngql_string(table),
            ngql_string(record_id),
        ]
    elif edge == "OUTPUT_OF":
        names = [
            "source_table",
            "source_record_id",
            "ingest_batch",
            "ingest_time",
            "confidence",
            "match_method",
            "match_evidence",
        ]
        values = [
            ngql_string(table),
            ngql_string(record_id),
            ngql_string(batch),
            ngql_string(now.isoformat()),
            str(score),
            ngql_string(method),
            ngql_string("project_source_record_id"),
        ]
    else:
        raise ValueError(f"不支持的专利关系: {edge}")
    return f"INSERT EDGE {edge}({','.join(names)}) VALUES {ngql_string(src)}->{ngql_string(dst)}:({','.join(values)});"


def extract_edges(
    row: dict[str, Any],
    resolve_subject: Callable[
        [str, str, dict[str, Any]], tuple[str, float, str] | None
    ],
    resolve_patent: Callable[[str], tuple[str, float] | None],
    batch: str,
    now: datetime,
    relation_types: set[str] | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    enabled = relation_types or {"INVENTED_BY", "APPLIED_BY", "OWNED_BY", "CITES"}
    src = f"patent_{str(row['patent_id']).strip()}"
    statements = []
    review = []
    for field, edge, kind in (
        ("inventors", "INVENTED_BY", "Person"),
        # 申请人、权利人可能是自然人或机构；源JSON没有type时必须跨两个实体域裁决。
        ("applicants", "APPLIED_BY", "Unknown"),
        ("assignees", "OWNED_BY", "Unknown"),
    ):
        if edge not in enabled:
            continue
        for i, item in enumerate(array(row.get(field))):
            name = item_name(item)
            actual_kind = subject_kind(kind, item)
            matched = resolve_subject(actual_kind, name, item if isinstance(item, dict) else {})
            if not name or not matched:
                review.append(
                    {
                        "patent_id": row["patent_id"],
                        "edge": edge,
                        "mention": name,
                        "reason": "未通过唯一性/置信度裁决",
                    }
                )
                continue
            vid, score, resolved_kind = matched
            statements.append(
                edge_statement(
                    edge,
                    src,
                    vid,
                    item_sequence(item, i),
                    "dwd_patent",
                    f"{row['patent_id']}:{field}:{i}",
                    batch,
                    now,
                    score,
                    resolved_kind,
                    source_name=name,
                )
            )
    if "CITES" not in enabled:
        return statements, review
    for field, reverse in (("patent_citations", False), ("cited_by", True)):
        for i, item in enumerate(array(row.get(field))):
            raw = item_identifier(item)
            matched = resolve_patent(raw)
            if not raw or not matched:
                review.append(
                    {
                        "patent_id": row["patent_id"],
                        "edge": "CITES",
                        "mention": raw,
                        "reason": "引用专利未唯一对齐",
                    }
                )
                continue
            vid, score = matched
            start, end = (vid, src) if reverse else (src, vid)
            statements.append(
                edge_statement(
                    "CITES",
                    start,
                    end,
                    None,
                    "dwd_patent_cited",
                    f"{row['patent_id']}:{field}:{i}",
                    batch,
                    now,
                    score,
                    reference_identifier=raw,
                )
            )
    return statements, review


class ExistingEntityIndexResolver:
    """只读复用其他负责人已创建的 Person/Organization Milvus Collection。"""

    COLLECTIONS = {"Person": "org_domain_person", "Organization": "org_domain_organization"}

    def __init__(self, client: Any):
        self.client = client
        self._by_name: dict[str, dict[str, list[str]]] = {}
        for kind, collection in self.COLLECTIONS.items():
            if not client.has_collection(collection):
                continue
            if hasattr(client, "query_iterator"):
                iterator = client.query_iterator(
                    collection,
                    batch_size=5000,
                    filter="",
                    output_fields=["vid", "canonical_name", "aliases", "external_id"],
                )
                rows = []
                try:
                    while batch := iterator.next():
                        rows.extend(batch)
                finally:
                    iterator.close()
            else:
                rows = client.query(
                    collection,
                    filter="",
                    limit=16384,
                    output_fields=["vid", "canonical_name", "aliases", "external_id"],
                )
            names: dict[str, list[str]] = {}
            for row in rows:
                vid = str(row["vid"])
                candidate_names = []
                if row.get("canonical_name"):
                    candidate_names.append(str(row["canonical_name"]))
                aliases = parse_json(row.get("aliases"))
                if isinstance(aliases, list):
                    candidate_names.extend(str(alias) for alias in aliases if alias)
                elif aliases:
                    candidate_names.extend(
                        part.strip() for part in str(aliases).split("|") if part.strip()
                    )
                for candidate_name in candidate_names:
                    names.setdefault(candidate_name.casefold(), []).append(vid)
            self._by_name[kind] = names
        self._patents: dict[str, list[str]] = {}
        if client.has_collection("patent"):
            rows = client.query(
                "patent",
                filter="",
                limit=16384,
                output_fields=[
                    "vid",
                    "patent_id",
                    "publication_number",
                    "application_number",
                    "granted_number",
                ],
            )
            for row in rows:
                for field in (
                    "patent_id",
                    "publication_number",
                    "application_number",
                    "granted_number",
                ):
                    key = normalize_identifier(row.get(field))
                    if key:
                        self._patents.setdefault(key, []).append(str(row["vid"]))

    def resolve_patent(self, identifier: str):
        vids = list(dict.fromkeys(self._patents.get(normalize_identifier(identifier), [])))
        return (vids[0], 1.0) if len(vids) == 1 else None

    def resolve(self, kind: str, name: str, metadata: dict[str, Any]):
        # external_id/person_id/org_id 等字段来自其他厂商时没有共同命名空间，
        # 即使字符串碰巧相同也不能证明是同一实体。索引在这里仅用于候选名称召回。
        if not name:
            return None
        key = name.casefold()
        if kind == "Unknown":
            org_vids = list(dict.fromkeys(self._by_name.get("Organization", {}).get(key, [])))
            person_vids = list(dict.fromkeys(self._by_name.get("Person", {}).get(key, [])))
            # 无类型申请人/权利人只有在“机构唯一命中且人员域零命中”时自动通过。
            # 名称同时出现在两个实体域时保持待消歧。
            if len(org_vids) == 1 and not person_vids:
                return org_vids[0], 0.98, "Organization"
            return None
        if kind not in self.COLLECTIONS:
            return None
        # Person 姓名不具备全局唯一性。当前专利源数据又没有机构、邮箱、ORCID
        # 等可与 Person 索引共同验证的上下文，因此禁止仅凭“索引中恰好一个同名”写边。
        if kind == "Person":
            return None
        vids = list(dict.fromkeys(self._by_name.get(kind, {}).get(key, [])))
        return (vids[0], 0.98, kind) if len(vids) == 1 else None


def graph_exact_resolvers(graph: Any, fallback: ExistingEntityIndexResolver | None = None):
    def esc(x: str) -> str:
        return x.replace("\\", "\\\\").replace('"', '\\"')

    def patent(raw: str):
        key = normalize_identifier(raw)
        if not key:
            return None
        if fallback and (matched := fallback.resolve_patent(raw)):
            return matched
        q = f'MATCH (p:Patent) WHERE replace(replace(toLower(p.patent_id), "-", ""), " ", "") == "{esc(key)}" OR replace(replace(toLower(p.publication_number), "-", ""), " ", "") == "{esc(key)}" OR replace(replace(toLower(p.application_number), "-", ""), " ", "") == "{esc(key)}" OR replace(replace(toLower(p.granted_number), "-", ""), " ", "") == "{esc(key)}" RETURN id(p) AS vid LIMIT 2'
        rows = graph.execute_read(q).records
        return (str(rows[0]["vid"]), 1.0) if len(rows) == 1 else None

    def subject(kind: str, name: str, metadata: dict[str, Any]):
        # 跨数据域的原始 id 不可直连。只有显式属于 dev 命名空间的 graph_vid
        # 才能在验证顶点存在后使用；其余情况进入 Milvus/名称消歧。
        graph_vid = trusted_graph_vid(metadata)
        if graph_vid and (node := graph.get_node(graph_vid)):
            labels = set(getattr(node, "labels", []) or [])
            resolved_kind = None
            if kind in {"Person", "Organization"} and kind in labels:
                resolved_kind = kind
            elif kind == "Unknown":
                resolved_kind = next((x for x in ("Person", "Organization") if x in labels), None)
            if resolved_kind:
                return graph_vid, 1.0, resolved_kind
        if not name:
            return None
        if fallback:
            return fallback.resolve(kind, name, metadata)
        if kind == "Unknown":
            org_rows = graph.execute_read(
                f'MATCH (v:`Organization`) WHERE toLower(coalesce(v.name_cn, coalesce(v.name_zh, v.name_en))) == "{esc(name.casefold())}" RETURN id(v) AS vid LIMIT 2'
            ).records
            person_rows = graph.execute_read(
                f'MATCH (v:`Person`) WHERE toLower(coalesce(v.name_cn, coalesce(v.name_zh, v.name_en))) == "{esc(name.casefold())}" RETURN id(v) AS vid LIMIT 1'
            ).records
            return (
                (str(org_rows[0]["vid"]), 0.99, "Organization")
                if len(org_rows) == 1 and not person_rows
                else None
            )
        if kind == "Person":
            return None
        q = f'MATCH (v:`{kind}`) WHERE toLower(coalesce(v.name_cn, coalesce(v.name_zh, v.name_en))) == "{esc(name.casefold())}" RETURN id(v) AS vid LIMIT 2'
        rows = graph.execute_read(q).records
        return (str(rows[0]["vid"]), 0.99, kind) if len(rows) == 1 else None

    return subject, patent


EDGE_WRITE_RE = re.compile(r'INSERT EDGE ([A-Z_]+)\([^)]*\) VALUES "([^"]+)"->"([^"]+)":')


def write_edge_if_absent(graph: Any, statement: str) -> bool:
    """显式保证幂等：同类型、同起点、同终点的rank=0边已存在则跳过。"""
    matched = EDGE_WRITE_RE.match(statement)
    if not matched:
        raise ValueError("无法解析待写入的专利边语句")
    edge_type, source, target = matched.groups()
    if graph.get_edge(f"{source}->{target}@0", edge_type) is not None:
        return False
    graph.execute_write(statement)
    return True


OUTPUT_SQL = "SELECT id, output_patents FROM dwd_zh_project_output ORDER BY id LIMIT %s OFFSET %s"


def extract_output_edges(
    row: dict[str, Any],
    resolve_patent: Callable[[str], tuple[str, float] | None],
    resolve_project: Callable[[str], str | None],
    batch: str,
    now: datetime,
) -> tuple[list[str], list[dict[str, Any]]]:
    statements, review = [], []
    source_project_id = str(row["id"]).strip()
    project_vid = resolve_project(source_project_id)
    if not project_vid:
        return [], [
            {
                "project_id": row["id"],
                "edge": "OUTPUT_OF",
                "mention": source_project_id,
                "reason": "项目源记录ID未唯一对齐到dev Project VID",
            }
        ]
    for i, item in enumerate(array(row.get("output_patents"))):
        raw = item_identifier(item)
        matched = resolve_patent(raw)
        if not raw or not matched:
            review.append(
                {
                    "project_id": row["id"],
                    "edge": "OUTPUT_OF",
                    "mention": raw,
                    "reason": "产出专利未唯一对齐",
                }
            )
            continue
        patent_vid, score = matched
        statements.append(
            edge_statement(
                "OUTPUT_OF",
                patent_vid,
                project_vid,
                None,
                "dwd_zh_project_output",
                f"{row['id']}:output_patents:{i}",
                batch,
                now,
                score,
            )
        )
    return statements, review


def load(
    batch_size: int, batch: str, dry_run: bool = False, relation_types: set[str] | None = None
) -> tuple[int, int, int]:
    os.environ["TRS_GRAPH_SPACE"] = "dev"
    graph = get_trs_graph_client()
    from pymilvus import MilvusClient

    milvus_uri = (
        os.getenv("MILVUS_URI")
        or f"http://{os.getenv('MILVUS_HOST', '127.0.0.1')}:{os.getenv('MILVUS_PORT', '19530')}"
    )
    fallback = ExistingEntityIndexResolver(
        MilvusClient(uri=milvus_uri, token=os.getenv("MILVUS_TOKEN") or None)
    )
    subject, patent = graph_exact_resolvers(graph, fallback)
    db = mysql_connection()
    offset = edges = reviews = 0
    now = datetime.now().replace(microsecond=0)
    enabled = relation_types or {"INVENTED_BY", "APPLIED_BY", "OWNED_BY", "OUTPUT_OF"}
    try:
        while True:
            with db.cursor() as cur:
                cur.execute(RELATION_SQL, (batch_size, offset))
                rows = list(cur.fetchall())
            if not rows:
                break
            for row in rows:
                statements, pending = extract_edges(row, subject, patent, batch, now, enabled)
                reviews += len(pending)
                for statement in statements:
                    if dry_run or write_edge_if_absent(graph, statement):
                        edges += 1
                for item in pending:
                    logger.warning("待消歧 %s", json.dumps(item, ensure_ascii=False))
            offset += len(rows)
        if "OUTPUT_OF" not in enabled:
            return offset, edges, reviews
        project_rows = graph.execute_read(
            "MATCH (p:Project) RETURN id(p) AS vid, "
            "p.source_record_id AS source_record_id"
        ).records
        projects_by_source_id: dict[str, list[str]] = {}
        for project_row in project_rows:
            source_id = str(project_row.get("source_record_id") or "").strip()
            if source_id:
                projects_by_source_id.setdefault(source_id, []).append(
                    str(project_row["vid"])
                )

        def resolve_project(source_id: str) -> str | None:
            vids = list(dict.fromkeys(projects_by_source_id.get(source_id, [])))
            return vids[0] if len(vids) == 1 else None

        output_offset = 0
        while True:
            with db.cursor() as cur:
                cur.execute(OUTPUT_SQL, (batch_size, output_offset))
                output_rows = list(cur.fetchall())
            if not output_rows:
                break
            for output_row in output_rows:
                statements, pending = extract_output_edges(
                    output_row, patent, resolve_project, batch, now
                )
                reviews += len(pending)
                for statement in statements:
                    if dry_run or write_edge_if_absent(graph, statement):
                        edges += 1
                for item in pending:
                    logger.warning("待消歧 %s", json.dumps(item, ensure_ascii=False))
            output_offset += len(output_rows)

    finally:
        db.close()
    return offset, edges, reviews


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--batch-size", type=int, default=100)
    p.add_argument("--batch-id", default=f"PATENT_REL_{datetime.now():%Y%m%d_%H%M%S}")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--relation-types",
        nargs="+",
        choices=["INVENTED_BY", "APPLIED_BY", "OWNED_BY", "CITES", "OUTPUT_OF"],
        default=["INVENTED_BY", "APPLIED_BY", "OWNED_BY", "OUTPUT_OF"],
    )
    a = p.parse_args()
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    print(load(a.batch_size, a.batch_id, a.dry_run, set(a.relation_types)))


if __name__ == "__main__":
    main()
