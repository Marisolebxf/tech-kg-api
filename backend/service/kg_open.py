"""对外图查询：目录白名单、只读查询、稳定排序和绑定筛选条件的 keyset 游标。

不修改公共图客户端的既有分页语义。全部 nGQL 由服务端生成；不回退无索引全扫。
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
from typing import Any

from infra.graph_db.exceptions import GraphRequestError

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}\Z")
QUERY_TIMEOUT_SECONDS = 20


class OpenQueryError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def identifier(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise OpenQueryError(f"不合法的类型或属性名: {value}")
    return f"`{value}`"


def literal(value: Any) -> str:
    if isinstance(value, float) and not math.isfinite(value):
        raise OpenQueryError("数值必须有限")
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def entity_payload(vertex: dict[str, Any]) -> dict[str, Any]:
    labels = list(vertex.get("labels") or [])
    properties = dict(vertex.get("properties") or {})
    return {
        "id": str(vertex["id"]),
        "type": labels[0] if labels else "",
        "types": labels,
        "name": str(properties.get("name") or properties.get("title") or ""),
        "properties": properties,
    }


def edge_payload(record: dict[str, Any]) -> dict[str, Any]:
    edge = record.get("e") or {}
    # 使用图库明确投影的端点与 rank，不解析可能含 @ / -> 的业务 VID。
    source, target = str(record["src"]), str(record["dst"])
    rank = int(record["edge_rank"])
    edge_type = edge["type"]
    return {
        "id": json.dumps(
            [edge_type, source, target, rank], ensure_ascii=False, separators=(",", ":")
        ),
        "type": edge_type,
        "source": source,
        "target": target,
        "rank": rank,
        "properties": dict(edge.get("properties") or {}),
    }


def _scope_key(scope: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(scope, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def encode_cursor(scope: dict[str, Any], after: list[Any]) -> str:
    raw = json.dumps(
        {"v": 1, "scope": _scope_key(scope), "after": after}, ensure_ascii=False
    ).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(token: str, scope: dict[str, Any], kinds: tuple[type, ...]) -> list[Any] | None:
    if not token:
        return None
    try:
        if len(token) > 4096:
            raise ValueError
        raw = base64.b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True)
        data = json.loads(raw)
        after = data["after"]
        if type(data["v"]) is not int or data["v"] != 1 or data["scope"] != _scope_key(scope):
            raise ValueError
        if not isinstance(after, list) or len(after) != len(kinds):
            raise ValueError
        if any(type(value) is not kind for value, kind in zip(after, kinds, strict=True)):
            raise ValueError
        if any(isinstance(value, str) and len(value) > 256 for value in after):
            raise ValueError
        if any(type(value) is int and not -(2**63) <= value < 2**63 for value in after):
            raise ValueError
        return after
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
        raise OpenQueryError("游标无效或与空间、接口、筛选条件不一致") from exc


def _after_predicate(columns: list[str], after: list[Any] | None) -> str:
    if after is None:
        return ""
    return " OR ".join(
        "("
        + " AND ".join(
            [f"{columns[j]} == {literal(after[j])}" for j in range(i)]
            + [f"{column} > {literal(after[i])}"]
        )
        + ")"
        for i, column in enumerate(columns)
    )


class OpenGraphQueries:
    def __init__(self, client: Any, catalog: dict[str, Any], space: str):
        self.client, self.catalog, self.space = client, catalog, space

    def entity_type(self, name: str) -> dict[str, Any]:
        identifier(name)
        for item in self.catalog["entityTypes"]:
            if item["name"] == name:
                return item
        raise OpenQueryError(f"实体类型不存在: {name}", 404)

    def relation_type(self, name: str) -> dict[str, Any]:
        identifier(name)
        for item in self.catalog["relationTypes"]:
            if item["name"] == name:
                return item
        raise OpenQueryError(f"关系类型不存在: {name}", 404)

    def execute(self, query: str) -> list[dict[str, Any]]:
        try:
            return self.client.execute_read(query, timeout=QUERY_TIMEOUT_SECONDS).records or []
        except GraphRequestError as exc:
            message = str(exc).lower()
            if "no index" in message or "no valid index" in message:
                raise OpenQueryError(
                    "查询所需图索引未就绪，请联系管理员创建并重建索引", 503
                ) from exc
            raise

    def stats(self) -> dict[str, Any] | None:
        try:
            return self.client.stats_snapshot()
        except GraphRequestError as exc:
            if "no any stats" in str(exc).lower() or "no stats" in str(exc).lower():
                return None
            raise

    def lookup(self, ids: list[str]) -> dict[str, dict[str, Any]]:
        unique = list(dict.fromkeys(ids))
        found: dict[str, dict[str, Any]] = {}
        for start in range(0, len(unique), 100):
            values = ", ".join(literal(value) for value in unique[start : start + 100])
            rows = self.execute(f"FETCH PROP ON * {values} YIELD vertex AS v")
            for row in rows:
                vertex = row.get("v")
                if isinstance(vertex, dict) and vertex.get("id") is not None:
                    payload = entity_payload(vertex)
                    found[payload["id"]] = payload
        return found

    def page(self, records, limit, scope, key, field):
        has_more = len(records) > limit
        items = records[:limit]
        return {
            field: items,
            "limit": limit,
            "hasMore": has_more,
            "nextCursor": encode_cursor(scope, key(items[-1])) if has_more else "",
        }

    def entities(
        self,
        name: str,
        limit: int,
        cursor: str = "",
        offset: int = 0,
    ) -> dict[str, Any]:
        self.entity_type(name)
        scope = {
            "space": self.space,
            "kind": "entities",
            "name": name,
        }
        after = decode_cursor(cursor, scope, (str,))
        if cursor and offset:
            raise OpenQueryError("cursor 与非零 offset 不能同时使用")
        query = f"LOOKUP ON {identifier(name)}"
        query += " YIELD vertex AS v | YIELD $-.v AS v, id($-.v) AS vid"
        if after:
            query += f" WHERE id($-.v) > {literal(after[0])}"
        query += f" | ORDER BY $-.vid | LIMIT {limit + 1} OFFSET {offset}"
        rows = self.execute(query)
        entities = [entity_payload(row["v"]) for row in rows]
        data = self.page(entities, limit, scope, lambda item: [item["id"]], "entities")
        data.update(entityType=name, offset=offset)
        return data

    def edges(
        self,
        name: str,
        limit: int,
        cursor: str = "",
        offset: int = 0,
        include_entities: bool = True,
    ) -> dict[str, Any]:
        self.relation_type(name)
        scope = {
            "space": self.space,
            "kind": "edges",
            "name": name,
        }
        after = decode_cursor(cursor, scope, (str, str, int))
        if cursor and offset:
            raise OpenQueryError("cursor 与非零 offset 不能同时使用")
        query = (
            f"LOOKUP ON {identifier(name)} YIELD edge AS e, src(edge) AS src, "
            "dst(edge) AS dst, rank(edge) AS edge_rank"
        )
        query += " | YIELD $-.e AS e, $-.src AS src, $-.dst AS dst, $-.edge_rank AS edge_rank"
        predicate = _after_predicate(["$-.src", "$-.dst", "$-.edge_rank"], after)
        if predicate:
            query += f" WHERE {predicate}"
        query += f" | ORDER BY $-.src, $-.dst, $-.edge_rank | LIMIT {limit + 1} OFFSET {offset}"
        edges = [edge_payload(row) for row in self.execute(query)]
        data = self.page(
            edges,
            limit,
            scope,
            lambda item: [item["source"], item["target"], item["rank"]],
            "edges",
        )
        if include_entities and data["edges"]:
            ids = [vid for edge in data["edges"] for vid in (edge["source"], edge["target"])]
            found = self.lookup(ids)
            for edge in data["edges"]:
                edge.update(
                    sourceEntity=found.get(edge["source"]), targetEntity=found.get(edge["target"])
                )
        data.update(relationType=name, offset=offset)
        return data
