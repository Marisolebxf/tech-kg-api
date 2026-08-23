"""Build Milvus indexes for entities owned by the 39 organization-domain tables.

The command reads existing vertices exclusively through
``infra.graph_db.get_trs_graph_client``.  It never creates graph vertices or
edges.  Dry-run is the default.

Examples:

    python -m script.organization_milvus_index --entity all --dry-run
    python -m script.organization_milvus_index --entity Organization --write
    python -m script.organization_milvus_index --entity all --write --replace
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from infra.graph_db import GraphNode, TRSGraphClient, get_trs_graph_client
from infra.milvus import OrganizationMilvusStore
from script.organization_etl_common import (
    DOMAIN_TABLE_BY_NAME,
    DOMAIN_TABLE_SPECS,
    chunks,
    clean_text,
    compact_json,
)
from service.organization_entity_alignment import (
    BM25SparseEncoder,
    HashingDenseEncoder,
)

logger = logging.getLogger("script.organization_milvus_index")

DEFAULT_BATCH_SIZE = 500
DEFAULT_DENSE_DIMENSION = 384
DEFAULT_STATE_DIR = Path(".cache/organization_milvus")
MAX_SEARCH_TEXT_BYTES = 30_000
DOMAIN_TABLES = frozenset(DOMAIN_TABLE_BY_NAME)
DOMAIN_ENTITY_TYPES = (
    "Organization",
    "Person",
    "News",
    "Event",
    "Product",
    "DataSource",
)
assert {spec.entity_tag for spec in DOMAIN_TABLE_SPECS if spec.entity_tag is not None} <= set(
    DOMAIN_ENTITY_TYPES
)

_CANONICAL_NAME_FIELDS: dict[str, tuple[str, ...]] = {
    "Organization": ("name_cn", "name_en", "name_alias", "name", "stock_noun"),
    "Person": ("name_cn", "name_en", "name"),
    "News": ("title",),
    "Event": ("title", "case_no", "event_type"),
    "Product": ("name",),
    "DataSource": ("table_cn_name", "source_table"),
}
_ALIAS_FIELDS: dict[str, tuple[str, ...]] = {
    "Organization": (
        "name_cn",
        "name_en",
        "name_alias",
        "stock_noun",
        "traditional_name",
    ),
    "Person": ("name_cn", "name_en", "name_alias"),
    "News": ("title",),
    "Event": ("title", "case_no"),
    "Product": ("name",),
    "DataSource": ("table_cn_name", "source_table"),
}
_SEARCH_FIELDS: dict[str, tuple[str, ...]] = {
    "Organization": (
        "name_cn",
        "name_en",
        "name_alias",
        "external_id",
        "org_kind",
        "country_code",
        "country",
        "province",
        "city",
        "address",
        "industry",
        "business_scope",
        "description",
    ),
    "Person": (
        "name_cn",
        "name_en",
        "person_kind",
        "nationality",
        "birth_date",
        "biography",
    ),
    "News": ("title", "content", "release_date", "original_url"),
    "Event": (
        "title",
        "event_type",
        "case_no",
        "content",
        "occur_date",
        "currency",
    ),
    "Product": ("name", "description"),
    "DataSource": ("table_cn_name", "source_table", "library", "tier"),
}


@dataclass(frozen=True)
class EntityIndexDocument:
    vid: str
    entity_type: str
    scope: str
    canonical_name: str
    aliases: str
    external_id: str
    country_code: str
    country: str
    province: str
    city: str
    address: str
    source_table: str
    source_record_id: str
    search_text: str
    content_hash: str


@dataclass
class EntityIndexStats:
    entity_type: str
    graph_total: int = 0
    domain_owned: int = 0
    indexed: int = 0
    skipped_out_of_scope: int = 0
    skipped_invalid: int = 0
    batches: int = 0
    collection: str = ""
    examples: list[dict[str, str]] = field(default_factory=list)


def _text(value: Any, *, max_length: int = 30_000) -> str:
    return clean_text(value, max_length=max_length) or ""


def _utf8_truncate(value: str, max_bytes: int) -> str:
    """Respect Milvus VARCHAR max_length, which is measured in UTF-8 bytes."""
    encoded = value.encode()
    if len(encoded) <= max_bytes:
        return value
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def _bounded_alias_json(values: Sequence[str], max_bytes: int = 8_000) -> str:
    accepted: list[str] = []
    for value in values:
        candidate = compact_json([*accepted, _utf8_truncate(value, 2_000)])
        if len(candidate.encode()) > max_bytes:
            break
        accepted.append(_utf8_truncate(value, 2_000))
    return compact_json(accepted)


def _first(properties: Mapping[str, Any], fields: Iterable[str]) -> str:
    for name in fields:
        if value := _text(properties.get(name), max_length=4096):
            return value
    return ""


def _unique_values(properties: Mapping[str, Any], fields: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for name in fields:
        value = _text(properties.get(name), max_length=4096)
        normalized = value.casefold()
        if value and normalized not in seen:
            seen.add(normalized)
            result.append(value)
    return result


def _extra_json(properties: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = properties.get("extra_json")
    if isinstance(raw, Mapping):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, Mapping) else {}


def _combined_properties(node: GraphNode) -> dict[str, Any]:
    properties = dict(node.properties)
    extra = _extra_json(properties)
    for key, value in extra.items():
        properties.setdefault(str(key), value)
    return properties


def _scope(source_table: str) -> str:
    spec = DOMAIN_TABLE_BY_NAME.get(source_table)
    return spec.scope if spec else "organization_domain"


def is_domain_owned(node: GraphNode) -> bool:
    source_table = _text(node.properties.get("source_table"), max_length=256)
    return source_table in DOMAIN_TABLES


def node_to_document(entity_type: str, node: GraphNode) -> EntityIndexDocument:
    if entity_type not in DOMAIN_ENTITY_TYPES:
        raise ValueError(f"entity type is outside organization domain: {entity_type}")
    properties = _combined_properties(node)
    source_table = _text(properties.get("source_table"), max_length=256)
    if source_table not in DOMAIN_TABLES:
        raise ValueError(f"node {node.id} is not owned by a 39-table source")

    canonical_name = _first(properties, _CANONICAL_NAME_FIELDS[entity_type])
    if not canonical_name:
        canonical_name = str(node.id)
    alias_values = _unique_values(properties, _ALIAS_FIELDS[entity_type])
    search_values = _unique_values(properties, _SEARCH_FIELDS[entity_type])
    for alias in alias_values:
        if alias.casefold() not in {value.casefold() for value in search_values}:
            search_values.append(alias)
    search_text = " ".join(search_values)
    if not search_text:
        search_text = canonical_name
    if properties.get("extra_json"):
        search_text = f"{search_text} {_text(properties['extra_json'])}"
    search_text = _utf8_truncate(search_text, MAX_SEARCH_TEXT_BYTES)
    content_hash = hashlib.sha256(f"{entity_type}|{node.id}|{search_text}".encode()).hexdigest()
    return EntityIndexDocument(
        vid=str(node.id),
        entity_type=entity_type,
        scope=_scope(source_table),
        canonical_name=_utf8_truncate(canonical_name, 2_000),
        aliases=_bounded_alias_json(alias_values),
        external_id=_utf8_truncate(_text(properties.get("external_id")), 1_000),
        country_code=_utf8_truncate(_text(properties.get("country_code")), 120),
        country=_utf8_truncate(_text(properties.get("country")), 500),
        province=_utf8_truncate(_text(properties.get("province")), 500),
        city=_utf8_truncate(_text(properties.get("city")), 500),
        address=_utf8_truncate(_text(properties.get("address")), 4_000),
        source_table=_utf8_truncate(source_table, 250),
        source_record_id=_utf8_truncate(
            _text(properties.get("source_record_id")),
            2_000,
        ),
        search_text=search_text,
        content_hash=content_hash,
    )


def iter_graph_nodes(
    graph: TRSGraphClient,
    entity_type: str,
    *,
    page_size: int = 500,
    max_records: int | None = None,
) -> Iterator[GraphNode]:
    offset = 0
    yielded = 0
    while True:
        page = graph.get_nodes_by_label(entity_type, limit=page_size, offset=offset)
        if not page.items:
            break
        for node in page.items:
            if max_records is not None and yielded >= max_records:
                return
            yielded += 1
            yield node
        offset += len(page.items)
        if offset >= page.total:
            break


def collect_documents(
    graph: TRSGraphClient,
    entity_type: str,
    *,
    page_size: int,
    max_records: int | None,
) -> tuple[list[EntityIndexDocument], EntityIndexStats]:
    stats = EntityIndexStats(entity_type=entity_type)
    documents: list[EntityIndexDocument] = []
    for node in iter_graph_nodes(
        graph,
        entity_type,
        page_size=page_size,
        max_records=None,
    ):
        stats.graph_total += 1
        if not is_domain_owned(node):
            stats.skipped_out_of_scope += 1
            continue
        try:
            document = node_to_document(entity_type, node)
        except (TypeError, ValueError):
            stats.skipped_invalid += 1
            logger.exception("cannot index %s node %s", entity_type, node.id)
            continue
        documents.append(document)
        stats.domain_owned += 1
        if len(stats.examples) < 3:
            stats.examples.append(
                {
                    "vid": document.vid,
                    "name": document.canonical_name,
                    "source_table": document.source_table,
                }
            )
        if max_records is not None and len(documents) >= max_records:
            break
    return documents, stats


def _state_dir(value: str | None) -> Path:
    return Path(value or os.environ.get("ORG_MILVUS_STATE_DIR") or DEFAULT_STATE_DIR).resolve()


def index_entity_type(
    graph: TRSGraphClient,
    store: OrganizationMilvusStore,
    entity_type: str,
    *,
    dense: HashingDenseEncoder,
    batch_size: int,
    state_dir: Path,
    write: bool,
    replace: bool,
    max_records: int | None,
) -> EntityIndexStats:
    documents, stats = collect_documents(
        graph,
        entity_type,
        page_size=batch_size,
        max_records=max_records,
    )
    stats.collection = store.collection_name(entity_type)
    if not documents:
        return stats

    bm25 = BM25SparseEncoder()
    bm25.fit([document.search_text for document in documents])

    if not write:
        stats.indexed = len(documents)
        return stats

    store.create_collection(
        entity_type,
        dense_dimension=dense.dimension,
        replace=replace,
    )
    for document_batch in chunks(documents, batch_size):
        records: list[dict[str, Any]] = []
        for document in document_batch:
            record = asdict(document)
            record["dense_vector"] = dense.encode(document.search_text)
            record["sparse_vector"] = bm25.encode_document(document.search_text)
            records.append(record)
        stats.indexed += store.upsert(entity_type, records)
        stats.batches += 1
    store.flush(entity_type)
    store.load(entity_type)
    bm25.save(state_dir / f"{store.collection_name(entity_type)}.bm25.json")
    return stats


def run_index(
    *,
    entity: str = "all",
    batch_size: int = DEFAULT_BATCH_SIZE,
    write: bool = False,
    replace: bool = False,
    dense_dimension: int = DEFAULT_DENSE_DIMENSION,
    state_dir: str | None = None,
    max_records: int | None = None,
    graph: TRSGraphClient | None = None,
    store: OrganizationMilvusStore | None = None,
) -> dict[str, Any]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if entity != "all" and entity not in DOMAIN_ENTITY_TYPES:
        raise ValueError(f"unknown organization-domain entity type: {entity}")
    selected = DOMAIN_ENTITY_TYPES if entity == "all" else (entity,)
    graph_client = graph or get_trs_graph_client()
    milvus_store = store or OrganizationMilvusStore()
    dense = HashingDenseEncoder(dense_dimension)
    resolved_state_dir = _state_dir(state_dir)
    results = []
    for entity_type in selected:
        logger.info("index entity=%s write=%s", entity_type, write)
        stats = index_entity_type(
            graph_client,
            milvus_store,
            entity_type,
            dense=dense,
            batch_size=batch_size,
            state_dir=resolved_state_dir,
            write=write,
            replace=replace,
            max_records=max_records,
        )
        results.append(asdict(stats))
    return {
        "write": write,
        "replace": replace,
        "entity_types": list(selected),
        "dense_dimension": dense_dimension,
        "state_dir": str(resolved_state_dir),
        "stats": results,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Index every existing entity owned by the 39 organization-domain tables."
    )
    parser.add_argument("--entity", choices=("all", *DOMAIN_ENTITY_TYPES), default="all")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--dense-dimension", type=int, default=DEFAULT_DENSE_DIMENSION)
    parser.add_argument("--state-dir")
    parser.add_argument("--max-records", type=int)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="replace only the selected organization-domain Milvus collections",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    result = run_index(
        entity=args.entity,
        batch_size=args.batch_size,
        write=args.write,
        replace=args.replace,
        dense_dimension=args.dense_dimension,
        state_dir=args.state_dir,
        max_records=args.max_records,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
