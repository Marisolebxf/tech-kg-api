"""Schema DDL nGQL 构建与执行。

创建实体/关系 Schema 时，在 ``TRS_GRAPH_SPACE`` 指向的图空间执行
``CREATE TAG/EDGE IF NOT EXISTS`` DDL，使 catalog 与图结构一致。
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Any

from infra.graph_db import GraphRequestError, get_trs_graph_client

logger = logging.getLogger(__name__)

NEBULA_SCALAR_TYPES = {"string", "int64", "double", "bool", "date", "datetime", "geo"}
FIXED_STRING_RE = re.compile(r"^fixed_string\(\d+\)$")

DDL_MAX_RETRIES = 3


def is_valid_data_type(data_type: str) -> bool:
    return data_type in NEBULA_SCALAR_TYPES or bool(FIXED_STRING_RE.fullmatch(data_type))


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


def execute_schema_ddl(ddl: str) -> tuple[str, str | None]:
    """执行 DDL，返回 ``(status, error)``；``status`` ∈ {"succeeded","failed"}。

    幂等（``IF NOT EXISTS``），失败重试最多 3 次应对图空间 DDL 传播延迟。
    """
    last_err: str | None = None
    try:
        client = get_trs_graph_client()
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


def run_schema_ddl(kind: str, name: str, properties: list[dict[str, Any]]) -> dict[str, Any]:
    """构建并执行 DDL，返回 ``{statement, status, error, executed_at}``。"""
    ddl = build_create_ddl(kind, name, properties)
    status, error = execute_schema_ddl(ddl)
    return {
        "statement": ddl,
        "status": status,
        "error": error,
        "executed_at": datetime.now().isoformat() if status == "succeeded" else None,
    }
