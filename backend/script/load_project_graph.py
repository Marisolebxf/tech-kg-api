"""Load Project vertices and Project-originating edges into TRSGraph ``dev``.

Writes FUNDED_BY, LEADS, HAS_PARTICIPANT, HAS_KEYWORD, and HAS_OUTPUT only.
It never creates cross-domain stubs or SOURCED_FROM/PARTICIPATES_IN/OUTPUT_OF.
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

from dao.project import ProjectDAO
from infra.graph_db import TRSGraphClient, close_trs_graph_client, get_trs_graph_client
from infra.graph_db.exceptions import GraphRequestError
from infra.mysql import get_mysql_client
from script.project_edge_schema import ensure_alignment_edge_schema, ensure_project_tag_confidence
from script.project_entity_matcher import MatchResult, ProjectEntityMatcher, normalize_text
from script.project_graph_utils import (
    build_output_count_props,
    build_project_props,
    edge_provenance,
    funded_by_org_props,
    keyword_vid,
    match_audit_props,
    parse_json_objects,
    parse_list,
    project_confidence,
    project_vid,
)
from script.project_ingest_report import ProjectIngestReport
from script.project_match_candidates import collect_match_candidates

__all__ = ["parse_list", "project_vid", "load_project_graph"]
logger = logging.getLogger("script.load_project_graph")
GRAPH_SPACE = "dev"
OUTPUT_FIELDS = (
    ("output_journal_articles", "journal_article", "paper"),
    ("output_conference_papers", "conference_paper", "paper"),
    ("output_degree_papers", "degree_paper", "paper"),
    ("output_patents", "patent", "patent"),
    ("output_reports", "report", "report"),
)


def preflight_graph(graph: TRSGraphClient, *, relations: bool) -> None:
    required_labels = {"Project"}
    required_edges: set[str] = set()
    if relations:
        required_labels.update({"Organization", "Person", "Keyword", "Paper", "Patent", "Report"})
        required_edges.update(
            {"FUNDED_BY", "LEADS", "HAS_PARTICIPANT", "HAS_KEYWORD", "HAS_OUTPUT"}
        )
    missing_labels = required_labels - set(graph.labels())
    missing_edges = required_edges - set(graph.edge_types())
    if missing_labels or missing_edges:
        raise RuntimeError(
            "Project graph schema incomplete; run init_project_schema first. "
            f"missing labels={sorted(missing_labels)}, edges={sorted(missing_edges)}"
        )


def _merge_node(graph: TRSGraphClient, labels: list[str], vid: str, props: dict[str, Any]) -> None:
    try:
        graph.merge_node(labels, {"vid": vid}, {**props, "vid": vid})
    except GraphRequestError as exc:
        logger.error("merge_node failed labels=%s vid=%s body=%s", labels, vid, exc.body)
        raise


def _merge_edge(
    graph: TRSGraphClient,
    source_id: str,
    target_id: str,
    edge_type: str,
    properties: dict[str, Any],
) -> None:
    identity = str(properties.get("source_record_id") or "")
    if not identity:
        raise ValueError(f"{edge_type} requires non-empty source_record_id")
    graph.merge_edge(
        source_id,
        target_id,
        edge_type,
        {"source_record_id": identity},
        properties,
    )


def get_dev_graph_client() -> TRSGraphClient:
    space = os.getenv("TRS_GRAPH_SPACE")
    if space != GRAPH_SPACE:
        raise RuntimeError(f"Project ETL requires TRS_GRAPH_SPACE=dev, got {space!r}")
    return get_trs_graph_client()


def _load_project_rows(
    dao: ProjectDAO,
    *,
    project_id: str | None = None,
    id_prefix: str | None,
    limit: int | None,
) -> list[tuple[Any, str, str]]:
    rows: list[tuple[Any, str, str]] = []
    query_prefix = project_id or id_prefix
    for list_fn, source, table in (
        (dao.list_zh, "zh_project", "dwd_zh_project"),
        (dao.list_en, "en_project", "dwd_en_project"),
    ):
        offset = 0
        while True:
            size = 200 if limit is None else min(200, max(limit - len(rows), 0))
            if size <= 0:
                return rows
            chunk = list_fn(offset=offset, limit=size, id_prefix=query_prefix)
            if project_id:
                chunk = [row for row in chunk if str(row.id) == project_id]
            if not chunk:
                break
            rows.extend((row, source, table) for row in chunk)
            if project_id or (limit is not None and len(rows) >= limit):
                return rows[:limit] if limit is not None else rows
            offset += len(chunk)
            if len(chunk) < size:
                break
    return rows


def stage_projects(
    graph: TRSGraphClient,
    projects: list[tuple[Any, str, str]],
    *,
    ingest_batch: str,
    ingest_time: str,
    dry_run: bool = False,
) -> int:
    defaults = {
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
    for row, source, table in projects:
        props = build_project_props(
            row,
            source=source,
            source_table=table,
            ingest_batch=ingest_batch,
            ingest_time=ingest_time,
        )
        if not dry_run:
            _merge_node(graph, ["Project"], project_vid(row.id), {**props, **defaults})
    return len(projects)


def _matched_vid(
    report: ProjectIngestReport,
    result: MatchResult,
    category: str,
    record: dict[str, Any],
) -> str | None:
    if result.status == "matched":
        report.increment(f"{category}_matched")
        return result.vid
    report.add(f"{category}_{result.status}", {**record, "evidence": result.evidence})
    return None


def stage_project_relations(
    graph: TRSGraphClient,
    projects: list[tuple[Any, str, str]],
    matcher: ProjectEntityMatcher,
    report: ProjectIngestReport,
    *,
    ingest_batch: str,
    ingest_time: str,
    dry_run: bool,
) -> None:
    for row, _source, table in projects:
        pvid = project_vid(row.id)
        provenance = edge_provenance(
            source_table=table,
            source_record_id=row.id,
            ingest_batch=ingest_batch,
            ingest_time=ingest_time,
        )
        institution = normalize_text(row.funded_institution).rstrip("；;")
        if institution:
            report.increment("organization_candidates")
            org_result = matcher.organization.match(institution, method="name_exact")
            target = _matched_vid(
                report,
                org_result,
                "organization",
                {"project_id": row.id, "field": "funded_institution", "value": institution},
            )
            if target:
                props = {
                    **provenance,
                    "funded_amount": float(row.funded_amount or 0),
                    "fund_category": row.fund_category or "",
                    **match_audit_props(org_result.method, org_result.evidence),
                    **funded_by_org_props(matcher.organization_id(target)),
                }
                if not dry_run:
                    _merge_edge(graph, pvid, target, "FUNDED_BY", props)
                report.increment("edges_FUNDED_BY")

        host = normalize_text(row.project_host)
        if host:
            report.increment("person_candidates")
            host_result = matcher.person.match(host, method="name_exact")
            target = _matched_vid(
                report,
                host_result,
                "person",
                {"project_id": row.id, "field": "project_host", "value": host},
            )
            if target:
                props = {
                    **provenance,
                    **match_audit_props(host_result.method, host_result.evidence),
                }
                if not dry_run:
                    _merge_edge(graph, pvid, target, "LEADS", props)
                report.increment("edges_LEADS")

        participants = {normalize_text(value) for value in parse_list(row.participants)}
        for participant in sorted(value for value in participants if value):
            report.increment("person_candidates")
            part_result = matcher.person.match(participant, method="name_exact")
            target = _matched_vid(
                report,
                part_result,
                "person",
                {"project_id": row.id, "field": "participants", "value": participant},
            )
            if target:
                props = {
                    **provenance,
                    **match_audit_props(part_result.method, part_result.evidence),
                }
                if not dry_run:
                    _merge_edge(graph, pvid, target, "HAS_PARTICIPANT", props)
                report.increment("edges_HAS_PARTICIPANT")

        for name in sorted(set(parse_list(row.participating_institution))):
            report.add(
                "cross_domain",
                {
                    "project_id": row.id,
                    "relation": "PARTICIPATES_IN",
                    "owner_domain": "organization",
                    "value": name,
                    "source_table": table,
                },
            )


def stage_keywords(
    graph: TRSGraphClient,
    projects: list[tuple[Any, str, str]],
    report: ProjectIngestReport,
    *,
    ingest_batch: str,
    ingest_time: str,
    dry_run: bool,
) -> None:
    for row, _source, table in projects:
        pvid = project_vid(row.id)
        provenance = edge_provenance(
            source_table=table,
            source_record_id=row.id,
            ingest_batch=ingest_batch,
            ingest_time=ingest_time,
        )
        keywords = {normalize_text(value) for value in parse_list(row.keywords)}
        for keyword in sorted(value for value in keywords if value):
            kvid = keyword_vid(keyword)
            if not dry_run and graph.get_node(kvid) is None:
                _merge_node(graph, ["Keyword"], kvid, {"keyword": keyword})
                report.increment("keywords_created")
            if not dry_run:
                _merge_edge(graph, pvid, kvid, "HAS_KEYWORD", provenance)
            report.increment("keyword_candidates")
            report.increment("edges_HAS_KEYWORD")


def _output_title(item: dict[str, Any]) -> str:
    return str(item.get("patent_title") or item.get("title") or "")


def _output_identifier(item: dict[str, Any]) -> str:
    return str(
        item.get("doi")
        or item.get("patent_number")
        or item.get("application_number")
        or item.get("publication_number")
        or item.get("patent_id")
        or ""
    )


def stage_outputs(
    graph: TRSGraphClient,
    dao: ProjectDAO,
    matcher: ProjectEntityMatcher,
    report: ProjectIngestReport,
    *,
    allowed_ids: set[str],
    id_prefix: str | None,
    ingest_batch: str,
    ingest_time: str,
    dry_run: bool,
) -> int:
    processed = 0
    matchers = {
        "paper": matcher.match_paper,
        "patent": matcher.match_patent,
        "report": matcher.match_report,
    }
    for list_fn, table in (
        (dao.list_zh_output, "dwd_zh_project_output"),
        (dao.list_en_output, "dwd_en_project_output"),
    ):
        offset = 0
        while True:
            rows = list_fn(offset=offset, limit=200, id_prefix=id_prefix)
            if not rows:
                break
            for row in rows:
                project_id = str(row.id)
                if project_id not in allowed_ids:
                    continue
                processed += 1
                pvid = project_vid(project_id)
                if not dry_run:
                    if graph.get_node(pvid) is None:
                        report.increment("missing_project_nodes")
                        continue
                    graph.update_node(pvid, build_output_count_props(row))
                report.increment("outputs_updated")

                for field, output_type, target_type in OUTPUT_FIELDS:
                    for item in parse_json_objects(getattr(row, field, None)):
                        report.increment(f"{target_type}_output_candidates")
                        result = matchers[target_type](item)
                        title, identifier = _output_title(item), _output_identifier(item)
                        target = _matched_vid(
                            report,
                            result,
                            "output",
                            {
                                "project_id": project_id,
                                "output_type": output_type,
                                "target_type": target_type,
                                "title": title,
                                "identifier": identifier,
                                "source_table": table,
                            },
                        )
                        if not target:
                            continue
                        relation_key = f"{project_id}|{output_type}|{target}"
                        props = {
                            "output_type": output_type,
                            "output_title": title,
                            "output_identifier": identifier,
                            **match_audit_props(result.method, result.evidence),
                            "source_table": table,
                            "source_record_id": relation_key,
                            "ingest_batch": ingest_batch,
                            "ingest_time": ingest_time,
                        }
                        if not dry_run:
                            _merge_edge(graph, pvid, target, "HAS_OUTPUT", props)
                        report.increment("edges_HAS_OUTPUT")
            offset += len(rows)
            if len(rows) < 200:
                break
    return processed


def stage_rel_table_candidates(
    session: Any, report: ProjectIngestReport, *, allowed_ids: set[str]
) -> None:
    for table, source_column, owner in (
        ("dwd_rel_project_paper", "paper_id", "paper"),
        ("dwd_rel_project_patent", "patent_id", "patent"),
    ):
        exists = session.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema=DATABASE() AND table_name=:table"
            ),
            {"table": table},
        ).scalar()
        if not exists:
            continue
        rows = session.execute(
            text(f"SELECT project_id, {source_column} AS source_id FROM `{table}`")
        ).mappings()
        for row in rows:
            if str(row["project_id"]) in allowed_ids:
                report.add(
                    "cross_domain",
                    {
                        "project_id": str(row["project_id"]),
                        "relation": "OUTPUT_OF",
                        "owner_domain": owner,
                        "source_id": str(row["source_id"]),
                        "source_table": table,
                    },
                )


def backfill_project_confidence(
    graph: TRSGraphClient,
    *,
    dry_run: bool = False,
    page_size: int = 500,
) -> dict[str, Any]:
    """回填现有 Project 节点的实体置信度。

    dev 上 Project 节点由历史批次写入、当时无 confidence 字段；merge_node 对
    已存在节点不可靠（见 CLAUDE.md 图库 caveat），故这里用 update_node 按
    节点已有属性重算 confidence 并写入。可幂等重跑。
    """
    scanned = 0
    updated = 0
    skipped = 0
    offset = 0
    while True:
        page = graph.get_nodes_by_label("Project", limit=page_size, offset=offset)
        items = list(getattr(page, "items", None) or [])
        if not items:
            break
        for node in items:
            scanned += 1
            vid = getattr(node, "id", None) or (node.get("id") if isinstance(node, dict) else None)
            props = getattr(node, "properties", None)
            if not isinstance(props, dict) and isinstance(node, dict):
                props = node.get("properties") or {}
            if not vid or not isinstance(props, dict):
                skipped += 1
                continue
            confidence = project_confidence(props)
            if not dry_run:
                try:
                    graph.update_node(str(vid), {"confidence": confidence})
                except GraphRequestError as exc:
                    logger.warning("update_node failed vid=%s body=%s", vid, exc.body)
                    skipped += 1
                    continue
            updated += 1
        if len(items) < page_size:
            break
        offset += len(items)
    report = {
        "dry_run": dry_run,
        "scanned": scanned,
        "updated": updated,
        "skipped": skipped,
    }
    logger.info("backfill_project_confidence summary: %s", report)
    return report


def load_project_graph(
    *,
    project_id: str | None = None,
    id_prefix: str | None = None,
    limit: int | None = None,
    ingest_batch: str | None = None,
    nodes_only: bool = False,
    relations_only: bool = False,
    dry_run: bool = False,
    strict_existing_entities: bool = True,
    report_dir: Path | None = None,
    graph: TRSGraphClient | None = None,
) -> dict[str, Any]:
    if nodes_only and relations_only:
        raise ValueError("--nodes-only and --relations-only are mutually exclusive")
    if not strict_existing_entities:
        raise ValueError("Project ETL does not support stub entities")

    ingest_batch = ingest_batch or datetime.now().strftime("BATCH_%Y%m%d_%H%M%S")
    ingest_time = datetime.now().isoformat(sep=" ", timespec="seconds")
    report = ProjectIngestReport(
        report_dir or Path("/tmp/project-ingest-reports") / ingest_batch,
        ingest_batch=ingest_batch,
        dry_run=dry_run,
    )
    mysql = get_mysql_client()
    owns_graph = graph is None
    graph = graph or get_dev_graph_client()
    session = mysql.session()
    try:
        preflight_graph(graph, relations=not nodes_only)
        if not dry_run and not nodes_only:
            ensure_alignment_edge_schema(graph)
            ensure_project_tag_confidence(graph)
        dao = ProjectDAO(session)
        projects = _load_project_rows(dao, project_id=project_id, id_prefix=id_prefix, limit=limit)
        allowed_ids = {str(row.id) for row, _source, _table in projects}
        report.increment("projects_scanned", len(projects))
        if not relations_only:
            report.increment(
                "projects_merged",
                stage_projects(
                    graph,
                    projects,
                    ingest_batch=ingest_batch,
                    ingest_time=ingest_time,
                    dry_run=dry_run,
                ),
            )
        if not nodes_only:
            candidates = collect_match_candidates(dao, projects, id_prefix=project_id or id_prefix)
            matcher = ProjectEntityMatcher.from_graph(graph, candidates)
            stage_outputs(
                graph,
                dao,
                matcher,
                report,
                allowed_ids=allowed_ids,
                id_prefix=project_id or id_prefix,
                ingest_batch=ingest_batch,
                ingest_time=ingest_time,
                dry_run=dry_run,
            )
            stage_project_relations(
                graph,
                projects,
                matcher,
                report,
                ingest_batch=ingest_batch,
                ingest_time=ingest_time,
                dry_run=dry_run,
            )
            stage_keywords(
                graph,
                projects,
                report,
                ingest_batch=ingest_batch,
                ingest_time=ingest_time,
                dry_run=dry_run,
            )
            stage_rel_table_candidates(session, report, allowed_ids=allowed_ids)
        return report.write()
    finally:
        session.close()
        if owns_graph:
            close_trs_graph_client()


def main() -> None:
    parser = argparse.ArgumentParser(description="Load Project domain into TRSGraph dev")
    parser.add_argument("--id", dest="project_id")
    parser.add_argument("--id-prefix")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--ingest-batch")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--nodes-only", action="store_true")
    mode.add_argument("--relations-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--backfill-confidence",
        action="store_true",
        help="仅回填现有 Project 节点的 confidence（用 update_node），不灌新数据",
    )
    parser.add_argument(
        "--strict-existing-entities",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--report-dir", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.backfill_confidence:
        graph = get_dev_graph_client()
        try:
            print(backfill_project_confidence(graph, dry_run=args.dry_run))
        finally:
            close_trs_graph_client()
        return
    print(
        load_project_graph(
            project_id=args.project_id,
            id_prefix=args.id_prefix,
            limit=args.limit,
            ingest_batch=args.ingest_batch,
            nodes_only=args.nodes_only,
            relations_only=args.relations_only,
            dry_run=args.dry_run,
            strict_existing_entities=args.strict_existing_entities,
            report_dir=args.report_dir,
        )
    )


if __name__ == "__main__":
    main()
