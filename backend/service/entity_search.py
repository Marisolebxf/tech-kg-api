"""实体检索：图实体同步 Milvus（BM25 稀疏 + m3e 稠密）混合搜索 + 图直查浏览。

两条查询路径：

1. ``browse``（关键词为空的默认视图）：直接查图空间按标签分页（页内按 vid 排序，
   跨标签优先用索引统计快照拼接分页窗口，快照不可用时实时计数）；
2. ``search``（关键词非空）：先用图库 VID / 已索引名称和业务 ID 精确查找；
   无精确命中时用 Milvus ``hybrid_search``（dense + BM25 sparse，RRF 融合），
   ``entity_type`` / ``graph_space`` 标量过滤；embedding 失败降级单路 BM25。

索引（``reindex``）按图空间独立：单集合 ``kg_entity`` 内 ``graph_space`` 字段
分区，使用 ``graph_space::vid`` 作为集合主键，BM25 词表状态存控制库
``kg_entity_search_state``（每空间一行）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from itertools import islice
from typing import Any

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from infra.entity_response_cache import EntityResponseCache
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
# m3e embedding 服务侧限制：单条 ≤16000 字符、单批 ≤ M3E_MAX_BATCH_SIZE（当前 64）。
# 任一超限服务直接 422 拒绝整批，全量重建在 pass 2 首批即中断（2026-09-21 实测）。
EMBED_TEXT_MAX_CHARS = int(os.getenv("ENTITY_SEARCH_EMBED_TEXT_MAX_CHARS", "16000"))
EMBED_BATCH_SIZE = int(os.getenv("ENTITY_SEARCH_EMBED_BATCH_SIZE", "64"))
# RRF 融合常数（与项目域一致）
RRF_K = 60
# 检索/展示文本上限
SEARCH_TEXT_MAX_BYTES = 32000
PROPERTY_TEXT_MAX_BYTES = 2048
PROPERTY_TEXT_MIN_BYTES = 96
PROPERTIES_JSON_MAX_BYTES = 60000
NAME_CANDIDATE_KEYS = (
    "name",
    "name_zh",
    "name_cn",
    "name_en",
    "title",
    "title_zh",
    "title_en",
    "project_name",
    "paper_title",
    "patent_name",
    "patent_title",
    "product_name",
    "keyword",
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

# 搜索/浏览响应缓存（L1 进程 + L2 Redis，实例从 handler 下沉到 service，
# 供 reindex 完成与人工审核写图联动统一失效——FUNC-00813 队列与图库联动）。
browse_cache = EntityResponseCache(
    namespace="entity-search:browse:v2",
    ttl_seconds=float(os.getenv("ENTITY_BROWSE_CACHE_SECONDS", "300")),
)
search_cache = EntityResponseCache(
    namespace="entity-search:search:v2",
    ttl_seconds=float(os.getenv("ENTITY_SEARCH_CACHE_SECONDS", "60")),
)


async def clear_entity_caches() -> None:
    """清掉搜索/浏览的 L1 进程 + L2 Redis 缓存（reindex 完成或写图联动时调用）。"""
    await asyncio.gather(browse_cache.clear(), search_cache.clear())


def invalidate_entity_caches_sync() -> None:
    """同步上下文的缓存失效入口：工作线程里 asyncio.run 全清；
    事件循环线程内只清 L1（Redis 由短 TTL 兜底），避免嵌套事件循环。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(clear_entity_caches())
    else:
        browse_cache.clear_local()
        search_cache.clear_local()


class EntitySearchError(Exception):
    """实体检索领域错误。"""


class EntitySearchReindexInProgressError(EntitySearchError):
    pass


def _resolve_embedding_config() -> dict[str, Any]:
    """embedding 服务配置：配置管理默认配置优先，回退 env（ENTITY_SEARCH_*/PATENT_*）。

    ``dim`` 可能为 None（配置未声明维度）——由重建时首个成功响应推断。
    """
    from service.embedding_config import resolve_embedding_settings

    settings = resolve_embedding_settings()
    if settings is None:
        raise EntitySearchError(
            "未配置 embedding 服务：请在「配置管理」设置默认 embedding 配置，"
            "或配置 ENTITY_SEARCH_EMBEDDING_*/PATENT_EMBEDDING_* 环境变量"
        )
    return {
        "base_url": settings["base_url"],
        "model": settings["model"],
        "api_key": settings["api_key"],
        "dim": settings.get("dimensions"),
        "config_id": settings.get("config_id"),
    }


def _embedding_client() -> EmbeddingClient | None:
    """按当前生效配置构造客户端；完全未配置时返回 None（查询端降级单路 BM25）。"""
    try:
        config = _resolve_embedding_config()
    except EntitySearchError:
        return None
    if config["base_url"]:
        return EmbeddingClient(
            api_key=config["api_key"],
            base_url=config["base_url"],
            model=config["model"],
            dimensions=config["dim"],
        )
    return EmbeddingClient(api_key=config["api_key"], model=config["model"])


def _current_embedding_fields() -> dict[str, Any]:
    """状态页附加字段：当前生效的 embedding 模型/配置来源；解析失败不拖垮状态读取。"""
    try:
        config = _resolve_embedding_config()
    except Exception:  # noqa: BLE001 - EntitySearchError / DB 故障均降级为未知
        return {"currentEmbeddingModel": None, "currentEmbeddingConfigId": None}
    return {
        "currentEmbeddingModel": config["model"],
        "currentEmbeddingConfigId": config.get("config_id"),
    }


def _scalar(value: Any) -> Any:
    """保留 JSON 可序列化的标量属性值；其余（list/dict/None）返回 None。"""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return None


def _iter_property_values(value: Any, *, depth: int = 0) -> Iterator[str]:
    """展开属性中的可检索叶子值，兼容原生 list/dict 与 JSON 字符串。"""
    if value is None or depth > 6:
        return
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return
        if normalized[:1] in {"[", "{"}:
            try:
                decoded = json.loads(normalized)
            except (TypeError, ValueError):
                decoded = None
            if isinstance(decoded, (Mapping, list, tuple, set)):
                yield from _iter_property_values(decoded, depth=depth + 1)
                return
        yield normalized
        return
    if isinstance(value, Mapping):
        for nested_key, nested_value in value.items():
            yield str(nested_key)
            yield from _iter_property_values(nested_value, depth=depth + 1)
        return
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        for item in value:
            yield from _iter_property_values(item, depth=depth + 1)
        return
    if isinstance(value, set):
        for item in sorted(value, key=str):
            yield from _iter_property_values(item, depth=depth + 1)
        return
    if isinstance(value, (int, float, bool)):
        yield str(value)


def _clip_search_text(value: str, limit: int) -> str:
    """保留长值首尾，避免只保留开头导致尾部关键词永远不可检索。"""
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value
    head = max((limit - 1) // 2, 1)
    tail = max(limit - head - 1, 1)
    prefix = encoded[:head].decode("utf-8", errors="ignore")
    suffix = encoded[-tail:].decode("utf-8", errors="ignore")
    return f"{prefix} {suffix}"


def _truncate_utf8(value: str, limit: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value
    return encoded[:limit].decode("utf-8", errors="ignore")


def _property_search_fragment(key: Any, value: Any, *, limit: int) -> str:
    parts = [str(key)]
    remaining = max(limit - len(parts[0].encode("utf-8")) - 1, 0)
    for leaf in _iter_property_values(value):
        if remaining <= 0:
            break
        clipped = _clip_search_text(leaf, remaining)
        parts.append(clipped)
        remaining -= len(clipped.encode("utf-8")) + 1
    return " ".join(parts) if len(parts) > 1 else ""


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
    """挑出可展示的公共属性；复杂值序列化后截断，按插入序保留。"""
    display: dict[str, Any] = {}
    for key, value in props.items():
        scalar = _scalar(value)
        if scalar is None:
            if not isinstance(value, (Mapping, list, tuple, set)):
                continue
            try:
                scalar = json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
            except (TypeError, ValueError):
                continue
        if scalar == "":
            continue
        text = str(scalar)
        if len(text) > 512:
            text = text[:512] + "…"
        key_text = str(key)
        candidate = {**display, key_text: text}
        if (
            len(json.dumps(candidate, ensure_ascii=False).encode("utf-8"))
            > PROPERTIES_JSON_MAX_BYTES
        ):
            break
        display[key_text] = text
    return display


def compose_entity_text(name: str, entity_type: str, props: dict[str, Any]) -> str:
    """BM25 / dense 共用语料：实体名、类型及展开后的全部属性键值。"""
    parts = [name, entity_type]
    remaining = (
        SEARCH_TEXT_MAX_BYTES - len(name.encode("utf-8")) - len(entity_type.encode("utf-8")) - 2
    )
    property_count = max(len(props), 1)
    per_property_limit = min(
        PROPERTY_TEXT_MAX_BYTES,
        max(PROPERTY_TEXT_MIN_BYTES, remaining // property_count),
    )
    for key, value in props.items():
        fragment = _property_search_fragment(key, value, limit=per_property_limit)
        if fragment:
            parts.append(fragment)
    return _truncate_utf8(
        " ".join(part for part in parts if part),
        SEARCH_TEXT_MAX_BYTES,
    )


def _batched(items: Iterable[dict[str, Any]], size: int) -> Iterator[list[dict[str, Any]]]:
    iterator = iter(items)
    while chunk := list(islice(iterator, size)):
        yield chunk


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


def _state_type_counts(session: Session, space: str, labels: list[str]) -> dict[str, int] | None:
    """读取完整的索引统计快照，无法安全用于跨标签分页时返回 ``None``。

    ``type_counts`` 由全量 reindex 生成。只有快照恰好覆盖当前图空间全部标签，
    才能替代逐标签实时 COUNT；部分重建、旧状态、损坏 JSON 或标签变化均回退
    原有实时计数路径，以免改变跨标签分页边界。
    """
    try:
        row = _load_state(session, space)
        raw_counts = json.loads(row.type_counts or "{}") if row is not None else {}
        if not isinstance(raw_counts, dict):
            return None

        counts: dict[str, int] = {}
        for label, count in raw_counts.items():
            if (
                not isinstance(label, str)
                or isinstance(count, bool)
                or not isinstance(count, int)
                or count < 0
            ):
                return None
            counts[label] = count

        # 严格匹配可区分全量快照与 entity_types 部分重建的快照。
        return counts if set(counts) == set(labels) else None
    except Exception:  # noqa: BLE001 - 状态不可用不应让图直查浏览失败
        logger.warning("读取实体计数快照失败（space=%s），回退实时计数", space, exc_info=True)
        return None


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
    from datetime import UTC, datetime

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
    row.updated_at = datetime.now(UTC)
    session.commit()


def _milvus_space_has_rows(milvus: Any, space: str) -> bool:
    """Return whether ``kg_entity`` really contains data for ``space``.

    The MySQL state row is only a snapshot from the last successful rebuild. It
    can outlive a dropped/replaced Milvus collection or a failed rebuild, so it
    must not be treated as proof that the current graph space is searchable.
    Querying one VID is enough to validate availability without an expensive
    full count.
    """
    rows = milvus.query(
        collection_name=COLLECTION_NAME,
        filter=f'graph_space == "{_escape_expression(space)}"',
        output_fields=["vid"],
        limit=1,
    )
    return bool(rows)


def _index_record(item: dict[str, Any]) -> dict[str, Any]:
    props = item["props"]
    name = extract_entity_name(props, item["vid"])
    entity_id = str(
        next(
            (props.get(key) for key in ("id", "entity_id") if _scalar(props.get(key))),
            "",
        )
        or item["vid"]
    )
    return {
        "vid": item["vid"],
        # Milvus VARCHAR max_length 按 UTF-8 字节计：中文 2048 字符可达 6144 字节，
        # 按字符切片会让整批 upsert 被 1100 拒绝（2026-09-21 实测 name 5430 字节）
        "entity_id": _truncate_utf8(entity_id, 256),
        "name": _truncate_utf8(name, 2048),
        "entity_type": item["entity_type"],
        "properties": extract_display_properties(props),
        "text": compose_entity_text(name, item["entity_type"], props),
    }


def _iter_index_records(
    graph: TRSGraphClient, labels: list[str], skipped: list[str] | None = None
) -> Iterator[dict[str, Any]]:
    for item in _iter_graph_entities(graph, labels, skipped=skipped):
        # 超长 VID（Nebula 上限 256B，Milvus vid 字段 128B）入不了主键字段：跳过
        if len(item["vid"].encode("utf-8")) > 128:
            logger.warning("VID 超过 128 字节，跳过入索引: %.60s…", item["vid"])
            continue
        record = _index_record(item)
        if record["text"]:
            yield record


def _iter_index_texts(
    graph: TRSGraphClient, labels: list[str], skipped: list[str] | None = None
) -> Iterator[str]:
    """首遍仅生成检索语料，避免为不落库的记录序列化展示属性。"""
    for item in _iter_graph_entities(graph, labels, skipped=skipped):
        name = extract_entity_name(item["props"], item["vid"])
        document = compose_entity_text(name, item["entity_type"], item["props"])
        if document:
            yield document


@contextmanager
def _database_reindex_guard(session: Session):
    """MySQL advisory lock prevents two API/worker processes rebuilding together."""
    bind = session.get_bind()
    if bind.dialect.name != "mysql":
        yield
        return
    with bind.connect() as connection:
        acquired = connection.execute(
            text("SELECT GET_LOCK(:name, 0)"), {"name": "kg_entity_search_reindex"}
        ).scalar()
        if acquired != 1:
            raise EntitySearchReindexInProgressError("索引重建正在进行中，请稍后再试")
        try:
            yield
        finally:
            connection.execute(
                text("SELECT RELEASE_LOCK(:name)"), {"name": "kg_entity_search_reindex"}
            )


def _database_reindex_running(session: Session) -> bool:
    bind = session.get_bind()
    if bind.dialect.name != "mysql":
        return _reindex_running
    try:
        with bind.connect() as connection:
            return (
                connection.execute(
                    text("SELECT IS_USED_LOCK(:name)"),
                    {"name": "kg_entity_search_reindex"},
                ).scalar()
                is not None
            )
    except Exception:  # noqa: BLE001 - 状态接口仍应返回其余可用信息
        logger.warning("检查实体索引重建锁失败", exc_info=True)
        return _reindex_running


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
        """按标签分页浏览实体（页内按 vid 排序）。

        单类型查询复用节点分页响应中的总数；跨标签查询优先用全量 reindex
        保存的类型计数快照计算分页窗口。快照不可安全使用时回退实时逐标签
        计数。两条路径均只拉取窗口涉及的标签分片。
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
            result = graph.get_nodes_by_label(type_filter, limit=limit, offset=offset)
            total = int(result.total)
            items = [_serialize_browse_item(node, type_filter) for node in result.items or []]
        else:
            counts = _state_type_counts(self._session, resolved_space, labels)
            if counts is None:
                counts = {
                    label: _node_count_cached(graph, resolved_space, label) for label in labels
                }
            total = sum(counts.values())
            window_start, window_end = offset, offset + limit
            cursor = 0
            for label in labels:
                count = counts[label]
                if cursor >= window_end:
                    break
                # 空标签（0 节点 TAG）只跳过——break 会把排在其后的有数据标签
                # 一并砍掉，浏览分页整体空白
                if count <= 0:
                    continue
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
        """全量重建指定图空间的实体索引：图 → embedding + BM25 → Milvus。"""
        global _reindex_running

        with _reindex_lock:
            if _reindex_running:
                raise EntitySearchReindexInProgressError("索引重建正在进行中，请稍后再试")
            _reindex_running = True
        try:
            with _database_reindex_guard(self._session):
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
        # Milvus entity_type 字段 64 字节上限：超长标签名（垃圾数据）直接排除
        labels = [label for label in labels if len(label.encode("utf-8")) <= 64]
        if entity_types:
            wanted = {item.strip() for item in entity_types if item.strip()}
            missing = sorted(wanted - set(labels))
            if missing:
                raise EntitySearchError(f"图空间中不存在这些实体类型: {', '.join(missing)}")
            # BM25 的词表和稀疏向量维度由整个语料库共同决定。只重建指定类型会让
            # 新词表与其他类型的旧稀疏向量不兼容；历史实现还会先删除空间全部行，
            # 再只写回当前类型。保留 entity_types 作为兼容校验参数，但始终重建
            # 当前图空间全部标签，保证向量、统计和实际行集合属于同一快照。

        # 第一遍只累计 BM25 文档频率/词表，不保留全量实体和 dense vectors。
        # dev2 约 52 万实体，历史实现一次性持有 records + 512 维向量会占用数 GB。
        skipped_labels: list[str] = []
        encoder = BM25SparseEncoder()
        encoder.fit_iterable(_iter_index_texts(graph, labels, skipped=skipped_labels))
        # 无索引且 REST 拉不动的大标签已跳过：第二遍不再重试（每次重试都是一轮超时）
        if skipped_labels:
            labels = [label for label in labels if label not in skipped_labels]
            logger.warning(
                "实体索引重建跳过无索引大标签: %s（补建标签索引后重建可收编）",
                sorted(set(skipped_labels)),
            )

        # 第二遍重新流式读取图实体，每批完成 embedding 后立即写入 Milvus。
        embedding_config = _resolve_embedding_config()
        client = _embedding_client()
        if client is None:
            raise EntitySearchError(
                "未配置 embedding 服务：请在「配置管理」设置默认 embedding 配置，"
                "或配置 ENTITY_SEARCH_EMBEDDING_*/PATENT_EMBEDDING_* 环境变量"
            )
        milvus = get_milvus_client()
        written = 0
        type_counts: dict[str, int] = {}
        replacement_started = False
        space_filter = f'graph_space == "{_escape_expression(resolved_space)}"'
        try:
            expected_dim = embedding_config["dim"]
            for chunk in _batched(
                _iter_index_records(graph, labels, skipped=skipped_labels), EMBED_BATCH_SIZE
            ):
                # 只裁 embedding 输入：BM25 语料/存储仍保留完整 32KB 文本
                batch = [record["text"][:EMBED_TEXT_MAX_CHARS] for record in chunk]
                vectors = client.embed(batch)
                if vectors is None or len(vectors) != len(batch):
                    raise EntitySearchError(
                        f"embedding 服务调用失败（model={embedding_config['model']}），索引未写入"
                    )
                if expected_dim is None:
                    # 配置未声明维度：以首个成功响应为准，后续批次与建集合都按它校验
                    expected_dim = len(vectors[0])
                if any(len(vector) != expected_dim for vector in vectors):
                    raise EntitySearchError(f"embedding 维度与配置不符（期望 {expected_dim}）")
                if not replacement_started:
                    self._ensure_collection(milvus, dim=expected_dim)
                    milvus.delete(collection_name=COLLECTION_NAME, filter=space_filter)
                    replacement_started = True
                rows = []
                for record, vector in zip(chunk, vectors, strict=True):
                    rows.append(
                        {
                            "document_id": f"{resolved_space}::{record['vid']}",
                            "vid": record["vid"],
                            "entity_id": record["entity_id"],
                            "name": record["name"],
                            "entity_type": record["entity_type"],
                            "graph_space": resolved_space,
                            "search_text": record["text"],
                            "properties": json.dumps(record["properties"], ensure_ascii=False),
                            "dense_vector": vector,
                            "sparse_vector": encoder.encode_document(record["text"]),
                        }
                    )
                    entity_type = record["entity_type"]
                    type_counts[entity_type] = type_counts.get(entity_type, 0) + 1
                milvus.upsert(collection_name=COLLECTION_NAME, data=rows)
                written += len(rows)
                if written % 5000 < len(rows):
                    logger.info("实体索引流式重建进度 space=%s written=%s", resolved_space, written)

            if not replacement_started:
                # 空间无实体：没有向量可推维度，只在集合已存在时清掉本空间旧行
                if expected_dim is not None:
                    self._ensure_collection(milvus, dim=expected_dim)
                if milvus.has_collection(COLLECTION_NAME):
                    milvus.delete(collection_name=COLLECTION_NAME, filter=space_filter)
                replacement_started = True
            if milvus.has_collection(COLLECTION_NAME):
                milvus.flush(COLLECTION_NAME)
                milvus.load_collection(COLLECTION_NAME)
        except Exception:
            # 不让失败批次伪装成可用的完整索引；状态行保留旧快照，查询端会
            # 通过“当前空间无行”明确报告 stateStale，管理员可安全重试。
            if replacement_started:
                try:
                    milvus.delete(collection_name=COLLECTION_NAME, filter=space_filter)
                    milvus.flush(COLLECTION_NAME)
                except Exception:  # noqa: BLE001 - 保留原始重建异常
                    logger.exception("清理失败的实体索引批次失败（space=%s）", resolved_space)
            raise

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
            "embeddingConfigId": embedding_config.get("config_id"),
            "skippedLabels": sorted(set(skipped_labels)),
            "durationSeconds": round(time.monotonic() - started, 2),
        }

    def upsert_entity(
        self, *, space: str, node_label: str, vid: str, is_new: bool
    ) -> dict[str, Any]:
        """图写后单实体增量入索引（人工审核 T_LINK 裁决联动，FUNC-00813）。

        与全量 reindex 同构：图读回顶点 → dense embed + BM25（state 词表）→ 幂等 upsert。
        前置守卫：空间索引已建成（state 快照 + BM25 词表可用）且当前无重建在跑；
        未建成 / 组件异常一律返回 ``upserted=False``，由调用方降级（下次全量重建兜底）。
        ``is_new``：create 落新 vid → 计数快照 +1；merge 覆盖已有行 → 计数不变。
        """
        if _database_reindex_running(self._session):
            return {"upserted": False, "reason": "reindex in progress"}
        state_row = _load_state(self._session, space)
        encoder = _load_bm25_from_state(self._session, space)
        if state_row is None or encoder is None or not (state_row.entity_count or 0):
            return {"upserted": False, "reason": "space index not built"}
        graph = get_space_client(space)
        node = graph.get_node(vid)
        if node is None:
            return {"upserted": False, "reason": "vertex not found in graph"}
        record = _index_record(
            {"vid": vid, "entity_type": node_label, "props": dict(node.properties or {})}
        )
        if not record["text"]:
            return {"upserted": False, "reason": "empty search text"}
        try:
            embedding_config = _resolve_embedding_config()
            client = _embedding_client()
        except EntitySearchError:
            return {"upserted": False, "reason": "embedding not configured"}
        if client is None:
            return {"upserted": False, "reason": "embedding not configured"}
        vectors = client.embed([record["text"][:EMBED_TEXT_MAX_CHARS]])
        if not vectors or len(vectors) != 1:
            return {"upserted": False, "reason": "embedding failed"}
        # 配置声明了维度才校验；未声明（首个响应推断口径）交给 Milvus 建行时报错降级
        if embedding_config["dim"] is not None and len(vectors[0]) != embedding_config["dim"]:
            return {"upserted": False, "reason": "embedding dim mismatch"}
        sparse_vector = encoder.encode_document(record["text"])
        if not sparse_vector:
            # Milvus 拒绝空稀疏向量：文本 token 全不在全量词表（全新造词）时降级跳过
            return {"upserted": False, "reason": "empty sparse vector"}
        try:
            milvus = get_milvus_client()
            if not milvus.has_collection(COLLECTION_NAME):
                return {"upserted": False, "reason": "collection missing"}
            milvus.upsert(
                collection_name=COLLECTION_NAME,
                data=[
                    {
                        "document_id": f"{space}::{vid}",
                        "vid": vid,
                        "entity_id": record["entity_id"],
                        "name": record["name"],
                        "entity_type": node_label,
                        "graph_space": space,
                        "search_text": record["text"],
                        "properties": json.dumps(record["properties"], ensure_ascii=False),
                        "dense_vector": vectors[0],
                        "sparse_vector": sparse_vector,
                    }
                ],
            )
        except Exception as exc:  # noqa: BLE001 - 增量失败不影响裁决，等全量重建兜底
            logger.warning("单实体入索引失败 vid=%s space=%s", vid, space)
            return {"upserted": False, "reason": f"milvus error: {exc}"}
        if is_new:
            self._bump_state_counts(state_row, node_label)
        return {"upserted": True, "vid": vid, "entityType": node_label}

    def _bump_state_counts(self, state_row: Any, node_label: str) -> None:
        """create 场景计数快照 +1：浏览分页窗口/总览与图保持一致（merge 不变）。"""
        from datetime import UTC, datetime

        try:
            counts = json.loads(state_row.type_counts or "{}")
        except Exception:  # noqa: BLE001 - 计数快照损坏按空处理
            counts = {}
        if not isinstance(counts, dict):
            counts = {}
        counts[node_label] = int(counts.get(node_label) or 0) + 1
        state_row.type_counts = json.dumps(counts, ensure_ascii=False)
        state_row.entity_count = int(state_row.entity_count or 0) + 1
        state_row.updated_at = datetime.now(UTC)
        self._session.commit()

    @staticmethod
    def _ensure_collection(milvus: Any, *, dim: int) -> None:
        """建 / 校验 kg_entity 集合；旧主键 schema 或维度变更时整体重建。

        ``vid`` 在不同图空间可能重复，不能作为共享集合主键。新版使用
        ``document_id=graph_space::vid``，检测到旧集合时丢弃并由本次全量重建恢复。
        维度是集合级属性：换 embedding 配置导致维度变化时同样整体丢弃重建——
        其它图空间的行随之失效，需各自重新构建索引（状态页按行数报 stateStale）。
        """
        from pymilvus import DataType  # type: ignore[import-not-found]

        if milvus.has_collection(COLLECTION_NAME):
            description = milvus.describe_collection(COLLECTION_NAME) or {}
            field_list = [
                field for field in description.get("fields", []) if isinstance(field, dict)
            ]
            field_names = {field.get("name") for field in field_list}
            if "graph_space" not in field_names or "document_id" not in field_names:
                # 旧 schema（单空间或 vid 主键版本）→ 丢弃重建
                milvus.drop_collection(COLLECTION_NAME)
            else:
                dense_field = next(
                    (field for field in field_list if field.get("name") == "dense_vector"),
                    None,
                )
                existing_dim = (dense_field or {}).get("params", {}).get("dim")
                if existing_dim is not None and existing_dim != dim:
                    milvus.drop_collection(COLLECTION_NAME)

        if not milvus.has_collection(COLLECTION_NAME):
            schema = milvus.create_schema(auto_id=False, enable_dynamic_field=False)
            schema.add_field("document_id", DataType.VARCHAR, is_primary=True, max_length=256)
            schema.add_field("vid", DataType.VARCHAR, max_length=128)
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
        """先查图库精确名称/ID；无精确命中时沿用 Milvus 混合检索。"""
        keyword = keyword.strip()
        if not keyword:
            raise EntitySearchError("关键词不能为空")
        resolved_space = space or _default_space()
        exact_error: Exception | None = None
        try:
            exact_items = self._graph_exact_matches(
                keyword=keyword, space=resolved_space, entity_type=entity_type
            )
        except Exception as exc:  # noqa: BLE001 - 图服务异常不阻断已有向量检索
            logger.exception("图库精确检索失败（space=%s），尝试已有实体索引", resolved_space)
            exact_error = exc
            exact_items = []
        if exact_items:
            items = exact_items[offset : offset + limit]
            return {
                "items": items,
                "offset": offset,
                "limit": limit,
                "returned": len(items),
                "total": len(exact_items),
                "keyword": keyword,
                "entityType": entity_type,
                "graphSpace": resolved_space,
                "mode": "graph-exact",
            }
        result = self._search_index(
            keyword=keyword,
            space=resolved_space,
            entity_type=entity_type,
            limit=limit,
            offset=offset,
        )
        if exact_error is not None and not result["items"]:
            raise EntitySearchError("图库精确检索暂不可用，请稍后重试") from exact_error
        return result

    @staticmethod
    def _graph_exact_matches(
        *, keyword: str, space: str, entity_type: str | None
    ) -> list[dict[str, Any]]:
        """VID 点查及任意已建图属性索引的精确查找，不遍历图库补齐向量索引。

        每个索引查询最多取检索窗口的 500 条，去重后以类型、VID 稳定排序。
        仅使用复合索引的首列，避免对不满足索引前缀的属性查询做全图扫描。
        """
        graph = get_space_client(space)
        matches: dict[tuple[str, str], dict[str, Any]] = {}

        def add(node: Any, label: str, *, indexed_property_match: bool = False) -> None:
            if entity_type and label != entity_type:
                return
            item = _serialize_browse_item(node, label)
            if indexed_property_match or keyword in (item["vid"], item["entityId"], item["name"]):
                matches[(label, item["vid"])] = item

        node = graph.get_node(keyword)
        if node is not None:
            for label in sorted(node.labels or []):
                add(node, label)

        try:
            indexes = graph.list_indexes(entity_type)
        except Exception:  # noqa: BLE001 - 元数据异常不丢弃已经确认的 VID 命中
            if not matches:
                raise
            logger.exception("读取图属性索引失败（space=%s），返回 VID 精确命中", space)
            return [matches[key] for key in sorted(matches)]
        indexed_fields = sorted(
            {
                (index.label, index.properties[0])
                for index in indexes
                if index.properties and (not entity_type or index.label == entity_type)
            }
        )
        index_error: Exception | None = None
        for label, prop in indexed_fields:
            # find_nodes 接收结构化属性，关键词不会被拼接成查询语句。
            try:
                result = graph.find_nodes([label], {prop: keyword}, limit=500, offset=0)
            except Exception as exc:  # noqa: BLE001 - 单个索引异常不丢弃其他精确命中
                index_error = exc
                logger.exception(
                    "图属性精确检索失败（space=%s, label=%s, prop=%s）", space, label, prop
                )
                continue
            for candidate in result.items or []:
                add(candidate, label, indexed_property_match=True)
        if index_error is not None and not matches:
            raise index_error
        return [matches[key] for key in sorted(matches)][:500]

    def _search_index(
        self,
        *,
        keyword: str,
        space: str,
        entity_type: str | None,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        """保留非精确关键词的 dense + BM25 检索及原有索引错误语义。"""
        resolved_space = space
        fetch = min(limit + offset, 500)
        not_indexed = EntitySearchError(
            f"图空间 {resolved_space} 尚未构建实体索引，请先在页面触发「重建索引」"
        )
        state_row = _load_state(self._session, resolved_space)
        if state_row is None:
            raise not_indexed
        try:
            milvus = get_milvus_client()
            collection_exists = bool(milvus.has_collection(COLLECTION_NAME))
        except Exception as exc:  # noqa: BLE001 - 明确暴露当前降级能力
            raise EntitySearchError(
                f"图空间 {resolved_space} 的实体语义索引当前不可用；"
                "已降级为 VID/已建图属性索引的精确查询"
            ) from exc
        if not collection_exists:
            raise not_indexed
        try:
            has_space_rows = _milvus_space_has_rows(milvus, resolved_space)
        except Exception as exc:  # noqa: BLE001 - expose the exact-query fallback clearly
            raise EntitySearchError(
                f"图空间 {resolved_space} 的实体语义索引当前不可用；"
                "VID/已建图属性索引的精确查询仍可用"
            ) from exc
        if not has_space_rows:
            raise EntitySearchError(
                f"图空间 {resolved_space} 的实体索引状态已过期（Milvus 中无该空间数据）；"
                "VID/已建图属性索引的精确查询仍可用"
            )

        conditions = [f'graph_space == "{_escape_expression(resolved_space)}"']
        if entity_type:
            conditions.append(f'entity_type == "{_escape_expression(entity_type)}"')
        expr = " and ".join(conditions)

        # 纯符号/乱码关键词（分词器分不出任何 token）：余弦相似度对此类输入
        # 无区分度（m3e 对符号串与任意实体的相似度都 0.65+，"搜什么都一样"），
        # 按无匹配返回。注意不能以"BM25 词项命中为空"判断——合法关键词的 token
        # 可能不在（小）词表里，那应走 dense 正常检索
        if not tokenize_alignment_text(keyword):
            return {
                "items": [],
                "offset": offset,
                "limit": limit,
                "returned": 0,
                "keyword": keyword,
                "entityType": entity_type,
                "graphSpace": resolved_space,
                "mode": "keyword",
            }
        embedding_client = _embedding_client()
        dense_vector = embedding_client.embed_one(keyword) if embedding_client else None
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
        """索引内实体类型 + 数量；状态快照与 Milvus 不一致时返回空。"""
        resolved_space = space or _default_space()
        row = _load_state(self._session, resolved_space)
        if row is None:
            return []
        try:
            milvus = get_milvus_client()
            if not milvus.has_collection(COLLECTION_NAME) or not _milvus_space_has_rows(
                milvus, resolved_space
            ):
                return []
        except Exception:  # noqa: BLE001 - 类型下拉不应因 Milvus 故障拖垮页面
            logger.warning("校验实体索引类型失败（space=%s）", resolved_space, exc_info=True)
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
        """索引状态：同时校验控制库快照和 Milvus 当前空间的真实数据。"""
        resolved_space = space or _default_space()
        row = _load_state(self._session, resolved_space)
        space_has_rows = False
        milvus_reachable = True
        try:
            milvus = get_milvus_client()
            collection_exists = bool(milvus.has_collection(COLLECTION_NAME))
            if collection_exists:
                space_has_rows = _milvus_space_has_rows(milvus, resolved_space)
        except Exception:  # noqa: BLE001 - Milvus 不可达时状态仍可读
            collection_exists = False
            milvus_reachable = False
        base = {
            "graphSpace": resolved_space,
            "collectionExists": collection_exists,
            "milvusReachable": milvus_reachable,
            "actualDataAvailable": space_has_rows,
            "reindexing": _database_reindex_running(self._session),
            **_current_embedding_fields(),
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
                "stateStale": False,
            }
        try:
            type_counts: dict[str, int] = json.loads(row.type_counts or "{}")
        except ValueError:
            type_counts = {}
        state_stale = row.entity_count > 0 and not space_has_rows
        effective_type_counts = type_counts if space_has_rows else {}
        return {
            **base,
            "indexed": collection_exists and space_has_rows and row.entity_count > 0,
            "entityCount": row.entity_count if space_has_rows else 0,
            "recordedEntityCount": row.entity_count,
            "stateStale": state_stale,
            "typeCounts": effective_type_counts,
            "recordedTypeCounts": type_counts,
            "types": [
                {"name": name, "count": count}
                for name, count in sorted(
                    effective_type_counts.items(), key=lambda item: (-item[1], item[0])
                )
            ],
            "embeddingModel": row.embedding_model or None,
            "embeddingModelChanged": (
                base["currentEmbeddingModel"] is not None
                and row.embedding_model is not None
                and base["currentEmbeddingModel"] != row.embedding_model
            ),
            "updatedAt": row.updated_at.isoformat() if row.updated_at else None,
            "bm25Ready": bool(space_has_rows and row.vocabulary and row.document_count),
        }


def _iter_graph_entities(
    graph: TRSGraphClient,
    labels: list[str],
    page_size: int = GRAPH_PAGE_SIZE,
    skipped: list[str] | None = None,
):
    """按标签分页拉取全部节点，yield {vid, entity_type, props}。

    优先走 nGQL ``LOOKUP ON <tag> YIELD vertex | LIMIT/OFFSET``：有索引的标签
    （organization_base 23 万等）索引枚举深分页仅 ~3s/页；REST ``/nodes/label``
    是 MATCH+SKIP 全量物化，大标签单页就能超过读超时（2026-09-21 实测 Paper
    在 REST 上 90s 服务端兜底超时，重建两次中断）。LOOKUP 不可用（标签无索引）
    时回退 REST 分页；REST 再失败的大标签记 warning 跳过并写入 ``skipped``
    ——待补建标签索引后下次全量重建收编，其余标签不受影响。
    """
    from infra.graph_db.exceptions import GraphRepoError

    skipped = skipped if skipped is not None else []
    for label in labels:
        try:
            probe = graph.execute_query(f"LOOKUP ON `{label}` YIELD vertex AS v | LIMIT 1")
        except (AttributeError, GraphRepoError):
            # AttributeError：客户端无原生查询能力（测试替身/旧版本）→ 走 REST
            probe = None
        if probe is not None:
            try:
                yield from _iter_label_via_lookup(graph, label)
            except GraphRepoError:
                # 长任务中途的瞬时图服务抖动不应报废整次重建：按标签降级跳过
                logger.warning("标签 %s LOOKUP 分页中途失败，本次重建跳过该标签", label)
                skipped.append(label)
            continue
        try:
            yield from _iter_label_via_rest(graph, label, page_size)
        except GraphRepoError:
            logger.warning(
                "标签 %s 无图索引且 REST 分页超时，本次重建跳过该标签（补建标签索引后重建可收编）",
                label,
            )
            skipped.append(label)


def _iter_label_via_lookup(graph: TRSGraphClient, label: str, page_size: int = 2000):
    """索引枚举分页：LOOKUP + LIMIT/OFFSET（对有索引标签是线性代价）。"""
    offset = 0
    while True:
        result = graph.execute_query(
            f"LOOKUP ON `{label}` YIELD vertex AS v | LIMIT {page_size} OFFSET {offset}"
        )
        records = result.records or []
        if not records:
            return
        for record in records:
            node = record.get("v") if isinstance(record, dict) else None
            if not isinstance(node, dict):
                continue
            vid = str(node.get("id") or "")
            if not vid:
                continue
            yield {"vid": vid, "entity_type": label, "props": dict(node.get("properties") or {})}
        offset += len(records)
        if len(records) < page_size:
            return


def _iter_label_via_rest(graph: TRSGraphClient, label: str, page_size: int):
    """REST /nodes/label 分页（原实现）：适合小标签。"""
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
