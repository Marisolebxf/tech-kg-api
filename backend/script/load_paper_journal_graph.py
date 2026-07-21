"""论文/期刊/报告 ETL：从 gkx_element 读源数据 → INSERT 到 TRSGraph dev 空间。

用法：
    cd backend && PYTHONPATH=. .venv/bin/python script/load_paper_journal_graph.py

VID 格式（按 ontology.md）：
    Paper:   paper_{id}
    Person:  person_{author_id}
    Journal: journal_{publication_id}
    Report:  report_{report_id}
"""

from __future__ import annotations

import logging
import os
import time
from urllib.parse import quote_plus

from infra.graph_db import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings
from infra.mysql import MySQLClient
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

SPACE = "dev"
BATCH = 1  # trs-graph 不支持多值 INSERT，每次 1 条
PAPER_LIMIT = ""  # 空=全量加载
MAX_WORKERS = 10  # 并发线程数


# ---------- 连接 ----------

def get_graph_client() -> TRSGraphClient:
    settings = TRSGraphSettings(
        base_url=os.getenv("TRS_GRAPH_BASE_URL", "http://localhost:8090"),
        space=SPACE,
        api_key=os.getenv("TRS_GRAPH_API_KEY"),
        timeout=int(os.getenv("TRS_GRAPH_TIMEOUT", "60")),
    )
    return TRSGraphClient(settings)


def get_mysql_client() -> MySQLClient:
    url = (
        f"mysql+pymysql://{quote_plus(os.getenv('MYSQL_USERNAME', 'root'))}:"
        f"{quote_plus(os.getenv('MYSQL_PASSWORD', '123456789'))}"
        f"@{os.getenv('MYSQL_HOST', '127.0.0.1')}:{os.getenv('MYSQL_PORT', '3306')}"
        f"/gkx_element?charset=utf8mb4"
    )
    return MySQLClient(url=url)


# ---------- 工具 ----------

def esc(v) -> str:
    """转义 nGQL 字符串值。"""
    if v is None:
        return "NULL"
    s = str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")
    return f'"{s}"'


def batch_insert_vertex(client: TRSGraphClient, tag: str, fields: list[str], rows: list[tuple], label: str) -> int:
    """INSERT VERTEX（单条），返回成功条数。"""
    ok = 0
    field_list = ",".join(fields)
    for i, (vid, vals) in enumerate(rows):
        val_str = ",".join(esc(v) for v in vals)
        ngql = f'USE {SPACE}; INSERT VERTEX {tag}({field_list}) VALUES "{vid}":({val_str});'
        try:
            client.execute_write(ngql)
            ok += 1
        except Exception as exc:
            if ok == 0:
                logger.warning(f"  {label} 首条失败: {exc} | nGQL: {ngql[:120]}")
        if (i + 1) % 100 == 0:
            logger.info(f"  {label} 进度: {i+1}/{len(rows)} (成功 {ok})")
    return ok


def batch_insert_edge(client: TRSGraphClient, edge: str, fields: list[str], rows: list[tuple], label: str) -> int:
    """INSERT EDGE（单条），rows = [(src_vid, dst_vid, val1, val2, ...)]。返回成功条数。"""
    ok = 0
    field_list = ",".join(fields) if fields else ""
    field_part = f"({field_list})" if fields else "()"
    for i, row in enumerate(rows):
        src, dst = row[0], row[1]
        vals = row[2:]
        val_str = ",".join(esc(v) for v in vals) if vals else ""
        ngql = f'USE {SPACE}; INSERT EDGE {edge}{field_part} VALUES "{src}"->"{dst}":({val_str});'
        try:
            client.execute_write(ngql)
            ok += 1
        except Exception as exc:
            if ok == 0:
                logger.warning(f"  {label} 首条失败: {exc} | nGQL: {ngql[:120]}")
        if (i + 1) % 100 == 0:
            logger.info(f"  {label} 进度: {i+1}/{len(rows)} (成功 {ok})")
    return ok


# ---------- ETL 各步骤 ----------

def load_zh_papers(client: TRSGraphClient, session) -> int:
    rows = session.execute(text(
        "SELECT id, doi, en_name, zh_name, cover_year_start, cover_date_start, "
        "language_classify, paper_type, publication_type, volume, issue, first_page, last_page, "
        "open_access, paper_url, data_source, created_time, updated_time FROM dwd_zh_paper"
    )).all()
    vertices = []
    for r in rows:
        vid = f"paper_{r[0]}"
        vals = (r[2], r[3], r[1], r[4], str(r[5]) if r[5] else None, r[6], r[7], r[8], r[9], r[10], r[11], r[12], r[13], r[14], r[15] or "zh_paper", str(r[16]) if r[16] else None, str(r[17]) if r[17] else None)
        vertices.append((vid, vals))
    ok = batch_insert_vertex(client, "Paper",
        ["title_en","title_zh","doi","publication_year","publication_date","language",
         "document_type","publication_type","volume","issue","start_page","end_page","is_oa",
         "source_url","source","created_time","updated_time"], vertices, "zh_paper")
    logger.info(f"  中文论文 Paper: {ok}/{len(vertices)}")
    return ok


def load_en_papers(client: TRSGraphClient, session) -> int:
    rows = session.execute(text(
        "SELECT id, doi, en_name, zh_name, cover_year_start, cover_date_start, "
        "language, paper_type, publication_type, volume, issue, first_page, last_page, "
        "open_access, paper_url, data_source, created_time, updated_time FROM dwd_en_paper"
    )).all()
    vertices = []
    for r in rows:
        vid = f"paper_{r[0]}"
        vals = (r[2], r[3], r[1], r[4], str(r[5]) if r[5] else None, r[6], r[7], r[8], r[9], r[10], r[11], r[12], r[13], r[14], r[15] or "en_paper", str(r[16]) if r[16] else None, str(r[17]) if r[17] else None)
        vertices.append((vid, vals))
    ok = batch_insert_vertex(client, "Paper",
        ["title_en","title_zh","doi","publication_year","publication_date","language",
         "document_type","publication_type","volume","issue","start_page","end_page","is_oa",
         "source_url","source","created_time","updated_time"], vertices, "en_paper")
    logger.info(f"  英文论文 Paper: {ok}/{len(vertices)}")
    return ok


def load_authors(client: TRSGraphClient, session) -> int:
    """加载中文+英文论文作者 → Person 节点 + AUTHORED_BY 边。"""
    person_seen = set()
    persons = []
    edges = []
    for tbl, src_label in [("dwd_zh_author", "zh_paper"), ("dwd_en_author", "en_paper")]:
        rows = session.execute(text(
            f"SELECT paper_id, author_sequence, author_id, en_name, zh_name, email, correspond, "
            f"affiliation FROM {tbl}"
        )).all()
        for r in rows:
            paper_vid = f"paper_{r[0]}"
            author_id = r[2]
            if not author_id:
                continue
            person_vid = f"person_{author_id}"
            if person_vid not in person_seen:
                person_seen.add(person_vid)
                email_val = r[5]
                if email_val and email_val != "[]":
                    # 取 JSON 数组第一个
                    import json
                    try:
                        emails = json.loads(email_val)
                        email_val = emails[0] if emails else None
                    except Exception:
                        pass
                persons.append((person_vid, (r[3], r[4], email_val, src_label)))
            edges.append((paper_vid, person_vid, r[1] or 0, r[6] or 0))
    ok_p = batch_insert_vertex(client, "Person", ["name_en","name_zh","email","source"], persons, "author")
    ok_e = batch_insert_edge(client, "AUTHORED_BY", ["author_order","is_corresponding"], edges, "authored_by")
    logger.info(f"  作者 Person: {ok_p}/{len(persons)}, AUTHORED_BY: {ok_e}/{len(edges)}")
    return ok_p


def load_journals(client: TRSGraphClient, session) -> int:
    """加载中文+英文期刊 → Journal 节点 + PUBLISHED_IN 边。"""
    journal_seen = set()
    journals = []
    edges = []

    # 中文期刊
    rows = session.execute(text(
        "SELECT paper_id, publication_id, zh_name, en_name, name_abbr, issn, eissn, country, "
        "founding_time, impact_factor, is_sci, cite_nums, annual_publication, publication_cycle "
        "FROM dwd_zh_journal WHERE publication_id IS NOT NULL"
    )).all()
    for r in rows:
        pub_id = r[1]
        jvid = f"journal_{pub_id}"
        if jvid not in journal_seen:
            journal_seen.add(jvid)
            journals.append((jvid, (r[2], r[3], r[4], r[5], r[6], r[7], str(r[8]) if r[8] else None, r[9], r[10], None, r[11], r[12], r[13], "zh_journal")))
        paper_vid = f"paper_{r[0]}"
        edges.append((paper_vid, jvid, None, None, None, None, None))

    # 英文期刊
    rows = session.execute(text(
        "SELECT publication_id, en_name, name_abbr, issn_print, issn_online, country, "
        "establish_time, impact_factor, jcr_zone, is_sci, annual_publication, publish_period "
        "FROM dwd_en_journal WHERE publication_id IS NOT NULL"
    )).all()
    for r in rows:
        pub_id = r[0]
        jvid = f"journal_{pub_id}"
        if jvid not in journal_seen:
            journal_seen.add(jvid)
            journals.append((jvid, (None, r[1], r[2], r[3], r[4], r[5], str(r[6]) if r[6] else None, r[7], r[9] or 0, r[8], None, r[10], r[11], "en_journal")))
        # 英文期刊没有 paper_id 关联，PUBLISHED_IN 边从 dwd_en_paper 的 publication_id 建
    # 英文论文 → 期刊边
    en_rows = session.execute(text("SELECT id, publication_id, volume, issue, first_page, last_page, cover_year_start FROM dwd_en_paper WHERE publication_id IS NOT NULL")).all()
    for r in en_rows:
        paper_vid = f"paper_{r[0]}"
        jvid = f"journal_{r[1]}"
        edges.append((paper_vid, jvid, r[2], r[3], r[4], r[5], r[6]))

    ok_j = batch_insert_vertex(client, "Journal",
        ["name_zh","name_en","name_abbr","issn","eissn","country","founding_time",
         "impact_factor","is_sci","jcr_zone","cite_nums","annual_publication","publication_cycle","source"],
        journals, "journal")
    ok_e = batch_insert_edge(client, "PUBLISHED_IN",
        ["volume","issue","start_page","end_page","publication_year"], edges, "published_in")
    logger.info(f"  期刊 Journal: {ok_j}/{len(journals)}, PUBLISHED_IN: {ok_e}/{len(edges)}")
    return ok_j


def load_references(client: TRSGraphClient, session) -> int:
    """参考文献 → CITES 边（Paper → Paper）。"""
    edges = []
    for tbl in ["dwd_zh_paper_reference", "dwd_en_paper_reference"]:
        rows = session.execute(text(f"SELECT id, doi FROM {tbl} WHERE doi IS NOT NULL AND doi != ''")).all()
        for r in rows:
            src_vid = f"paper_{r[0]}"
            # 参考文献用 doi 作为目标 Paper 的标识（如果存在同名 Paper）
            dst_vid = f"paper_ref_{r[1]}"  # 参考文献不一定在库内，用 ref_doi 标识
            edges.append((src_vid, dst_vid, r[1]))
    ok = batch_insert_edge(client, "CITES", ["reference_identifier"], edges, "cites")
    logger.info(f"  参考文献 CITES: {ok}/{len(edges)}")
    return ok


def load_citations(client: TRSGraphClient, session) -> int:
    """引用 → CITED_BY 边（Paper → Paper）。"""
    edges = []
    for tbl in ["dwd_zh_paper_citation", "dwd_en_paper_citation"]:
        rows = session.execute(text(f"SELECT id, doi FROM {tbl} WHERE doi IS NOT NULL AND doi != ''")).all()
        for r in rows:
            src_vid = f"paper_{r[0]}"
            dst_vid = f"paper_cit_{r[1]}"
            edges.append((src_vid, dst_vid, r[1]))
    ok = batch_insert_edge(client, "CITED_BY", ["citation_identifier"], edges, "cited_by")
    logger.info(f"  引用 CITED_BY: {ok}/{len(edges)}")
    return ok


def load_reports(client: TRSGraphClient, session) -> int:
    """加载中文+英文报告 → Report 节点。"""
    reports = []
    # 中文报告
    rows = session.execute(text(
        "SELECT report_id, title_cn, report_category, report_type, abstract_cn, keywords_cn, "
        "page_count, preparation_time, source_url FROM dwd_zh_report"
    )).all()
    for r in rows:
        vid = f"report_{r[0]}"
        reports.append((vid, (r[1], None, r[2], r[3], r[4], r[5], r[6], str(r[7]) if r[7] else None, r[8], "zh_report")))
    # 英文报告
    rows = session.execute(text(
        "SELECT report_id, title_en, document_type, page_count, publication_date, source_url, abstract_en, keywords_en FROM dwd_en_report"
    )).all()
    for r in rows:
        vid = f"report_{r[0]}"
        reports.append((vid, (None, r[1], None, r[2], r[6], r[7], r[3], str(r[4]) if r[4] else None, r[5], "en_report")))
    ok = batch_insert_vertex(client, "Report",
        ["title_cn","title_en","report_category","report_type","abstract","keywords",
         "page_count","publication_date","source_url","source"], reports, "report")
    logger.info(f"  报告 Report: {ok}/{len(reports)}")
    return ok


# ---------- 主流程 ----------

def main() -> None:
    logger.info("=== 论文/期刊/报告 ETL: gkx_element → TRSGraph(dev) ===\n")
    mysql = get_mysql_client()
    graph = get_graph_client()
    graph.connect()
    session = mysql.session()
    try:
        t0 = time.time()
        logger.info("1. 加载论文 Paper 节点（全量）")
        load_zh_papers(graph, session)
        load_en_papers(graph, session)
        # 以下步骤首次已全量加载，跳过避免重复（如需重跑取消注释）
        # logger.info("\n2. 加载作者 Person 节点 + AUTHORED_BY 边")
        # load_authors(graph, session)
        # logger.info("\n3. 加载期刊 Journal 节点 + PUBLISHED_IN 边")
        # load_journals(graph, session)
        # logger.info("\n4. 加载参考文献 CITES 边")
        # load_references(graph, session)
        # logger.info("\n5. 加载引用 CITED_BY 边")
        # load_citations(graph, session)
        # logger.info("\n6. 加载报告 Report 节点")
        # load_reports(graph, session)
        logger.info(f"\n=== ETL 完成，耗时 {time.time()-t0:.1f}s ===")
    finally:
        session.close()
        mysql.dispose()


if __name__ == "__main__":
    main()
