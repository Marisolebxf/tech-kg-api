"""Persist relation extraction results into TRS Graph in the background."""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Any

from graph_db import GraphDBConfig, connect
from graph_db.base import GraphDatabase

logger = logging.getLogger(__name__)


RELATION_EXTRACTION_SCHEMA_NGQLS: list[str] = [
    "CREATE TAG IF NOT EXISTS relation_extraction_job (job_id string, method string, source_type string, source_hash string, source_text string, entity_count string, relation_count string, status string, created_at string, started_at string, finished_at string, error_message string)",
    "CREATE TAG IF NOT EXISTS relation_extracted_entity (entity_id string, entity_text string, entity_type string, source_type string, source_hash string, job_id string, entity_order string, status string, extracted_at string, raw_entity_id string)",
    "CREATE EDGE IF NOT EXISTS relation_extraction_has_entity (source_type string, source_hash string, entity_order string, extracted_at string)",
    "CREATE EDGE IF NOT EXISTS relation_extracted_edge (relation_id string, relation_type string, confidence string, source string, source_type string, source_hash string, job_id string, extracted_at string, relation_order string, head_text string, head_type string, tail_text string, tail_type string, source_text string)",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def _chunked(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


class RelationExtractionGraphWriter:
    """Write extracted relations into TRS Graph."""

    def __init__(self, db: GraphDatabase):
        self.db = db

    def ensure_schema(self) -> None:
        for ngql in RELATION_EXTRACTION_SCHEMA_NGQLS:
            try:
                self.db.execute_write(ngql)
            except Exception as exc:  # pragma: no cover - schema may already exist or backend may reject repeated DDL
                logger.warning("Ensure relation extraction schema failed: %s", exc)

    def persist(
        self,
        *,
        task_id: str,
        method: str,
        source_text: str,
        entities: list[dict[str, Any]],
        relations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.ensure_schema()

        normalized_text = _normalize_text(source_text or "")
        source_hash = _short_hash(f"relation|{method}|{normalized_text}")
        now = _utc_now()
        job_node_id = task_id
        entity_written = 0
        relation_written = 0
        batch_size = max(1, int(os.getenv("GRAPH_BATCH_SIZE", "200")))
        try:
            self.db.merge_node(
                labels=["relation_extraction_job"],
                identity_props={"vid": job_node_id},
                properties={
                    "job_id": job_node_id,
                    "method": method,
                    "source_type": "relation",
                    "source_hash": source_hash,
                    "source_text": normalized_text[:4000],
                    "entity_count": str(len(entities)),
                    "relation_count": str(len(relations)),
                    "status": "running",
                    "created_at": now,
                    "started_at": now,
                    "finished_at": "",
                    "error_message": "",
                },
            )

            entity_id_map: dict[tuple[str, str], str] = {}
            entity_nodes: list[dict[str, Any]] = []
            has_entity_edges: list[dict[str, Any]] = []
            relation_edges: list[dict[str, Any]] = []

            for index, entity in enumerate(entities, start=1):
                entity_text = _normalize_text(str(entity.get("text") or ""))
                entity_type = _normalize_text(str(entity.get("label") or entity.get("type") or "UNKNOWN")) or "UNKNOWN"
                raw_entity_id = _normalize_text(str(entity.get("id") or f"E{index}"))
                key = (entity_text, entity_type)
                if key in entity_id_map:
                    continue

                entity_id = _short_hash(f"relation|{source_hash}|{entity_type}|{entity_text}")
                entity_id_map[key] = entity_id
                entity_nodes.append(
                    {
                        "vid": entity_id,
                        "entity_id": entity_id,
                        "entity_text": entity_text,
                        "entity_type": entity_type,
                        "source_type": "relation",
                        "source_hash": source_hash,
                        "job_id": job_node_id,
                        "entity_order": str(index),
                        "status": "extracted",
                        "extracted_at": now,
                        "raw_entity_id": raw_entity_id,
                    }
                )
                has_entity_edges.append(
                    {
                        "source_id": job_node_id,
                        "target_id": entity_id,
                        "source_type": "relation",
                        "source_hash": source_hash,
                        "entity_order": str(index),
                        "extracted_at": now,
                    }
                )

            for index, relation in enumerate(relations, start=1):
                head = relation.get("head") or {}
                tail = relation.get("tail") or {}
                head_text = _normalize_text(str(head.get("text") or ""))
                tail_text = _normalize_text(str(tail.get("text") or ""))
                head_type = _normalize_text(str(head.get("label") or head.get("type") or "UNKNOWN")) or "UNKNOWN"
                tail_type = _normalize_text(str(tail.get("label") or tail.get("type") or "UNKNOWN")) or "UNKNOWN"
                relation_type = _normalize_text(str(relation.get("relation") or "UNKNOWN")) or "UNKNOWN"
                confidence = relation.get("confidence", 1.0)
                source = _normalize_text(str(relation.get("source") or method or "unknown")) or "unknown"
                relation_id = _short_hash(
                    f"relation|{source_hash}|{head_text}|{relation_type}|{tail_text}|{index}"
                )

                head_key = (head_text, head_type)
                tail_key = (tail_text, tail_type)

                head_entity_id = entity_id_map.get(head_key)
                if head_entity_id is None:
                    head_entity_id = _short_hash(f"relation|{source_hash}|{head_type}|{head_text}")
                    entity_id_map[head_key] = head_entity_id
                    entity_nodes.append(
                        {
                            "vid": head_entity_id,
                            "entity_id": head_entity_id,
                            "entity_text": head_text,
                            "entity_type": head_type,
                            "source_type": "relation",
                            "source_hash": source_hash,
                            "job_id": job_node_id,
                            "entity_order": str(len(entity_id_map)),
                            "status": "extracted",
                            "extracted_at": now,
                            "raw_entity_id": "",
                        }
                    )
                    has_entity_edges.append(
                        {
                            "source_id": job_node_id,
                            "target_id": head_entity_id,
                            "source_type": "relation",
                            "source_hash": source_hash,
                            "entity_order": str(len(entity_id_map)),
                            "extracted_at": now,
                        }
                    )

                tail_entity_id = entity_id_map.get(tail_key)
                if tail_entity_id is None:
                    tail_entity_id = _short_hash(f"relation|{source_hash}|{tail_type}|{tail_text}")
                    entity_id_map[tail_key] = tail_entity_id
                    entity_nodes.append(
                        {
                            "vid": tail_entity_id,
                            "entity_id": tail_entity_id,
                            "entity_text": tail_text,
                            "entity_type": tail_type,
                            "source_type": "relation",
                            "source_hash": source_hash,
                            "job_id": job_node_id,
                            "entity_order": str(len(entity_id_map)),
                            "status": "extracted",
                            "extracted_at": now,
                            "raw_entity_id": "",
                        }
                    )
                    has_entity_edges.append(
                        {
                            "source_id": job_node_id,
                            "target_id": tail_entity_id,
                            "source_type": "relation",
                            "source_hash": source_hash,
                            "entity_order": str(len(entity_id_map)),
                            "extracted_at": now,
                        }
                    )

                relation_edges.append(
                    {
                        "source_id": head_entity_id,
                        "target_id": tail_entity_id,
                        "relation_id": relation_id,
                        "relation_type": relation_type,
                        "confidence": str(confidence),
                        "source": source,
                        "source_type": "relation",
                        "source_hash": source_hash,
                        "job_id": job_node_id,
                        "extracted_at": now,
                        "relation_order": str(index),
                        "head_text": head_text,
                        "head_type": head_type,
                        "tail_text": tail_text,
                        "tail_type": tail_type,
                        "source_text": normalized_text[:4000],
                    }
                )

            for chunk in _chunked(entity_nodes, batch_size):
                try:
                    self.db.batch_create_nodes(chunk, ["relation_extracted_entity"])
                    entity_written += len(chunk)
                except Exception as exc:
                    logger.warning("Batch create relation extracted entities failed, falling back to merge loop: %s", exc)
                    for entity_props in chunk:
                        try:
                            self.db.merge_node(
                                labels=["relation_extracted_entity"],
                                identity_props={"vid": str(entity_props.get("vid", ""))},
                                properties=dict(entity_props),
                            )
                            entity_written += 1
                        except Exception as item_exc:
                            logger.warning("Failed to persist relation extracted entity %s: %s", entity_props.get("vid", ""), item_exc)

            for chunk in _chunked(has_entity_edges, batch_size):
                try:
                    self.db.batch_create_edges(chunk, "relation_extraction_has_entity")
                except Exception as exc:
                    logger.warning("Batch create relation extraction entity edges failed, falling back to single writes: %s", exc)
                    for edge_props in chunk:
                        try:
                            self.db.create_edge(
                                source_id=edge_props["source_id"],
                                target_id=edge_props["target_id"],
                                edge_type="relation_extraction_has_entity",
                                properties={
                                    "source_type": edge_props["source_type"],
                                    "source_hash": edge_props["source_hash"],
                                    "entity_order": edge_props["entity_order"],
                                    "extracted_at": edge_props["extracted_at"],
                                },
                            )
                        except Exception as item_exc:
                            logger.warning(
                                "Failed to persist relation extraction entity edge %s->%s: %s",
                                edge_props["source_id"],
                                edge_props["target_id"],
                                item_exc,
                            )

            for chunk in _chunked(relation_edges, batch_size):
                try:
                    self.db.batch_create_edges(chunk, "relation_extracted_edge")
                    relation_written += len(chunk)
                except Exception as exc:
                    logger.warning("Batch create relation edges failed, falling back to single writes: %s", exc)
                    for edge_props in chunk:
                        try:
                            self.db.create_edge(
                                source_id=edge_props["source_id"],
                                target_id=edge_props["target_id"],
                                edge_type="relation_extracted_edge",
                                properties={
                                    "relation_id": edge_props["relation_id"],
                                    "relation_type": edge_props["relation_type"],
                                    "confidence": edge_props["confidence"],
                                    "source": edge_props["source"],
                                    "source_type": edge_props["source_type"],
                                    "source_hash": edge_props["source_hash"],
                                    "job_id": edge_props["job_id"],
                                    "extracted_at": edge_props["extracted_at"],
                                    "relation_order": edge_props["relation_order"],
                                    "head_text": edge_props["head_text"],
                                    "head_type": edge_props["head_type"],
                                    "tail_text": edge_props["tail_text"],
                                    "tail_type": edge_props["tail_type"],
                                    "source_text": edge_props["source_text"],
                                },
                            )
                            relation_written += 1
                        except Exception as item_exc:
                            logger.warning(
                                "Failed to persist relation edge %s->%s: %s",
                                edge_props["source_id"],
                                edge_props["target_id"],
                                item_exc,
                            )

            finished_at = _utc_now()
            self.db.merge_node(
                labels=["relation_extraction_job"],
                identity_props={"vid": job_node_id},
                properties={
                    "job_id": job_node_id,
                    "method": method,
                    "source_type": "relation",
                    "source_hash": source_hash,
                    "source_text": normalized_text[:4000],
                    "entity_count": str(len(entities)),
                    "relation_count": str(len(relations)),
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
                "relation_written": relation_written,
                "finished_at": finished_at,
            }
        except Exception as exc:
            failed_at = _utc_now()
            try:
                self.db.merge_node(
                    labels=["relation_extraction_job"],
                    identity_props={"vid": job_node_id},
                    properties={
                        "job_id": job_node_id,
                        "method": method,
                        "source_type": "relation",
                        "source_hash": source_hash,
                        "source_text": normalized_text[:4000],
                        "entity_count": str(len(entities)),
                        "relation_count": str(len(relations)),
                        "status": "failed",
                        "created_at": now,
                        "started_at": now,
                        "finished_at": failed_at,
                        "error_message": str(exc)[:2000],
                    },
                )
            except Exception as update_exc:  # pragma: no cover - best effort only
                logger.warning("Failed to mark relation extraction job as failed: %s", update_exc)
            raise


def persist_relation_extraction_job(
    *,
    task_id: str,
    method: str,
    source_text: str,
    entities: list[dict[str, Any]],
    relations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Background-safe helper used by the router task."""
    db = None
    try:
        db = connect(GraphDBConfig.from_env(prefix="GRAPH_DB"))
        writer = RelationExtractionGraphWriter(db)
        return writer.persist(
            task_id=task_id,
            method=method,
            source_text=source_text,
            entities=entities,
            relations=relations,
        )
    finally:
        if db is not None:
            db.close()
