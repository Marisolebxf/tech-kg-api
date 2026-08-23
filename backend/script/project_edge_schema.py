"""Project schema 幂等补列（dev 已有 space 上 ALTER EDGE / TAG ADD）。"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger("script.project_edge_schema")

GRAPH_SPACE = os.getenv("TRS_GRAPH_SPACE", "dev")

# Project 实体置信度字段（与 PROJECT_CONFIDENCE_FIELDS 对应的图属性）。
PROJECT_TAG_ALIGNMENT_PROPS: dict[str, str] = {"confidence": "double"}

# Properties required for match audit + org provenance on existing edges.
EDGE_ALIGNMENT_PROPS: dict[str, dict[str, str]] = {
    "FUNDED_BY": {
        "match_method": "string",
        "match_evidence": "string",
        "confidence": "double",
        "organization_id": "string",
        "organization_source_table": "string",
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
    "HAS_OUTPUT": {
        "match_method": "string",
        "match_evidence": "string",
        "confidence": "double",
    },
}


def ensure_alignment_edge_schema(graph: Any, *, space: str = GRAPH_SPACE) -> None:
    """ALTER EDGE ADD missing match_*/organization_* columns (idempotent)."""
    for edge_type, wanted in EDGE_ALIGNMENT_PROPS.items():
        try:
            described = graph.execute_read(f"USE {space}; DESCRIBE EDGE {edge_type};")
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
            f"USE {space}; ALTER EDGE {edge_type} ADD ("
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
                        graph.execute_read(f"USE {space}; DESCRIBE EDGE {edge_type};"),
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
    # DESCRIBE 可见后，/api/v1/nodes/merge 与 INSERT VERTEX 仍需数秒才接受新列，
    # 否则报 "Unknown column ... in schema"。多等 5s 覆盖该传播延迟。
    time.sleep(5)


def ensure_project_tag_confidence(graph: Any, *, space: str = GRAPH_SPACE) -> None:
    """幂等 ALTER TAG Project ADD 缺失的实体置信度列（如 confidence）。"""
    try:
        described = graph.execute_read(f"USE {space}; DESCRIBE TAG Project;")
    except Exception as exc:  # noqa: BLE001
        logger.warning("DESCRIBE TAG Project failed: %s", exc)
        return
    existing = {
        str(row.get("Field") or row.get("field") or "")
        for row in (getattr(described, "records", None) or [])
    }
    missing = [
        (name, kind) for name, kind in PROJECT_TAG_ALIGNMENT_PROPS.items() if name not in existing
    ]
    if not missing:
        return
    ddl = (
        f"USE {space}; ALTER TAG Project ADD ("
        + ", ".join(f"{name} {kind}" for name, kind in missing)
        + ");"
    )
    logger.info("altering tag schema: %s", ddl)
    graph.execute_write(ddl)
    for attempt in range(15):
        visible = {
            str(row.get("Field") or row.get("field") or "")
            for row in (
                getattr(
                    graph.execute_read(f"USE {space}; DESCRIBE TAG Project;"),
                    "records",
                    None,
                )
                or []
            )
        }
        if {name for name, _ in missing} <= visible:
            break
        if attempt == 14:
            raise RuntimeError("Project tag new properties not visible after ALTER")
        time.sleep(1)
    # DESCRIBE 可见后，/api/v1/nodes/merge 与 INSERT VERTEX 仍需数秒才接受新列，
    # 否则报 "Unknown column ... in schema"。多等 5s 覆盖该传播延迟。
    time.sleep(5)
