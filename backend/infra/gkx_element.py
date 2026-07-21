"""gkx_element 只读 MySQL 客户端。

机构图 ETL 只从要素库读取数据。连接参数与业务库 MYSQL_* 隔离，避免脚本误连
techkg/gkx_local；会话在执行任何业务 SQL 前显式切换为只读事务。
"""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from urllib.parse import quote_plus

from sqlalchemy import text
from sqlalchemy.orm import Session

from infra.mysql import MySQLClient


def build_gkx_element_url() -> str:
    host = os.getenv("GKX_ELEMENT_MYSQL_HOST", "127.0.0.1")
    port = int(os.getenv("GKX_ELEMENT_MYSQL_PORT", "3306"))
    database = os.getenv("GKX_ELEMENT_MYSQL_DATABASE", "gkx_element")
    username = quote_plus(os.getenv("GKX_ELEMENT_MYSQL_USERNAME", "root"))
    password = quote_plus(os.getenv("GKX_ELEMENT_MYSQL_PASSWORD", ""))
    return (
        f"mysql+pymysql://{username}:{password}@{host}:{port}/{database}"
        "?charset=utf8mb4"
    )


_client: MySQLClient | None = None


def get_gkx_element_client() -> MySQLClient:
    global _client
    if _client is None:
        _client = MySQLClient(url=build_gkx_element_url(), pool_size=2, max_overflow=2)
    return _client


@contextmanager
def gkx_element_read_session() -> Generator[Session, None, None]:
    """提供只读 Session；离开上下文始终回滚并关闭。"""
    session = get_gkx_element_client().session()
    try:
        session.execute(text("SET TRANSACTION READ ONLY"))
        yield session
    finally:
        session.rollback()
        session.close()


def reset_gkx_element_client() -> None:
    global _client
    if _client is not None:
        _client.dispose()
    _client = None
