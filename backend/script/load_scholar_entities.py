"""学者领域实体抽取：将 ``gkx_element.dwd_scholar`` 系列表映射为 TRSGraph Person 顶点。

范围（学者领域实体）：
  - Person 顶点：主键为 ``dwd_scholar.scholar_id``；同时并入 ``dwd_scholar_talent_flag``
    的 ``academician`` 和 ``dwd_scholar_research_direction`` 的 ``fields`` 作为属性。

按领域划分：本脚本仅落 Person 顶点。机构 / 论文 / 项目 / 专利顶点由其他领域批次
负责；顶点间关系由 ``load_scholar_relations.py`` 与其他领域脚本独立生成。

图客户端使用 ``infra.graph_db.get_trs_graph_client``（读取 ``TRS_GRAPH_*``），不直接
依赖 nebula3 SDK。

用法::

    # 干跑：只统计并预览前若干条 Person 顶点
    MYSQL_DATABASE=gkx_element uv run python -m script.load_scholar_entities --dry-run

    # 实际写入 dev 空间
    TRS_GRAPH_SPACE=dev MYSQL_DATABASE=gkx_element \\
        uv run python -m script.load_scholar_entities
"""

from __future__ import annotations

import argparse
import logging
import os
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import select, text

from db_model.scholar import (
    DwdScholarResearchDirection,
    DwdScholarTalentFlag,
)
from infra.graph_db import get_trs_graph_client
from infra.mysql import MySQLClient

logger = logging.getLogger("script.load_scholar_entities")

BATCH_ID = f"BATCH_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_scholar_entities"


# ---------------------------------------------------------------------------
# VID
# ---------------------------------------------------------------------------
def person_vid(scholar_id: str) -> str:
    return f"person_{scholar_id.strip()}"


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------
def _fetch_talent_flags(session) -> dict[str, str]:
    """一次性加载全表：scholar_id -> academician（数据量小，1~2 万级）。"""
    rows = session.execute(
        select(DwdScholarTalentFlag.scholar_id, DwdScholarTalentFlag.academician)
    ).all()
    return {r.scholar_id: r.academician or "" for r in rows if r.scholar_id}


def _fetch_research_directions(session) -> dict[str, str]:
    """scholar_id -> fields。同 scholar_id 可能多行，用中文分号拼接。"""
    rows = session.execute(
        select(
            DwdScholarResearchDirection.scholar_id,
            DwdScholarResearchDirection.fields,
        )
    ).all()
    merged: dict[str, list[str]] = {}
    for r in rows:
        if not r.scholar_id or not r.fields:
            continue
        merged.setdefault(r.scholar_id, []).append(r.fields.strip())
    return {sid: "；".join(fs) for sid, fs in merged.items()}


def _iter_scholars(session, batch_size: int = 500) -> Iterable[dict]:
    """分页读取 ``dwd_scholar``。

    使用原生 SQL 是为了兼容 ``scholar_org_id`` 列在部分环境尚未部署的情况，
    与 ``load_scholar_relations.py`` 中的做法一致。
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
        SELECT scholar_id, name_en, name_zh, avatar,
               {org_id_col},
               scholar_org_name_zh, scholar_org_name_en,
               bio, bio_zh,
               work_experience_date,
               work_experience_institution_en, work_experience_department_en,
               work_experience_position_en,
               work_experience_institution_zh, work_experience_department_zh,
               work_experience_position_zh,
               education_background_date,
               education_background_institution_en, education_background_degree_en,
               education_background_institution_zh, education_background_degree_zh,
               paper_nums, citation_nums, h_index, status,
               DATE_FORMAT(update_time, '%Y-%m-%d %H:%i:%s') AS update_time
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
            yield dict(r._mapping)
        offset += len(rows)
        if len(rows) < batch_size:
            break


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------
def _build_person_props(
    row: dict,
    academician: str,
    fields: str,
    now: str,
) -> dict:
    org_name = row.get("scholar_org_name_zh") or row.get("scholar_org_name_en") or ""
    return {
        "name_en": row.get("name_en") or "",
        "name_zh": row.get("name_zh") or "",
        "email": "",
        "source": "scholar",
        "avatar": row.get("avatar") or "",
        "scholar_org": org_name,
        "bio_zh": row.get("bio_zh") or "",
        "biography": row.get("bio") or "",
        "paper_nums": int(row.get("paper_nums") or 0),
        "citation_nums": int(row.get("citation_nums") or 0),
        "h_index": int(row.get("h_index") or 0),
        "scholar_status": int(row.get("status") or 0),
        "is_academician": academician,
        "research_fields": fields,
        "work_experience_date": row.get("work_experience_date") or "",
        "work_experience_institution_en": row.get("work_experience_institution_en") or "",
        "work_experience_department_en": row.get("work_experience_department_en") or "",
        "work_experience_position_en": row.get("work_experience_position_en") or "",
        "work_experience_institution_zh": row.get("work_experience_institution_zh") or "",
        "work_experience_department_zh": row.get("work_experience_department_zh") or "",
        "work_experience_position_zh": row.get("work_experience_position_zh") or "",
        "education_background_date": row.get("education_background_date") or "",
        "education_background_institution_en": row.get("education_background_institution_en") or "",
        "education_background_degree_en": row.get("education_background_degree_en") or "",
        "education_background_institution_zh": row.get("education_background_institution_zh") or "",
        "education_background_degree_zh": row.get("education_background_degree_zh") or "",
        # Provenance
        "source_system": "gkx_element",
        "source_table": "dwd_scholar",
        "source_record_id": row["scholar_id"],
        "source_url": "",
        "ingest_batch": BATCH_ID,
        "ingest_time": now,
        "source_update_time": row.get("update_time") or "",
        "confidence": 1.0,
        "organization_base": "dwd_scholar",
        "organization_id": "scholar_id",
    }


def load_persons(session, graph, *, dry_run: bool, preview: int = 5) -> dict:
    """遍历 ``dwd_scholar`` 并写入 Person 顶点。"""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    talent_flags = _fetch_talent_flags(session)
    logger.info("preloaded %d talent_flag rows", len(talent_flags))
    directions = _fetch_research_directions(session)
    logger.info("preloaded %d research_direction rows", len(directions))

    ok = shown = 0
    for row in _iter_scholars(session):
        sid = row["scholar_id"]
        vid = person_vid(sid)
        props = _build_person_props(row, talent_flags.get(sid, ""), directions.get(sid, ""), now)
        if dry_run:
            if shown < preview:
                logger.info(
                    "[dry-run] %s  name=%s org=%s papers=%s h=%s",
                    vid,
                    props["name_zh"] or props["name_en"],
                    props["scholar_org"],
                    props["paper_nums"],
                    props["h_index"],
                )
                shown += 1
        else:
            # 显式传入 vid，避免 `_ensure_vid` 把 source_record_id 当成 VID。
            graph.merge_node(
                ["Person"],
                {"vid": vid, "source_record_id": sid},
                props,
            )
        ok += 1
    return {"written": ok}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run(*, database: str = "gkx_element", dry_run: bool = False) -> dict:
    mysql = MySQLClient(database=database)
    graph = get_trs_graph_client()
    logger.info(
        "start batch=%s database=%s dry_run=%s graph_space=%s",
        BATCH_ID,
        database,
        dry_run,
        os.environ.get("TRS_GRAPH_SPACE", "dev"),
    )

    session = mysql.session()
    try:
        stats = load_persons(session, graph, dry_run=dry_run)
        logger.info("Person: %s", stats)
    finally:
        session.close()

    return {"batch": BATCH_ID, "person": stats}


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="only preview the first few nodes; do not write anything.",
    )
    ap.add_argument(
        "--database",
        default=os.environ.get("MYSQL_DATABASE", "gkx_element"),
        help="MySQL database name (default: gkx_element).",
    )
    return ap.parse_args()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    args = _parse_args()
    result = run(database=args.database, dry_run=args.dry_run)
    logger.info("done: %s", result)
