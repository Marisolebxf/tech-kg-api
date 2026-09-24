"""隔离脚本 SDK：仅通过定长 JSON RPC 调用宿主批准的资源方法。"""

from __future__ import annotations

import json
import sys
import threading
from itertools import count
from typing import Any

MAX_RPC_BYTES = 8 * 1024 * 1024
_RPC_LOCK = threading.Lock()
_RPC_IDS = count(1)


def rpc(resource: str, method: str, args: tuple = (), kwargs: dict | None = None) -> Any:
    with _RPC_LOCK:
        request_id = next(_RPC_IDS)
        message = {
            "type": "rpc",
            "id": request_id,
            "resource": resource,
            "method": method,
            "args": args,
            "kwargs": kwargs or {},
        }
        encoded = json.dumps(message, ensure_ascii=False, allow_nan=False)
        if len((encoded + "\n").encode("utf-8")) > MAX_RPC_BYTES:
            raise ValueError("SDK 请求超过大小限制")
        sys.__stdout__.write(encoded + "\n")
        sys.__stdout__.flush()
        line = sys.__stdin__.readline(MAX_RPC_BYTES + 1)
        if not line or not line.endswith("\n") or len(line.encode("utf-8")) > MAX_RPC_BYTES:
            raise RuntimeError("SDK 响应缺失或超过大小限制")
        response = json.loads(line)
        if not isinstance(response, dict) or response.get("id") != request_id:
            raise RuntimeError("SDK 响应标识不匹配")
        if "error" in response:
            raise RuntimeError(str(response["error"]))
        if "result" not in response:
            raise RuntimeError("SDK 响应缺少结果")
        return response["result"]


class Model(dict):
    """图模型同时支持属性和 JSON 字典访问；不含真实客户端或凭据。"""

    def __getattribute__(self, name):
        if not name.startswith("_") and dict.__contains__(self, name):
            return dict.__getitem__(self, name)
        return dict.__getattribute__(self, name)

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def model_dump(self, **kwargs):
        return dict(self)

    def dict(self, **kwargs):
        return dict(self)


def wrap(value):
    if isinstance(value, list):
        return [wrap(item) for item in value]
    if isinstance(value, dict):
        return Model(
            {
                key: wrap(item) if key in {"items", "nodes", "edges"} else item
                for key, item in value.items()
            }
        )
    return value


class Result:
    def __init__(self, payload):
        self.columns = list(payload.get("columns") or [])
        self.rows = list(payload.get("rows") or [])
        if not self.columns and self.rows and isinstance(self.rows[0], dict):
            self.columns = list(self.rows[0])
        self.rowcount = int(payload.get("rowcount", len(self.rows)))
        self.description = [(key, None, None, None, None, None, None) for key in self.columns]
        self._position = 0
        self._mapping = False

    def mappings(self):
        self._mapping = True
        return self

    def _row(self, row):
        if self._mapping:
            return (
                dict(row) if isinstance(row, dict) else dict(zip(self.columns, row, strict=False))
            )
        return tuple(row.get(key) for key in self.columns) if isinstance(row, dict) else tuple(row)

    def fetchone(self):
        if self._position >= len(self.rows):
            return None
        row = self._row(self.rows[self._position])
        self._position += 1
        return row

    def fetchmany(self, size=1):
        rows = []
        for _ in range(size):
            row = self.fetchone()
            if row is None:
                break
            rows.append(row)
        return rows

    def fetchall(self):
        return self.fetchmany(len(self.rows) - self._position)

    def all(self):
        return self.fetchall()

    def first(self):
        return self.fetchone()

    def scalar(self):
        row = self.fetchone()
        return next(iter(row.values()), None) if isinstance(row, dict) else row[0] if row else None

    def keys(self):
        return list(self.columns)

    def __iter__(self):
        while (row := self.fetchone()) is not None:
            yield row


class MysqlConnection:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement, parameters=None):
        if parameters is not None and not isinstance(parameters, dict):
            raise ValueError("查询参数必须是命名参数字典")
        return Result(rpc("mysql", "query", (str(statement), parameters or {})))

    def close(self):
        pass

    def commit(self):
        pass  # 只读 RPC 不持有远程事务。

    def rollback(self):
        pass

    def cursor(self, *args, **kwargs):
        return MysqlCursor()


class MysqlCursor(MysqlConnection):
    def __init__(self):
        self._result = Result({})

    def execute(self, statement, parameters=None):
        self._result = super().execute(statement, parameters)
        return self._result.rowcount

    @property
    def description(self):
        return self._result.description

    @property
    def rowcount(self):
        return self._result.rowcount

    def fetchone(self):
        return self._result.fetchone()

    def fetchmany(self, size=1):
        return self._result.fetchmany(size)

    def fetchall(self):
        return self._result.fetchall()

    def __iter__(self):
        return iter(self._result)


class MysqlProxy(MysqlConnection):
    @property
    def engine(self):
        return self

    def connect(self):
        return MysqlConnection()

    def begin(self):
        return MysqlConnection()

    def session_scope(self):
        return MysqlConnection()

    def create_session(self):
        return MysqlConnection()

    def session(self):
        return MysqlConnection()


GRAPH_METHODS = (
    "execute_read",
    "execute_query",
    "execute_write",
    "get_node",
    "get_nodes_by_label",
    "paged_nodes_by_label",
    "find_nodes",
    "get_node_edges",
    "get_edge",
    "get_edges_by_type",
    "find_edges",
    "get_neighbours",
    "shortest_path",
    "labels",
    "edge_types",
    "node_count",
    "edge_count",
    "label_count",
    "stats_snapshot",
    "stats_tag_counts",
    "create_node",
    "merge_node",
    "update_node",
    "delete_node",
    "create_edge",
    "merge_edge",
    "update_edge",
    "delete_edge",
    "batch_create_nodes",
    "batch_create_edges",
)
MILVUS_METHODS = (
    "query",
    "search",
    "get",
    "list_collections",
    "has_collection",
    "describe_collection",
    "get_collection_stats",
    "insert",
    "upsert",
    "delete",
    "flush",
)
SEMANTIC_METHODS = (
    "health",
    "catalog",
    "general_entities",
    "research_entities",
    "domain_entities",
    "classify_zh",
    "classify_en",
    "classify_domain",
    "keywords_zh",
    "keywords_en",
    "concept_definitions",
    "research_questions",
    "moves_zh",
    "moves_en",
    "fund_moves",
    "citation_intent",
    "citation_sentiment",
    "relation_extract",
    "deep_cluster",
    "cluster_labels",
    "structured_review",
)


def _method(resource, method):
    def call(self, *args, **kwargs):
        if any(
            key in kwargs
            for key in (
                "db_name",
                "database",
                "using_database",
                "uri",
                "token",
                "api_key",
                "base_url",
                "space",
            )
        ):
            raise ValueError("不允许覆盖 SDK 资源归属或连接参数")
        value = rpc(resource, method, args, kwargs)
        if resource == "graph":
            if method in ("execute_read", "execute_query", "execute_write"):
                value = {"records": [], "columns": [], "summary": {}, **(value or {})}
            return wrap(value)
        return value

    return call


def make_proxy(resource: str, semantic_type=None):
    if resource == "mysql":
        return MysqlProxy()
    methods = {
        "graph": GRAPH_METHODS,
        "milvus": MILVUS_METHODS,
        "llm": ("synthesize", "synthesize_json"),
        "embedding": ("embed", "embed_one"),
        "semantic": SEMANTIC_METHODS,
    }[resource]
    attrs = {name: _method(resource, name) for name in methods}
    if resource == "semantic" and semantic_type is not None:
        for name in (
            "entities_of",
            "data_of",
            "definitions_of",
            "questions_of",
            "record_id_of",
            "triples_of",
            "keywords_of",
            "classifications_of",
            "clusters_of",
            "cluster_labels_of",
        ):
            attrs[name] = staticmethod(getattr(semantic_type, name))
    return type(f"{resource.title()}Proxy", (), attrs)()


def public_context(raw):
    allowed = (
        "stepId",
        "attempt",
        "prevOutputs",
        "executionId",
        "taskId",
        "definitionId",
        "watermark",
        "checkpoint",
        "source",
    )
    result = {key: raw[key] for key in allowed if key in raw}
    result["_sandbox"] = True
    for resource in ("mysql", "graph", "milvus", "llm", "embedding", "semantic"):
        value = raw.get(resource)
        result[resource] = bool(value) and (
            not isinstance(value, dict) or value.get("available", True) is True
        )
    return result
