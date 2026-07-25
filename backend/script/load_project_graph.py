"""MySQL gkx_element 项目表 → TRSGraph space=`dev` ETL。

Stage:
  1. Project 顶点（dwd_zh_project / dwd_en_project）
  2. FUNDED_BY / LEADS（机构/人桩）
  3. PARTICIPATES_IN / HAS_PARTICIPANT
  4. HAS_KEYWORD
  5. Output UPSERT 计数 + JSON → OUTPUT_OF
  6. Rel 表（若存在）→ OUTPUT_OF
  7. DataSource + SOURCED_FROM

用法：
  TRS_GRAPH_SPACE=dev python -m script.load_project_graph --id-prefix fake-
  TRS_GRAPH_SPACE=dev python -m script.load_project_graph --limit 500
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import text

from dao.project import ProjectDAO
from infra.graph_db import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings
from infra.graph_db.exceptions import GraphRequestError
from infra.mysql import get_mysql_client
from script.project_graph_utils import (
    build_output_count_props,
    build_project_props,
    edge_provenance,
    keyword_vid,
    normalize_name,
    org_vid,
    paper_stub_vid,
    parse_json_objects,
    parse_list,
    patent_stub_vid,
    person_vid,
    project_vid,
)

# re-export for unit tests that import from this module
__all__ = [
    "parse_list",
    "project_vid",
    "load_project_graph",
]

logger = logging.getLogger("script.load_project_graph")

GRAPH_SPACE = "dev"
SOURCE_SYSTEM = "gkx_element"
STUB_SOURCE = "project_stub"


def _merge_node(graph: TRSGraphClient, labels: list[str], vid: str, props: dict[str, Any]) -> None:
    payload = {**props, "vid": vid}
    try:
        graph.merge_node(labels, {"vid": vid}, payload)
    except GraphRequestError as exc:
        logger.error(
            "merge_node failed labels=%s vid=%s status=%s body=%s props_keys=%s",
            labels,
            vid,
            exc.status_code,
            (exc.body or "")[:800],
            sorted(payload.keys()),
        )
        raise


def _merge_edge(
    graph: TRSGraphClient,
    source_id: str,
    target_id: str,
    edge_type: str,
    properties: dict[str, Any],
) -> None:
    """trs-graph requires non-empty identityProps on edge merge."""
    identity = {
        "source_record_id": str(properties.get("source_record_id") or f"{source_id}->{target_id}"),
    }
    try:
        graph.merge_edge(source_id, target_id, edge_type, identity, properties)
    except GraphRequestError as exc:
        logger.error(
            "merge_edge failed type=%s %s->%s status=%s body=%s",
            edge_type,
            source_id,
            target_id,
            exc.status_code,
            (exc.body or "")[:800],
        )
        raise


def _stub_provenance(*, ingest_batch: str, ingest_time: str, record_id: str) -> dict[str, str]:
    return {
        "source_system": SOURCE_SYSTEM,
        "source_table": "project_stub",
        "source_record_id": record_id,
        "source_url": "",
        "ingest_batch": ingest_batch,
        "ingest_time": ingest_time,
        "source_update_time": "",
    }


def get_dev_graph_client() -> TRSGraphClient:
    settings = TRSGraphSettings.from_env()
    settings.space = GRAPH_SPACE
    client = TRSGraphClient(settings)
    client.connect()
    return client


def _merge_stub_person(
    graph: TRSGraphClient, name: str, *, ingest_batch: str, ingest_time: str
) -> str:
    """增量写 Person 桩：已存在则跳过，避免覆盖同事数据。"""
    vid = person_vid(name)
    if graph.get_node(vid) is not None:
        return vid
    is_ascii = all(ord(c) < 128 for c in name)
    # 现网 Person：name_zh/name_en（无 name_cn / person_kind）
    props = {
        "name_zh": "" if is_ascii else name,
        "name_en": name if is_ascii else "",
        **_stub_provenance(ingest_batch=ingest_batch, ingest_time=ingest_time, record_id=vid),
    }
    _merge_node(graph, ["Person"], vid, props)
    return vid


def _merge_stub_org(
    graph: TRSGraphClient, name: str, *, ingest_batch: str, ingest_time: str
) -> str:
    """增量写 Organization 桩：已存在则跳过。"""
    cleaned = normalize_name(name).rstrip("；;")
    vid = org_vid(cleaned)
    if graph.get_node(vid) is not None:
        return vid
    is_ascii = all(ord(c) < 128 for c in cleaned)
    # 现网 Organization：无 org_id / source_url / source_update_time
    props = {
        "name_cn": cleaned,
        "name_en": cleaned if is_ascii else "",
        "org_kind": STUB_SOURCE,
        "source_system": SOURCE_SYSTEM,
        "source_table": "project_stub",
        "source_record_id": vid,
        "ingest_batch": ingest_batch,
        "ingest_time": ingest_time,
    }
    _merge_node(graph, ["Organization"], vid, props)
    return vid


def _merge_keyword(
    graph: TRSGraphClient, keyword: str, *, ingest_batch: str, ingest_time: str
) -> str:
    """现网 Keyword 仅有 keyword 列；已存在则跳过。"""
    del ingest_batch, ingest_time  # 现网 Tag 无溯源列
    vid = keyword_vid(keyword)
    if graph.get_node(vid) is not None:
        return vid
    _merge_node(graph, ["Keyword"], vid, {"keyword": keyword.strip().lower()})
    return vid


def _merge_stub_paper(
    graph: TRSGraphClient,
    *,
    vid: str,
    title: str,
    doi: str,
    source_table: str,
    source_record_id: str,
    ingest_batch: str,
    ingest_time: str,
) -> None:
    """增量写 Paper 桩：已存在则跳过。现网用 title_zh/title_en。"""
    if graph.get_node(vid) is not None:
        return
    is_ascii = all(ord(c) < 128 for c in title) if title else True
    props = {
        "title_zh": "" if is_ascii else title,
        "title_en": title if is_ascii else "",
        "doi": doi or "",
        "source_system": SOURCE_SYSTEM,
        "source_table": source_table,
        "source_record_id": source_record_id,
        "source_url": "",
        "ingest_batch": ingest_batch,
        "ingest_time": ingest_time,
        "source_update_time": "",
    }
    _merge_node(graph, ["Paper"], vid, props)


def _merge_stub_patent(
    graph: TRSGraphClient,
    *,
    vid: str,
    title: str,
    publication_number: str,
    source_table: str,
    source_record_id: str,
    ingest_batch: str,
    ingest_time: str,
) -> None:
    """增量写 Patent 桩：已存在则跳过。现网用 title_zh/title_en；datetime 列不写空串。"""
    del ingest_batch, ingest_time
    if graph.get_node(vid) is not None:
        return
    is_ascii = all(ord(c) < 128 for c in title) if title else True
    props = {
        "title_zh": "" if is_ascii else (title or ""),
        "title_en": (title or "") if is_ascii else "",
        "publication_number": publication_number or "",
        "source_system": SOURCE_SYSTEM,
        "source_table": source_table,
        "source_record_id": source_record_id,
        "source_url": "",
    }
    _merge_node(graph, ["Patent"], vid, props)


def _load_project_rows(
    dao: ProjectDAO,
    *,
    id_prefix: str | None,
    limit: int | None,
) -> list[tuple[Any, str, str]]:
    rows: list[tuple[Any, str, str]] = []
    batch = 200
    for list_fn, source, table in (
        (dao.list_zh, "zh_project", "dwd_zh_project"),
        (dao.list_en, "en_project", "dwd_en_project"),
    ):
        offset = 0
        while True:
            chunk_limit = batch if limit is None else min(batch, max(limit - len(rows), 0))
            if chunk_limit <= 0:
                return rows
            chunk = list_fn(offset=offset, limit=chunk_limit, id_prefix=id_prefix)
            if not chunk:
                break
            for row in chunk:
                rows.append((row, source, table))
                if limit is not None and len(rows) >= limit:
                    return rows
            offset += len(chunk)
            if len(chunk) < chunk_limit:
                break
    return rows


def stage_projects(
    graph: TRSGraphClient,
    projects: list[tuple[Any, str, str]],
    *,
    ingest_batch: str,
    ingest_time: str,
) -> int:
    count = 0
    for row, source, table in projects:
        props = build_project_props(
            row,
            source=source,
            source_table=table,
            ingest_batch=ingest_batch,
            ingest_time=ingest_time,
        )
        # default output counts
        props.update(
            {
                "total_outputs": 0,
                "journal_articles_count": 0,
                "conference_papers_count": 0,
                "books_count": 0,
                "degree_papers_count": 0,
                "patents_count": 0,
                "clinical_trials_count": 0,
                "products_count": 0,
                "awards_count": 0,
                "reports_count": 0,
                "other_outputs_count": 0,
            }
        )
        vid = project_vid(row.id)
        _merge_node(graph, ["Project"], vid, props)
        count += 1
    return count


def stage_funded_and_leads(
    graph: TRSGraphClient,
    projects: list[tuple[Any, str, str]],
    *,
    ingest_batch: str,
    ingest_time: str,
) -> None:
    for row, _source, table in projects:
        pvid = project_vid(row.id)
        ep = edge_provenance(
            source_table=table,
            source_record_id=row.id,
            ingest_batch=ingest_batch,
            ingest_time=ingest_time,
        )
        institution = normalize_name(row.funded_institution).rstrip("；;")
        if institution:
            ovid = _merge_stub_org(
                graph, institution, ingest_batch=ingest_batch, ingest_time=ingest_time
            )
            _merge_edge(
                graph,
                pvid,
                ovid,
                "FUNDED_BY",
                {
                    "funded_amount": float(row.funded_amount or 0),
                    "fund_category": row.fund_category or "",
                    **ep,
                },
            )
        host = normalize_name(row.project_host)
        if host:
            person = _merge_stub_person(
                graph, host, ingest_batch=ingest_batch, ingest_time=ingest_time
            )
            _merge_edge(graph, pvid, person, "LEADS", ep)


def stage_participants(
    graph: TRSGraphClient,
    projects: list[tuple[Any, str, str]],
    *,
    ingest_batch: str,
    ingest_time: str,
) -> None:
    for row, _source, table in projects:
        pvid = project_vid(row.id)
        ep = edge_provenance(
            source_table=table,
            source_record_id=row.id,
            ingest_batch=ingest_batch,
            ingest_time=ingest_time,
        )
        for org_name in parse_list(row.participating_institution):
            ovid = _merge_stub_org(
                graph, org_name, ingest_batch=ingest_batch, ingest_time=ingest_time
            )
            _merge_edge(graph, ovid, pvid, "PARTICIPATES_IN", ep)
        for person_name in parse_list(row.participants):
            person = _merge_stub_person(
                graph, person_name, ingest_batch=ingest_batch, ingest_time=ingest_time
            )
            _merge_edge(graph, pvid, person, "HAS_PARTICIPANT", ep)


def stage_keywords(
    graph: TRSGraphClient,
    projects: list[tuple[Any, str, str]],
    *,
    ingest_batch: str,
    ingest_time: str,
) -> None:
    for row, _source, table in projects:
        pvid = project_vid(row.id)
        ep = edge_provenance(
            source_table=table,
            source_record_id=row.id,
            ingest_batch=ingest_batch,
            ingest_time=ingest_time,
        )
        for kw in parse_list(row.keywords):
            kvid = _merge_keyword(graph, kw, ingest_batch=ingest_batch, ingest_time=ingest_time)
            _merge_edge(graph, pvid, kvid, "HAS_KEYWORD", ep)


def stage_outputs(
    graph: TRSGraphClient,
    dao: ProjectDAO,
    *,
    id_prefix: str | None,
    ingest_batch: str,
    ingest_time: str,
) -> int:
    count = 0
    for list_fn, table in (
        (dao.list_zh_output, "dwd_zh_project_output"),
        (dao.list_en_output, "dwd_en_project_output"),
    ):
        offset = 0
        batch = 200
        while True:
            rows = list_fn(offset=offset, limit=batch, id_prefix=id_prefix)
            if not rows:
                break
            for row in rows:
                pvid = project_vid(row.id)
                counts = build_output_count_props(row)
                try:
                    existing = graph.get_node(pvid)
                    if existing is not None:
                        graph.update_node(pvid, counts)
                    else:
                        logger.warning("project node missing for output id=%s", row.id)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("update counts failed for %s: %s", row.id, exc)

                ep = edge_provenance(
                    source_table=table,
                    source_record_id=row.id,
                    ingest_batch=ingest_batch,
                    ingest_time=ingest_time,
                )
                for field in (
                    "output_journal_articles",
                    "output_conference_papers",
                    "output_degree_papers",
                ):
                    for item in parse_json_objects(getattr(row, field, None)):
                        paper_id = paper_stub_vid(
                            doi=str(item.get("doi") or "") or None,
                            title=str(item.get("title") or "") or None,
                        )
                        _merge_stub_paper(
                            graph,
                            vid=paper_id,
                            title=str(item.get("title") or ""),
                            doi=str(item.get("doi") or ""),
                            source_table=table,
                            source_record_id=row.id,
                            ingest_batch=ingest_batch,
                            ingest_time=ingest_time,
                        )
                        _merge_edge(graph, paper_id, pvid, "OUTPUT_OF", ep)

                for item in parse_json_objects(getattr(row, "output_patents", None)):
                    patent_id = patent_stub_vid(
                        patent_number=str(
                            item.get("patent_number") or item.get("publication_number") or ""
                        )
                        or None,
                        title=str(item.get("patent_title") or item.get("title") or "") or None,
                    )
                    _merge_stub_patent(
                        graph,
                        vid=patent_id,
                        title=str(item.get("patent_title") or item.get("title") or ""),
                        publication_number=str(
                            item.get("patent_number") or item.get("publication_number") or ""
                        ),
                        source_table=table,
                        source_record_id=row.id,
                        ingest_batch=ingest_batch,
                        ingest_time=ingest_time,
                    )
                    _merge_edge(graph, patent_id, pvid, "OUTPUT_OF", ep)
                count += 1
            offset += len(rows)
            if len(rows) < batch:
                break
    return count


def stage_rel_tables(
    graph: TRSGraphClient,
    session: Any,
    *,
    ingest_batch: str,
    ingest_time: str,
) -> int:
    count = 0
    for table, src_col, prefix, label in (
        ("dwd_rel_project_paper", "paper_id", "paper_", "Paper"),
        ("dwd_rel_project_patent", "patent_id", "patent_", "Patent"),
    ):
        exists = session.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema=DATABASE() AND table_name=:t"
            ),
            {"t": table},
        ).scalar()
        if not exists:
            logger.info("rel table %s not found — skip", table)
            continue
        rows = (
            session.execute(
                text(f"SELECT project_id, {src_col} AS src_id FROM `{table}` LIMIT 10000")
            )
            .mappings()
            .all()
        )
        for row in rows:
            project_id = str(row["project_id"])
            src_id = str(row["src_id"])
            pvid = project_vid(project_id)
            svid = f"{prefix}{src_id}"[:64]
            if label == "Paper":
                _merge_stub_paper(
                    graph,
                    vid=svid,
                    title="",
                    doi="",
                    source_table=table,
                    source_record_id=f"{project_id}:{src_id}",
                    ingest_batch=ingest_batch,
                    ingest_time=ingest_time,
                )
            else:
                _merge_stub_patent(
                    graph,
                    vid=svid,
                    title="",
                    publication_number=src_id,
                    source_table=table,
                    source_record_id=f"{project_id}:{src_id}",
                    ingest_batch=ingest_batch,
                    ingest_time=ingest_time,
                )
            ep = edge_provenance(
                source_table=table,
                source_record_id=f"{project_id}:{src_id}",
                ingest_batch=ingest_batch,
                ingest_time=ingest_time,
            )
            _merge_edge(graph, svid, pvid, "OUTPUT_OF", ep)
            count += 1
    return count


def stage_datasource(
    graph: TRSGraphClient,
    projects: list[tuple[Any, str, str]],
    *,
    ingest_batch: str,
    ingest_time: str,
) -> None:
    tables = {
        "dwd_zh_project": "深势-国内项目信息表",
        "dwd_en_project": "深势-国外项目信息表",
        "dwd_zh_project_output": "深势-国内项目产出信息表",
        "dwd_en_project_output": "深势-国外项目产出信息表",
    }
    for table, cn_name in tables.items():
        ds_vid = f"ds_{table}"
        # 已存在则跳过，避免覆盖同事 DataSource
        if graph.get_node(ds_vid) is not None:
            continue
        props = {
            "source_table": table,
            "table_cn_name": cn_name,
            "tier": "element",
            "library": SOURCE_SYSTEM,
        }
        _merge_node(graph, ["DataSource"], ds_vid, props)

    for row, _source, table in projects:
        pvid = project_vid(row.id)
        ds_vid = f"ds_{table}"
        _merge_edge(
            graph,
            pvid,
            ds_vid,
            "SOURCED_FROM",
            {
                "source_table": table,
                "source_record_id": str(row.id),
                "ingest_batch": ingest_batch,
                "ingest_time": ingest_time,
            },
        )


def load_project_graph(
    *,
    id_prefix: str | None = None,
    limit: int | None = None,
    ingest_batch: str | None = None,
) -> dict[str, int]:
    ingest_batch = ingest_batch or datetime.now().strftime("BATCH_%Y%m%d_%H%M%S")
    ingest_time = datetime.now().isoformat(sep=" ", timespec="seconds")

    mysql = get_mysql_client()
    graph = get_dev_graph_client()
    session = mysql.session()
    stats = {"projects": 0, "outputs": 0, "rels": 0}
    try:
        dao = ProjectDAO(session)
        projects = _load_project_rows(dao, id_prefix=id_prefix, limit=limit)
        logger.info("stage1 projects=%d batch=%s", len(projects), ingest_batch)
        stats["projects"] = stage_projects(
            graph, projects, ingest_batch=ingest_batch, ingest_time=ingest_time
        )
        logger.info("stage2 FUNDED_BY / LEADS")
        stage_funded_and_leads(graph, projects, ingest_batch=ingest_batch, ingest_time=ingest_time)
        logger.info("stage3 PARTICIPATES_IN / HAS_PARTICIPANT")
        stage_participants(graph, projects, ingest_batch=ingest_batch, ingest_time=ingest_time)
        logger.info("stage4 HAS_KEYWORD")
        stage_keywords(graph, projects, ingest_batch=ingest_batch, ingest_time=ingest_time)
        logger.info("stage5 outputs")
        stats["outputs"] = stage_outputs(
            graph,
            dao,
            id_prefix=id_prefix,
            ingest_batch=ingest_batch,
            ingest_time=ingest_time,
        )
        logger.info("stage6 rel tables")
        stats["rels"] = stage_rel_tables(
            graph, session, ingest_batch=ingest_batch, ingest_time=ingest_time
        )
        logger.info("stage7 DataSource + SOURCED_FROM")
        stage_datasource(graph, projects, ingest_batch=ingest_batch, ingest_time=ingest_time)
        logger.info("done: %s", stats)
        return stats
    finally:
        session.close()
        graph.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Load project subgraph into TRSGraph space=dev")
    parser.add_argument(
        "--id-prefix", default=None, help="Only load rows whose id starts with prefix"
    )
    parser.add_argument("--limit", type=int, default=None, help="Max project rows (zh+en combined)")
    parser.add_argument("--ingest-batch", default=None, help="Optional ingest batch id")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stats = load_project_graph(
        id_prefix=args.id_prefix,
        limit=args.limit,
        ingest_batch=args.ingest_batch,
    )
    print(stats)


if __name__ == "__main__":
    main()
