"""脚本数据访问溯源采集器（观测式，非管控）。

kg_sdk.Context 构造 mysql/graph/milvus/llm/embedding 客户端时包一层观测代理，
把脚本实际访问的资源记录到模块级 ``_STATE``，并同步 append 到 sidecar JSONL
（路径来自 ``KG_ACCESS_LOG`` env，由 activity 传入临时文件）。每条事件
open→write→close，脚本超时被 kill 也能留账。

本模块被两种方式导入：子进程里作为顶层 ``access``（PYTHONPATH 含 backend/sdk），
worker/测试里作为 ``sdk.access``。不依赖 kg_sdk，避免循环导入。
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any

_LOCK = threading.Lock()

_NGQL_QUERY_LIMIT = 10
_SNIPPET_LIMIT = 200


class _AccessState:
    """访问事件累积器；apply 一条事件，render 出 JSON 可序列化报告。"""

    def __init__(self) -> None:
        self.mysql: dict[str, dict[str, dict[str, Any]]] = {}
        self.graph: dict[str, dict[str, dict[str, Any]]] = {}
        self.milvus: dict[str, dict[str, Any]] = {}
        self.llm: dict[str, dict[str, int]] = {}
        self.embedding: dict[str, dict[str, int]] = {}
        self.unparsed: dict[str, Any] = {"count": 0, "last": ""}
        self.ngql: dict[str, Any] = {"ops": set(), "count": 0, "queries": []}

    def apply(self, event: dict[str, Any]) -> None:
        kind = event.get("t")
        if kind == "mysql":
            table = event.get("table")
            if not table:
                return
            db = event.get("db") or "_"
            bucket = self.mysql.setdefault(db, {}).setdefault(
                table, {"ops": set(), "statements": 0}
            )
            bucket["ops"].add(event.get("op") or "OTHER")
            bucket["statements"] += 1
        elif kind == "mysql_unparsed":
            self.unparsed["count"] += 1
            self.unparsed["last"] = str(event.get("sql") or "")[:_SNIPPET_LIMIT]
        elif kind == "graph":
            name = event.get("name")
            if not name:
                return
            bucket = self.graph.setdefault(event.get("kind") or "tag", {}).setdefault(
                name, {"ops": set(), "count": 0}
            )
            bucket["ops"].add(event.get("op") or "read")
            bucket["count"] += 1
        elif kind == "ngql":
            self.ngql["ops"].add(event.get("op") or "query")
            self.ngql["count"] += 1
            query = str(event.get("query") or "")[:120]
            if query and query not in self.ngql["queries"]:
                if len(self.ngql["queries"]) >= _NGQL_QUERY_LIMIT:
                    self.ngql["queries"].pop(0)
                self.ngql["queries"].append(query)
        elif kind == "milvus":
            collection = event.get("collection")
            if not collection:
                return
            bucket = self.milvus.setdefault(collection, {"ops": set(), "count": 0})
            bucket["ops"].add(event.get("op") or "read")
            bucket["count"] += 1
        elif kind in ("llm", "embedding"):
            model = event.get("model") or "unknown"
            bucket = getattr(self, kind).setdefault(model, {"calls": 0, "failures": 0})
            bucket["calls"] += 1
            if not event.get("ok", True):
                bucket["failures"] += 1

    def render(self) -> dict[str, Any]:
        def render_counted(names: dict[str, dict[str, Any]]) -> dict[str, Any]:
            return {
                name: {"ops": sorted(v["ops"]), "count": v["count"]} for name, v in names.items()
            }

        return {
            "mysql": {
                db: {
                    table: {"ops": sorted(v["ops"]), "statements": v["statements"]}
                    for table, v in tables.items()
                }
                for db, tables in self.mysql.items()
            }
            | {"_unparsed": dict(self.unparsed)},
            "graph": {kind: render_counted(names) for kind, names in self.graph.items()}
            | {
                "_ngql": {
                    "ops": sorted(self.ngql["ops"]),
                    "count": self.ngql["count"],
                    "queries": list(self.ngql["queries"]),
                }
            },
            "milvus": render_counted(self.milvus),
            "llm": {model: dict(v) for model, v in self.llm.items()},
            "embedding": {model: dict(v) for model, v in self.embedding.items()},
        }


_STATE = _AccessState()


def _append_sidecar(event: dict[str, Any]) -> None:
    path = os.environ.get("KG_ACCESS_LOG")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


def _emit(event: dict[str, Any]) -> None:
    with _LOCK:
        _STATE.apply(event)
    _append_sidecar(event)


# ---- MySQL ----

_OP_BY_CLASS_NAME = {
    "Select": "SELECT",
    "Union": "SELECT",
    "Insert": "INSERT",
    "Update": "UPDATE",
    "Delete": "DELETE",
    "Create": "DDL",
    "Drop": "DDL",
    "Alter": "DDL",
    "TruncateTable": "DDL",
    "Truncate": "DDL",
}


def record_mysql_statement(sql: str, db: str | None = None) -> None:
    """解析 SQL 记录访问的表（JOIN/子查询/CTE/INSERT INTO 均覆盖）。

    sqlglot 解析失败降级记 ``_unparsed`` 计数 + 原文片段，绝不抛错。
    """
    try:
        if not sql or not sql.strip():
            return
        import sqlglot
        from sqlglot import expressions as exp

        tree = sqlglot.parse_one(sql)
    except Exception:  # noqa: BLE001
        _emit({"t": "mysql_unparsed", "sql": str(sql)[:_SNIPPET_LIMIT]})
        return
    try:
        op = _OP_BY_CLASS_NAME.get(type(tree).__name__, "OTHER")
        cte_names = {cte.alias_or_name for cte in tree.find_all(exp.CTE)}
        seen: set[tuple[str, str]] = set()
        for table in tree.find_all(exp.Table):
            name = table.name
            if not name or (name in cte_names and not table.db):
                continue
            table_db = table.db or db or "_"
            if (table_db, name) in seen:
                continue
            seen.add((table_db, name))
            _emit({"t": "mysql", "db": table_db, "table": name, "op": op})
    except Exception:  # noqa: BLE001
        _emit({"t": "mysql_unparsed", "sql": str(sql)[:_SNIPPET_LIMIT]})


def observe_mysql_client(client: Any, default_db: str | None) -> Any:
    """挂 SQLAlchemy ``before_cursor_execute`` 钩子，记录所有经过 engine 的 SQL。"""
    try:
        from sqlalchemy import event as sa_event

        engine = client.engine

        def _record(conn: Any, cursor: Any, statement: Any, *args: Any, **kwargs: Any) -> None:
            try:
                record_mysql_statement(str(statement), db=default_db)
            except Exception:  # noqa: BLE001
                pass

        sa_event.listen(engine, "before_cursor_execute", _record)
    except Exception:  # noqa: BLE001
        pass
    return client


# ---- graph 代理 ----

_GRAPH_READ_PREFIXES = ("get_", "find_", "list_")
_GRAPH_READ_NAMES = {"node_count", "edge_count", "labels", "edge_types", "shortest_path"}
_GRAPH_WRITE_PREFIXES = ("create_", "merge_", "update_", "delete_", "batch_", "drop_")
# 方法名 → (tag/edge, label/edge_type 所在位置参数下标)
_GRAPH_ARG_POS = {
    "create_node": ("tag", 0),
    "merge_node": ("tag", 0),
    "find_nodes": ("tag", 0),
    "get_nodes_by_label": ("tag", 0),
    "batch_create_nodes": ("tag", 1),
    "create_edge": ("edge", 2),
    "merge_edge": ("edge", 2),
    "get_edges_by_type": ("edge", 0),
    "find_edges": ("edge", 0),
    "batch_create_edges": ("edge", 1),
}


def _graph_call_op(method: str) -> str | None:
    if method in ("execute_query", "execute_read", "execute_write"):
        return None  # 单独按 nGQL 记录
    if method.startswith(_GRAPH_READ_PREFIXES) or method in _GRAPH_READ_NAMES:
        return "read"
    if method.startswith(_GRAPH_WRITE_PREFIXES):
        return "write"
    return None


def _record_graph_call(method: str, args: tuple, kwargs: dict) -> None:
    try:
        if method in ("execute_query", "execute_read", "execute_write"):
            query = kwargs.get("query")
            if query is None and args:
                query = args[0]
            op = {"execute_query": "query", "execute_read": "read", "execute_write": "write"}[
                method
            ]
            _emit({"t": "ngql", "op": op, "query": str(query or "")})
            return
        op = _graph_call_op(method)
        if op is None:
            return
        pos = _GRAPH_ARG_POS.get(method)
        kind = pos[0] if pos else ("edge" if "edge" in method else "tag")
        if pos and len(args) > pos[1]:
            _record_graph_names(kind, args[pos[1]], op)
        if "edge_type" in kwargs:
            _record_graph_names("edge", kwargs.get("edge_type"), op)
        elif kind == "tag":
            for key in ("labels", "label"):
                if key in kwargs:
                    _record_graph_names("tag", kwargs.get(key), op)
    except Exception:  # noqa: BLE001
        pass


def _record_graph_names(kind: str, value: Any, op: str) -> None:
    if isinstance(value, str) and value:
        _emit({"t": "graph", "kind": kind, "name": value, "op": op})
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            if isinstance(item, str) and item:
                _emit({"t": "graph", "kind": kind, "name": item, "op": op})


class ObservedGraphClient:
    """TRSGraphClient 观测代理：转发原客户端，按方法名记录 tag/edge 读写。"""

    def __init__(self, client: Any) -> None:
        object.__setattr__(self, "_observed_client", client)

    def __getattr__(self, name: str) -> Any:
        client = object.__getattribute__(self, "_observed_client")
        attr = getattr(client, name)
        if not callable(attr):
            return attr

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            _record_graph_call(name, args, kwargs)
            return attr(*args, **kwargs)

        return wrapper


# ---- milvus 代理 ----


def _milvus_op(method: str) -> str | None:
    if method.startswith(("insert", "upsert", "delete")):
        return "write"
    if method.startswith(("query", "search", "get", "list")):
        return "read"
    return None


class ObservedMilvusClient:
    """pymilvus.MilvusClient 观测代理：从 collection_name 参数记 collection 读写。"""

    def __init__(self, client: Any) -> None:
        object.__setattr__(self, "_observed_client", client)

    def __getattr__(self, name: str) -> Any:
        client = object.__getattribute__(self, "_observed_client")
        attr = getattr(client, name)
        if not callable(attr):
            return attr

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                op = _milvus_op(name)
                collection = kwargs.get("collection_name") or kwargs.get("collection")
                if not collection and args and isinstance(args[0], str):
                    collection = args[0]
                if op and collection:
                    _emit({"t": "milvus", "collection": collection, "op": op})
            except Exception:  # noqa: BLE001
                pass
            return attr(*args, **kwargs)

        return wrapper


# ---- llm / embedding 代理 ----


class _ObservedModelClient:
    """LLMClient / EmbeddingClient 观测代理：记模型名、调用次数、成败。

    infra.llm 的降级约定是失败返回 None 而非抛错，故 None 视为失败。
    """

    _bucket = "llm"

    def __init__(self, client: Any) -> None:
        object.__setattr__(self, "_observed_client", client)

    def __getattr__(self, name: str) -> Any:
        client = object.__getattribute__(self, "_observed_client")
        attr = getattr(client, name)
        if not callable(attr):
            return attr

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                model = getattr(client, "model", None) or "unknown"
            except Exception:  # noqa: BLE001
                model = "unknown"
            try:
                result = attr(*args, **kwargs)
            except Exception:
                _emit({"t": self._bucket, "model": model, "ok": False})
                raise
            _emit({"t": self._bucket, "model": model, "ok": result is not None})
            return result

        return wrapper


class ObservedLLMClient(_ObservedModelClient):
    _bucket = "llm"


class ObservedEmbeddingClient(_ObservedModelClient):
    _bucket = "embedding"


# ---- 汇总 / sidecar ----


def access_report() -> dict[str, Any]:
    """当前累积的访问报告（ops set 转 sorted list）。"""
    with _LOCK:
        return _STATE.render()


def reset_access_report() -> None:
    """测试用：清空累积状态（与 reset_current_context 对称）。"""
    global _STATE
    with _LOCK:
        _STATE = _AccessState()


def flush_access_sidecar() -> None:
    """把内存汇总报告作为最后一行 snapshot 写入 sidecar（crash 前的兜底留账）。"""
    _append_sidecar({"t": "report", "report": access_report()})


def report_from_sidecar(path: str | None) -> dict[str, Any] | None:
    """重放 sidecar JSONL 生成报告；文件缺失/全损坏返回 None。"""
    if not path or not os.path.exists(path):
        return None
    state = _AccessState()
    final_report: dict[str, Any] | None = None
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                if not isinstance(event, dict):
                    continue
                if event.get("t") == "report":
                    report = event.get("report")
                    if isinstance(report, dict):
                        final_report = report
                else:
                    state.apply(event)
    except Exception:  # noqa: BLE001
        return None
    if (
        final_report is None
        and not state.mysql
        and not state.graph
        and not state.milvus
        and not state.llm
        and not state.embedding
    ):
        return None
    report = state.render()
    if final_report is not None:
        report = merge_access_reports(report, final_report) or report
    return report


def merge_access_reports(
    primary: dict[str, Any] | None, secondary: dict[str, Any] | None
) -> dict[str, Any] | None:
    """合并两份报告（同一子进程运行的两次快照）：ops 并集、计数取 max、primary 优先。

    典型场景：sidecar 重放报告（primary）+ stdout 回传报告（secondary）。
    """
    if not primary and not secondary:
        return None
    if not primary:
        return secondary
    if not secondary:
        return primary

    def merge_counted(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key in set(a) | set(b):
            va = a.get(key) or {}
            vb = b.get(key) or {}
            out[key] = {
                "ops": sorted(set(va.get("ops", ())) | set(vb.get("ops", ()))),
                "count": max(va.get("count", 0), vb.get("count", 0)),
            }
        return out

    def merge_calls(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key in set(a) | set(b):
            va = a.get(key) or {}
            vb = b.get(key) or {}
            out[key] = {
                "calls": max(va.get("calls", 0), vb.get("calls", 0)),
                "failures": max(va.get("failures", 0), vb.get("failures", 0)),
            }
        return out

    merged: dict[str, Any] = {}

    ma = primary.get("mysql") or {}
    mb = secondary.get("mysql") or {}
    mysql: dict[str, Any] = {}
    for db in (set(ma) | set(mb)) - {"_unparsed"}:
        ta = ma.get(db) or {}
        tb = mb.get(db) or {}
        for table in set(ta) | set(tb):
            va = ta.get(table) or {}
            vb = tb.get(table) or {}
            mysql.setdefault(db, {})[table] = {
                "ops": sorted(set(va.get("ops", ())) | set(vb.get("ops", ()))),
                "statements": max(va.get("statements", 0), vb.get("statements", 0)),
            }
    ua = ma.get("_unparsed") or {}
    ub = mb.get("_unparsed") or {}
    mysql["_unparsed"] = {
        "count": max(ua.get("count", 0), ub.get("count", 0)),
        "last": ua.get("last") or ub.get("last") or "",
    }
    merged["mysql"] = mysql

    ga = primary.get("graph") or {}
    gb = secondary.get("graph") or {}
    graph: dict[str, Any] = {}
    for kind in (set(ga) | set(gb)) - {"_ngql"}:
        graph[kind] = merge_counted(ga.get(kind) or {}, gb.get(kind) or {})
    na = ga.get("_ngql") or {}
    nb = gb.get("_ngql") or {}
    graph["_ngql"] = {
        "ops": sorted(set(na.get("ops", ())) | set(nb.get("ops", ()))),
        "count": max(na.get("count", 0), nb.get("count", 0)),
        "queries": na.get("queries") or nb.get("queries") or [],
    }
    merged["graph"] = graph

    merged["milvus"] = merge_counted(primary.get("milvus") or {}, secondary.get("milvus") or {})
    merged["llm"] = merge_calls(primary.get("llm") or {}, secondary.get("llm") or {})
    merged["embedding"] = merge_calls(
        primary.get("embedding") or {}, secondary.get("embedding") or {}
    )
    return merged
