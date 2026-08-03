"""Milvus helpers shared by organization-domain and Project-domain scripts.

- ``OrganizationMilvusStore`` — org-domain collections (legacy ``connections`` API).
- ``get_milvus_client`` — process-level ``MilvusClient`` for flat collections
  (``project`` / ``paper`` / …), same style as scholar/paper feature branches.

``pymilvus`` is imported lazily so ordinary API processes do not connect on import.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_DEFAULT_DB = "default"
_DEFAULT_TIMEOUT = 30

_client_lock = threading.Lock()
_client: Any = None


def _host_port_from_env() -> tuple[str, int]:
    """Resolve host/port from ``MILVUS_URI`` or ``MILVUS_HOST`` / ``MILVUS_PORT``."""
    uri = os.environ.get("MILVUS_URI")
    if uri:
        parsed = urlparse(uri)
        if parsed.hostname:
            return parsed.hostname, int(parsed.port or 19530)
    return (
        os.environ.get("MILVUS_HOST", "127.0.0.1"),
        int(os.environ.get("MILVUS_PORT", "19530")),
    )


@dataclass(frozen=True)
class MilvusSettings:
    """Connection and collection settings for organization-domain indexes."""

    host: str = "127.0.0.1"
    port: int = 19530
    alias: str = "organization_domain"
    collection_prefix: str = "org_domain"
    consistency_level: str = "Strong"

    @classmethod
    def from_env(cls) -> MilvusSettings:
        host, port = _host_port_from_env()
        return cls(
            host=host,
            port=port,
            alias=os.environ.get("ORG_MILVUS_CONNECTION_ALIAS", "organization_domain"),
            collection_prefix=os.environ.get("ORG_MILVUS_COLLECTION_PREFIX", "org_domain"),
            consistency_level=os.environ.get("ORG_MILVUS_CONSISTENCY", "Strong"),
        )


@dataclass(frozen=True)
class MilvusSearchHit:
    """One normalized Milvus hybrid-search result."""

    vid: str
    score: float
    fields: dict[str, Any]


class OrganizationMilvusStore:
    """Create, populate and query per-entity organization-domain collections."""

    def __init__(self, settings: MilvusSettings | None = None) -> None:
        self.settings = settings or MilvusSettings.from_env()
        self._connected = False

    def collection_name(self, entity_type: str) -> str:
        safe = entity_type.strip().casefold().replace("-", "_")
        if not safe.replace("_", "").isalnum():
            raise ValueError(f"unsafe entity type for Milvus collection: {entity_type!r}")
        return f"{self.settings.collection_prefix}_{safe}"

    @staticmethod
    def _pymilvus() -> dict[str, Any]:
        try:
            from pymilvus import (  # type: ignore[import-not-found]
                AnnSearchRequest,
                Collection,
                CollectionSchema,
                DataType,
                FieldSchema,
                WeightedRanker,
                connections,
                utility,
            )
        except ImportError as exc:
            raise RuntimeError(
                "pymilvus is required for organization-domain indexing; run the project "
                "dependency installation before using this command"
            ) from exc
        return {
            "AnnSearchRequest": AnnSearchRequest,
            "Collection": Collection,
            "CollectionSchema": CollectionSchema,
            "DataType": DataType,
            "FieldSchema": FieldSchema,
            "WeightedRanker": WeightedRanker,
            "connections": connections,
            "utility": utility,
        }

    def connect(self) -> None:
        if self._connected:
            return
        api = self._pymilvus()
        api["connections"].connect(
            alias=self.settings.alias,
            host=self.settings.host,
            port=str(self.settings.port),
        )
        self._connected = True

    def close(self) -> None:
        if not self._connected:
            return
        self._pymilvus()["connections"].disconnect(self.settings.alias)
        self._connected = False

    def list_collections(self) -> list[str]:
        self.connect()
        return sorted(self._pymilvus()["utility"].list_collections(using=self.settings.alias))

    def has_collection(self, entity_type: str) -> bool:
        self.connect()
        return bool(
            self._pymilvus()["utility"].has_collection(
                self.collection_name(entity_type),
                using=self.settings.alias,
            )
        )

    def drop_collection(self, entity_type: str) -> None:
        """Drop only the named organization-domain collection."""
        self.connect()
        name = self.collection_name(entity_type)
        api = self._pymilvus()
        if api["utility"].has_collection(name, using=self.settings.alias):
            api["utility"].drop_collection(name, using=self.settings.alias)

    def create_collection(
        self,
        entity_type: str,
        *,
        dense_dimension: int,
        replace: bool = False,
    ) -> None:
        """Create one collection with scalar, BM25 sparse and dense fields."""
        if dense_dimension <= 0:
            raise ValueError("dense_dimension must be positive")
        self.connect()
        api = self._pymilvus()
        name = self.collection_name(entity_type)
        exists = api["utility"].has_collection(name, using=self.settings.alias)
        if exists and not replace:
            return
        if exists:
            api["utility"].drop_collection(name, using=self.settings.alias)

        data_type = api["DataType"]
        field_schema = api["FieldSchema"]
        fields = [
            field_schema("vid", data_type.VARCHAR, is_primary=True, max_length=128),
            field_schema("entity_type", data_type.VARCHAR, max_length=64),
            field_schema("scope", data_type.VARCHAR, max_length=32),
            field_schema("canonical_name", data_type.VARCHAR, max_length=2048),
            field_schema("aliases", data_type.VARCHAR, max_length=8192),
            field_schema("external_id", data_type.VARCHAR, max_length=1024),
            field_schema("country_code", data_type.VARCHAR, max_length=128),
            field_schema("country", data_type.VARCHAR, max_length=512),
            field_schema("province", data_type.VARCHAR, max_length=512),
            field_schema("city", data_type.VARCHAR, max_length=512),
            field_schema("address", data_type.VARCHAR, max_length=4096),
            field_schema("source_table", data_type.VARCHAR, max_length=256),
            field_schema("source_record_id", data_type.VARCHAR, max_length=2048),
            field_schema("search_text", data_type.VARCHAR, max_length=32768),
            field_schema("content_hash", data_type.VARCHAR, max_length=64),
            field_schema("dense_vector", data_type.FLOAT_VECTOR, dim=dense_dimension),
            field_schema("sparse_vector", data_type.SPARSE_FLOAT_VECTOR),
        ]
        schema = api["CollectionSchema"](
            fields,
            description=f"{entity_type} entities owned by the domestic/foreign organization domain",
            enable_dynamic_field=False,
        )
        collection = api["Collection"](
            name,
            schema=schema,
            using=self.settings.alias,
            consistency_level=self.settings.consistency_level,
        )
        collection.create_index(
            "dense_vector",
            {
                "index_type": "HNSW",
                "metric_type": "COSINE",
                "params": {"M": 16, "efConstruction": 200},
            },
            index_name="dense_hnsw",
        )
        collection.create_index(
            "sparse_vector",
            {
                "index_type": "SPARSE_INVERTED_INDEX",
                "metric_type": "IP",
                "params": {"drop_ratio_build": 0.0},
            },
            index_name="bm25_sparse_inverted",
        )
        for field in ("external_id", "country_code", "source_table"):
            collection.create_index(
                field,
                {"index_type": "INVERTED"},
                index_name=f"{field}_inverted",
            )

    def _collection(self, entity_type: str) -> Any:
        self.connect()
        return self._pymilvus()["Collection"](
            self.collection_name(entity_type),
            using=self.settings.alias,
        )

    def upsert(self, entity_type: str, records: list[dict[str, Any]]) -> int:
        if not records:
            return 0
        collection = self._collection(entity_type)
        collection.upsert(records)
        return len(records)

    def flush(self, entity_type: str) -> None:
        self._collection(entity_type).flush()

    def load(self, entity_type: str) -> None:
        self._collection(entity_type).load()

    def count(self, entity_type: str) -> int:
        collection = self._collection(entity_type)
        collection.flush()
        return int(collection.num_entities)

    @staticmethod
    def _escape_expression(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    def query_by_external_id(
        self,
        entity_type: str,
        external_id: str,
        *,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        collection = self._collection(entity_type)
        collection.load()
        escaped = self._escape_expression(external_id)
        return list(
            collection.query(
                expr=f'external_id == "{escaped}"',
                output_fields=[
                    "vid",
                    "canonical_name",
                    "aliases",
                    "external_id",
                    "country_code",
                    "country",
                    "province",
                    "city",
                    "address",
                    "source_table",
                ],
                limit=limit,
            )
        )

    def hybrid_search(
        self,
        entity_type: str,
        *,
        dense_vector: list[float],
        sparse_vector: dict[int, float],
        limit: int = 20,
        dense_weight: float = 0.45,
        sparse_weight: float = 0.55,
    ) -> list[MilvusSearchHit]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        collection = self._collection(entity_type)
        collection.load()
        api = self._pymilvus()
        requests = [
            api["AnnSearchRequest"](
                [dense_vector],
                "dense_vector",
                {"metric_type": "COSINE", "params": {"ef": max(64, limit * 4)}},
                limit=limit,
            ),
            api["AnnSearchRequest"](
                [sparse_vector],
                "sparse_vector",
                {"metric_type": "IP", "params": {"drop_ratio_search": 0.0}},
                limit=limit,
            ),
        ]
        results = collection.hybrid_search(
            requests,
            api["WeightedRanker"](dense_weight, sparse_weight),
            limit=limit,
            output_fields=[
                "vid",
                "canonical_name",
                "aliases",
                "external_id",
                "country_code",
                "country",
                "province",
                "city",
                "address",
                "source_table",
            ],
        )
        hits: list[MilvusSearchHit] = []
        for hit in results[0] if results else []:
            entity = getattr(hit, "entity", None)
            output_fields = (
                "vid",
                "canonical_name",
                "aliases",
                "external_id",
                "country_code",
                "country",
                "province",
                "city",
                "address",
                "source_table",
            )
            fields = (
                {
                    field: entity.get(field)
                    for field in output_fields
                    if entity.get(field) is not None
                }
                if entity is not None
                else {}
            )
            fields.setdefault("vid", str(hit.id))
            hits.append(
                MilvusSearchHit(
                    vid=str(fields["vid"]),
                    score=float(hit.distance),
                    fields=fields,
                )
            )
        return hits


def get_milvus_client() -> Any:
    """Return a process-shared ``pymilvus.MilvusClient`` (Project / paper-style scripts)."""
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None:
            return _client
        from pymilvus import MilvusClient  # type: ignore[import-not-found]

        host, port = _host_port_from_env()
        uri = os.environ.get("MILVUS_URI") or f"http://{host}:{port}"
        token = os.environ.get("MILVUS_TOKEN") or None
        db_name = os.environ.get("MILVUS_DB_NAME", _DEFAULT_DB)
        timeout = int(os.environ.get("MILVUS_TIMEOUT", str(_DEFAULT_TIMEOUT)))
        logger.info("Connecting to Milvus uri=%s db=%s", uri, db_name)
        kwargs: dict[str, Any] = {"uri": uri, "db_name": db_name, "timeout": timeout}
        if token:
            kwargs["token"] = token
        _client = MilvusClient(**kwargs)
    return _client


def reset_milvus_client() -> None:
    """Test helper: drop the ``MilvusClient`` singleton."""
    global _client
    with _client_lock:
        if _client is not None:
            try:
                _client.close()
            except Exception:  # noqa: BLE001
                pass
        _client = None
