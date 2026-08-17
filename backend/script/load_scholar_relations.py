"""学者领域关系抽取：写入 TRSGraph dev 图空间。

范围（学者领域出向边）：
  - AFFILIATED_WITH  : Person → Organization   （来源：``dwd_scholar``）
  - COAUTHOR_WITH    : Person → Person         （来源：``dwd_scholar_coauthor``）

跨域兜底（可选，默认关闭；起点属于论文领域）：
  - AUTHORED_BY      : Paper → Person          （来源：``dwd_scholar_paper_relation``）
    仅当图中已存在两端顶点时才写入，缺一即跳过。

设计要点：
  * 图客户端使用 ``infra.graph_db.get_trs_graph_client``（读取 ``TRS_GRAPH_*`` 环境变量），
    不直接依赖 nebula3 SDK。
  * MySQL 使用 ``infra.mysql.MySQLClient(database='gkx_element')``，仅覆盖数据库名，其余
    连接参数走 ``MYSQL_HOST/PORT/USERNAME/PASSWORD`` 环境变量。
  * 只做关系抽取，不新建 Person / Organization / Paper 顶点；顶点由对应领域批次写入。
  * 目标顶点使用命名约定：
        Person       -> ``person_{scholar_id}``
        Organization -> ``org_{scholar_org_id}`` 优先，否则 ``org_{md5(name)[:16]}``
        Paper        -> ``paper_{paper_id}``
  * ``merge_edge`` 幂等写入，重复执行不会产生重复边。

用法::

    # 干跑：只统计 & 打印前若干条待写入的边，不实际写入
    MYSQL_DATABASE=gkx_element uv run python -m script.load_scholar_relations --dry-run

    # 实际写入 dev 图空间（默认边集：AFFILIATED_WITH + COAUTHOR_WITH）
    TRS_GRAPH_SPACE=dev MYSQL_DATABASE=gkx_element \
        uv run python -m script.load_scholar_relations

    # 追加跨域兜底：只写两端都已存在的 AUTHORED_BY 边
    TRS_GRAPH_SPACE=dev MYSQL_DATABASE=gkx_element \
        uv run python -m script.load_scholar_relations --include-authored-by-fallback
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import select, text

from db_model.scholar import DwdScholarCoauthor, DwdScholarPaperRelation
from infra.graph_db import get_trs_graph_client
from infra.mysql import MySQLClient
from script.scholar_provenance import (
    CONFIDENCE_CROSS_DOMAIN_ID,
    CONFIDENCE_PLACEHOLDER_ORG,
    CONFIDENCE_SOURCE_PRIMARY_KEY,
    confidence_props,
    organization_provenance,
)

logger = logging.getLogger("script.load_scholar_relations")

BATCH_ID = f"BATCH_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_scholar_rel"

# 学者的机构信息来自学者表本身；对齐到正式 Organization 之前机构溯源表就是 dwd_scholar。
ORGANIZATION_BASE_TABLE = "dwd_scholar"


# ---------------------------------------------------------------------------
# VID conventions
# ---------------------------------------------------------------------------
def person_vid(scholar_id: str) -> str:
    return f"person_{scholar_id.strip()}"


def paper_vid(paper_id) -> str:
    return f"paper_{paper_id}"


def org_vid(scholar_org_id: str | None, org_name: str | None) -> str | None:
    """优先使用 ``scholar_org_id``，否则用机构名 md5 摘要作为回退 VID。"""
    if scholar_org_id and scholar_org_id.strip():
        return f"org_{scholar_org_id.strip()}"
    if org_name and org_name.strip():
        key = org_name.strip().lower()
        return f"org_{hashlib.md5(key.encode('utf-8')).hexdigest()[:16]}"
    return None


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------
def _iter_scholar_affiliations(session, batch_size: int = 500) -> Iterable[dict]:
    """从 ``dwd_scholar`` 分页读取学者→机构映射所需字段。

    直接用 SQL 而非 ORM，因为 ``scholar_org_id`` 是新增字段，在部分环境的
    ``gkx_element`` 中可能尚未部署；使用 ``information_schema`` 探测后按需
    选择 SELECT 列表。
    """
    has_org_id = (
        session.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema = DATABASE() "
                "AND table_name = 'dwd_scholar' "
                "AND column_name = 'scholar_org_id'"
            )
        ).scalar_one()
        > 0
    )

    org_id_col = "scholar_org_id" if has_org_id else "NULL AS scholar_org_id"
    sql = text(
        f"""
        SELECT scholar_id,
               {org_id_col},
               scholar_org_name_zh,
               scholar_org_name_en
        FROM dwd_scholar
        WHERE status = 1
        ORDER BY scholar_id
        LIMIT :limit OFFSET :offset
        """
    )

    offset = 0
    while True:
        rows = session.execute(sql, {"limit": batch_size, "offset": offset}).all()
        if not rows:
            break
        for r in rows:
            yield {
                "scholar_id": r.scholar_id,
                "scholar_org_id": r.scholar_org_id,
                "org_zh": r.scholar_org_name_zh,
                "org_en": r.scholar_org_name_en,
            }
        offset += len(rows)
        if len(rows) < batch_size:
            break


def _iter_coauthor_rows(session, batch_size: int = 1000) -> Iterable[dict]:
    """从 ``dwd_scholar_coauthor`` 分页读取合作关系。"""
    offset = 0
    while True:
        rows = session.execute(
            select(
                DwdScholarCoauthor.scholar_id,
                DwdScholarCoauthor.co_scholar_id,
                DwdScholarCoauthor.co_paper_count,
            )
            .where(DwdScholarCoauthor.status == 1)
            .order_by(DwdScholarCoauthor.scholar_id, DwdScholarCoauthor.co_scholar_id)
            .offset(offset)
            .limit(batch_size)
        ).all()
        if not rows:
            break
        for r in rows:
            yield {
                "scholar_id": r.scholar_id,
                "co_scholar_id": r.co_scholar_id,
                "co_paper_count": int(r.co_paper_count or 0),
            }
        offset += len(rows)
        if len(rows) < batch_size:
            break


def _iter_paper_relations(session, batch_size: int = 2000) -> Iterable[dict]:
    """从 ``dwd_scholar_paper_relation`` 分页读取学者-论文关联。"""
    offset = 0
    while True:
        rows = session.execute(
            select(
                DwdScholarPaperRelation.paper_id,
                DwdScholarPaperRelation.scholar_id,
                DwdScholarPaperRelation.citations,
            )
            .where(DwdScholarPaperRelation.status == 1)
            .order_by(DwdScholarPaperRelation.paper_id, DwdScholarPaperRelation.scholar_id)
            .offset(offset)
            .limit(batch_size)
        ).all()
        if not rows:
            break
        for r in rows:
            yield {
                "paper_id": r.paper_id,
                "scholar_id": r.scholar_id,
                "citations": int(r.citations or 0),
            }
        offset += len(rows)
        if len(rows) < batch_size:
            break


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------
def load_affiliations(session, graph, *, dry_run: bool, preview: int = 5) -> dict:
    """写入 AFFILIATED_WITH 边。

    置信度按机构标识来源分档：源表带 ``scholar_org_id`` 时为
    :data:`~script.scholar_provenance.CONFIDENCE_SOURCE_PRIMARY_KEY`；只能按机构名
    md5 生成桩机构时降为 :data:`~script.scholar_provenance.CONFIDENCE_PLACEHOLDER_ORG`。

    Returns:
        统计字典，含写入条数、无机构跳过条数、桩机构条数。
    """
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    ok = skipped = shown = placeholder = 0

    for rec in _iter_scholar_affiliations(session):
        src = person_vid(rec["scholar_id"])
        org_name = rec["org_zh"] or rec["org_en"] or ""
        dst = org_vid(rec["scholar_org_id"], org_name)
        if not dst:
            skipped += 1
            continue

        has_org_id = bool(rec["scholar_org_id"] and rec["scholar_org_id"].strip())
        if has_org_id:
            conf = confidence_props(
                CONFIDENCE_SOURCE_PRIMARY_KEY,
                "source_org_id",
                "dwd_scholar.scholar_org_id 直接指向机构，无需名称推断",
            )
        else:
            conf = confidence_props(
                CONFIDENCE_PLACEHOLDER_ORG,
                "org_name_md5_placeholder",
                "源表无 scholar_org_id，机构顶点按机构名 md5 生成桩 VID，待正式 Organization 落地后对齐",
            )
            placeholder += 1

        props = {
            "affiliation_name": org_name,
            "source": "scholar",
            "source_table": "dwd_scholar",
            "source_record_id": rec["scholar_id"],
            "ingest_batch": BATCH_ID,
            "ingest_time": now,
            **organization_provenance(
                ORGANIZATION_BASE_TABLE if has_org_id else None,
                rec["scholar_org_id"] if has_org_id else None,
            ),
            **conf,
        }
        if dry_run:
            if shown < preview:
                logger.info(
                    "[dry-run] %s -[AFFILIATED_WITH]-> %s  %s  confidence=%s",
                    src,
                    dst,
                    org_name,
                    props["confidence"],
                )
                shown += 1
        else:
            graph.merge_edge(
                src,
                dst,
                "AFFILIATED_WITH",
                {"source_record_id": rec["scholar_id"]},
                props,
            )
        ok += 1

    return {"written": ok, "skipped_no_org": skipped, "placeholder_org": placeholder}


def load_coauthors(session, graph, *, dry_run: bool, preview: int = 5) -> dict:
    """写入 COAUTHOR_WITH 边。返回统计信息。"""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    ok = shown = 0

    for rec in _iter_coauthor_rows(session):
        src = person_vid(rec["scholar_id"])
        dst = person_vid(rec["co_scholar_id"])
        rid = f"{rec['scholar_id']}_{rec['co_scholar_id']}"
        props = {
            "co_paper_count": rec["co_paper_count"],
            "source_table": "dwd_scholar_coauthor",
            "source_record_id": rid,
            "ingest_batch": BATCH_ID,
            "ingest_time": now,
            **confidence_props(
                CONFIDENCE_SOURCE_PRIMARY_KEY,
                "source_primary_key",
                "dwd_scholar_coauthor 双方 scholar_id 均为源表主键，无需推断",
            ),
        }
        if dry_run:
            if shown < preview:
                logger.info(
                    "[dry-run] %s -[COAUTHOR_WITH]-> %s  co_paper_count=%s",
                    src,
                    dst,
                    rec["co_paper_count"],
                )
                shown += 1
        else:
            graph.merge_edge(src, dst, "COAUTHOR_WITH", {"source_record_id": rid}, props)
        ok += 1

    return {"written": ok}


def load_authored_by_fallback(session, graph, *, dry_run: bool, preview: int = 5) -> dict:
    """跨域兜底：写入 AUTHORED_BY 边（Paper → Person）。

    起点属于论文领域，本函数只在 **两端顶点在图中均已存在** 的前提下写入。
    对每个 Paper / Person VID 通过 ``graph.get_node`` 做一次存在性探测并缓存，
    避免重复查询同一顶点。
    """
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    written = shown = 0
    skipped_missing_paper = skipped_missing_person = 0

    paper_exists: dict[str, bool] = {}
    person_exists: dict[str, bool] = {}

    def _exists(vid: str, cache: dict[str, bool]) -> bool:
        if vid in cache:
            return cache[vid]
        exists = graph.get_node(vid) is not None
        cache[vid] = exists
        return exists

    for rec in _iter_paper_relations(session):
        src = paper_vid(rec["paper_id"])
        dst = person_vid(rec["scholar_id"])
        rid = f"{rec['paper_id']}_{rec['scholar_id']}"

        if not _exists(src, paper_exists):
            skipped_missing_paper += 1
            continue
        if not _exists(dst, person_exists):
            skipped_missing_person += 1
            continue

        props = {
            "citations": rec["citations"],
            "source_table": "dwd_scholar_paper_relation",
            "source_record_id": rid,
            "ingest_batch": BATCH_ID,
            "ingest_time": now,
            **confidence_props(
                CONFIDENCE_CROSS_DOMAIN_ID,
                "cross_domain_id_match",
                "paper_id 与 scholar_id 分别命中已存在的 Paper、Person 顶点",
            ),
        }
        if dry_run:
            if shown < preview:
                logger.info(
                    "[dry-run] %s -[AUTHORED_BY]-> %s  citations=%s",
                    src,
                    dst,
                    rec["citations"],
                )
                shown += 1
        else:
            graph.merge_edge(src, dst, "AUTHORED_BY", {"source_record_id": rid}, props)
        written += 1

    return {
        "written": written,
        "skipped_missing_paper": skipped_missing_paper,
        "skipped_missing_person": skipped_missing_person,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run(
    *,
    database: str = "gkx_element",
    dry_run: bool = False,
    include_authored_by_fallback: bool = False,
) -> dict:
    mysql = MySQLClient(database=database)
    graph = get_trs_graph_client()
    logger.info(
        "start batch=%s database=%s dry_run=%s graph_space=%s authored_by_fallback=%s",
        BATCH_ID,
        database,
        dry_run,
        os.environ.get("TRS_GRAPH_SPACE", "dev"),
        include_authored_by_fallback,
    )

    session = mysql.session()
    try:
        aff_stats = load_affiliations(session, graph, dry_run=dry_run)
        logger.info("AFFILIATED_WITH: %s", aff_stats)
        co_stats = load_coauthors(session, graph, dry_run=dry_run)
        logger.info("COAUTHOR_WITH: %s", co_stats)

        result: dict = {
            "batch": BATCH_ID,
            "affiliated_with": aff_stats,
            "coauthor_with": co_stats,
        }

        if include_authored_by_fallback:
            ab_stats = load_authored_by_fallback(session, graph, dry_run=dry_run)
            logger.info("AUTHORED_BY (fallback): %s", ab_stats)
            result["authored_by_fallback"] = ab_stats

        return result
    finally:
        session.close()


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="only preview the first few edges; do not write anything.",
    )
    ap.add_argument(
        "--database",
        default=os.environ.get("MYSQL_DATABASE", "gkx_element"),
        help="MySQL database name (default: gkx_element).",
    )
    ap.add_argument(
        "--include-authored-by-fallback",
        action="store_true",
        help=(
            "Also emit AUTHORED_BY edges from dwd_scholar_paper_relation, "
            "but only when both Paper and Person vertices already exist "
            "in the graph. Off by default to keep scope on scholar-domain "
            "outgoing edges."
        ),
    )
    return ap.parse_args()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    args = _parse_args()
    result = run(
        database=args.database,
        dry_run=args.dry_run,
        include_authored_by_fallback=args.include_authored_by_fallback,
    )
    logger.info("done: %s", result)
