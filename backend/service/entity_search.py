"""实体检索：图实体同步 Milvus（BM25 稀疏 + m3e 稠密）混合搜索 + 图直查浏览。

两条查询路径：

1. ``browse``（关键词为空的默认视图）：直接查图空间按标签分页（页内按 vid 排序，
   跨标签用各标签计数拼接分页窗口）——反映图库实时数据，不依赖 Milvus 索引；
2. ``search``（关键词非空）：Milvus ``hybrid_search``（dense + BM25 sparse，RRF
   融合），``entity_type`` / ``graph_space`` 标量过滤；embedding 失败降级单路 BM25。

索引（``reindex``）按图空间独立：单集合 ``kg_entity`` 内 ``graph_space`` 字段
分区，BM25 词表状态存控制库 ``kg_entity_search_state``（每空间一行）。
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from infra.graph_db import TRSGraphClient, get_space_client
from infra.llm import EmbeddingClient
from infra.milvus import get_milvus_client
from service.organization_entity_alignment import (
    BM25SparseEncoder,
    tokenize_alignment_text,
)

logger = logging.getLogger(__name__)

COLLECTION_NAME = "kg_entity"
DEFAULT_PAGE_SIZE = 10
GRAPH_PAGE_SIZE = 200
EMBED_BATCH_SIZE = 64
UPSERT_BATCH_SIZE = 200
# RRF 融合常数（与项目域一致）
RRF_K = 60
# 检索/展示文本上限
SEARCH_TEXT_MAX_CHARS = 4000
PROPERTIES_JSON_MAX_CHARS = 60000
NAME_CANDIDATE_KEYS = (
    "name",
    "name_zh",
    "name_cn",
    "title",
    "title_zh",
    "label",
    "cn_name",
    "display_name",
    "org_name",
)
# 标签节点数缓存 TTL（Nebula count 是全量扫描）
_NODE_COUNT_TTL_SECONDS = 300.0

_reindex_lock = threading.Lock()
_reindex_running = False
_node_count_cache: dict[tuple[str, str], tuple[float, int]] = {}


class EntitySearchError(Exception):
    """实体检索领域错误。"""


class EntitySearchReindexInProgressError(EntitySearchError):
    pass


def _env_embedding_config() -> dict[str, Any]:
    """embedding 服务配置：ENTITY_SEARCH_EMBEDDING_* 优先，回退 PATENT_EMBEDDING_*。"""
    base_url = (
        os.getenv("ENTITY_SEARCH_EMBEDDING_BASE_URL")
        or os.getenv("PATENT_EMBEDDING_BASE_URL")
        or ""
    )
    model = (
        os.getenv("ENTITY_SEARCH_EMBEDDING_MODEL")
        or os.getenv("PATENT_EMBEDDING_MODEL")
        or "moka-ai/m3e-small"
    )
    api_key = (
        os.getenv("ENTITY_SEARCH_EMBEDDING_API_KEY")
        or os.getenv("PATENT_EMBEDDING_API_KEY")
        or "local-no-auth"
    )
    dim = int(
        os.getenv("ENTITY_SEARCH_EMBEDDING_DIM") or os.getenv("PATENT_EMBEDDING_DIM") or "512"
    )
    return {"base_url": base_url, "model": model, "api_key": api_key, "dim": dim}


def _embedding_client() -> EmbeddingClient:
    config = _env_embedding_config()
    if config["base_url"]:
        return EmbeddingClient(
            api_key=config["api_key"], base_url=config["base_url"], model=config["model"]
        )
    return EmbeddingClient(api_key=config["api_key"], model=config["model"])


def _scalar(value: Any) -> Any:
    """保留 JSON 可序列化的标量属性值；其余（list/dict/None）返回 None。"""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return None


def _escape_expression(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def extract_entity_name(props: dict[str, Any], vid: str) -> str:
    for key in NAME_CANDIDATE_KEYS:
        value = props.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
    return str(vid)


def extract_display_properties(props: dict[str, Any]) -> dict[str, Any]:
    """挑出可展示的公共属性（标量、键值均截断），按插入序保留。"""
    display: dict[str, Any] = {}
    for key, value in props.items():
        scalar = _scalar(value)
        if scalar is None or scalar == "":
            continue
        text = str(scalar)
        if len(text) > 512:
            text = text[:512] + "…"
        display[str(key)] = text
        if len(json.dumps(display, ensure_ascii=False)) >= PROPERTIES_JSON_MAX_CHARS:
            break
    return display


def compose_entity_text(name: str, entity_type: str, props: dict[str, Any]) -> str:
    """BM25 / dense 共用语料：实体名 + 类型 + 标量属性键值。"""
    parts = [name, entity_type]
    for key, value in props.items():
        scalar = _scalar(value)
        if scalar is None or scalar == "":
            continue
        text = str(scalar)
        if len(text) > 256:
            text = text[:256]
        parts.append(f"{key} {text}")
    return " ".join(part for part in parts if part)[:SEARCH_TEXT_MAX_CHARS]


def _serialize_browse_item(node: Any, entity_type: str) -> dict[str, Any]:
    """图直查节点 → 与检索一致的列表项结构。"""
    props = dict(node.properties or {})
    vid = str(node.id)
    entity_id = str(
        next((props.get(key) for key in ("id", "entity_id") if _scalar(props.get(key))), "") or vid
    )
    return {
        "vid": vid,
        "entityId": entity_id[:256],
        "name": extract_entity_name(props, vid)[:2048],
        "entityType": entity_type,
        "properties": extract_display_properties(props),
        "score": None,
    }


def _node_count_cached(graph: TRSGraphClient, space: str, label: str) -> int:
    """带 TTL 缓存的标签节点数（Nebula count 是全量扫描，秒级）。"""
    key = (space, label)
    cached = _node_count_cache.get(key)
    if cached and time.monotonic() - cached[0] < _NODE_COUNT_TTL_SECONDS:
        return cached[1]
    count = int(graph.node_count(label))
    _node_count_cache[key] = (time.monotonic(), count)
    return count


# ---------------------------------------------------------------------------
# 控制库状态（按图空间一行）
# ---------------------------------------------------------------------------


_state_table_checked = False


def _ensure_state_table() -> None:
    """幂等建 kg_entity_search_state 表；旧 schema（int id 主键）属可再生状态，直接重建。

    进程内只做一次检查（inspect/create_all 都有成本）；所有读写路径（含
    search/types/status）都先经由此函数，避免旧库升级后首个查询报列不存在。
    """
    global _state_table_checked
    if _state_table_checked:
        return
    from db_model.entity_search import EntitySearchState
    from infra.workflow_mysql import get_workflow_engine

    engine = get_workflow_engine()
    inspector = inspect(engine)
    if inspector.has_table(EntitySearchState.__tablename__):
        columns = {
            column["name"] for column in inspector.get_columns(EntitySearchState.__tablename__)
        }
        if "id" in columns and "graph_space" not in columns:
            EntitySearchState.__table__.drop(engine, checkfirst=True)
    EntitySearchState.metadata.create_all(engine, tables=[EntitySearchState.__table__])
    _state_table_checked = True


def _load_state(session: Session, space: str) -> Any:
    from db_model.entity_search import EntitySearchState

    _ensure_state_table()
    return session.scalar(select(EntitySearchState).where(EntitySearchState.graph_space == space))


def _load_bm25_from_state(session: Session, space: str) -> BM25SparseEncoder | None:
    """从控制库状态行恢复 BM25 编码器；无状态或损坏返回 None。"""
    row = _load_state(session, space)
    if row is None or not row.vocabulary or not row.document_count:
        return None
    try:
        encoder = BM25SparseEncoder(
            vocabulary=json.loads(row.vocabulary),
            document_frequency=json.loads(row.document_frequency),
            document_count=row.document_count,
            average_document_length=row.average_document_length,
            k1=row.k1,
            b=row.b,
        )
        return encoder if encoder.fitted else None
    except Exception:  # noqa: BLE001 - 状态损坏按未建索引处理
        logger.exception("恢复 BM25 状态失败（space=%s），按未建索引处理", space)
        return None


def _save_state(
    session: Session,
    *,
    space: str,
    encoder: BM25SparseEncoder,
    entity_count: int,
    type_counts: dict[str, int],
    embedding_model: str,
) -> None:
    from datetime import datetime

    from db_model.entity_search import EntitySearchState

    row = _load_state(session, space)
    if row is None:
        row = EntitySearchState(graph_space=space)
        session.add(row)
    row.vocabulary = json.dumps(encoder.vocabulary, ensure_ascii=False, separators=(",", ":"))
    row.document_frequency = json.dumps(
        encoder.document_frequency, ensure_ascii=False, separators=(",", ":")
    )
    row.document_count = encoder.document_count
    row.average_document_length = encoder.average_document_length
    row.k1 = encoder.k1
    row.b = encoder.b
    row.entity_count = entity_count
    row.type_counts = json.dumps(type_counts, ensure_ascii=False)
    row.embedding_model = embedding_model
    row.updated_at = datetime.utcnow()
    session.commit()


class EntitySearchService:
    """实体 Milvus 混合检索 + 图直查浏览（browse / search / reindex / types / status）。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # 浏览（关键词为空）：图直查分页
    # ------------------------------------------------------------------
    def browse(
        self,
        *,
        space: str | None = None,
        entity_type: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> dict[str, Any]:
        """按标签分页浏览实体（页内按 vid 排序），反映图库实时数据。

        跨标签分页按标签名次序拼接各标签计数得到全局窗口，只拉取窗口涉及的
        标签分片——实体再多也只取当页所需（「只在图空间中取前几个」）。
        """
        graph = get_space_client(space or _default_space())
        resolved_space = space or _default_space()
        labels = sorted(graph.labels())
        if entity_type:
            if entity_type not in labels:
                raise EntitySearchError(f"图空间中不存在实体类型: {entity_type}")
            labels = [entity_type]

        type_filter = entity_type
        items: list[dict[str, Any]] = []
        if type_filter:
            total = _node_count_cached(graph, resolved_space, type_filter)
            result = graph.get_nodes_by_label(type_filter, limit=limit, offset=offset)
            items = [_serialize_browse_item(node, type_filter) for node in result.items or []]
        else:
            counts = {label: _node_count_cached(graph, resolved_space, label) for label in labels}
            total = sum(counts.values())
            window_start, window_end = offset, offset + limit
            cursor = 0
            for label in labels:
                count = counts[label]
                if count <= 0 or cursor >= window_end:
                    break
                label_start = cursor
                label_end = cursor + count
                cursor = label_end
                # 只拉取与当前页窗口相交的标签分片
                slice_start = max(window_start, label_start) - label_start
                slice_end = min(window_end, label_end) - label_start
                if slice_start >= slice_end:
                    continue
                result = graph.get_nodes_by_label(
                    label, limit=slice_end - slice_start, offset=slice_start
                )
                items.extend(_serialize_browse_item(node, label) for node in result.items or [])
        items.sort(key=lambda item: str(item["vid"]))
        return {
            "items": items[:limit],
            "offset": offset,
            "limit": limit,
            "total": total,
            "entityType": entity_type,
            "mode": "browse",
        }

    # ------------------------------------------------------------------
    # 索引构建
    # ------------------------------------------------------------------
    def reindex(
        self,
        *,
        space: str | None = None,
        entity_types: list[str] | None = None,
    ) -> dict[str, Any]:
        """按图空间重建 ``kg_entity`` 中该空间的实体索引：图 → embedding + BM25 → Milvus。"""
        global _reindex_running

        with _reindex_lock:
            if _reindex_running:
                raise EntitySearchReindexInProgressError("索引重建正在进行中，请稍后再试")
            _reindex_running = True
        try:
            return self._reindex_locked(space=space, entity_types=entity_types)
        finally:
            with _reindex_lock:
                _reindex_running = False

    def _reindex_locked(
        self, *, space: str | None, entity_types: list[str] | None
    ) -> dict[str, Any]:
        started = time.monotonic()
        resolved_space = space or _default_space()
        graph = get_space_client(resolved_space)
        labels = sorted(graph.labels())
        if entity_types:
            wanted = {item.strip() for item in entity_types if item.strip()}
            labels = [label for label in labels if label in wanted]
            missing = sorted(wanted - set(labels))
            if missing:
                raise EntitySearchError(f"图空间中不存在这些实体类型: {', '.join(missing)}")

        records: list[dict[str, Any]] = []
        for item in _iter_graph_entities(graph, labels):
            props = item["props"]
            name = extract_entity_name(props, item["vid"])
            entity_id = str(
                next(
                    (props.get(key) for key in ("id", "entity_id") if _scalar(props.get(key))),
                    "",
                )
                or item["vid"]
            )
            records.append(
                {
                    "vid": item["vid"],
                    "entity_id": entity_id[:256],
                    "name": name[:2048],
                    "entity_type": item["entity_type"],
                    "properties": extract_display_properties(props),
                    "text": compose_entity_text(name, item["entity_type"], props),
                }
            )
        records = [record for record in records if record["text"]]

        # BM25 fit 全量语料
        encoder = BM25SparseEncoder()
        encoder.fit([record["text"] for record in records])

        # dense embedding 分批
        embedding_config = _env_embedding_config()
        client = _embedding_client()
        dense_vectors: list[list[float] | None] = []
        for start in range(0, len(records), EMBED_BATCH_SIZE):
            batch = [record["text"] for record in records[start : start + EMBED_BATCH_SIZE]]
            vectors = client.embed(batch)
            if vectors is None or len(vectors) != len(batch):
                raise EntitySearchError(
                    f"embedding 服务调用失败（model={embedding_config['model']}），索引未写入"
                )
            if any(len(vector) != embedding_config["dim"] for vector in vectors):
                raise EntitySearchError(
                    f"embedding 维度与配置不符（期望 {embedding_config['dim']}）"
                )
            dense_vectors.extend(vectors)

        milvus = get_milvus_client()
        self._ensure_collection(milvus, dim=embedding_config["dim"])
        # 按空间覆盖旧数据（不影响其他空间的索引）
        milvus.delete(
            collection_name=COLLECTION_NAME,
            filter=f'graph_space == "{_escape_expression(resolved_space)}"',
        )
        written = 0
        for start in range(0, len(records), UPSERT_BATCH_SIZE):
            chunk = records[start : start + UPSERT_BATCH_SIZE]
            rows = []
            for index, record in enumerate(chunk):
                vector = dense_vectors[start + index]
                if vector is None:
                    continue
                rows.append(
                    {
                        "vid": record["vid"],
                        "entity_id": record["entity_id"],
                        "name": record["name"],
                        "entity_type": record["entity_type"],
                        "graph_space": resolved_space,
                        "search_text": record["text"],
                        "properties": json.dumps(record["properties"], ensure_ascii=False)[
                            :PROPERTIES_JSON_MAX_CHARS
                        ],
                        "dense_vector": vector,
                        "sparse_vector": encoder.encode_document(record["text"]),
                    }
                )
            if rows:
                milvus.upsert(collection_name=COLLECTION_NAME, data=rows)
                written += len(rows)
        milvus.flush(COLLECTION_NAME)
        milvus.load_collection(COLLECTION_NAME)

        type_counts: dict[str, int] = {}
        for record in records:
            type_counts[record["entity_type"]] = type_counts.get(record["entity_type"], 0) + 1
        _ensure_state_table()
        _save_state(
            self._session,
            space=resolved_space,
            encoder=encoder,
            entity_count=written,
            type_counts=type_counts,
            embedding_model=embedding_config["model"],
        )
        return {
            "entityCount": written,
            "typeCounts": type_counts,
            "graphSpace": resolved_space,
            "embeddingModel": embedding_config["model"],
            "durationSeconds": round(time.monotonic() - started, 2),
        }

    @staticmethod
    def _ensure_collection(milvus: Any, *, dim: int) -> None:
        """建 / 校验 kg_entity 集合；旧 schema（无 graph_space 字段）整体重建。"""
        from pymilvus import DataType  # type: ignore[import-not-found]

        if milvus.has_collection(COLLECTION_NAME):
            description = milvus.describe_collection(COLLECTION_NAME) or {}
            fields = {
                field.get("name")
                for field in description.get("fields", [])
                if isinstance(field, dict)
            }
            if "graph_space" not in fields:
                # 旧 schema（单空间版本）→ 丢弃重建，重新 reindex 即可恢复
                milvus.drop_collection(COLLECTION_NAME)

        if not milvus.has_collection(COLLECTION_NAME):
            schema = milvus.create_schema(auto_id=False, enable_dynamic_field=False)
            schema.add_field("vid", DataType.VARCHAR, is_primary=True, max_length=128)
            schema.add_field("entity_id", DataType.VARCHAR, max_length=256)
            schema.add_field("name", DataType.VARCHAR, max_length=2048)
            schema.add_field("entity_type", DataType.VARCHAR, max_length=64)
            schema.add_field("graph_space", DataType.VARCHAR, max_length=64)
            schema.add_field("search_text", DataType.VARCHAR, max_length=32768)
            schema.add_field("properties", DataType.VARCHAR, max_length=65535)
            schema.add_field("dense_vector", DataType.FLOAT_VECTOR, dim=dim)
            schema.add_field("sparse_vector", DataType.SPARSE_FLOAT_VECTOR)
            index_params = milvus.prepare_index_params()
            index_params.add_index(
                field_name="dense_vector",
                index_type="HNSW",
                metric_type="COSINE",
                params={"M": 16, "efConstruction": 200},
            )
            index_params.add_index(
                field_name="sparse_vector",
                index_type="SPARSE_INVERTED_INDEX",
                metric_type="IP",
                params={"drop_ratio_build": 0.0},
            )
            for field_name in ("entity_type", "graph_space"):
                index_params.add_index(field_name=field_name, index_type="INVERTED")
            milvus.create_collection(
                collection_name=COLLECTION_NAME,
                schema=schema,
                index_params=index_params,
            )

    # ------------------------------------------------------------------
    # 关键词检索
    # ------------------------------------------------------------------
    def search(
        self,
        *,
        keyword: str,
        space: str | None = None,
        entity_type: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> dict[str, Any]:
        """混合检索（dense + BM25 sparse，RRF 融合），按图空间 + 实体类型过滤。"""
        keyword = keyword.strip()
        if not keyword:
            raise EntitySearchError("关键词不能为空")
        resolved_space = space or _default_space()
        fetch = min(limit + offset, 500)
        milvus = get_milvus_client()
        not_indexed = EntitySearchError(
            f"图空间 {resolved_space} 尚未构建实体索引，请先在页面触发「重建索引」"
        )
        state_row = _load_state(self._session, resolved_space)
        if state_row is None:
            raise not_indexed
        if not milvus.has_collection(COLLECTION_NAME):
            raise not_indexed

        conditions = [f'graph_space == "{_escape_expression(resolved_space)}"']
        if entity_type:
            conditions.append(f'entity_type == "{_escape_expression(entity_type)}"')
        expr = " and ".join(conditions)

        dense_vector = _embedding_client().embed_one(keyword)
        encoder = _load_bm25_from_state(self._session, resolved_space)
        sparse_vector = encoder.encode_query(keyword) if encoder else None

        hits = self._hybrid_search(
            milvus,
            dense_vector=dense_vector,
            sparse_vector=sparse_vector,
            expr=expr,
            limit=fetch,
        )
        window = hits[offset : offset + limit]
        items = []
        for hit in window:
            fields = hit.get("fields") or hit
            properties = {}
            raw = fields.get("properties")
            if isinstance(raw, str) and raw:
                try:
                    properties = json.loads(raw)
                except ValueError:
                    properties = {}
            elif isinstance(raw, dict):
                properties = raw
            items.append(
                {
                    "vid": fields.get("vid"),
                    "entityId": fields.get("entity_id"),
                    "name": fields.get("name"),
                    "entityType": fields.get("entity_type"),
                    "properties": properties,
                    "score": round(float(hit.get("distance", 0.0)), 6),
                }
            )
        return {
            "items": items,
            "offset": offset,
            "limit": limit,
            "returned": len(items),
            "keyword": keyword,
            "entityType": entity_type,
            "graphSpace": resolved_space,
            "mode": "hybrid"
            if dense_vector is not None and sparse_vector
            else ("dense" if dense_vector is not None else "sparse"),
        }

    @staticmethod
    def _hybrid_search(
        milvus: Any,
        *,
        dense_vector: list[float] | None,
        sparse_vector: dict[int, float] | None,
        expr: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """按可用的向量路数选择 hybrid / 单路 search；返回扁平化命中列表。"""
        from pymilvus import AnnSearchRequest, RRFRanker  # type: ignore[import-not-found]

        output_fields = ["vid", "entity_id", "name", "entity_type", "properties"]
        if dense_vector is None and not sparse_vector:
            raise EntitySearchError("关键词无法编码（embedding 与 BM25 均不可用）")

        if dense_vector is not None and sparse_vector:
            requests = [
                AnnSearchRequest(
                    data=[dense_vector],
                    anns_field="dense_vector",
                    param={"metric_type": "COSINE", "params": {"ef": 128}},
                    limit=limit,
                    expr=expr,
                ),
                AnnSearchRequest(
                    data=[sparse_vector],
                    anns_field="sparse_vector",
                    param={"metric_type": "IP", "params": {"drop_ratio_search": 0.0}},
                    limit=limit,
                    expr=expr,
                ),
            ]
            response = milvus.hybrid_search(
                collection_name=COLLECTION_NAME,
                reqs=requests,
                ranker=RRFRanker(k=RRF_K),
                limit=limit,
                output_fields=output_fields,
            )
        elif dense_vector is not None:
            response = milvus.search(
                collection_name=COLLECTION_NAME,
                data=[dense_vector],
                anns_field="dense_vector",
                search_params={"metric_type": "COSINE", "params": {"ef": 128}},
                filter=expr or "",
                limit=limit,
                output_fields=output_fields,
            )
        else:
            response = milvus.search(
                collection_name=COLLECTION_NAME,
                data=[sparse_vector],
                anns_field="sparse_vector",
                search_params={"metric_type": "IP", "params": {"drop_ratio_search": 0.0}},
                filter=expr or "",
                limit=limit,
                output_fields=output_fields,
            )

        hits: list[dict[str, Any]] = []
        results = response[0] if response else []
        for hit in results:
            if isinstance(hit, dict):
                # MilvusClient 高层 API：{"id", "distance", "entity": {field: value}}
                fields = dict(hit.get("entity") or {})
                distance = hit.get("distance", 0.0)
            else:
                entity = getattr(hit, "entity", None)
                fields = (
                    {field: entity.get(field) for field in output_fields}
                    if entity is not None
                    else {}
                )
                distance = getattr(hit, "distance", None) or getattr(hit, "score", 0.0)
            hits.append({"distance": distance or 0.0, "fields": fields})
        return hits

    # ------------------------------------------------------------------
    # 类型 / 状态
    # ------------------------------------------------------------------
    def types(self, *, space: str | None = None) -> list[dict[str, Any]]:
        """索引内实体类型 + 数量（来自该空间状态行；未建索引返回 []）。"""
        row = _load_state(self._session, space or _default_space())
        if row is None:
            return []
        try:
            counts: dict[str, int] = json.loads(row.type_counts or "{}")
        except ValueError:
            counts = {}
        return [
            {"name": name, "count": count}
            for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ]

    def status(self, *, space: str | None = None) -> dict[str, Any]:
        """索引状态：是否已建、实体数、类型统计、更新时间（按图空间）。"""
        resolved_space = space or _default_space()
        row = _load_state(self._session, resolved_space)
        try:
            milvus = get_milvus_client()
            collection_exists = bool(milvus.has_collection(COLLECTION_NAME))
        except Exception:  # noqa: BLE001 - Milvus 不可达时状态仍可读
            collection_exists = False
        base = {
            "graphSpace": resolved_space,
            "collectionExists": collection_exists,
            "reindexing": _reindex_running,
        }
        if row is None:
            return {
                **base,
                "indexed": False,
                "entityCount": 0,
                "typeCounts": {},
                "types": [],
                "embeddingModel": None,
                "updatedAt": None,
                "bm25Ready": False,
            }
        try:
            type_counts: dict[str, int] = json.loads(row.type_counts or "{}")
        except ValueError:
            type_counts = {}
        return {
            **base,
            "indexed": collection_exists and row.entity_count > 0,
            "entityCount": row.entity_count,
            "typeCounts": type_counts,
            "types": [
                {"name": name, "count": count}
                for name, count in sorted(type_counts.items(), key=lambda item: (-item[1], item[0]))
            ],
            "embeddingModel": row.embedding_model or None,
            "updatedAt": row.updated_at.isoformat() if row.updated_at else None,
            "bm25Ready": bool(row.vocabulary and row.document_count),
        }


def _iter_graph_entities(
    graph: TRSGraphClient, labels: list[str], page_size: int = GRAPH_PAGE_SIZE
):
    """按标签分页拉取全部节点，yield {vid, entity_type, props}。"""
    for label in labels:
        offset = 0
        while True:
            result = graph.get_nodes_by_label(label, limit=page_size, offset=offset)
            items = result.items or []
            if not items:
                break
            for node in items:
                vid = str(node.id)
                if not vid:
                    continue
                yield {"vid": vid, "entity_type": label, "props": dict(node.properties or {})}
            offset += len(items)
            if len(items) < page_size:
                break


def _default_space() -> str:
    from infra.graph_db.config import TRSGraphSettings

    return TRSGraphSettings.from_env().space


def tokenize_query(keyword: str) -> list[str]:
    """暴露给测试/调试的查询分词。"""
    return tokenize_alignment_text(keyword)
