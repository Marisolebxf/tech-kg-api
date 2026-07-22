#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
学者领域 ETL 脚本
从科技要素数据库 (gkx_element) 中读取学者相关源数据，
按照 ontology.md 本体设计和 mapping.md 映射关系，
将数据写入 TRSGraph dev 图空间。

涉及表：
  dwd_scholar                  -> Person Tag
  dwd_scholar_talent_flag      -> Person.is_academician (合并入 Person)
  dwd_scholar_research_direction -> Person.research_fields (合并入 Person)
  dwd_scholar_coauthor         -> COAUTHOR_WITH Edge
  dwd_scholar_paper_relation   -> AUTHORED_BY Edge (Paper -> Person)
  dwd_scholar_papers           -> Paper Tag

依赖：
  pip install nebula3-python==3.8.3 pymysql
"""

import os
import json
import hashlib
import logging
import datetime
import argparse

import pymysql
import pymysql.cursors
from nebula3.gclient.net import ConnectionPool
from nebula3.Config import Config

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 配置（优先读环境变量，其次使用默认值）
# ---------------------------------------------------------------------------
MYSQL_HOST     = os.getenv("MYSQL_HOST",     "127.0.0.1")
MYSQL_PORT     = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER     = os.getenv("MYSQL_USER",     "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "gkx_element")

NEBULA_HOST    = os.getenv("NEBULA_HOST",    "127.0.0.1")
NEBULA_PORT    = int(os.getenv("NEBULA_PORT", "9669"))
NEBULA_USER    = os.getenv("NEBULA_USER",    "root")
NEBULA_PASSWORD= os.getenv("NEBULA_PASSWORD","nebula")
NEBULA_SPACE   = os.getenv("NEBULA_SPACE",   "dev")

BATCH_ID       = os.getenv("INGEST_BATCH",
                            "BATCH_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def _esc(v) -> str:
    """将 Python 值转为 nGQL 字符串字面量（含引号）。"""
    if v is None:
        return '""'
    return json.dumps(str(v), ensure_ascii=False)


def make_person_vid(scholar_id: str) -> str:
    return f"person_{scholar_id}"


def make_org_vid(org_name: str) -> str:
    h = hashlib.md5(org_name.strip().lower().encode()).hexdigest()[:16]
    return f"org_{h}"


def make_ds_vid(table_name: str) -> str:
    return f"ds_{table_name}"


# ---------------------------------------------------------------------------
# 数据库连接
# ---------------------------------------------------------------------------
def get_mysql(host, port, user, password, database):
    return pymysql.connect(
        host=host, port=port, user=user, password=password,
        database=database, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def get_nebula(host, port, user, password):
    cfg = Config()
    cfg.max_connection_pool_size = 4
    pool = ConnectionPool()
    if not pool.init([(host, port)], cfg):
        raise RuntimeError(f"Cannot connect to NebulaGraph {host}:{port}")
    session = pool.get_session(user, password)
    return session, pool


# ---------------------------------------------------------------------------
# 读取源数据
# ---------------------------------------------------------------------------
SCHOLAR_SQL = """
SELECT
    s.scholar_id, s.name_en, s.name_zh, s.avatar,
    s.scholar_org_name_en, s.scholar_org_name_zh,
    s.bio, s.bio_zh,
    s.work_experience_date, s.work_experience_institution_en,
    s.work_experience_department_en, s.work_experience_position_en,
    s.work_experience_institution_zh, s.work_experience_department_zh,
    s.work_experience_position_zh,
    s.education_background_date, s.education_background_institution_en,
    s.education_background_degree_en, s.education_background_institution_zh,
    s.education_background_degree_zh,
    s.paper_nums, s.citation_nums, s.h_index, s.status,
    DATE_FORMAT(s.update_time, '%%Y-%%m-%%d %%H:%%i:%%s') AS update_time,
    t.academician,
    r.fields AS research_fields
FROM dwd_scholar s
LEFT JOIN dwd_scholar_talent_flag      t ON t.scholar_id = s.scholar_id
LEFT JOIN dwd_scholar_research_direction r ON r.scholar_id = s.scholar_id
WHERE s.status = 1
"""

PAPER_SQL = """
SELECT
    p.id, p.zh_name, p.en_name, p.paper_url,
    DATE_FORMAT(p.cover_date_start, '%%Y-%%m-%%d') AS publication_date,
    p.zh_abstract, p.en_abstract, p.doi, p.publication_en_name,
    DATE_FORMAT(p.update_time, '%%Y-%%m-%%d %%H:%%i:%%s') AS update_time
FROM dwd_scholar_papers p
WHERE p.status = 1 AND p.id IS NOT NULL
"""

COAUTHOR_SQL = """
SELECT scholar_id, co_scholar_id, co_paper_count
FROM dwd_scholar_coauthor
WHERE status = 1
"""

REL_SQL = """
SELECT paper_id, scholar_id, citations
FROM dwd_scholar_paper_relation
WHERE status = 1
"""

DATASOURCE_META = [
    ("dwd_scholar",                    "学者"),
    ("dwd_scholar_talent_flag",        "学者人才标识"),
    ("dwd_scholar_research_direction", "学者研究方向"),
    ("dwd_scholar_papers",             "学者论文信息"),
    ("dwd_scholar_paper_relation",     "学者论文关系"),
    ("dwd_scholar_coauthor",           "学者合作者关系"),
]


# ---------------------------------------------------------------------------
# nGQL 生成
# ---------------------------------------------------------------------------
def ngql_datasource(table: str, cn: str) -> str:
    vid = _esc(make_ds_vid(table))
    return (
        f"INSERT VERTEX DataSource(source_table, table_cn_name, tier, library) "
        f"VALUES {vid}:({_esc(table)}, {_esc(cn)}, \"element\", \"gkx_element\")"
    )


def ngql_person(row: dict, now: str) -> str:
    vid = _esc(make_person_vid(row["scholar_id"]))
    org = row.get("scholar_org_name_zh") or row.get("scholar_org_name_en") or ""
    return (
        f"INSERT VERTEX Person("
        f"name_en, name_zh, email, source, avatar, scholar_org, bio_zh, "
        f"paper_nums, citation_nums, h_index, scholar_status, "
        f"is_academician, research_fields, "
        f"work_experience_date, work_experience_institution_en, work_experience_department_en, "
        f"work_experience_position_en, work_experience_institution_zh, work_experience_department_zh, "
        f"work_experience_position_zh, "
        f"education_background_date, education_background_institution_en, education_background_degree_en, "
        f"education_background_institution_zh, education_background_degree_zh, "
        f"source_system, source_table, source_record_id, source_url, "
        f"ingest_batch, ingest_time, source_update_time) "
        f"VALUES {vid}:("
        f"{_esc(row.get('name_en'))}, {_esc(row.get('name_zh'))}, "
        f"\"\", \"scholar\", "
        f"{_esc(row.get('avatar'))}, {_esc(org)}, {_esc(row.get('bio_zh'))}, "
        f"{int(row.get('paper_nums') or 0)}, "
        f"{int(row.get('citation_nums') or 0)}, "
        f"{int(row.get('h_index') or 0)}, "
        f"{int(row.get('status') or 0)}, "
        f"{_esc(row.get('academician'))}, {_esc(row.get('research_fields'))}, "
        f"{_esc(row.get('work_experience_date'))}, "
        f"{_esc(row.get('work_experience_institution_en'))}, "
        f"{_esc(row.get('work_experience_department_en'))}, "
        f"{_esc(row.get('work_experience_position_en'))}, "
        f"{_esc(row.get('work_experience_institution_zh'))}, "
        f"{_esc(row.get('work_experience_department_zh'))}, "
        f"{_esc(row.get('work_experience_position_zh'))}, "
        f"{_esc(row.get('education_background_date'))}, "
        f"{_esc(row.get('education_background_institution_en'))}, "
        f"{_esc(row.get('education_background_degree_en'))}, "
        f"{_esc(row.get('education_background_institution_zh'))}, "
        f"{_esc(row.get('education_background_degree_zh'))}, "
        f"\"gkx_element\", \"dwd_scholar\", {_esc(row['scholar_id'])}, \"\", "
        f"{_esc(BATCH_ID)}, {_esc(now)}, {_esc(row.get('update_time'))})"
    )


def ngql_person_sourced_from(scholar_id: str, now: str) -> str:
    src = _esc(make_person_vid(scholar_id))
    dst = _esc(make_ds_vid("dwd_scholar"))
    return (
        f"INSERT EDGE SOURCED_FROM(source_table, source_record_id, ingest_batch, ingest_time) "
        f"VALUES {src}->{dst}:(\"dwd_scholar\", {_esc(scholar_id)}, {_esc(BATCH_ID)}, {_esc(now)})"
    )


def ngql_org(org_name_zh: str, org_name_en: str, scholar_id: str, now: str) -> str:
    vid = _esc(make_org_vid(org_name_zh or org_name_en))
    return (
        f"INSERT VERTEX Organization(name_cn, name_en, org_kind, "
        f"source_system, source_table, source_record_id, ingest_batch, ingest_time) "
        f"VALUES {vid}:({_esc(org_name_zh)}, {_esc(org_name_en)}, "
        f"\"scholar_affiliation\", \"gkx_element\", \"dwd_scholar\", "
        f"{_esc(scholar_id)}, {_esc(BATCH_ID)}, {_esc(now)})"
    )


def ngql_affiliated_with(scholar_id: str, org_name: str, now: str) -> str:
    src = _esc(make_person_vid(scholar_id))
    dst = _esc(make_org_vid(org_name))
    return (
        f"INSERT EDGE AFFILIATED_WITH(affiliation_name, source, "
        f"source_table, source_record_id, ingest_batch, ingest_time) "
        f"VALUES {src}->{dst}:({_esc(org_name)}, \"scholar\", "
        f"\"dwd_scholar\", {_esc(scholar_id)}, {_esc(BATCH_ID)}, {_esc(now)})"
    )


def ngql_paper(row: dict, now: str) -> str:
    vid = _esc(f"paper_{row['id']}")
    return (
        f"INSERT VERTEX Paper("
        f"title_en, title_zh, doi, publication_date, source_url, source, "
        f"created_time, updated_time, abstract_zh, abstract_en, publication_name, "
        f"source_system, source_table, source_record_id, "
        f"ingest_batch, ingest_time, source_update_time) "
        f"VALUES {vid}:("
        f"{_esc(row.get('en_name'))}, {_esc(row.get('zh_name'))}, "
        f"{_esc(row.get('doi'))}, {_esc(row.get('publication_date'))}, "
        f"{_esc(row.get('paper_url'))}, \"scholar_paper\", "
        f"{_esc(now)}, {_esc(row.get('update_time'))}, "
        f"{_esc(row.get('zh_abstract'))}, {_esc(row.get('en_abstract'))}, "
        f"{_esc(row.get('publication_en_name'))}, "
        f"\"gkx_element\", \"dwd_scholar_papers\", {_esc(str(row['id']))}, "
        f"{_esc(BATCH_ID)}, {_esc(now)}, {_esc(row.get('update_time'))})"
    )


def ngql_paper_sourced_from(paper_id, now: str) -> str:
    src = _esc(f"paper_{paper_id}")
    dst = _esc(make_ds_vid("dwd_scholar_papers"))
    return (
        f"INSERT EDGE SOURCED_FROM(source_table, source_record_id, ingest_batch, ingest_time) "
        f"VALUES {src}->{dst}:(\"dwd_scholar_papers\", {_esc(str(paper_id))}, "
        f"{_esc(BATCH_ID)}, {_esc(now)})"
    )


def ngql_coauthor_with(row: dict, now: str) -> str:
    src = _esc(make_person_vid(row["scholar_id"]))
    dst = _esc(make_person_vid(row["co_scholar_id"]))
    rid = f"{row['scholar_id']}_{row['co_scholar_id']}"
    return (
        f"INSERT EDGE COAUTHOR_WITH(co_paper_count, source_table, source_record_id, "
        f"ingest_batch, ingest_time) "
        f"VALUES {src}->{dst}:({int(row['co_paper_count'])}, "
        f"\"dwd_scholar_coauthor\", {_esc(rid)}, {_esc(BATCH_ID)}, {_esc(now)})"
    )


def ngql_authored_by(row: dict, now: str) -> str:
    src = _esc(f"paper_{row['paper_id']}")
    dst = _esc(make_person_vid(row["scholar_id"]))
    rid = f"{row['paper_id']}_{row['scholar_id']}"
    return (
        f"INSERT EDGE AUTHORED_BY(citations, source_table, source_record_id, "
        f"ingest_batch, ingest_time) "
        f"VALUES {src}->{dst}:({int(row['citations'])}, "
        f"\"dwd_scholar_paper_relation\", {_esc(rid)}, {_esc(BATCH_ID)}, {_esc(now)})"
    )


# ---------------------------------------------------------------------------
# ETL 主流程
# ---------------------------------------------------------------------------
def run_etl(dry_run: bool = False):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"ETL start  batch={BATCH_ID}  dry_run={dry_run}")

    # --- 读取源数据 ---
    conn = get_mysql(MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE)
    try:
        with conn.cursor() as cur:
            cur.execute(SCHOLAR_SQL)
            scholars = cur.fetchall()
            cur.execute(PAPER_SQL)
            papers = cur.fetchall()
            cur.execute(COAUTHOR_SQL)
            coauthors = cur.fetchall()
            cur.execute(REL_SQL)
            rels = cur.fetchall()
    finally:
        conn.close()

    logger.info(f"source rows: scholars={len(scholars)}, papers={len(papers)}, "
                f"coauthors={len(coauthors)}, rels={len(rels)}")

    # --- 构建所有 nGQL 语句 ---
    stmts = []

    # DataSource vertices
    for table, cn in DATASOURCE_META:
        stmts.append(ngql_datasource(table, cn))

    # Persons / Orgs / edges
    seen_orgs: set = set()
    for row in scholars:
        stmts.append(ngql_person(row, now))
        stmts.append(ngql_person_sourced_from(row["scholar_id"], now))

        org_zh = row.get("scholar_org_name_zh") or ""
        org_en = row.get("scholar_org_name_en") or ""
        org_key = org_zh or org_en
        if org_key:
            ovid = make_org_vid(org_key)
            if ovid not in seen_orgs:
                seen_orgs.add(ovid)
                stmts.append(ngql_org(org_zh, org_en, row["scholar_id"], now))
            stmts.append(ngql_affiliated_with(row["scholar_id"], org_key, now))

    # Papers
    for row in papers:
        stmts.append(ngql_paper(row, now))
        stmts.append(ngql_paper_sourced_from(row["id"], now))

    # COAUTHOR_WITH
    for row in coauthors:
        stmts.append(ngql_coauthor_with(row, now))

    # AUTHORED_BY
    for row in rels:
        stmts.append(ngql_authored_by(row, now))

    logger.info(f"generated {len(stmts)} nGQL statements")

    # --- dry_run: 只打印，不执行 ---
    if dry_run:
        for stmt in stmts:
            print(stmt + ";")
        logger.info("dry_run mode: statements printed, nothing written")
        return

    # --- 执行写入 ---
    session, pool = get_nebula(NEBULA_HOST, NEBULA_PORT, NEBULA_USER, NEBULA_PASSWORD)
    try:
        session.execute(f"USE {NEBULA_SPACE}")
        ok = err = 0
        for stmt in stmts:
            r = session.execute(stmt)
            if r.is_succeeded():
                ok += 1
            else:
                err += 1
                logger.warning(f"FAILED: {r.error_msg()} | {stmt[:120]}")
        logger.info(f"write done: ok={ok} err={err}")
    finally:
        session.release()
        pool.close()


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="学者领域 ETL：gkx_element → TRSGraph dev")
    parser.add_argument("--dry-run", action="store_true",
                        help="只生成 nGQL 语句并打印，不实际写入图数据库")
    parser.add_argument("--mysql-host",     default=MYSQL_HOST)
    parser.add_argument("--mysql-port",     type=int, default=MYSQL_PORT)
    parser.add_argument("--mysql-user",     default=MYSQL_USER)
    parser.add_argument("--mysql-password", default=MYSQL_PASSWORD)
    parser.add_argument("--mysql-db",       default=MYSQL_DATABASE)
    parser.add_argument("--nebula-host",    default=NEBULA_HOST)
    parser.add_argument("--nebula-port",    type=int, default=NEBULA_PORT)
    parser.add_argument("--nebula-user",    default=NEBULA_USER)
    parser.add_argument("--nebula-password",default=NEBULA_PASSWORD)
    parser.add_argument("--nebula-space",   default=NEBULA_SPACE)
    parser.add_argument("--batch-id",       default=BATCH_ID)
    args = parser.parse_args()

    MYSQL_HOST     = args.mysql_host
    MYSQL_PORT     = args.mysql_port
    MYSQL_USER     = args.mysql_user
    MYSQL_PASSWORD = args.mysql_password
    MYSQL_DATABASE = args.mysql_db
    NEBULA_HOST    = args.nebula_host
    NEBULA_PORT    = args.nebula_port
    NEBULA_USER    = args.nebula_user
    NEBULA_PASSWORD= args.nebula_password
    NEBULA_SPACE   = args.nebula_space
    BATCH_ID       = args.batch_id

    run_etl(dry_run=args.dry_run)
