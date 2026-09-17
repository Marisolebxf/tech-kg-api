"""Schema DDL nGQL 构建与执行。

创建实体/关系 Schema 时，在目标图空间执行 ``CREATE TAG/EDGE IF NOT EXISTS``
DDL，使 catalog 与图结构一致。图空间默认取 ``TRS_GRAPH_SPACE``，创建 Schema
时可显式指定其他空间。
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Any

from infra.graph_db import GraphRequestError, get_space_client, get_trs_graph_client
from infra.graph_db.config import TRSGraphSettings

logger = logging.getLogger(__name__)

NEBULA_SCALAR_TYPES = {"string", "int64", "double", "bool", "date", "datetime", "geo"}
FIXED_STRING_RE = re.compile(r"^fixed_string\((\d+)\)$")
# Nebula FIXED_STRING 长度上限 1024（FBSTRING 实现），0 无意义
FIXED_STRING_MAX_LENGTH = 1024

DDL_MAX_RETRIES = 3


def default_graph_space() -> str:
    # 与默认 client 的真实空间同源（service.graph_space.default_graph_space 同口径）。
    # 不能再用独立的 env 回退字面量：TRS_GRAPH_SPACE 未设时 TRSGraphSettings 回退
    # "dev"，若这里回退 "techkg"，显式指定默认空间名的 Schema DDL 会被 _ddl_client
    # 静默路由进默认空间（目录登记的空间与 DDL 实际落点不一致）。
    return TRSGraphSettings.from_env().space


def list_graph_spaces() -> list[str]:
    """列出图服务全部空间（经默认 client，测试可 monkeypatch 该模块入口）。"""
    return get_trs_graph_client().list_spaces()


def is_valid_data_type(data_type: str) -> bool:
    match = FIXED_STRING_RE.fullmatch(data_type)
    if not match:
        return data_type in NEBULA_SCALAR_TYPES
    return 1 <= int(match.group(1)) <= FIXED_STRING_MAX_LENGTH


def build_create_ddl(kind: str, name: str, properties: list[dict[str, Any]]) -> str:
    """构建 ``CREATE TAG/EDGE IF NOT EXISTS`` nGQL。

    ``kind``: ``entity`` → TAG，``relation`` → EDGE。
    ``properties``: ``[{name, data_type, required, ...}]``。
    """
    keyword = "TAG" if kind == "entity" else "EDGE"
    parts: list[str] = []
    for prop in properties:
        col = f"{prop['name']} {prop['data_type']}"
        if prop.get("required"):
            col += " NOT NULL"
        parts.append(col)
    body = ", ".join(parts)
    return f"CREATE {keyword} IF NOT EXISTS {name}({body});"


def _ddl_client(graph_space: str | None):
    # 默认空间走默认 client（env 指向、可被测试 monkeypatch）；
    # 仅显式指定的其他空间才按空间缓存 client
    if not graph_space or graph_space == default_graph_space():
        return get_trs_graph_client()
    return get_space_client(graph_space)


def execute_schema_ddl(ddl: str, graph_space: str | None = None) -> tuple[str, str | None]:
    """执行 DDL，返回 ``(status, error)``；``status`` ∈ {"succeeded","failed"}。

    幂等（``IF NOT EXISTS``），失败重试最多 3 次应对图空间 DDL 传播延迟。
    """
    last_err: str | None = None
    try:
        client = _ddl_client(graph_space)
    except Exception as exc:  # noqa: BLE001
        logger.exception("获取 graph client 失败")
        return "failed", f"图服务连接失败: {exc}"

    for attempt in range(DDL_MAX_RETRIES):
        try:
            client.execute_write(ddl)
            return "succeeded", None
        except GraphRequestError as exc:
            last_err = str(exc)
            logger.warning("DDL 执行失败（第 %d 次）: %s", attempt + 1, last_err)
            if attempt < DDL_MAX_RETRIES - 1:
                time.sleep(1 + attempt)
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            logger.exception("DDL 执行异常")
            break
    return "failed", last_err


def run_schema_ddl(
    kind: str,
    name: str,
    properties: list[dict[str, Any]],
    graph_space: str | None = None,
) -> dict[str, Any]:
    """构建并执行 DDL，返回 ``{statement, status, error, executed_at}``。"""
    ddl = build_create_ddl(kind, name, properties)
    status, error = execute_schema_ddl(ddl, graph_space)
    return {
        "statement": ddl,
        "status": status,
        "error": error,
        "executed_at": datetime.now().isoformat() if status == "succeeded" else None,
    }


def build_alter_add_ddl(kind: str, name: str, prop: dict[str, Any]) -> str:
    """构建 ``ALTER TAG/EDGE <name> ADD (<prop> <type>)`` nGQL。

    Nebula 的 ALTER ADD 不支持 NOT NULL——新增属性在图里一律可空
    （目录保留 required 口径，仅约束语义）。
    """
    keyword = "TAG" if kind == "entity" else "EDGE"
    return f"ALTER {keyword} {name} ADD ({prop['name']} {prop['data_type']});"


def run_alter_add_ddl(
    kind: str,
    name: str,
    prop: dict[str, Any],
    graph_space: str | None = None,
) -> dict[str, Any]:
    """构建并执行属性新增 DDL，返回 ``{statement, status, error, executed_at}``。"""
    ddl = build_alter_add_ddl(kind, name, prop)
    status, error = execute_schema_ddl(ddl, graph_space)
    return {
        "statement": ddl,
        "status": status,
        "error": error,
        "executed_at": datetime.now().isoformat() if status == "succeeded" else None,
    }


def build_alter_drop_ddl(kind: str, name: str, prop_name: str) -> str:
    """构建 ``ALTER TAG/EDGE <name> DROP (<prop>)`` nGQL（物理删列连带全量数据）。"""
    keyword = "TAG" if kind == "entity" else "EDGE"
    return f"ALTER {keyword} {name} DROP ({prop_name});"


def run_alter_drop_ddl(
    kind: str,
    name: str,
    prop_name: str,
    graph_space: str | None = None,
) -> dict[str, Any]:
    """构建并执行属性删除 DDL，返回 ``{statement, status, error, executed_at}``。"""
    ddl = build_alter_drop_ddl(kind, name, prop_name)
    status, error = execute_schema_ddl(ddl, graph_space)
    return {
        "statement": ddl,
        "status": status,
        "error": error,
        "executed_at": datetime.now().isoformat() if status == "succeeded" else None,
    }


def describe_schema_columns(
    kind: str, name: str, graph_space: str | None = None
) -> list[str] | None:
    """``DESCRIBE TAG/EDGE`` 列出图库属性列名；对象不存在/查询失败返回 ``None``。"""
    keyword = "TAG" if kind == "entity" else "EDGE"
    try:
        client = _ddl_client(graph_space)
        result = client.execute_query(f"DESCRIBE {keyword} {name};")
    except Exception as exc:  # noqa: BLE001
        logger.warning("DESCRIBE %s %s 失败: %s", keyword, name, exc)
        return None
    columns: list[str] = []
    for record in result.records or []:
        if isinstance(record, dict):
            field = record.get("Field")
            if field:
                columns.append(str(field))
    return columns


def _quote_vid(value: Any) -> str:
    """nGQL 字符串 VID 字面量：转义反斜杠与双引号后包双引号。"""
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def _graph_type_names(kind: str, client: Any) -> set[str] | None:
    """``SHOW TAGS/EDGES`` 列出图空间已有类型名；查询失败返回 ``None``（无法判定）。"""
    query = "SHOW TAGS;" if kind == "entity" else "SHOW EDGES;"
    try:
        result = client.execute_query(query)
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s 失败: %s", query, exc)
        return None
    names: set[str] = set()
    for record in result.records or []:
        if isinstance(record, dict):
            name = record.get("Name")
            if name:
                names.add(str(name))
    return names


# 批量 DELETE 单条语句打包的点/边数上限（防超长语句）
BULK_DELETE_CHUNK = 256


def delete_schema_graph_data(
    kind: str, name: str, graph_space: str | None = None
) -> dict[str, Any]:
    """删除图空间中该 Schema 的全部数据并 ``DROP TAG/EDGE IF EXISTS``（真删，不可逆）。

    删除 Schema 目录前的图数据清理：按类型分页枚举存量点/边，nGQL 批量
    ``DELETE VERTEX`` / ``DELETE EDGE`` 物理删除，随后 DROP 类型定义。
    类型不存在（创建时 DDL 未执行过）则跳过数据删除，幂等可重试。
    返回 ``{status, error, typeExisted, verticesDeleted, edgesDeleted, dropStatement}``。
    """
    keyword = "TAG" if kind == "entity" else "EDGE"
    result: dict[str, Any] = {
        "status": "succeeded",
        "error": None,
        "typeExisted": True,
        "verticesDeleted": 0,
        "edgesDeleted": 0,
        "dropStatement": None,
    }
    try:
        client = _ddl_client(graph_space)
    except Exception as exc:  # noqa: BLE001
        result.update(status="failed", error=f"图服务连接失败: {exc}")
        return result

    existing = _graph_type_names(kind, client)
    if existing is not None and name not in existing:
        # 图库里本就没有该 TAG/EDGE：无数据可删，也无需 DROP
        result["typeExisted"] = False
        return result

    try:
        if kind == "entity":
            result["verticesDeleted"] = _delete_all_vertices(client, name)
        else:
            result["edgesDeleted"] = _delete_all_edges(client, name)
    except Exception as exc:  # noqa: BLE001
        logger.exception("删除图数据失败: %s %s", keyword, name)
        result.update(status="failed", error=f"图数据删除失败: {exc}")
        return result

    drop = f"DROP {keyword} IF EXISTS {name};"
    status, error = execute_schema_ddl(drop, graph_space)
    result["dropStatement"] = drop
    if status != "succeeded":
        result.update(status="failed", error=f"DROP {keyword} 失败: {error}")
    return result


def _delete_all_vertices(client: Any, label: str) -> int:
    """分页枚举 TAG 全部点并批量 ``DELETE VERTEX``，返回删除数。

    边删边取：已删除的点从枚举结果消失、剩余点前移，因此每页固定取
    offset=0，直到取空（用 offset 递增会跳过前移上来的剩余点）。
    """
    deleted = 0
    prev_first: str | None = None
    while True:
        page = client.get_nodes_by_label(label, limit=BULK_DELETE_CHUNK, offset=0)
        if not page.items:
            break
        first = str(page.items[0].id)
        if first == prev_first:
            # 删除未生效（枚举结果没变）：报错退出，避免死循环
            raise RuntimeError(f"DELETE VERTEX 未生效，仍枚举到点 {first}")
        prev_first = first
        vids = [_quote_vid(node.id) for node in page.items]
        client.execute_write(f"DELETE VERTEX {', '.join(vids)};")
        deleted += len(vids)
    return deleted


def _delete_all_edges(client: Any, edge_type: str) -> int:
    """分页枚举 EDGE 类型全部边并批量 ``DELETE EDGE``，返回删除数。

    同 ``_delete_all_vertices``：边删边取，每页固定 offset=0。
    """
    from infra.graph_db.convert import _parse_edge_id

    deleted = 0
    prev_first: str | None = None
    while True:
        page = client.get_edges_by_type(edge_type, limit=BULK_DELETE_CHUNK, offset=0)
        if not page.items:
            break
        first = str(page.items[0].id)
        if first == prev_first:
            # 删除未生效（枚举结果没变）：报错退出，避免死循环
            raise RuntimeError(f"DELETE EDGE 未生效，仍枚举到边 {first}")
        prev_first = first
        specs = []
        for edge in page.items:
            source, target, ranking = _parse_edge_id(str(edge.id))
            specs.append(f"{_quote_vid(source)} -> {_quote_vid(target)}@{ranking}")
        client.execute_write(f"DELETE EDGE {edge_type} {', '.join(specs)};")
        deleted += len(specs)
    return deleted
