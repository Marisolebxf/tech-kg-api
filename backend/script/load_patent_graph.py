"""从 gkx_element 映射并装载 Patent、Keyword 和 HAS_KEYWORD 到 dev。"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

# 流程：MySQL读取 → 字段映射 → 生成nGQL → 公共图客户端写入dev。
from infra.graph_db import get_trs_graph_client

logger = logging.getLogger(__name__)

# 1. Patent目标属性
PATENT_PROPERTIES = (
    "patent_id",
    "publication_number",
    "application_number",
    "application_kind",
    "country_code",
    "country",
    "publication_date",
    "application_date",
    "granted_number",
    "grant_date",
    "status",
    "anticipated_expiration",
    "title_original",
    "title_en",
    "title_zh",
    "abstract_zh",
    "language",
    "main_ipcr",
    "further_ipcr",
    "main_cpc",
    "further_cpc",
    "keywords",
    "citation_nums",
    "cited_by_nums",
    "patent_value",
    "simple_family_number",
    "db_source",
    "create_time",
    "update_time",
    "confidence",
    "organization_base",
    "organization_id",
)

# 2. MySQL数据读取
SQL_FILE = Path(__file__).resolve().parents[1] / "dao" / "sql" / "patent_entity_extract.sql"
SELECT_SQL = SQL_FILE.read_text(encoding="utf-8")


def mysql_connection() -> pymysql.Connection:
    """连接MySQL数据源。"""
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


# 3. 字段解析与映射
def parse_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def original_text(value: Any) -> str:
    value = parse_json(value)
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and (text := item.get("text") or item.get("content")):
                return "\n".join(map(str, text)) if isinstance(text, list) else str(text)
    return str(value or "")


def normalized_language(value: Any) -> str:
    value = parse_json(value)
    return ",".join(map(str, value)) if isinstance(value, list) else str(value or "")


def keyword_values(value: Any) -> list[str]:
    value = parse_json(value)
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, dict):
            item = item.get("zhName") or item.get("enName") or item.get("name") or ""
        keyword = " ".join(unicodedata.normalize("NFKC", str(item)).strip().split())
        key = keyword.casefold()
        if keyword and key not in seen:
            seen.add(key)
            result.append(keyword)
    return result


def keyword_vid(keyword: str) -> str:
    normalized = keyword.casefold().encode("utf-8")
    return f"keyword_{hashlib.md5(normalized).hexdigest()}"  # noqa: S324


def json_snapshot(value: Any) -> str:
    value = parse_json(value)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")) if value is not None else ""


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


def ngql_date(value: Any) -> str:
    return f"date({ngql_string(str(value)[:10])})" if value else "NULL"


def ngql_datetime(value: Any) -> str:
    if value is None:
        return "NULL"
    text = (
        value.strftime("%Y-%m-%dT%H:%M:%S")
        if isinstance(value, datetime)
        else str(value).replace(" ", "T")[:19]
    )
    return f"datetime({ngql_string(text)})"


def ngql_int(value: Any) -> str:
    return str(int(value or 0))


def patent_payload(row: dict[str, Any]) -> tuple[str, list[str]]:
    """映射29个业务属性，并附加3个置信度/溯源属性。"""
    patent_id = str(row.get("patent_id") or "").strip()
    if not patent_id:
        raise ValueError("patent_id 为空")
    values = [
        ngql_string(patent_id),
        ngql_string(row.get("publication_number")),
        ngql_string(row.get("application_number")),
        ngql_string(row.get("application_kind")),
        ngql_string(row.get("country_code")),
        ngql_string(row.get("country")),
        ngql_int(row.get("publication_date")),
        ngql_int(row.get("application_date")),
        ngql_string(row.get("granted_number")),
        ngql_string(row.get("grant_date")),
        ngql_string(row.get("status")),
        ngql_int(row.get("anticipated_expiration")),
        ngql_string(original_text(row.get("titles"))),
        ngql_string(row.get("title_en")),
        ngql_string(row.get("title_zh")),
        ngql_string(row.get("abstract_zh")),
        ngql_string(normalized_language(row.get("language"))),
        ngql_string(row.get("main_ipcr")),
        ngql_string(json_snapshot(row.get("further_ipcr"))),
        ngql_string(row.get("main_cpc")),
        ngql_string(json_snapshot(row.get("further_cpc"))),
        ngql_string(json_snapshot(row.get("keywords"))),
        ngql_int(row.get("citation_nums")),
        ngql_int(row.get("cited_by_nums")),
        ngql_int(row.get("patent_value")),
        ngql_string(row.get("simple_family_number")),
        ngql_string(row.get("db_source")),
        ngql_datetime(row.get("create_time")),
        ngql_datetime(row.get("update_time")),
        "1.0",
        ngql_string("dwd_patent"),
        ngql_string("patent_id"),
    ]
    return f"patent_{patent_id}", values


# 4. nGQL构造：Patent、Keyword和HAS_KEYWORD
def patent_statement(payloads: list[tuple[str, list[str]]]) -> str:
    """生成Patent顶点nGQL。"""
    rows = ",".join(f"{ngql_string(vid)}:({','.join(values)})" for vid, values in payloads)
    return f"INSERT VERTEX Patent({','.join(PATENT_PROPERTIES)}) VALUES {rows};"


def keyword_statements(
    rows: list[dict[str, Any]], batch_id: str = "", ingest_time: datetime | None = None
) -> tuple[str, str]:
    """生成Keyword顶点和HAS_KEYWORD边nGQL。"""
    vertices: dict[str, str] = {}
    edges: dict[tuple[str, str], str] = {}
    for row in rows:
        patent_vid = f"patent_{str(row['patent_id']).strip()}"
        for index, keyword in enumerate(keyword_values(row.get("keywords"))):
            vid = keyword_vid(keyword)
            vertices[vid] = keyword
            edges.setdefault((patent_vid, vid), f"{str(row['patent_id']).strip()}:keywords:{index}")
    vertex_ngql = ""
    edge_ngql = ""
    if vertices:
        values = ",".join(
            f"{ngql_string(vid)}:({ngql_string(word)},1.0,{ngql_string('dwd_patent')},{ngql_string('keywords')})"
            for vid, word in vertices.items()
        )
        vertex_ngql = f"INSERT VERTEX Keyword(keyword,confidence,organization_base,organization_id) VALUES {values};"
    if edges:
        values = ",".join(
            f"{ngql_string(src)}->{ngql_string(dst)}:(1.0,{ngql_string('dwd_patent')},{ngql_string(src.removeprefix('patent_'))})"
            for src, dst in edges
        )
        edge_ngql = (
            f"INSERT EDGE HAS_KEYWORD(confidence,source_table,source_record_id) VALUES {values};"
        )
    return vertex_ngql, edge_ngql


def family_statements(rows: list[dict[str, Any]]) -> tuple[str, str]:
    """生成PatentFamily顶点和确定的MEMBER_OF_FAMILY边。"""
    families: dict[str, str] = {}
    edges: set[tuple[str, str, str]] = set()
    for row in rows:
        number = str(row.get("simple_family_number") or "").strip()
        patent_id = str(row.get("patent_id") or "").strip()
        if not number or not patent_id:
            continue
        family_vid = f"patent_family_{number}"
        families[family_vid] = number
        edges.add((f"patent_{patent_id}", family_vid, patent_id))
    vertex_ngql = ""
    edge_ngql = ""
    if families:
        values = ",".join(
            f"{ngql_string(vid)}:({ngql_string(number)},1.0,{ngql_string('dwd_patent_family')},{ngql_string('simple_family_number')})"
            for vid, number in families.items()
        )
        vertex_ngql = f"INSERT VERTEX PatentFamily(family_number,confidence,organization_base,organization_id) VALUES {values};"
    if edges:
        values = ",".join(
            f"{ngql_string(src)}->{ngql_string(dst)}:(1.0,{ngql_string('source_family_number')},{ngql_string('simple_family_number由源表直接给出')},{ngql_string('dwd_patent_family')},{ngql_string(source_id)})"
            for src, dst, source_id in edges
        )
        edge_ngql = f"INSERT EDGE MEMBER_OF_FAMILY(confidence,match_method,match_evidence,source_table,source_record_id) VALUES {values};"
    return vertex_ngql, edge_ngql


DDL_FILE = Path(__file__).resolve().parents[1] / "schemas" / "ddl" / "patent_ddl.ngql"


def ensure_schema(graph: Any) -> None:
    """幂等创建本加载器所需Schema，并为旧HAS_KEYWORD补字段。"""
    ddl = DDL_FILE.read_text(encoding="utf-8")
    definitions = re.findall(r"CREATE\s+(?:TAG|EDGE)\b.*?;", ddl, flags=re.I | re.S)
    for statement in definitions:
        graph.execute_write(statement)
    for name in ("PatentFamily", "MEMBER_OF_FAMILY"):
        command = f"DESCRIBE TAG {name}" if name == "PatentFamily" else f"DESCRIBE EDGE {name}"
        for attempt in range(15):
            try:
                graph.execute_read(command)
                break
            except Exception:
                if attempt == 14:
                    raise
                time.sleep(1)
    entity_fields = {"confidence", "organization_base", "organization_id"}
    for tag in ("Patent", "Keyword", "PatentFamily"):
        existing_fields = {
            str(row["Field"]) for row in graph.execute_read(f"DESCRIBE TAG {tag}").records
        }
        missing_fields = entity_fields - existing_fields
        if missing_fields:
            definitions = {
                "confidence": "double",
                "organization_base": "string",
                "organization_id": "string",
            }
            graph.execute_write(
                f"ALTER TAG {tag} ADD ("
                + ",".join(f"{field} {definitions[field]}" for field in sorted(missing_fields))
                + ");"
            )
        for attempt in range(15):
            visible = {
                str(row["Field"]) for row in graph.execute_read(f"DESCRIBE TAG {tag}").records
            }
            if entity_fields <= visible:
                break
            if attempt == 14:
                raise RuntimeError(f"{tag}实体置信度/溯源属性未在TRSGraph中生效")
            time.sleep(1)
    existing = {
        str(row["Field"]) for row in graph.execute_read("DESCRIBE EDGE HAS_KEYWORD").records
    }
    missing = [("confidence", "double"), ("source_table", "string"), ("source_record_id", "string")]
    missing = [(field, kind) for field, kind in missing if field not in existing]
    if missing:
        graph.execute_write(
            f"ALTER EDGE HAS_KEYWORD ADD ({', '.join(f'{field} {kind}' for field, kind in missing)});"
        )
    wanted = {"confidence", "source_table", "source_record_id"}
    for attempt in range(15):
        visible = {
            str(row["Field"]) for row in graph.execute_read("DESCRIBE EDGE HAS_KEYWORD").records
        }
        if wanted <= visible:
            break
        if attempt == 14:
            raise RuntimeError("HAS_KEYWORD新属性未在TRSGraph中生效")
        time.sleep(1)


# 5. 主流程：读取MySQL并通过公共图客户端写入dev
def load_patents(batch_size: int) -> tuple[int, int, int]:
    os.environ["TRS_GRAPH_SPACE"] = "dev"
    graph = get_trs_graph_client()  # 公共图数据库能力
    ensure_schema(graph)
    connection = mysql_connection()
    loaded = keyword_count = edge_count = 0
    try:
        while True:
            with connection.cursor() as cursor:
                # MySQL按批读取
                cursor.execute(SELECT_SQL, (batch_size, loaded))
                rows = list(cursor.fetchall())
            if not rows:
                break
            for start in range(0, len(rows), 1):
                group = rows[start : start + 1]
                # 写入Patent
                graph.execute_write(patent_statement([patent_payload(row) for row in group]))
                vertex_ngql, edge_ngql = keyword_statements(group)
                if vertex_ngql:
                    graph.execute_write(vertex_ngql)  # 写入Keyword
                if edge_ngql:
                    graph.execute_write(edge_ngql)  # 写入HAS_KEYWORD
                family_vertex_ngql, family_edge_ngql = family_statements(group)
                if family_vertex_ngql:
                    graph.execute_write(family_vertex_ngql)
                if family_edge_ngql:
                    graph.execute_write(family_edge_ngql)
                references = sum(len(keyword_values(row.get("keywords"))) for row in group)
                keyword_count += references
                edge_count += references
            loaded += len(rows)
            logger.info("装载进度 Patent=%d", loaded)
    finally:
        connection.close()
    return loaded, keyword_count, edge_count


def main() -> None:
    parser = argparse.ArgumentParser(description="从 MySQL 装载专利图数据到 dev")
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    patent_count, keyword_count, edge_count = load_patents(args.batch_size)
    logger.info(
        "完成 Patent=%d，Keyword引用=%d，HAS_KEYWORD=%d", patent_count, keyword_count, edge_count
    )


if __name__ == "__main__":
    main()
