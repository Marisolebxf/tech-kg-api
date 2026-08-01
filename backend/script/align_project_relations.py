"""项目关系对齐补边：精确匹配优先，再对机构/人员做 Milvus hybrid 回退。

边界（与 mapping_project 一致）：
- 不建桩、不写 SAME_AS / PARTICIPATES_IN / OUTPUT_OF
- 只 merge FUNDED_BY / LEADS / HAS_PARTICIPANT / HAS_OUTPUT
- 成果边不做标题语义自动对齐；仅 DOI/专利号等标识符精确增强

用法::

    cd backend
    uv sync --extra milvus
    MILVUS_URI=http://127.0.0.1:19530 MILVUS_PORT=19530 TRS_GRAPH_SPACE=dev \\
      uv run python -m script.align_project_relations --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv

from dao.project import ProjectDAO
from infra.graph_db import close_trs_graph_client
from infra.milvus import MilvusSettings, OrganizationMilvusStore, get_milvus_client
from infra.mysql import get_mysql_client
from script.load_project_graph import (
    OUTPUT_FIELDS,
    _load_project_rows,
    _merge_edge,
    _output_identifier,
    _output_title,
    get_dev_graph_client,
    preflight_graph,
)
from script.project_entity_matcher import (
    MatchResult,
    ProjectEntityMatcher,
    normalize_doi,
    normalize_patent_number,
    normalize_text,
)
from script.project_graph_utils import edge_provenance, parse_json_objects, parse_list, project_vid
from script.project_ingest_report import ProjectIngestReport
from script.project_match_candidates import collect_match_candidates
from service.organization_entity_alignment import (
    BM25SparseEncoder,
    HashingDenseEncoder,
    OrganizationAlignmentContext,
    OrganizationHybridMatcher,
)
from service.project_milvus import (
    DEFAULT_ORG_MARGIN,
    DEFAULT_ORG_THRESHOLD,
    DEFAULT_PERSON_MARGIN,
    DEFAULT_PERSON_NAME_MIN,
    DEFAULT_PERSON_THRESHOLD,
    DEFAULT_TOP_K,
    decide_person,
    score_person_hit,
)

logger = logging.getLogger("script.align_project_relations")

DEFAULT_STATE_DIR = ".cache/organization_milvus"
GRAPH_SPACE = "dev"

# Properties required for alignment audit fields on existing edges.
_EDGE_ALIGNMENT_PROPS: dict[str, dict[str, str]] = {
    "FUNDED_BY": {
        "match_method": "string",
        "match_evidence": "string",
        "confidence": "double",
    },
    "LEADS": {
        "match_method": "string",
        "match_evidence": "string",
        "confidence": "double",
    },
    "HAS_PARTICIPANT": {
        "match_method": "string",
        "match_evidence": "string",
        "confidence": "double",
    },
}


def ensure_alignment_edge_schema(graph: Any) -> None:
    """ALTER EDGE ADD missing match_* columns on already-deployed spaces (patent-style)."""
    for edge_type, wanted in _EDGE_ALIGNMENT_PROPS.items():
        try:
            described = graph.execute_read(f"USE {GRAPH_SPACE}; DESCRIBE EDGE {edge_type};")
        except Exception as exc:  # noqa: BLE001
            logger.warning("DESCRIBE EDGE %s failed: %s", edge_type, exc)
            continue
        existing = {
            str(row.get("Field") or row.get("field") or "")
            for row in (getattr(described, "records", None) or [])
        }
        missing = [(name, kind) for name, kind in wanted.items() if name not in existing]
        if not missing:
            continue
        ddl = (
            f"USE {GRAPH_SPACE}; ALTER EDGE {edge_type} ADD ("
            + ", ".join(f"{name} {kind}" for name, kind in missing)
            + ");"
        )
        logger.info("altering edge schema: %s", ddl)
        graph.execute_write(ddl)
        for attempt in range(15):
            visible = {
                str(row.get("Field") or row.get("field") or "")
                for row in (
                    getattr(
                        graph.execute_read(f"USE {GRAPH_SPACE}; DESCRIBE EDGE {edge_type};"),
                        "records",
                        None,
                    )
                    or []
                )
            }
            if {name for name, _ in missing} <= visible:
                break
            if attempt == 14:
                raise RuntimeError(f"{edge_type} new properties not visible after ALTER")
            time.sleep(1)


def _configure_milvus_port_from_uri() -> None:
    """Keep OrganizationMilvusStore (HOST/PORT) aligned with MILVUS_URI when set."""
    uri = os.environ.get("MILVUS_URI")
    if not uri:
        return
    parsed = urlparse(uri)
    if parsed.hostname and not os.environ.get("MILVUS_HOST"):
        os.environ["MILVUS_HOST"] = parsed.hostname
    if parsed.port and not os.environ.get("MILVUS_PORT"):
        os.environ["MILVUS_PORT"] = str(parsed.port)


def _state_dir() -> Path:
    return Path(os.environ.get("ORG_MILVUS_STATE_DIR") or DEFAULT_STATE_DIR).resolve()


def _load_org_matcher(
    store: OrganizationMilvusStore,
    *,
    entity_type: str,
) -> OrganizationHybridMatcher | None:
    if not store.has_collection(entity_type):
        logger.warning(
            "Milvus collection for %s missing (%s); hybrid skipped",
            entity_type,
            store.collection_name(entity_type),
        )
        return None
    path = _state_dir() / f"{store.collection_name(entity_type)}.bm25.json"
    if not path.exists():
        logger.warning("BM25 state missing at %s; hybrid skipped for %s", path, entity_type)
        return None
    try:
        store.load(entity_type)
    except Exception:  # noqa: BLE001
        pass
    bm25 = BM25SparseEncoder.load(path)
    return OrganizationHybridMatcher(
        store,
        bm25,
        HashingDenseEncoder(384),
        threshold=DEFAULT_ORG_THRESHOLD,
        margin=DEFAULT_ORG_MARGIN,
        top_k=DEFAULT_TOP_K,
    )


def _align_organization(
    matcher: ProjectEntityMatcher,
    org_hybrid: OrganizationHybridMatcher | None,
    name: str,
    *,
    project_id: str,
    source_table: str,
) -> MatchResult:
    exact = matcher.organization.match(name, method="name_exact")
    if exact.status != "not_found":
        return exact
    if org_hybrid is None:
        return exact
    decision = org_hybrid.align(
        OrganizationAlignmentContext(
            name=name,
            source_table=source_table,
            source_record_id=project_id,
        )
    )
    if decision.status == "matched" and decision.selected_vid:
        return MatchResult(
            "matched",
            decision.selected_vid,
            "milvus_hybrid",
            f"score={decision.score:.4f};margin={decision.margin:.4f}",
        )
    return MatchResult("not_found", evidence=decision.reason or exact.evidence)


def _align_person(
    matcher: ProjectEntityMatcher,
    person_store: OrganizationMilvusStore,
    person_bm25: BM25SparseEncoder | None,
    person_dense: HashingDenseEncoder,
    name: str,
    *,
    institution: str,
    discipline: str,
) -> MatchResult:
    exact = matcher.person.match(name, method="name_exact")
    if exact.status != "not_found":
        return exact
    if person_bm25 is None or not person_store.has_collection("Person"):
        return exact
    query_text = " ".join(part for part in (name, institution, discipline) if part)
    sparse = person_bm25.encode_query(query_text or name)
    if not sparse:
        return MatchResult("not_found", evidence="empty_sparse_query")
    hits = person_store.hybrid_search(
        "Person",
        dense_vector=person_dense.encode(query_text or name),
        sparse_vector=sparse,
        limit=DEFAULT_TOP_K,
    )
    scored = [
        score_person_hit(
            query_name=name,
            institution=institution,
            discipline=discipline,
            hit=hit,
        )
        for hit in hits
    ]
    scored.sort(key=lambda item: (-item.score, item.vid))
    decision = decide_person(
        scored,
        threshold=DEFAULT_PERSON_THRESHOLD,
        margin=DEFAULT_PERSON_MARGIN,
        name_min=DEFAULT_PERSON_NAME_MIN,
    )
    if decision.status == "matched" and decision.vid:
        return MatchResult("matched", decision.vid, decision.method, decision.evidence)
    return MatchResult("not_found", evidence=decision.evidence or exact.evidence)


def _record_match(
    report: ProjectIngestReport,
    result: MatchResult,
    category: str,
    record: dict[str, Any],
) -> str | None:
    if result.status == "matched":
        report.increment(f"{category}_matched")
        if result.method == "milvus_hybrid":
            report.increment(f"{category}_hybrid_matched")
        return result.vid
    report.add(f"{category}_{result.status}", {**record, "evidence": result.evidence})
    return None


def _build_doi_registry(milvus: Any, collection: str) -> dict[str, str]:
    if not milvus.has_collection(collection):
        return {}
    registry: dict[str, str] = {}
    offset = 0
    while True:
        try:
            rows = milvus.query(
                collection_name=collection,
                filter="doi != ''",
                output_fields=["vid", "doi"],
                limit=16384,
                offset=offset,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("query %s doi registry failed: %s", collection, exc)
            return registry
        if not rows:
            break
        for row in rows:
            doi = normalize_doi(row.get("doi"))
            vid = row.get("vid")
            if doi and vid:
                registry[doi] = str(vid)
        offset += len(rows)
        if len(rows) < 16384:
            break
    logger.info("milvus %s doi registry size=%d", collection, len(registry))
    return registry


def _build_patent_number_registry(milvus: Any, collection: str) -> dict[str, str]:
    if not milvus.has_collection(collection):
        return {}
    fields = ("publication_number", "application_number", "granted_number", "patent_id")
    registry: dict[str, str] = {}
    offset = 0
    while True:
        try:
            rows = milvus.query(
                collection_name=collection,
                filter="",
                output_fields=["vid", *fields],
                limit=16384,
                offset=offset,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("query %s patent registry failed: %s", collection, exc)
            return registry
        if not rows:
            break
        for row in rows:
            vid = str(row.get("vid") or "")
            if not vid:
                continue
            for field in fields:
                number = normalize_patent_number(row.get(field))
                if number:
                    registry.setdefault(number, vid)
        offset += len(rows)
        if len(rows) < 16384:
            break
    logger.info("milvus %s patent number registry size=%d", collection, len(registry))
    return registry


def _confidence_from_result(result: MatchResult) -> float:
    if result.method in {
        "name_exact",
        "doi_exact",
        "doi_registry_exact",
        "patent_number_exact",
        "patent_number_registry_exact",
        "title_exact",
        "title_year_exact",
    }:
        return 1.0
    match = re.search(r"score=([0-9.]+)", result.evidence or "")
    if match:
        try:
            return round(float(match.group(1)), 4)
        except ValueError:
            pass
    return 0.9


def _normalize_output_item(item: dict[str, Any], target_type: str) -> dict[str, Any]:
    """Strengthen identifier normalization before exact matching."""
    cleaned = dict(item)
    if target_type == "paper":
        doi = normalize_doi(cleaned.get("doi") or cleaned.get("DOI"))
        if doi:
            cleaned["doi"] = doi
        for key in ("title", "title_zh", "title_en"):
            if cleaned.get(key):
                cleaned[key] = normalize_text(cleaned[key])
        if cleaned.get("year"):
            cleaned["year"] = str(cleaned["year"]).strip()[:4]
    elif target_type == "patent":
        for key in (
            "patent_number",
            "application_number",
            "publication_number",
            "patent_id",
        ):
            if cleaned.get(key):
                cleaned[key] = normalize_patent_number(cleaned[key])
        title = cleaned.get("patent_title") or cleaned.get("title")
        if title:
            cleaned["patent_title"] = normalize_text(title)
            cleaned["title"] = cleaned["patent_title"]
    else:
        if cleaned.get("title"):
            cleaned["title"] = normalize_text(cleaned["title"])
        if cleaned.get("year"):
            cleaned["year"] = str(cleaned["year"]).strip()[:4]
    return cleaned


def _match_output(
    matcher: ProjectEntityMatcher,
    item: dict[str, Any],
    target_type: str,
    *,
    doi_registry: dict[str, str],
    patent_registry: dict[str, str],
) -> MatchResult:
    cleaned = _normalize_output_item(item, target_type)
    if target_type == "paper":
        doi = normalize_doi(cleaned.get("doi"))
        if doi and doi in doi_registry:
            return MatchResult("matched", doi_registry[doi], "doi_registry_exact", doi)
        return matcher.match_paper(cleaned)
    if target_type == "patent":
        for key in (
            "patent_number",
            "application_number",
            "publication_number",
            "patent_id",
        ):
            number = normalize_patent_number(cleaned.get(key))
            if number and number in patent_registry:
                return MatchResult(
                    "matched",
                    patent_registry[number],
                    "patent_number_registry_exact",
                    number,
                )
        return matcher.match_patent(cleaned)
    return matcher.match_report(cleaned)


def run(
    *,
    dry_run: bool,
    project_id: str | None = None,
    id_prefix: str | None = None,
    limit: int | None = None,
    report_dir: Path | None = None,
    ingest_batch: str | None = None,
) -> dict[str, Any]:
    _configure_milvus_port_from_uri()
    ingest_batch = ingest_batch or datetime.now().strftime(
        "BATCH_%Y%m%d_%H%M%S_PROJECT_ALIGN_MILVUS"
    )
    ingest_time = datetime.now().isoformat(sep=" ", timespec="seconds")
    report = ProjectIngestReport(
        report_dir or Path("/tmp/project-align-reports") / ingest_batch,
        ingest_batch=ingest_batch,
        dry_run=dry_run,
    )

    graph = get_dev_graph_client()
    preflight_graph(graph, relations=True)
    if not dry_run:
        ensure_alignment_edge_schema(graph)
    mysql = get_mysql_client()
    session = mysql.session()
    try:
        dao = ProjectDAO(session)
        projects = _load_project_rows(dao, project_id=project_id, id_prefix=id_prefix, limit=limit)
        allowed_ids = {str(row.id) for row, _s, _t in projects}
        report.increment("projects_scanned", len(projects))
        candidates = collect_match_candidates(dao, projects, id_prefix=id_prefix)
        matcher = ProjectEntityMatcher.from_graph(graph, candidates)

        store = OrganizationMilvusStore(MilvusSettings.from_env())
        org_hybrid = _load_org_matcher(store, entity_type="Organization")
        person_bm25: BM25SparseEncoder | None = None
        person_dense = HashingDenseEncoder(384)
        if store.has_collection("Person"):
            person_state = _state_dir() / f"{store.collection_name('Person')}.bm25.json"
            if person_state.exists():
                person_bm25 = BM25SparseEncoder.load(person_state)
                try:
                    store.load("Person")
                except Exception:  # noqa: BLE001
                    pass
            else:
                logger.warning("Person BM25 state missing at %s", person_state)
        else:
            logger.warning("org_domain_person collection missing; person hybrid skipped")

        milvus = get_milvus_client()
        doi_registry = _build_doi_registry(milvus, "paper")
        patent_registry = _build_patent_number_registry(milvus, "patent")

        for row, _source, table in projects:
            pvid = project_vid(row.id)
            provenance = edge_provenance(
                source_table=table,
                source_record_id=row.id,
                ingest_batch=ingest_batch,
                ingest_time=ingest_time,
            )
            institution = normalize_text(row.funded_institution).rstrip("；;")
            discipline = normalize_text(row.discipline)

            if institution:
                report.increment("organization_candidates")
                result = _align_organization(
                    matcher,
                    org_hybrid,
                    institution,
                    project_id=str(row.id),
                    source_table=table,
                )
                target = _record_match(
                    report,
                    result,
                    "organization",
                    {
                        "project_id": row.id,
                        "field": "funded_institution",
                        "value": institution,
                        "match_method": result.method,
                    },
                )
                if target:
                    props = {
                        **provenance,
                        "funded_amount": float(row.funded_amount or 0),
                        "fund_category": row.fund_category or "",
                        "match_method": result.method or "name_exact",
                        "match_evidence": result.evidence,
                        "confidence": _confidence_from_result(result),
                    }
                    if not dry_run:
                        _merge_edge(graph, pvid, target, "FUNDED_BY", props)
                    report.increment("edges_FUNDED_BY")

            host = normalize_text(row.project_host)
            if host:
                report.increment("person_candidates")
                result = _align_person(
                    matcher,
                    store,
                    person_bm25,
                    person_dense,
                    host,
                    institution=institution,
                    discipline=discipline,
                )
                target = _record_match(
                    report,
                    result,
                    "person",
                    {
                        "project_id": row.id,
                        "field": "project_host",
                        "value": host,
                        "match_method": result.method,
                    },
                )
                if target:
                    props = {
                        **provenance,
                        "match_method": result.method or "name_exact",
                        "match_evidence": result.evidence,
                        "confidence": _confidence_from_result(result),
                    }
                    if not dry_run:
                        _merge_edge(graph, pvid, target, "LEADS", props)
                    report.increment("edges_LEADS")

            for participant in sorted(
                {normalize_text(v) for v in parse_list(row.participants) if normalize_text(v)}
            ):
                report.increment("person_candidates")
                result = _align_person(
                    matcher,
                    store,
                    person_bm25,
                    person_dense,
                    participant,
                    institution=institution,
                    discipline=discipline,
                )
                target = _record_match(
                    report,
                    result,
                    "person",
                    {
                        "project_id": row.id,
                        "field": "participants",
                        "value": participant,
                        "match_method": result.method,
                    },
                )
                if target:
                    props = {
                        **provenance,
                        "match_method": result.method or "name_exact",
                        "match_evidence": result.evidence,
                        "confidence": _confidence_from_result(result),
                    }
                    if not dry_run:
                        _merge_edge(graph, pvid, target, "HAS_PARTICIPANT", props)
                    report.increment("edges_HAS_PARTICIPANT")

        matchers = {
            "paper": "paper",
            "patent": "patent",
            "report": "report",
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
                for out_row in rows:
                    pid = str(out_row.id)
                    if pid not in allowed_ids:
                        continue
                    pvid = project_vid(pid)
                    for field, output_type, target_type in OUTPUT_FIELDS:
                        for item in parse_json_objects(getattr(out_row, field, None)):
                            report.increment(f"{matchers[target_type]}_output_candidates")
                            result = _match_output(
                                matcher,
                                item,
                                target_type,
                                doi_registry=doi_registry,
                                patent_registry=patent_registry,
                            )
                            title, identifier = _output_title(item), _output_identifier(item)
                            target = _record_match(
                                report,
                                result,
                                "output",
                                {
                                    "project_id": pid,
                                    "output_type": output_type,
                                    "target_type": target_type,
                                    "title": title,
                                    "identifier": identifier,
                                    "source_table": table,
                                    "match_method": result.method,
                                },
                            )
                            if not target:
                                continue
                            relation_key = f"{pid}|{output_type}|{target}"
                            props = {
                                "output_type": output_type,
                                "output_title": title,
                                "output_identifier": identifier,
                                "match_method": result.method,
                                "match_evidence": result.evidence,
                                "confidence": 1.0,
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

        summary = report.write()
        logger.info("align summary: %s", summary)
        return summary
    finally:
        session.close()
        close_trs_graph_client()


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--project-id")
    ap.add_argument("--id-prefix")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--report-dir", type=Path)
    ap.add_argument("--ingest-batch")
    return ap.parse_args()


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    args = _parse_args()
    result = run(
        dry_run=args.dry_run,
        project_id=args.project_id,
        id_prefix=args.id_prefix,
        limit=args.limit,
        report_dir=args.report_dir,
        ingest_batch=args.ingest_batch,
    )
    logger.info("result: %s", result)


if __name__ == "__main__":
    main()
