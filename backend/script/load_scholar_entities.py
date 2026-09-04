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
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text

from db_model.scholar import (
    DwdScholarResearchDirection,
    DwdScholarTalentFlag,
)
from infra.graph_db import get_trs_graph_client
from infra.mysql import MySQLClient
from script.etl_watermark import Watermark
from script.scholar_provenance import (
    CONFIDENCE_SOURCE_PRIMARY_KEY,
    confidence_props,
    organization_provenance,
)

logger = logging.getLogger("script.load_scholar_entities")

BATCH_ID = f"BATCH_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_scholar_entities"

# 学者的机构信息（scholar_org_id / scholar_org_name_*）来自学者表本身，
# 对齐到正式 Organization 之前，机构溯源表就是 dwd_scholar。
ORGANIZATION_BASE_TABLE = "dwd_scholar"


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


def _scholar_sql(
    org_id_col: str, since: str | None, scholar_id: str | None, limit: int | None
) -> str:
    """构造 dwd_scholar 查询 SQL。

    - ``since``(增量水位)→ ``AND update_time > :since``
    - ``scholar_id``(定向)→ ``AND scholar_id = :sid``
    - ``limit``(总上限/采样)→ ``LIMIT :cap`` 单次查询;否则分页 ``LIMIT :limit OFFSET :offset``
    """
    where = "WHERE status = 1"
    if since:
        where += " AND update_time > :since"
    if scholar_id:
        where += " AND scholar_id = :sid"
    tail = (
        "ORDER BY scholar_id LIMIT :cap"
        if limit is not None
        else "ORDER BY scholar_id LIMIT :limit OFFSET :offset"
    )
    return f"""
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
        {where}
        {tail}
        """


def _iter_scholars(
    session,
    batch_size: int = 500,
    *,
    since: str | None = None,
    scholar_id: str | None = None,
    limit: int | None = None,
) -> Iterable[dict]:
    """分页读取 ``dwd_scholar``(支持增量水位 ``since``、定向 ``scholar_id``、采样 ``limit``)。

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
    sql = text(_scholar_sql(org_id_col, since, scholar_id, limit))

    def _params(extra: dict | None = None) -> dict:
        p: dict = {}
        if since:
            p["since"] = since
        if scholar_id:
            p["sid"] = scholar_id
        if extra:
            p.update(extra)
        return p

    if limit is not None:
        for r in session.execute(sql, _params({"cap": limit})).all():
            yield dict(r._mapping)
        return

    offset = 0
    while True:
        rows = session.execute(sql, _params({"limit": batch_size, "offset": offset})).all()
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
        # 机构溯源：便于从学者顶点反查其机构来自哪张表的哪条记录
        **organization_provenance(
            ORGANIZATION_BASE_TABLE if row.get("scholar_org_id") else None,
            row.get("scholar_org_id"),
        ),
        # 置信度：主键直取，无歧义
        **confidence_props(
            CONFIDENCE_SOURCE_PRIMARY_KEY,
            "source_primary_key",
            "dwd_scholar.scholar_id 主键直接抽取，未经推断",
        ),
    }


# ---------------------------------------------------------------------------
# nGQL INSERT 渲染(替代 merge_node——后者在 trs-graph 上不可靠)
# ---------------------------------------------------------------------------
def _esc(v: Any, numeric: bool = False) -> str:
    if v is None or (isinstance(v, str) and v == ""):
        return "NULL"
    if numeric:
        try:
            f = float(v)
            return str(int(f)) if f.is_integer() else repr(f)
        except (TypeError, ValueError):
            return "0"
    s = str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")
    return f'"{s}"'


def describe_tag_field_types(graph, tag: str) -> dict[str, str]:
    """DESCRIBE TAG → {field: type};失败/空返回 {}(调用方据此跳过或写空顶点)。"""
    try:
        result = graph.execute_read(f"DESCRIBE TAG {tag};")
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, str] = {}
    for rec in result.records if result else []:
        field = None
        typ = "string"
        for k in ("Field", "field", "Property", "property"):
            v = rec.get(k)
            if v:
                field = str(v)
                break
        for k in ("Type", "type"):
            v = rec.get(k)
            if v:
                typ = str(v)
                break
        if field:
            out[field] = typ
    return out


def render_person_insert(vid: str, props: dict, field_types: dict[str, str]) -> str:
    """渲染 nGQL ``INSERT VERTEX Person(...)``。

    自适应:只写 tag 实有且 props 也有的字段(按 tag 字段顺序);数字类型(int/double/float)
    不加引号,其余转义加引号。field_types 来自 :func:`describe_tag_field_types`。
    无匹配字段时写空属性顶点(保证 vid 存在,rank@0 幂等)。
    """
    fields = [f for f in field_types if f in props]
    if not fields:
        return f'INSERT VERTEX Person() VALUES "{vid}":();'
    vals = []
    for f in fields:
        numeric = any(t in (field_types.get(f) or "") for t in ("int", "double", "float"))
        vals.append(_esc(props.get(f), numeric=numeric))
    fl = ",".join(fields)
    return f"INSERT VERTEX Person({fl}) VALUES {_esc(vid)}:({','.join(vals)});"


def load_persons(
    session,
    graph,
    *,
    dry_run: bool,
    preview: int = 5,
    since: str | None = None,
    scholar_id: str | None = None,
    limit: int | None = None,
) -> dict:
    """遍历 ``dwd_scholar`` 并写入 Person 顶点。

    ``since``/``scholar_id``/``limit`` 透传给 :func:`_iter_scholars`(增量/定向/采样)。
    返回 ``written`` 与本批 ``max_update_time``(供增量前进水位)。
    """
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    talent_flags = _fetch_talent_flags(session)
    logger.info("preloaded %d talent_flag rows", len(talent_flags))
    directions = _fetch_research_directions(session)
    logger.info("preloaded %d research_direction rows", len(directions))

    # 自适应 Person tag 字段(DESCRIBE 一次);nGQL INSERT 只写 tag 实有字段,数字不加引号。
    person_field_types = describe_tag_field_types(graph, "Person") if not dry_run else {}
    logger.info("Person tag fields: %d (%s)", len(person_field_types), list(person_field_types)[:6])

    ok = shown = 0
    max_ts = ""
    for row in _iter_scholars(session, since=since, scholar_id=scholar_id, limit=limit):
        sid = row["scholar_id"]
        vid = person_vid(sid)
        props = _build_person_props(row, talent_flags.get(sid, ""), directions.get(sid, ""), now)
        ts = row.get("update_time") or ""
        if ts and ts > max_ts:
            max_ts = ts
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
            # nGQL INSERT(替代 merge_node——后者在 trs-graph 上不可靠,见 CLAUDE.md)
            graph.execute_write(render_person_insert(vid, props, person_field_types))
        ok += 1
    return {"written": ok, "max_update_time": max_ts or None}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run(
    *,
    database: str = "gkx_element",
    dry_run: bool = False,
    mode: str = "full",
    scholar_id: str | None = None,
    limit: int | None = None,
) -> dict:
    mysql = MySQLClient(database=database)
    graph = get_trs_graph_client()
    since: str | None = None
    if mode == "incremental":
        wm = Watermark.for_domain("scholar")
        since = wm.read()
        logger.info("incremental: scholar watermark=%s", since)
    logger.info(
        "start batch=%s database=%s mode=%s scholar_id=%s limit=%s dry_run=%s graph_space=%s",
        BATCH_ID,
        database,
        mode,
        scholar_id,
        limit,
        dry_run,
        os.environ.get("TRS_GRAPH_SPACE", "dev"),
    )

    session = mysql.session()
    stats: dict = {}
    try:
        stats = load_persons(
            session, graph, dry_run=dry_run, since=since, scholar_id=scholar_id, limit=limit
        )
        logger.info("Person: %s", stats)
    finally:
        session.close()

    # 整批成功后才前进水位(中途抛异常则不前进→下次重跑这批,rank@0 幂等无害)
    if mode == "incremental" and not dry_run and stats.get("max_update_time"):
        Watermark.for_domain("scholar").advance_if_higher(stats["max_update_time"])
        logger.info("scholar watermark advanced to %s", stats["max_update_time"])
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
    ap.add_argument(
        "--mode",
        choices=("full", "incremental"),
        default="full",
        help="full=全量;incremental=只灌 update_time>水位 的行(读 script/.etl_watermark/scholar.txt)",
    )
    ap.add_argument("--scholar-id", help="只灌该 scholar(定向,如 855924f1)")
    ap.add_argument("--limit", type=int, help="最多取 N 行(采样/测通)")
    return ap.parse_args()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    args = _parse_args()
    result = run(
        database=args.database,
        dry_run=args.dry_run,
        mode=args.mode,
        scholar_id=args.scholar_id,
        limit=args.limit,
    )
    logger.info("done: %s", result)
