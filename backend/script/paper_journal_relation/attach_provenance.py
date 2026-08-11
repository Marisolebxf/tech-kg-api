"""给论文域实体挂 organization_base tag + 写 confidence + 溯源（dev 公共空间，只动论文域顶点）。

organization_base tag 已存在（organization_id, confidence, source_system, source_table,
source_record_id, source_url, ingest_batch, ingest_time, source_update_time, extra_json）。
本脚本把它作为溯源+置信度 mixin 挂到论文域实体上：
  - 真实 Paper/Person/Journal/Report：从 gkx_element 取 vid，confidence=1.0
  - Keyword：dev MATCH（Keyword tag 论文域专属），confidence=1.0
  - 桩 Paper（paper_ref_/cit_/rel_/rp_，doi-only 不在库）：dev MATCH，confidence=0.3
  - organization_id 留空（gkx_element 论文表无 org_id 外键，待机构域对齐回填）

dev 公共空间安全：
  - 真实实体 vid 从 MySQL 取（论文域专属），不碰学者/机构/项目/专利域顶点
  - Person 只取 dwd_zh/en_author.author_id（论文作者），不碰学者域 Person
  - 桩/Keyword 按 vid 前缀/tag 精确匹配，论文域专属
  - INSERT TAG 是给顶点加一个 mixin tag，不改动顶点原有 domain tag 的任何属性

幂等：再跑会覆盖 organization_base tag（同值），无副作用。

用法：
    cd backend && PYTHONPATH=. .venv/bin/python script/paper_journal_relation/attach_provenance.py
"""

from __future__ import annotations

import logging
import os
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text

from infra.graph_db import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings

logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

SPACE = "dev"
BATCH = 500
INGEST_BATCH = "paper_prov_20260811"
INGEST_TIME = "2026-08-11T00:00:00Z"
SOURCE_SYSTEM = "gkx_element"

# 真实实体：MySQL 查询 → (vid 生成, source_table)
REAL_ENTITY_QUERIES = [
    # (label, sql, vid_template, source_table, vid_param_index)
    (
        "Paper_zh",
        "SELECT id FROM dwd_zh_paper",
        "paper_{}",
        "dwd_zh_paper",
    ),
    (
        "Paper_en",
        "SELECT id FROM dwd_en_paper",
        "paper_{}",
        "dwd_en_paper",
    ),
    (
        "Person_zh",
        "SELECT DISTINCT author_id FROM dwd_zh_author WHERE author_id IS NOT NULL",
        "person_{}",
        "dwd_zh_author",
    ),
    (
        "Person_en",
        "SELECT DISTINCT author_id FROM dwd_en_author WHERE author_id IS NOT NULL",
        "person_{}",
        "dwd_en_author",
    ),
    (
        "Journal_zh",
        "SELECT DISTINCT publication_id FROM dwd_zh_journal WHERE publication_id IS NOT NULL",
        "journal_{}",
        "dwd_zh_journal",
    ),
    (
        "Journal_en",
        "SELECT DISTINCT publication_id FROM dwd_en_journal WHERE publication_id IS NOT NULL",
        "journal_{}",
        "dwd_en_journal",
    ),
    (
        "Report_zh",
        "SELECT DISTINCT report_id FROM dwd_zh_report WHERE report_id IS NOT NULL",
        "report_{}",
        "dwd_zh_report",
    ),
    (
        "Report_en",
        "SELECT DISTINCT report_id FROM dwd_en_report WHERE report_id IS NOT NULL",
        "report_{}",
        "dwd_en_report",
    ),
]

# 桩：dev MATCH 前缀 → (source_table, confidence)
STUB_PREFIXES = [
    ("paper_ref_", "dwd_zh_paper_reference", 0.3),
    ("paper_cit_", "dwd_zh_paper_citation", 0.3),
    ("paper_rel_", "dwd_zh_paper_related", 0.3),
    ("paper_rp_", "dwd_zh_report_paper", 0.3),
]


def get_graph() -> TRSGraphClient:
    s = TRSGraphSettings(
        base_url=os.getenv("TRS_GRAPH_BASE_URL", "http://localhost:8090"),
        space=SPACE,
        api_key=os.getenv("TRS_GRAPH_API_KEY"),
        timeout=int(os.getenv("TRS_GRAPH_TIMEOUT", "120")),
    )
    c = TRSGraphClient(s)
    c.connect()
    return c


def get_mysql_engine():
    url = (
        f"mysql+pymysql://{quote_plus(os.getenv('MYSQL_USERNAME', 'root'))}:"
        f"{quote_plus(os.getenv('MYSQL_PASSWORD', '123456789'))}"
        f"@{os.getenv('MYSQL_HOST', '127.0.0.1')}:{os.getenv('MYSQL_PORT', '3306')}"
        f"/gkx_element?charset=utf8mb4"
    )
    return create_engine(url)


def esc(v) -> str:
    if v is None:
        return '""'
    s = str(v).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def insert_tag_batch(
    client: TRSGraphClient,
    rows: list[tuple[str, str, float, str, str]],
) -> int:
    """rows = [(vid, source_record_id, confidence, source_table)]。挂 organization_base tag。"""
    if not rows:
        return 0
    fields = (
        "organization_id, confidence, source_system, source_table, source_record_id, "
        "ingest_batch, ingest_time"
    )
    parts = []
    for vid, rec_id, conf, src_tbl in rows:
        parts.append(
            f'"{vid}":("",{float(conf)},{esc(SOURCE_SYSTEM)},{esc(src_tbl)},'
            f"{esc(rec_id)},{esc(INGEST_BATCH)},{esc(INGEST_TIME)})"
        )
    for i in range(0, len(parts), BATCH):
        chunk = ",".join(parts[i : i + BATCH])
        try:
            # INSERT VERTEX organization_base 给已存在顶点加 mixin tag，保留原 domain tag
            # （此 Nebula 版本不支持 INSERT TAG 语法；INSERT VERTEX 单 tag 是加性，不覆盖其它 tag）
            client.execute_write(
                f"USE {SPACE}; INSERT VERTEX organization_base({fields}) VALUES {chunk};"
            )
        except Exception as exc:
            logger.warning(
                "  INSERT VERTEX organization_base 批失败 (%d): %s", len(chunk), str(exc)[:120]
            )
    return len(rows)


def fetch_real_vids(label: str, sql: str, vid_tmpl: str) -> list[tuple[str, str]]:
    """从 MySQL 取 (vid, source_record_id)。"""
    eng = get_mysql_engine()
    with eng.connect() as conn:
        rows = conn.execute(text(sql)).all()
    eng.dispose()
    out = []
    for r in rows:
        rec_id = str(r[0])
        out.append((vid_tmpl.format(rec_id), rec_id))
    logger.info("  %s: MySQL 取 %d 个", label, len(out))
    return out


def fetch_dev_vids_by_prefix(client: TRSGraphClient, prefix: str) -> list[str]:
    """dev MATCH 指定前缀的所有桩 vid（清桩后只剩 26 字符正确集 + paper_rp_）。SKIP/LIMIT 分页。"""
    vids = []
    limit = 5000
    offset = 0
    while True:
        q = (
            f'USE {SPACE}; MATCH (v) WHERE id(v) STARTS WITH "{prefix}" '
            f"RETURN id(v) AS vid SKIP {offset} LIMIT {limit};"
        )
        r = client.execute_read(q)
        batch = [str(rec.get("vid")) for rec in r.records if rec.get("vid")]
        if not batch:
            break
        vids.extend(batch)
        offset += len(batch)
        if len(batch) < limit:
            break
    return vids


def fetch_keyword_vids(client: TRSGraphClient) -> list[str]:
    vids = []
    limit = 5000
    offset = 0
    while True:
        q = f"USE {SPACE}; MATCH (v:Keyword) RETURN id(v) AS vid SKIP {offset} LIMIT {limit};"
        r = client.execute_read(q)
        batch = [str(rec.get("vid")) for rec in r.records if rec.get("vid")]
        if not batch:
            break
        vids.extend(batch)
        offset += len(batch)
        if len(batch) < limit:
            break
    return vids


def main() -> None:
    client = get_graph()
    total = 0
    logger.info("=== 挂 organization_base + confidence（真实实体 confidence=1.0）===")
    for label, sql, vid_tmpl, src_tbl in REAL_ENTITY_QUERIES:
        try:
            rows = fetch_real_vids(label, sql, vid_tmpl)
        except Exception as exc:
            logger.warning("  %s MySQL 取数失败: %s", label, str(exc)[:120])
            continue
        batch = [(vid, rec_id, 1.0, src_tbl) for vid, rec_id in rows]
        total += insert_tag_batch(client, batch)
        logger.info("  %s: 挂 tag %d", label, len(batch))

    logger.info("=== Keyword（dev MATCH，confidence=1.0）===")
    kw_vids = fetch_keyword_vids(client)
    logger.info("  Keyword: %d 个", len(kw_vids))
    total += insert_tag_batch(client, [(v, v, 1.0, "dwd_zh_paper_classification") for v in kw_vids])

    logger.info("=== 桩 Paper（dev MATCH，confidence=0.3）===")
    for prefix, src_tbl, conf in STUB_PREFIXES:
        vids = fetch_dev_vids_by_prefix(client, prefix)
        logger.info("  %s: %d 个", prefix, len(vids))
        total += insert_tag_batch(client, [(v, v, conf, src_tbl) for v in vids])

    logger.info("=== 总计挂 organization_base tag %d 个顶点 ===", total)
    # 校验
    try:
        r = client.execute_read(
            f"USE {SPACE}; MATCH (v) WHERE v.organization_base.confidence IS NOT NULL "
            f"RETURN count(*) AS c;"
        )
        logger.info("  校验: organization_base 非空节点数 = %s", r.records[0].get("c"))
    except Exception as exc:
        logger.warning("  校验失败: %s", str(exc)[:120])
    client.close()


if __name__ == "__main__":
    main()
