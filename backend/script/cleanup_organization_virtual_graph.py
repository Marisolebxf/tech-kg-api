"""Safely inventory and remove organization-domain stub graph data in dev.

The default mode is report-only.  A write requires an explicit cleanup batch and
an identical confirmation token.  Shared nodes or edges without organization
provenance are never deleted.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from infra.graph_db import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings
from script.organization_etl_common import (
    DEFAULT_SPACE,
    DOMAIN_TABLE_BY_NAME,
    RELATION_SPECS,
    chunks,
    clean_text,
    ngql_identifier,
    ngql_literal,
)

STUB_PREFIXES = (
    "org_stub_",
    "organization_stub_",
    "virtual_org_",
    "mock_org_",
    "placeholder_org_",
)
SYNTHETIC_SOURCE_TABLES = frozenset({"mock", "stub", "virtual", "placeholder", "test"})
SYNTHETIC_EXTRA_JSON_MARKERS = (
    "MOCK_ORG",
    "STUB_ORG",
    "VIRTUAL_ORG",
    "PLACEHOLDER_ORG",
    "TEST_ORG",
)


@dataclass(frozen=True)
class CleanupEdge:
    edge_type: str
    source_vid: str
    target_vid: str
    rank: int
    source_table: str | None
    properties: Any = None


@dataclass(frozen=True)
class CleanupVertex:
    vid: str
    source_table: str | None
    properties: Any = None


@dataclass(frozen=True)
class CleanupTag:
    tag: str
    vid: str
    source_table: str | None
    properties: Any = None


def _rank(value: Any) -> int:
    return int(value if isinstance(value, int) else clean_text(value) or "0")


def _properties(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, Mapping) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def collect_stub_vertices(graph: TRSGraphClient) -> list[CleanupVertex]:
    conditions = " OR ".join(
        f"id(v) STARTS WITH {ngql_literal(prefix)}" for prefix in STUB_PREFIXES
    )
    query = (
        "MATCH (v:`Organization`) WHERE " + conditions + " "
        "RETURN id(v) AS vid,v.Organization.source_table AS source_table,"
        "properties(v) AS properties;"
    )
    result = graph.execute_read(query)
    return [
        CleanupVertex(
            vid=clean_text(row.get("vid")) or "",
            source_table=clean_text(row.get("source_table")),
            properties=row.get("properties"),
        )
        for row in result.records
        if clean_text(row.get("vid")) is not None
    ]


def collect_incident_edges(
    graph: TRSGraphClient, vertices: Sequence[CleanupVertex], *, batch_size: int = 200
) -> list[CleanupEdge]:
    edges: dict[tuple[str, str, str, int], CleanupEdge] = {}
    for batch in chunks(vertices, batch_size):
        vids = ",".join(ngql_literal(item.vid) for item in batch)
        query = (
            "MATCH (s)-[e]->(t) "
            f"WHERE id(s) IN [{vids}] OR id(t) IN [{vids}] "
            "RETURN type(e) AS edge_type,id(s) AS source_vid,id(t) AS target_vid,"
            "rank(e) AS edge_rank,properties(e) AS properties;"
        )
        for row in graph.execute_read(query).records:
            properties = row.get("properties")
            edge = CleanupEdge(
                edge_type=clean_text(row.get("edge_type")) or "",
                source_vid=clean_text(row.get("source_vid")) or "",
                target_vid=clean_text(row.get("target_vid")) or "",
                rank=_rank(row.get("edge_rank")),
                source_table=clean_text(_properties(properties).get("source_table")),
                properties=properties,
            )
            if edge.edge_type and edge.source_vid and edge.target_vid:
                edges[(edge.edge_type, edge.source_vid, edge.target_vid, edge.rank)] = edge
    return list(edges.values())


def _synthetic_extra_json_condition(reference: str) -> str:
    return " OR ".join(
        f"{reference}.extra_json CONTAINS {ngql_literal(marker)}"
        for marker in SYNTHETIC_EXTRA_JSON_MARKERS
    )


def collect_synthetic_tags(graph: TRSGraphClient) -> list[CleanupTag]:
    """Find organization tags whose persisted source payload is explicitly synthetic."""
    tags: dict[tuple[str, str], CleanupTag] = {}
    available = set(graph.labels())
    for tag in ("Organization", "organization_base", "Person", "News", "Event", "Product"):
        if tag not in available:
            continue
        ident = ngql_identifier(tag)
        reference = f"v.{ident}"
        query = (
            f"MATCH (v:{ident}) WHERE {_synthetic_extra_json_condition(reference)} "
            f"RETURN id(v) AS vid,{reference}.source_table AS source_table,"
            "properties(v) AS properties;"
        )
        for row in graph.execute_read(query).records:
            vid = clean_text(row.get("vid"))
            if vid is None:
                continue
            item = CleanupTag(
                tag=tag,
                vid=vid,
                source_table=clean_text(row.get("source_table")),
                properties=row.get("properties"),
            )
            tags[(tag, vid)] = item
    return list(tags.values())


def collect_synthetic_edges(graph: TRSGraphClient) -> list[CleanupEdge]:
    """Find explicitly labelled virtual relations even when neither endpoint is a stub."""
    source_values = sorted(
        SYNTHETIC_SOURCE_TABLES | {value.upper() for value in SYNTHETIC_SOURCE_TABLES}
    )
    sources = ",".join(ngql_literal(value) for value in source_values)
    edges: dict[tuple[str, str, str, int], CleanupEdge] = {}
    available = set(graph.edge_types())
    for edge_type in sorted({spec.edge_type for spec in RELATION_SPECS} & available):
        ident = ngql_identifier(edge_type)
        extra_condition = _synthetic_extra_json_condition("e")
        query = (
            f"MATCH (s)-[e:{ident}]->(t) WHERE "
            f"e.source_table IN [{sources}] OR {extra_condition} "
            "RETURN type(e) AS edge_type,id(s) AS source_vid,id(t) AS target_vid,"
            "rank(e) AS edge_rank,properties(e) AS properties;"
        )
        for row in graph.execute_read(query).records:
            properties = row.get("properties")
            edge = CleanupEdge(
                edge_type=clean_text(row.get("edge_type")) or edge_type,
                source_vid=clean_text(row.get("source_vid")) or "",
                target_vid=clean_text(row.get("target_vid")) or "",
                rank=_rank(row.get("edge_rank")),
                source_table=clean_text(_properties(properties).get("source_table")),
                properties=properties,
            )
            if edge.source_vid and edge.target_vid:
                edges[(edge.edge_type, edge.source_vid, edge.target_vid, edge.rank)] = edge
    return list(edges.values())


def _owned_edge(edge: CleanupEdge) -> bool:
    source = (edge.source_table or "").casefold()
    return source in DOMAIN_TABLE_BY_NAME or source in SYNTHETIC_SOURCE_TABLES


def build_cleanup_plan(graph: TRSGraphClient) -> dict[str, Any]:
    vertices = collect_stub_vertices(graph)
    synthetic_tags = collect_synthetic_tags(graph)
    incident = collect_incident_edges(graph, vertices)
    synthetic = collect_synthetic_edges(graph)
    all_edges = {
        (edge.edge_type, edge.source_vid, edge.target_vid, edge.rank): edge
        for edge in (*incident, *synthetic)
    }
    blocking_vids = {
        vid
        for edge in incident
        if not _owned_edge(edge)
        for vid in (edge.source_vid, edge.target_vid)
    }
    deletable_edges = [edge for edge in all_edges.values() if _owned_edge(edge)]
    deletable_vertices = [item for item in vertices if item.vid not in blocking_vids]
    blocked_vertices = [item for item in vertices if item.vid in blocking_vids]
    return {
        "domain": "domestic_and_foreign_organization",
        "space": DEFAULT_SPACE,
        "stubPrefixes": list(STUB_PREFIXES),
        "deletableEdges": [asdict(item) for item in deletable_edges],
        "deletableTags": [asdict(item) for item in synthetic_tags],
        "deletableVertices": [asdict(item) for item in deletable_vertices],
        "blockedVertices": [asdict(item) for item in blocked_vertices],
        "blockedReason": "incident edge has no organization-domain provenance",
    }


def execute_cleanup(graph: TRSGraphClient, plan: dict[str, Any]) -> dict[str, int]:
    deleted_edges = 0
    deleted_tags = 0
    deleted_vertices = 0
    for raw in plan["deletableEdges"]:
        query = (
            f"DELETE EDGE {ngql_identifier(raw['edge_type'])} "
            f"{ngql_literal(raw['source_vid'])}->{ngql_literal(raw['target_vid'])}"
            f"@{int(raw['rank'])};"
        )
        graph.execute_write(query)
        deleted_edges += 1
    for raw in plan["deletableTags"]:
        graph.execute_write(
            "DELETE TAG {} FROM {};".format(ngql_identifier(raw["tag"]), ngql_literal(raw["vid"]))
        )
        deleted_tags += 1
    for raw in plan["deletableVertices"]:
        # No WITH EDGE: a vertex that still has a shared edge must fail closed.
        graph.execute_write(f"DELETE VERTEX {ngql_literal(raw['vid'])};")
        deleted_vertices += 1
    return {
        "deletedEdges": deleted_edges,
        "deletedTags": deleted_tags,
        "deletedVertices": deleted_vertices,
    }


def run(
    *,
    dry_run: bool = True,
    cleanup_batch: str | None = None,
    confirm_batch: str | None = None,
    report_path: str | Path | None = None,
    graph: TRSGraphClient | None = None,
) -> dict[str, Any]:
    if graph is None:
        settings = TRSGraphSettings.from_env().model_copy(update={"space": DEFAULT_SPACE})
        client = TRSGraphClient(settings)
        client.connect()
    else:
        client = graph
    plan = build_cleanup_plan(client)
    batch = cleanup_batch or f"ORG_CLEAN_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    result: dict[str, Any] = {"batch": batch, "dryRun": dry_run, "plan": plan}
    if not dry_run:
        if not cleanup_batch or confirm_batch != cleanup_batch:
            raise ValueError("write mode requires matching --cleanup-batch and --confirm-batch")
        result["deleted"] = execute_cleanup(client, plan)
    path = (
        Path(report_path)
        if report_path
        else Path("var/reports/organization") / f"{batch}_cleanup.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["reportPath"] = str(path.resolve())
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", dest="dry_run", action="store_true")
    mode.add_argument("--write", dest="dry_run", action="store_false")
    parser.set_defaults(dry_run=True)
    parser.add_argument("--space", choices=(DEFAULT_SPACE,), default=DEFAULT_SPACE)
    parser.add_argument("--cleanup-batch")
    parser.add_argument("--confirm-batch")
    parser.add_argument("--report-path")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run(
        dry_run=args.dry_run,
        cleanup_batch=args.cleanup_batch,
        confirm_batch=args.confirm_batch,
        report_path=args.report_path,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
