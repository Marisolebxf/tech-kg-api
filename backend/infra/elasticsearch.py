"""实体关键词搜索的 Elasticsearch 索引（ES 通道）。

实体列表文字搜索（``GET /v1/entity-search/keyword``）在图上是逐标签
CONTAINS 全扫，属性无法建索引，真实空间（56 标签 / 百万级点）单次搜索
20s+，前端必超时。本模块提供 ES 镜像索引的薄 REST 封装：

- 每个图空间一个索引 ``kg_entity_kw_{space}``（与 Milvus 集合按空间隔离同思路）；
- ``search_text`` 用 ngram(2..3) 分词器，match + operator=and 等价于
  图上的「VID 或任一属性值包含关键词」（子串语义，Nebula 原生索引做不到）；
- ``item`` 字段存的是与图直查完全一致的序列化列表项（object, enabled=false
  只存不索引），命中后直接回放，前端零改动、响应结构零漂移；
- 排序 ``[{entity_type}, {vid}]`` 与图路径「标签字典序 + 标签内 VID 序」一致，
  分页翻页顺序稳定。

不引入 elasticsearch-py 依赖：httpx 直连 REST（本项目已有依赖），只用到
ensure / bulk / search / count / refresh / delete-index 六个动作。

环境变量
--------
- ``ENTITY_SEARCH_ES_URL``    — 例如 ``http://es1016-es:9200``；留空 = ES 通道关闭（默认）
- ``ENTITY_SEARCH_ES_TIMEOUT`` — 查询超时秒数，默认 10

用法::

    from infra.elasticsearch import get_entity_keyword_es

    store = get_entity_keyword_es()   # 未配置时返回 None，调用方回退图直查
    if store and store.ready("dev2"):
        counts = store.counts("dev2", "大学")

索引同步目前由 ``script/build_entity_keyword_index.py`` 全量重建；图上增量
写入不实时同步（spike 范围，#458 的教训是同步链路才是难点，先验证查询侧收益）。
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 10.0
_BULK_TIMEOUT_SECONDS = 120.0
# 分桶上限：真实空间标签数（dev2 56 个）；命中标签超过该数的空间 counts 会截断
_AGG_BUCKET_SIZE = 1000
# 「索引已就绪」正缓存的 TTL：避免每次搜索都 HEAD+count 探测
_READY_TTL_SECONDS = 60.0
_INDEX_NAME_RE = re.compile(r"[^a-z0-9_]+")

_client_lock = threading.Lock()
_client: EntityKeywordES | None = None


class ElasticsearchError(RuntimeError):
    """ES 请求失败（网络/HTTP/批内错误）。调用方应回退图直查，不向用户抛出。"""


class EntityKeywordES:
    """实体关键词索引的 REST 封装，线程安全（httpx.Client 自带连接池）。"""

    def __init__(self, base_url: str, timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._http = httpx.Client(base_url=self._base_url, timeout=timeout)
        self._ready_cache: dict[str, tuple[float, bool]] = {}
        self._ready_lock = threading.Lock()

    # ------------------------------------------------------------------ 基础

    def close(self) -> None:
        self._http.close()

    @staticmethod
    def index_name(space: str) -> str:
        """图空间名 → 合法索引名（ES 索引必须小写、不含 ``-`` 等字符）。"""
        cleaned = _INDEX_NAME_RE.sub("_", (space or "").strip().lower()).strip("_")
        if not cleaned:
            raise ElasticsearchError(f"非法图空间名，无法生成索引: {space!r}")
        return f"kg_entity_kw_{cleaned}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        content: str | None = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        try:
            response = self._http.request(
                method,
                path,
                content=content,
                params=params,
                headers={"Content-Type": "application/x-ndjson"} if content else None,
                timeout=timeout or self._timeout,
            )
        except httpx.HTTPError as exc:
            raise ElasticsearchError(f"Elasticsearch 请求失败: {exc}") from exc
        return response

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        try:
            response = self._request(
                method,
                path,
                content=json.dumps(body, ensure_ascii=False) if body is not None else None,
                params=params,
                timeout=timeout,
            )
        except ElasticsearchError:
            raise
        if response.status_code >= 400:
            raise ElasticsearchError(
                f"Elasticsearch {method} {path} → {response.status_code}: {response.text[:300]}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise ElasticsearchError(f"Elasticsearch 响应非 JSON: {response.text[:200]}") from exc

    # ------------------------------------------------------------- 索引管理

    INDEX_SETTINGS: dict[str, Any] = {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "analysis": {
                "tokenizer": {
                    "kw_ngram": {
                        # 只保留字母/数字：换行、标点等是属性边界，gram 不跨界；
                        # 中文按字切 gram，等价 CONTAINS；1 字符关键词无 gram，
                        # 由调用方回退图直查（见 service 层）
                        "type": "ngram",
                        "min_gram": 2,
                        "max_gram": 3,
                        "token_chars": ["letter", "digit"],
                    }
                },
                "analyzer": {
                    "kw_ngram": {"type": "custom", "tokenizer": "kw_ngram", "filter": ["lowercase"]}
                },
            },
        },
        "mappings": {
            "properties": {
                # 排序专用：分页顺序 = entity_type → vid，与图路径一致
                "vid": {"type": "keyword", "index": False},
                "entity_type": {"type": "keyword"},
                # 检索专用：VID + 全量属性值（未截断），ngram 子串匹配
                "search_text": {
                    "type": "text",
                    "analyzer": "kw_ngram",
                    "norms": False,
                    "index_options": "docs",
                },
                # 回放专用：与图直查一致的列表项，只存 _source 不索引
                "item": {"type": "object", "enabled": False},
            }
        },
    }

    def ensure_index(self, space: str) -> None:
        """索引不存在则按模板创建（已存在则不动，幂等）。"""
        name = self.index_name(space)
        response = self._request("HEAD", f"/{name}")
        if response.status_code == 200:
            return
        if response.status_code != 404:
            raise ElasticsearchError(
                f"Elasticsearch HEAD /{name} → {response.status_code}: {response.text[:200]}"
            )
        self._request_json("PUT", f"/{name}", body=self.INDEX_SETTINGS)

    def drop_index(self, space: str) -> bool:
        name = self.index_name(space)
        response = self._request("DELETE", f"/{name}")
        with self._ready_lock:
            self._ready_cache.pop(name, None)
        return response.status_code in (200, 404)

    def refresh(self, space: str) -> None:
        self._request_json("POST", f"/{self.index_name(space)}/_refresh")

    def doc_count(self, space: str) -> int:
        data = self._request_json(
            "POST", f"/{self.index_name(space)}/_count", body={"query": {"match_all": {}}}
        )
        return int(data.get("count") or 0)

    def ready(self, space: str) -> bool:
        """索引已建且非空（同步过）才走 ES；未同步的空间必须回退图直查，
        否则未同步空间会错误地返回 0 命中。"""
        name = self.index_name(space)
        with self._ready_lock:
            cached = self._ready_cache.get(name)
            if cached and cached[1] and time.monotonic() - cached[0] < _READY_TTL_SECONDS:
                return True
        try:
            head = self._request("HEAD", f"/{name}")
            if head.status_code != 200:
                return False
            count = self.doc_count(space)
        except ElasticsearchError as exc:
            logger.warning("ES 就绪探测失败(space=%s): %s", space, exc)
            return False
        ok = count > 0
        if ok:
            with self._ready_lock:
                self._ready_cache[name] = (time.monotonic(), True)
        return ok

    # --------------------------------------------------------------- 写入

    def upsert(self, space: str, docs: list[dict[str, Any]], *, refresh: bool = False) -> int:
        """批量写入。``docs`` 元素需含 ``vid``/``entity_type``/``search_text``/``item``；
        _id = vid，重复同步幂等（覆盖旧文档）。返回成功条数。"""
        if not docs:
            return 0
        name = self.index_name(space)
        lines: list[str] = []
        for doc in docs:
            if not doc.get("vid"):
                raise ElasticsearchError("ES 文档缺少 vid")
            lines.append(
                json.dumps({"index": {"_index": name, "_id": str(doc["vid"])}}, ensure_ascii=False)
            )
            lines.append(json.dumps(doc, ensure_ascii=False))
        body = "\n".join(lines) + "\n"
        data = self._bulk(body, refresh=refresh)
        if data.get("errors"):
            first = next(
                (
                    item.get("index", {}).get("error")
                    for item in data.get("items", [])
                    if item.get("index", {}).get("error")
                ),
                "unknown",
            )
            raise ElasticsearchError(f"ES bulk 部分失败: {first}")
        return len(docs)

    def _bulk(self, body: str, *, refresh: bool = False) -> dict[str, Any]:
        response = self._request(
            "POST",
            "/_bulk",
            content=body,
            params={"refresh": "true"} if refresh else None,
            timeout=_BULK_TIMEOUT_SECONDS,
        )
        if response.status_code >= 400:
            raise ElasticsearchError(
                f"Elasticsearch bulk → {response.status_code}: {response.text[:300]}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise ElasticsearchError(
                f"Elasticsearch bulk 响应非 JSON: {response.text[:200]}"
            ) from exc

    # --------------------------------------------------------------- 查询

    def _match_query(self, keyword: str, entity_type: str | None) -> dict[str, Any]:
        # and：所有 gram 都要在同一 search_text（= 同一实体的 VID/属性值集合）出现，
        # 等价图上 CONTAINS 的 OR 谓词（任一值包含整词）
        clause: dict[str, Any] = {"match": {"search_text": {"query": keyword, "operator": "and"}}}
        if entity_type:
            return {"bool": {"must": clause, "filter": [{"term": {"entity_type": entity_type}}]}}
        return clause

    def counts(self, space: str, keyword: str, *, entity_type: str | None = None) -> dict[str, int]:
        """全量匹配计数：terms 聚合一次拿到每个标签的命中数。"""
        data = self._request_json(
            "POST",
            f"/{self.index_name(space)}/_search",
            body={
                "size": 0,
                "track_total_hits": True,
                "query": self._match_query(keyword, entity_type),
                "aggs": {"by_type": {"terms": {"field": "entity_type", "size": _AGG_BUCKET_SIZE}}},
            },
        )
        buckets = data.get("aggregations", {}).get("by_type", {}).get("buckets", [])
        return {str(bucket["key"]): int(bucket["doc_count"]) for bucket in buckets}

    def page(
        self,
        space: str,
        keyword: str,
        *,
        entity_type: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """按 (entity_type, vid) 稳定排序取页，返回 (items, total)。"""
        data = self._request_json(
            "POST",
            f"/{self.index_name(space)}/_search",
            body={
                "size": int(limit),
                "from": int(offset),
                "track_total_hits": True,
                "query": self._match_query(keyword, entity_type),
                "sort": [{"entity_type": "asc"}, {"vid": "asc"}],
            },
        )
        hits = data.get("hits", {})
        items = [hit["_source"]["item"] for hit in hits.get("hits", []) if hit.get("_source")]
        total = int(hits.get("total", {}).get("value") or 0)
        return items, total


def get_entity_keyword_es() -> EntityKeywordES | None:
    """进程级单例；``ENTITY_SEARCH_ES_URL`` 未配置返回 None（ES 通道关闭）。"""
    global _client

    url = os.environ.get("ENTITY_SEARCH_ES_URL", "").strip()
    if not url:
        return None
    with _client_lock:
        if _client is None:
            _client = EntityKeywordES(
                url, timeout=float(os.environ.get("ENTITY_SEARCH_ES_TIMEOUT", "10"))
            )
        return _client


def reset_entity_keyword_es() -> None:
    """测试用：清空单例并关闭连接。"""
    global _client

    with _client_lock:
        if _client is not None:
            _client.close()
        _client = None
