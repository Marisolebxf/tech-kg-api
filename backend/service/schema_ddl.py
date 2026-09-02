"""Schema DDL nGQL 构建与执行。

创建实体/关系 Schema 时，在目标图空间执行 ``CREATE TAG/EDGE IF NOT EXISTS``
DDL，使 catalog 与图结构一致。图空间默认取 ``TRS_GRAPH_SPACE``，创建 Schema
时可显式指定其他空间。
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime
from typing import Any

from infra.graph_db import GraphRequestError, get_space_client, get_trs_graph_client

logger = logging.getLogger(__name__)

NEBULA_SCALAR_TYPES = {"string", "int64", "double", "bool", "date", "datetime", "geo"}
FIXED_STRING_RE = re.compile(r"^fixed_string\((\d+)\)$")
# Nebula FIXED_STRING 长度上限 1024（FBSTRING 实现），0 无意义
FIXED_STRING_MAX_LENGTH = 1024

DDL_MAX_RETRIES = 3


def default_graph_space() -> str:
    return os.getenv("TRS_GRAPH_SPACE", "techkg")


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
