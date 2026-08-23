"""Acceptance snapshots and durable reports for the organization domain only."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from infra.graph_db import TRSGraphClient
from script.organization_etl_common import (
    DOMAIN_TABLE_BY_NAME,
    RELATION_SPECS,
    ngql_identifier,
    ngql_literal,
)

OWNED_TAGS = ("Organization", "organization_base", "Person", "News", "Event", "Product")
OWNED_EDGE_TYPES = tuple(sorted({spec.edge_type for spec in RELATION_SPECS}))


def _number(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _first_record(graph: TRSGraphClient, query: str) -> dict[str, Any]:
    result = graph.execute_read(query)
    return dict(result.records[0]) if result.records else {}


def collect_graph_snapshot(graph: TRSGraphClient) -> dict[str, Any]:
    """Collect organization-owned coverage without counting other domains."""
    tables = ",".join(ngql_literal(name) for name in sorted(DOMAIN_TABLE_BY_NAME))
    available_tags = set(graph.labels())
    available_edges = set(graph.edge_types())
    snapshot: dict[str, Any] = {
        "tags": {},
        "edges": {},
        "virtual": {"stubVertices": 0, "syntheticEdges": 0},
        "errors": [],
    }
    for tag in OWNED_TAGS:
        if tag not in available_tags:
            snapshot["tags"][tag] = {
                "total": 0,
                "confidenceCount": 0,
                "organizationIdCount": 0,
            }
            continue
        ident = ngql_identifier(tag)
        query = (
            f"MATCH (v:{ident}) WHERE v.{ident}.source_table IN [{tables}] "
            f"RETURN count(v) AS total,count(v.{ident}.confidence) AS confidence_count,"
            f"count(v.{ident}.organization_id) AS organization_id_count;"
        )
        try:
            row = _first_record(graph, query)
            snapshot["tags"][tag] = {
                "total": _number(row.get("total")),
                "confidenceCount": _number(row.get("confidence_count")),
                "organizationIdCount": _number(row.get("organization_id_count")),
            }
        except Exception as exc:
            snapshot["errors"].append(f"tag {tag}: {exc}")
    stub_conditions = " OR ".join(
        f"id(v) STARTS WITH {ngql_literal(prefix)}"
        for prefix in (
            "org_stub_",
            "organization_stub_",
            "virtual_org_",
            "mock_org_",
            "placeholder_org_",
        )
    )
    if "Organization" in available_tags:
        try:
            row = _first_record(
                graph,
                "MATCH (v:`Organization`) WHERE " + stub_conditions + " RETURN count(v) AS total;",
            )
            snapshot["virtual"]["stubVertices"] = _number(row.get("total"))
        except Exception as exc:
            snapshot["errors"].append(f"stub vertices: {exc}")

    synthetic_sources = ",".join(
        ngql_literal(value)
        for value in (
            "mock",
            "stub",
            "virtual",
            "placeholder",
            "test",
            "MOCK",
            "STUB",
            "VIRTUAL",
            "PLACEHOLDER",
            "TEST",
        )
    )
    for edge_type in OWNED_EDGE_TYPES:
        if edge_type not in available_edges:
            snapshot["edges"][edge_type] = {
                "total": 0,
                "confidenceCount": 0,
                "organizationIdCount": 0,
            }
            continue
        ident = ngql_identifier(edge_type)
        query = (
            f"MATCH ()-[e:{ident}]->() WHERE e.source_table IN [{tables}] "
            "RETURN count(e) AS total,count(e.confidence) AS confidence_count,"
            "count(e.organization_id) AS organization_id_count;"
        )
        try:
            row = _first_record(graph, query)
            snapshot["edges"][edge_type] = {
                "total": _number(row.get("total")),
                "confidenceCount": _number(row.get("confidence_count")),
                "organizationIdCount": _number(row.get("organization_id_count")),
            }
            synthetic = _first_record(
                graph,
                f"MATCH ()-[e:{ident}]->() WHERE e.source_table IN [{synthetic_sources}] "
                "RETURN count(e) AS total;",
            )
            snapshot["virtual"]["syntheticEdges"] += _number(synthetic.get("total"))
        except Exception as exc:
            snapshot["errors"].append(f"edge {edge_type}: {exc}")
    return snapshot


def _coverage(items: Mapping[str, Mapping[str, Any]], field: str) -> tuple[int, int, float]:
    total = sum(_number(item.get("total")) for item in items.values())
    covered = sum(_number(item.get(field)) for item in items.values())
    return covered, total, round(covered / total, 6) if total else 1.0


def _delta(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for kind in ("tags", "edges"):
        result[kind] = {}
        names = set(before.get(kind, {})) | set(after.get(kind, {}))
        for name in sorted(names):
            old = _number(before.get(kind, {}).get(name, {}).get("total"))
            new = _number(after.get(kind, {}).get(name, {}).get("total"))
            result[kind][name] = new - old
    result["virtual"] = {
        name: _number(after.get("virtual", {}).get(name))
        - _number(before.get("virtual", {}).get(name))
        for name in ("stubVertices", "syntheticEdges")
    }
    return result


def write_acceptance_report(
    *,
    batch: str,
    workflow_result: Mapping[str, Any],
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    output_dir: str | Path | None = None,
) -> dict[str, str]:
    """Write machine-readable and review-friendly organization acceptance reports."""
    root = Path(
        output_dir
        or os.getenv("ORGANIZATION_REPORT_DIR")
        or Path(__file__).resolve().parents[1] / "var" / "reports" / "organization"
    )
    root.mkdir(parents=True, exist_ok=True)
    safe_batch = "".join(ch if ch.isalnum() or ch in "_-" else "-" for ch in batch)
    json_path = root / f"{safe_batch}_acceptance.json"
    markdown_path = root / f"{safe_batch}_acceptance.md"
    entity_conf = _coverage(after.get("tags", {}), "confidenceCount")
    entity_org = _coverage(after.get("tags", {}), "organizationIdCount")
    edge_conf = _coverage(after.get("edges", {}), "confidenceCount")
    edge_org = _coverage(after.get("edges", {}), "organizationIdCount")
    report = {
        "domain": "domestic_and_foreign_organization",
        "space": os.getenv("TRS_GRAPH_SPACE", "dev"),
        "batch": batch,
        "generatedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "before": before,
        "after": after,
        "delta": _delta(before, after),
        "coverage": {
            "entityConfidence": entity_conf,
            "entityOrganizationId": entity_org,
            "relationConfidence": edge_conf,
            "relationOrganizationId": edge_org,
        },
        "workflow": dict(workflow_result),
    }
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# 国内外机构图谱批次验收报告",
        "",
        "- 图空间：{}".format(os.getenv("TRS_GRAPH_SPACE", "dev")),
        f"- 批次：{batch}",
        f"- 实体 confidence 覆盖：{entity_conf[0]}/{entity_conf[1]} ({entity_conf[2]:.2%})",
        f"- 实体 organization_id 覆盖：{entity_org[0]}/{entity_org[1]} ({entity_org[2]:.2%})",
        f"- 关系 confidence 覆盖：{edge_conf[0]}/{edge_conf[1]} ({edge_conf[2]:.2%})",
        f"- 关系 organization_id 覆盖：{edge_org[0]}/{edge_org[1]} ({edge_org[2]:.2%})",
        f"- 桩节点：{after.get('virtual', {}).get('stubVertices', 0)}",
        f"- 明确虚拟关系：{after.get('virtual', {}).get('syntheticEdges', 0)}",
        "",
        "## 数量变化",
        "",
        "```json",
        json.dumps(report["delta"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## 工作流统计",
        "",
        "```json",
        json.dumps(report["workflow"], ensure_ascii=False, indent=2),
        "```",
    ]
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path)}
