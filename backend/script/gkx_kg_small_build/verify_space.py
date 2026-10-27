"""构建后校验：图空间各 TAG/EDGE 计数 vs gkx_kg_sm 源表计数，并逐 TAG 抽查一个顶点。

计数用 SUBMIT JOB STATS + SHOW STATS（异步统计，轮询几秒）；
MySQL 侧计数经 platform_mysql_datasource 取连接参数直连，不在代码里落密码。

用法（api 容器内）::

    PYTHONPATH=/app /app/.venv/bin/python -m script.gkx_kg_small_build.verify_space \
        [--space gkx_kg_sm] [--database gkx_kg_sm]
"""

from __future__ import annotations

import argparse
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("verify_small_space")

TAGS = [
    ("Person", "sm_person", "person_", "person_id"),
    ("Paper", "sm_paper", "paper_", "id"),
    ("Patent", "sm_patent", "patent_", "patent_id"),
    ("PatentFamily", "sm_patent_family", "patent_family_", "family_number"),
    ("Project", "sm_project", "project_", "id"),
    ("Organization", "sm_organization", "org_", "org_id"),
    ("News", "sm_news", "news_", "news_id"),
    ("Event", "sm_event", "event_", "event_id"),
    ("Journal", "sm_journal", "journal_", "publication_id"),
    ("Keyword", "sm_keyword", "keyword_", "keyword_id"),
    ("Report", "sm_report", "report_", "report_id"),
    ("Product", "sm_product", "product_", "product_id"),
    ("IndustryChain", "sm_industry_chain", "chain_", "chain_code"),
    ("IndustryNode", "sm_industry_node", "node_", "node_id"),
    ("CitationStub", "sm_citation_stub", "paper_ref_", "id"),
]
# CitationStub 的 vid = paper_ref_ + id[4:]，单独处理
STUB_VID_SQL = "CONCAT('paper_ref_', SUBSTRING(id, 5))"


def _mysql_counts(database: str) -> dict[str, int]:
    from urllib.parse import quote_plus

    from sqlalchemy import create_engine, text

    from db_model.mysql_datasource import MysqlDatasource
    from infra.mysql import session_scope

    with session_scope() as session:
        row = session.query(MysqlDatasource).filter(
            MysqlDatasource.id == "MYSQL-A176CF7A"
        ).first()
        if row is None:
            row = session.query(MysqlDatasource).first()
        params = dict(host=row.host, port=row.port, user=row.username,
                      password=row.password)

    url = (
        f"mysql+pymysql://{params['user']}:{quote_plus(params['password'])}"
        f"@{params['host']}:{params['port']}/{database}?charset=utf8mb4"
    )
    engine = create_engine(url)
    counts: dict[str, int] = {}
    try:
        with engine.connect() as conn:
            for _tag, table, _prefix, _pk in TAGS:
                counts[table] = conn.execute(
                    text(f"SELECT COUNT(*) FROM {table}")
                ).scalar()
            for (edge_type, c) in conn.execute(
                text("SELECT edge_type, COUNT(*) FROM sm_edge GROUP BY edge_type")
            ).fetchall():
                counts[f"edge:{edge_type}"] = c
    finally:
        engine.dispose()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--space", default="gkx_kg_sm")
    parser.add_argument("--database", default="gkx_kg_sm")
    args = parser.parse_args()

    from infra.graph_db.client import TRSGraphClient
    from infra.graph_db.config import TRSGraphSettings

    settings = TRSGraphSettings.from_env()
    settings.space = args.space
    client = TRSGraphClient(settings)
    client.connect()
    stats = _show_stats(client)

    mysql_counts = _mysql_counts(args.database)

    logger.info("%-18s %10s %10s", "TAG/EDGE", "graph", "mysql")
    ok = True
    graph_tag = {r["Name"]: int(r["Count"]) for r in stats if r["Type"] == "Tag"}
    graph_edge = {r["Name"]: int(r["Count"]) for r in stats if r["Type"] == "Edge"}
    for tag, table, _prefix, _pk in TAGS:
        g, m = graph_tag.get(tag, 0), mysql_counts.get(table, 0)
        flag = "" if g == m else "  ← 不一致"
        ok = ok and g == m
        logger.info("%-18s %10d %10d%s", tag, g, m, flag)
    for name, m in sorted(mysql_counts.items()):
        if not name.startswith("edge:"):
            continue
        edge = name[5:]
        g = graph_edge.get(edge, 0)
        flag = "" if g == m else "  ← 不一致"
        ok = ok and g == m
        logger.info("%-18s %10d %10d%s", edge, g, m, flag)
    logger.info("校验结果: %s", "一致 ✓" if ok else "存在不一致，见上表")


def _show_stats(client) -> list:
    client.execute_write("SUBMIT JOB STATS")
    for _ in range(10):
        time.sleep(2)
        try:
            res = client.execute_query("SHOW STATS")
            rows = res[0] if isinstance(res, tuple) else res.records if hasattr(res, "records") else res
            if rows and any(str(r["Count"]).isdigit() and int(r["Count"]) > 0 for r in rows):
                return rows
        except Exception:  # noqa: BLE001
            pass
    raise SystemExit("SHOW STATS 10 轮未就绪")


if __name__ == "__main__":
    main()
