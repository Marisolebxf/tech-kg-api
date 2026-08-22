"""产业链企业 org 节点回填：为缺失的链上企业建 Organization 节点。

背景：dev 图空间 BELONGS_TO_NODE 只有 374/2951，因为链上 2074 家企业里大部分
`org_{antitypic}` 节点不存在，被边 ETL 的"端点不存在就 skip"逻辑跳过。

链表（dwd_org_industry_chain_dtl）和事件表（资讯/财务/风险）本来就用同一套
org_id（antitypic），所以"实体绑定"本质 = 回填缺失的 org 节点。回填后重跑边
ETL，被 skip 的 BELONGS_TO_NODE / HAS_NEWS / INVOLVED_IN / EXECUTIVE_OF 自动补连。

本脚本：
  1. 从 dwd_org_industry_chain_dtl 取全量 (antitypic, credit_code)
  2. 从 dwd_org_industry_chain_prod_dtl 按 antitypic 聚合 company_name + tech_product
  3. 探测 dev 中已存在的 org_{antitypic}，对缺失集合 INSERT VERTEX Organization

vid = org_{antitypic}（与 BELONGS_TO_NODE 端点期望一致，复用 organization_vid 约定）。
credit_code 写入 Organization.external_id（canonical 键，供未来对齐用）。

安全约束：纯增量 INSERT VERTEX，不删不改现有节点；缺失集合 vid 本来就不存在，
不会覆盖任何已有 org。可重跑（已存在的 vid 会被 existing 集合跳过）。

用法：
    cd backend && PYTHONPATH=. .venv/bin/python script/industry_chain_etl/backfill_chain_org_nodes.py
"""

from __future__ import annotations

import json
import logging
import os
from urllib.parse import quote_plus

from sqlalchemy import text

from infra.graph_db import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings
from infra.mysql import MySQLClient

logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

SPACE = os.getenv("TRS_GRAPH_SPACE", "dev")
BATCH = 500
INGEST_BATCH = "chain_org_backfill_20260810"
INGEST_TIME = "2026-08-10"

# Organization tag 字段（与 schemas/dev_organization_schema.ngql 一致）
ORG_FIELDS = [
    "org_id",
    "name_cn",
    "external_id",
    "main_products",
    "org_kind",
    "extra_json",
    "source_system",
    "source_table",
    "source_record_id",
    "ingest_batch",
    "ingest_time",
]


def get_graph_client() -> TRSGraphClient:
    s = TRSGraphSettings.from_env()
    s.space = SPACE
    c = TRSGraphClient(s)
    c.connect()
    return c


def get_mysql_client() -> MySQLClient:
    url = (
        f"mysql+pymysql://{quote_plus(os.getenv('MYSQL_USERNAME', 'root'))}:"
        f"{quote_plus(os.getenv('MYSQL_PASSWORD', '123456789'))}"
        f"@{os.getenv('MYSQL_HOST', '127.0.0.1')}:{os.getenv('MYSQL_PORT', '3306')}"
        f"/gkx_element?charset=utf8mb4"
    )
    return MySQLClient(url=url)


def esc(v) -> str:
    if v is None:
        return "NULL"
    s = str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")
    return f'"{s}"'


def _write(client: TRSGraphClient, ngql: str, label: str) -> bool:
    try:
        client.execute_write(ngql)
        return True
    except Exception as exc:
        logger.warning("  %s 失败: %s", label, str(exc)[:160])
        return False


def fetch_existing_org_vids(graph: TRSGraphClient) -> set[str]:
    """取 dev 中所有 Organization 节点 vid。"""
    existing: set[str] = set()
    try:
        r = graph.execute_read(f"USE {SPACE}; MATCH (v:Organization) RETURN id(v) AS vid;")
        existing = {str(rec.get("vid")) for rec in r.records if rec.get("vid")}
    except Exception as exc:
        logger.warning("  取已有 org 失败: %s", exc)
    return existing


def collect_chain_companies(session) -> dict[str, dict]:
    """汇集链上企业：antitypic -> {credit_code, company_name, tech_products}.

    credit_code 优先取 prod_dtl，回退 dtl；company_name/products 取 prod_dtl。
    """
    companies: dict[str, dict] = {}

    # 1) dtl: antitypic + credit_code（全量链上企业集合）
    dtl_rows = session.execute(
        text("SELECT antitypic, credit_code FROM dwd_org_industry_chain_dtl")
    ).all()
    for antitypic, credit_code in dtl_rows:
        if not antitypic:
            continue
        cc = companies.setdefault(
            antitypic, {"credit_code": "", "company_name": "", "products": []}
        )
        if credit_code and not cc["credit_code"]:
            cc["credit_code"] = str(credit_code)

    # 2) prod_dtl: antitypic + company_name + credit_code + tech_product（聚合）
    prod_rows = session.execute(
        text(
            "SELECT antitypic, company_name, credit_code, tech_product "
            "FROM dwd_org_industry_chain_prod_dtl"
        )
    ).all()
    for antitypic, company_name, credit_code, tech_product in prod_rows:
        if not antitypic:
            continue
        cc = companies.setdefault(
            antitypic, {"credit_code": "", "company_name": "", "products": []}
        )
        if credit_code and not cc["credit_code"]:
            cc["credit_code"] = str(credit_code)
        if company_name and not cc["company_name"]:
            cc["company_name"] = str(company_name)
        if tech_product and str(tech_product) not in cc["products"]:
            cc["products"].append(str(tech_product))

    return companies


def build_vertex_rows(missing: dict[str, dict]) -> list[tuple]:
    """构造 INSERT VERTEX 行：(vid, org_id, name_cn, external_id, main_products, org_kind, extra_json, ...)."""
    rows = []
    for antitypic, info in missing.items():
        vid = f"org_{antitypic}"
        products = "；".join(info["products"][:20]) if info["products"] else ""
        extra = {
            "antitypic": antitypic,
            "credit_code": info["credit_code"],
            "company_name": info["company_name"],
            "source_tables": ["dwd_org_industry_chain_dtl", "dwd_org_industry_chain_prod_dtl"],
        }
        rows.append(
            (
                vid,
                antitypic,  # org_id
                info["company_name"],  # name_cn
                info["credit_code"],  # external_id (credit_code)
                products,  # main_products
                "industry_chain_enterprise",  # org_kind
                json.dumps(extra, ensure_ascii=False),  # extra_json
                "gkx_element",  # source_system
                "dwd_org_industry_chain_prod_dtl",  # source_table
                antitypic,  # source_record_id
                INGEST_BATCH,
                INGEST_TIME,
            )
        )
    return rows


def batch_insert_vertex(client, tag, fields, rows, label):
    if not rows:
        return 0
    fl = ",".join(fields)
    vals = ",".join(f"{esc(vid)}:({','.join(esc(v) for v in vals)})" for vid, *vals in rows)
    _write(client, f"USE {SPACE}; INSERT VERTEX {tag}({fl}) VALUES {vals};", label)
    return len(rows)


def main() -> None:
    graph = get_graph_client()
    mysql = get_mysql_client()

    logger.info("=== 阶段 A：回填缺失链上企业 org 节点 ===")

    with mysql.session_scope() as session:
        companies = collect_chain_companies(session)
    logger.info("  链上企业 distinct antitypic: %d", len(companies))

    existing = fetch_existing_org_vids(graph)
    logger.info("  dev 已有 Organization 节点: %d", len(existing))

    missing = {a: info for a, info in companies.items() if f"org_{a}" not in existing}
    logger.info("  缺失（需回填）: %d", len(missing))
    logger.info("  已存在（跳过）: %d", len(companies) - len(missing))

    rows = build_vertex_rows(missing)
    logger.info("  待写入 Organization 节点: %d", len(rows))

    written = 0
    for i in range(0, len(rows), BATCH):
        written += batch_insert_vertex(
            graph, "Organization", ORG_FIELDS, rows[i : i + BATCH], "Organization(backfill)"
        )
    logger.info("  写入完成: %d", written)

    # 统计
    try:
        logger.info("  Organization 节点总数: %s", graph.node_count("Organization"))
    except Exception:
        pass

    graph.close()
    logger.info("=== 阶段 A 完成 ===")


if __name__ == "__main__":
    main()
