"""Persist entity extraction results into TRS Graph in the background."""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Any

from graph_db import GraphDBConfig, connect
from graph_db.base import GraphDatabase

logger = logging.getLogger(__name__)


EXTRACTION_SCHEMA_NGQLS: list[str] = [
    "CREATE TAG IF NOT EXISTS extraction_job (job_id string, source_type string, source_hash string, source_text string, entity_count string, status string, created_at string, started_at string, finished_at string, error_message string)",
    "CREATE TAG IF NOT EXISTS extracted_entity (entity_id string, entity_text string, entity_type string, source_type string, source_hash string, job_id string, entity_order string, status string, extracted_at string, raw_entity_id string)",
    "CREATE EDGE IF NOT EXISTS extraction_has_entity (source_type string, source_hash string, entity_order string, extracted_at string)",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def _chunked(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


class ExtractionGraphWriter:
    """Write extracted entities into TRS Graph."""

    def __init__(self, db: GraphDatabase):
        self.db = db

    def ensure_schema(self) -> None:
        for ngql in EXTRACTION_SCHEMA_NGQLS:
            try:
                self.db.execute_write(ngql)
            except Exception as exc:  # pragma: no cover - schema may already exist or backend may reject repeated DDL
                logger.warning("Ensure extraction schema failed: %s", exc)

    def persist(
        self,
        *,
        task_id: str,
        source_type: str,
        source_text: str,
        entities: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.ensure_schema()

        normalized_text = _normalize_text(source_text or "")
        source_hash = _short_hash(f"{source_type}|{normalized_text}")
        now = _utc_now()
        job_node_id = task_id
        entity_written = 0
        batch_size = max(1, int(os.getenv("GRAPH_BATCH_SIZE", "200")))

        self.db.merge_node(
            labels=["extraction_job"],
            identity_props={"vid": job_node_id},
            properties={
                "job_id": job_node_id,
                "source_type": source_type,
                "source_hash": source_hash,
                "source_text": normalized_text[:4000],
                "entity_count": str(len(entities)),
                "status": "running",
                "created_at": now,
                "started_at": now,
                "finished_at": "",
                "error_message": "",
            },
        )

        entity_nodes: list[dict[str, Any]] = []
        entity_edges: list[dict[str, Any]] = []
        for index, entity in enumerate(entities, start=1):
            entity_text = _normalize_text(str(entity.get("text") or ""))
            entity_type = _normalize_text(str(entity.get("type") or "Other")) or "Other"
            raw_entity_id = _normalize_text(str(entity.get("id") or f"E{index}"))
            entity_id = _short_hash(f"{source_type}|{source_hash}|{entity_type}|{entity_text}")
            entity_nodes.append(
                {
                    "vid": entity_id,
                    "entity_id": entity_id,
                    "entity_text": entity_text,
                    "entity_type": entity_type,
                    "source_type": source_type,
                    "source_hash": source_hash,
                    "job_id": job_node_id,
                    "entity_order": str(index),
                    "status": "extracted",
                    "extracted_at": now,
                    "raw_entity_id": raw_entity_id,
                }
            )
            entity_edges.append(
                {
                    "source_id": job_node_id,
                    "target_id": entity_id,
                    "source_type": source_type,
                    "source_hash": source_hash,
                    "entity_order": str(index),
                    "extracted_at": now,
                }
            )

        for chunk in _chunked(entity_nodes, batch_size):
            try:
                self.db.batch_create_nodes(chunk, ["extracted_entity"])
                entity_written += len(chunk)
            except Exception as exc:
                logger.warning("Batch create extracted entities failed, falling back to merge loop: %s", exc)
                for entity_props in chunk:
                    try:
                        vid = str(entity_props.get("vid", ""))
                        self.db.merge_node(
                            labels=["extracted_entity"],
                            identity_props={"vid": vid},
                            properties=dict(entity_props),
                        )
                        entity_written += 1
                    except Exception as item_exc:
                        logger.warning("Failed to persist extracted entity %s: %s", entity_props.get("vid", ""), item_exc)

        for chunk in _chunked(entity_edges, batch_size):
            try:
                self.db.batch_create_edges(chunk, "extraction_has_entity")
            except Exception as exc:
                logger.warning("Batch create extraction edges failed, falling back to single writes: %s", exc)
                for edge_props in chunk:
                    try:
                        self.db.create_edge(
                            source_id=edge_props["source_id"],
                            target_id=edge_props["target_id"],
                            edge_type="extraction_has_entity",
                            properties={
                                "source_type": edge_props["source_type"],
                                "source_hash": edge_props["source_hash"],
                                "entity_order": edge_props["entity_order"],
                                "extracted_at": edge_props["extracted_at"],
                            },
                        )
                    except Exception as item_exc:
                        logger.warning(
                            "Failed to persist extraction edge %s->%s: %s",
                            edge_props["source_id"],
                            edge_props["target_id"],
                            item_exc,
                        )

        finished_at = _utc_now()
        self.db.merge_node(
            labels=["extraction_job"],
            identity_props={"vid": job_node_id},
            properties={
                "job_id": job_node_id,
                "source_type": source_type,
                "source_hash": source_hash,
                "source_text": normalized_text[:4000],
                "entity_count": str(len(entities)),
                "status": "succeeded",
                "created_at": now,
                "started_at": now,
                "finished_at": finished_at,
                "error_message": "",
            },
        )

        return {
            "job_node_id": job_node_id,
            "source_hash": source_hash,
            "entity_written": entity_written,
            "finished_at": finished_at,
        }


def persist_extraction_job(
    *,
    task_id: str,
    source_type: str,
    source_text: str,
    entities: list[dict[str, Any]],
) -> dict[str, Any]:
    """Background-safe helper used by the router task."""
    db = None
    try:
        db = connect(GraphDBConfig.from_env(prefix="GRAPH_DB"))
        writer = ExtractionGraphWriter(db)
        return writer.persist(
            task_id=task_id,
            source_type=source_type,
            source_text=source_text,
            entities=entities,
        )
    finally:
        if db is not None:
            db.close()
