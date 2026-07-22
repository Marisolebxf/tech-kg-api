"""将gkx_element专利基本属性装载到TRSGraph dev空间。

本脚本只创建Patent节点，不创建任何Edge。MySQL使用专利ETL独立连接；
TRSGraph写入统一复用 infra.graph_db 公共客户端的 execute_write/execute_read。

示例：
    TRS_GRAPH_SPACE=dev PATENT_MYSQL_PASSWORD=*** \
      uv run python -m script.load_patent_graph --init-schema --load --verify
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from infra.graph_db import get_trs_graph_client

logger = logging.getLogger("script.load_patent_graph")

DDL_FILE = Path(__file__).resolve().parents[1] / "schemas" / "ddl" / "patent_ddl.ngql"
PATENT_PROPERTIES = (
    "patent_id",
    "publication_number",
    "application_kind",
    "country_code",
    "country",
    "publication_kind",
    "publication_date",
    "publication_year",
    "publication_month",
    "application_number",
    "application_country",
    "application_date",
    "application_year",
    "application_month",
    "pct_application_number",
    "pct_application_date",
    "pct_national_stage_date",
    "pct_publication_number",
    "pct_publication_date",
    "title_original",
    "title_en",
    "title_zh",
    "abstract_original",
    "abstract_en",
    "abstract_zh",
    "language",
    "granted_number",
    "main_ipcr",
    "further_ipcr",
    "main_cpc",
    "further_cpc",
    "keywords",
    "status",
    "grant_date",
    "grant_year",
    "grant_month",
    "anticipated_expiration",
    "expiration_year",
    "citation_nums",
    "cited_by_nums",
    "non_patent_citation_nums",
    "patent_value",
    "simple_family_number",
    "source_system",
    "source_table",
    "source_record_id",
    "source_url",
    "ingest_batch",
    "ingest_time",
    "source_update_time",
)

SELECT_SQL = """
SELECT
  p.id, p.patent_id, p.publication_number, p.application_kind, p.country_code, p.country,
  JSON_UNQUOTE(JSON_EXTRACT(p.publication_reference, '$.kind')) AS publication_kind,
  JSON_UNQUOTE(JSON_EXTRACT(p.publication_reference, '$.pbdt')) AS publication_date,
  JSON_UNQUOTE(JSON_EXTRACT(p.publication_reference, '$.pbdt_year')) AS publication_year,
  JSON_UNQUOTE(JSON_EXTRACT(p.publication_reference, '$.pbdt_month')) AS publication_month,
  JSON_UNQUOTE(JSON_EXTRACT(p.application_reference, '$.apno')) AS application_number,
  JSON_UNQUOTE(JSON_EXTRACT(p.application_reference, '$.country')) AS application_country,
  JSON_UNQUOTE(JSON_EXTRACT(p.application_reference, '$.apdt')) AS application_date,
  JSON_UNQUOTE(JSON_EXTRACT(p.application_reference, '$.apdt_year')) AS application_year,
  JSON_UNQUOTE(JSON_EXTRACT(p.application_reference, '$.apdt_month')) AS application_month,
  JSON_UNQUOTE(JSON_EXTRACT(p.pct_or_regional_filing_data, '$.apno')) AS pct_application_number,
  JSON_UNQUOTE(JSON_EXTRACT(p.pct_or_regional_filing_data, '$.apdt')) AS pct_application_date,
  JSON_UNQUOTE(JSON_EXTRACT(p.pct_or_regional_filing_data, '$.etdt')) AS pct_national_stage_date,
  JSON_UNQUOTE(JSON_EXTRACT(p.pct_or_regional_publishing_data, '$.pn')) AS pct_publication_number,
  JSON_UNQUOTE(JSON_EXTRACT(p.pct_or_regional_publishing_data, '$.pbdt')) AS pct_publication_date,
  p.language, p.granted_number,
  p.main_classification_ipcr AS main_ipcr, p.further_classification_ipcr AS further_ipcr,
  p.main_classification_cpc AS main_cpc, p.further_classification_cpc AS further_cpc,
  p.keywords, p.value AS patent_value, p.update_time,
  t.titles, t.title_localized, t.title_zh,
  a.abstracts, a.abstract_localized, a.abstract_zh,
  l.status,
  JSON_UNQUOTE(JSON_EXTRACT(l.dates_of_public_availability, '$.date')) AS grant_date,
  JSON_UNQUOTE(JSON_EXTRACT(l.dates_of_public_availability, '$.year')) AS grant_year,
  JSON_UNQUOTE(JSON_EXTRACT(l.dates_of_public_availability, '$.month')) AS grant_month,
  l.anticipated_expiration, l.expiration_year,
  c.reference_cited AS citation_nums, c.cited_by_nums,
  c.non_patent_count AS non_patent_citation_nums,
  f.simple_family_number
FROM dwd_patent p
LEFT JOIN dwd_patent_title t ON t.patent_id = p.patent_id
LEFT JOIN dwd_patent_abstract a ON a.patent_id = p.patent_id
LEFT JOIN dwd_patent_legal l ON l.patent_id = p.patent_id
LEFT JOIN dwd_patent_cited c ON c.patent_id = p.patent_id
LEFT JOIN dwd_patent_family f ON f.patent_id = p.patent_id
ORDER BY p.id
LIMIT %s OFFSET %s
"""



def mysql_connection() -> pymysql.Connection:
    """创建专利 ETL 独立 MySQL 连接，不使用项目 MySQL 公共能力。"""
    password = os.getenv("PATENT_MYSQL_PASSWORD")
    if password is None:
        raise RuntimeError("缺少PATENT_MYSQL_PASSWORD环境变量")
    return pymysql.connect(
        host=os.getenv("PATENT_MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("PATENT_MYSQL_PORT", "3306")),
        user=os.getenv("PATENT_MYSQL_USERNAME", "root"),
        password=password,
        database=os.getenv("PATENT_MYSQL_DATABASE", "gkx_element"),
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=True,
    )


def split_ngql(content: str) -> list[str]:
    """按分号拆分当前简单DDL，并忽略整行注释。"""
    clean_lines = [line for line in content.splitlines() if not line.lstrip().startswith("--")]
    return [part.strip() for part in "\n".join(clean_lines).split(";") if part.strip()]


def init_schema() -> None:
    graph = get_trs_graph_client()
    for statement in split_ngql(DDL_FILE.read_text(encoding="utf-8")):
        last_error: Exception | None = None
        for attempt in range(1, 6):
            try:
                graph.execute_write(statement)
                last_error = None
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt == 5:
                    break
                time.sleep(attempt)
        if last_error is not None:
            raise last_error
    logger.info("Patent Schema初始化完成")


def localized_text(raw: Any, language: str, fallback: Any = "") -> str:
    """从 JSON 对象或旧多语言数组中提取指定语言文本。"""
    if raw is None:
        return str(fallback or "")
    value = raw
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return value
    if isinstance(value, dict):
        candidate = value.get(language)
        if isinstance(candidate, list):
            return "\n".join(str(item) for item in candidate)
        if candidate is not None:
            return str(candidate)
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and item.get("language") == language:
                return str(item.get("text") or "")
    return str(fallback or "")


def first_localized_text(raw: Any, fallback: Any = "") -> str:
    """提取多语言 JSON 中第一个非空文本。"""
    if raw is None:
        return str(fallback or "")
    value = raw
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return value
    if isinstance(value, dict):
        for candidate in value.values():
            if isinstance(candidate, list):
                text = "\n".join(str(item) for item in candidate if item is not None)
            else:
                text = str(candidate or "")
            if text:
                return text
    return str(fallback or "")


def normalized_language(raw: Any) -> str:
    """将 JSON 语言数组统一为逗号分隔字符串。"""
    if raw is None:
        return ""
    value = raw
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return value
    if isinstance(value, list):
        return ",".join(str(item).strip() for item in value if str(item).strip())
    return str(value)


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
    if value is None or str(value).strip() == "":
        return 'date("1970-01-01")'
    return f"date({ngql_string(str(value)[:10])})"


def ngql_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        text = value.strftime("%Y-%m-%dT%H:%M:%S")
    else:
        text = str(value or "1970-01-01 00:00:00").replace(" ", "T")[:19]
    return f"datetime({ngql_string(text)})"


def ngql_int(value: Any) -> str:
    if value is None or str(value).strip() == "":
        return "0"
    return str(int(value))


def patent_payload(
    row: dict[str, Any], batch_id: str, ingest_time: datetime
) -> tuple[str, list[str]]:
    patent_id = str(row["patent_id"]).strip()
    if not patent_id:
        raise ValueError("patent_id为空")

    title_original = first_localized_text(row.get("titles"), row.get("title_zh"))
    title_en = localized_text(row.get("title_localized"), "en")
    title_zh = str(row.get("title_zh") or "") or localized_text(row.get("titles"), "zh")
    abstract_original = first_localized_text(row.get("abstracts"), row.get("abstract_zh"))
    abstract_en = localized_text(row.get("abstract_localized"), "en")
    abstract_zh = str(row.get("abstract_zh") or "") or localized_text(
        row.get("abstracts"), "zh"
    )

    values = [
        ngql_string(patent_id),
        ngql_string(row.get("publication_number")),
        ngql_string(row.get("application_kind")),
        ngql_string(row.get("country_code")),
        ngql_string(row.get("country")),
        ngql_string(row.get("publication_kind")),
        ngql_string(row.get("publication_date")),
        ngql_int(row.get("publication_year")),
        ngql_string(row.get("publication_month")),
        ngql_string(row.get("application_number")),
        ngql_string(row.get("application_country")),
        ngql_string(row.get("application_date")),
        ngql_int(row.get("application_year")),
        ngql_string(row.get("application_month")),
        ngql_string(row.get("pct_application_number")),
        ngql_string(row.get("pct_application_date")),
        ngql_string(row.get("pct_national_stage_date")),
        ngql_string(row.get("pct_publication_number")),
        ngql_string(row.get("pct_publication_date")),
        ngql_string(title_original),
        ngql_string(title_en),
        ngql_string(title_zh),
        ngql_string(abstract_original),
        ngql_string(abstract_en),
        ngql_string(abstract_zh),
        ngql_string(normalized_language(row.get("language"))),
        ngql_string(row.get("granted_number")),
        ngql_string(row.get("main_ipcr")),
        ngql_string(row.get("further_ipcr")),
        ngql_string(row.get("main_cpc")),
        ngql_string(row.get("further_cpc")),
        ngql_string(row.get("keywords")),
        ngql_string(row.get("status")),
        ngql_string(row.get("grant_date")),
        ngql_int(row.get("grant_year")),
        ngql_string(row.get("grant_month")),
        ngql_date(row.get("anticipated_expiration")),
        ngql_int(row.get("expiration_year")),
        ngql_int(row.get("citation_nums")),
        ngql_int(row.get("cited_by_nums")),
        ngql_int(row.get("non_patent_citation_nums")),
        ngql_int(row.get("patent_value")),
        ngql_string(row.get("simple_family_number")),
        ngql_string("gkx_element"),
        ngql_string("dwd_patent"),
        ngql_string(patent_id),
        ngql_string(""),
        ngql_string(batch_id),
        ngql_datetime(ingest_time),
        ngql_datetime(row.get("update_time")),
    ]
    return f"patent_{patent_id}", values


def insert_statement(payloads: list[tuple[str, list[str]]]) -> str:
    rows = ",\n".join(f"{ngql_string(vid)}:({', '.join(values)})" for vid, values in payloads)
    return f"INSERT VERTEX Patent({', '.join(PATENT_PROPERTIES)}) VALUES\n{rows};"


def fetch_batch(connection: pymysql.Connection, limit: int, offset: int) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(SELECT_SQL, (limit, offset))
        return list(cursor.fetchall())


def load_patents(
    *, batch_size: int, offset: int, limit: int | None, batch_id: str, dry_run: bool
) -> int:
    graph = None if dry_run else get_trs_graph_client()
    connection = mysql_connection()
    ingest_time = datetime.now().replace(microsecond=0)
    loaded = 0
    current_offset = offset
    try:
        while limit is None or loaded < limit:
            requested = batch_size if limit is None else min(batch_size, limit - loaded)
            rows = fetch_batch(connection, requested, current_offset)
            if not rows:
                break
            payloads = [patent_payload(row, batch_id, ingest_time) for row in rows]
            statement = insert_statement(payloads)
            if dry_run:
                logger.info(
                    "dry-run批次 offset=%d rows=%d nGQL字符=%d",
                    current_offset,
                    len(rows),
                    len(statement),
                )
            else:
                assert graph is not None
                graph.execute_write(statement)
            loaded += len(rows)
            current_offset += len(rows)
            logger.info("Patent装载进度：%d", loaded)
            if len(rows) < requested:
                break
    finally:
        connection.close()
    return loaded


def verify() -> list[dict[str, Any]]:
    graph = get_trs_graph_client()
    result = graph.execute_read("MATCH (p:Patent) RETURN count(p) AS patent_count")
    logger.info("dev空间Patent统计：%s", result.records)
    return result.records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="装载Patent基本实体到TRSGraph")
    parser.add_argument("--init-schema", action="store_true")
    parser.add_argument("--load", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--batch-id", default=f"PATENT_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not (args.init_schema or args.load or args.verify):
        raise SystemExit("至少指定--init-schema、--load或--verify之一")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.init_schema:
        init_schema()
    if args.load:
        count = load_patents(
            batch_size=args.batch_size,
            offset=args.offset,
            limit=args.limit,
            batch_id=args.batch_id,
            dry_run=args.dry_run,
        )
        logger.info("本次处理Patent节点：%d", count)
    if args.verify and not args.dry_run:
        verify()


if __name__ == "__main__":
    main()
