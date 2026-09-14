"""gkx_local 只读 MySQL 会话工厂。

gkx 为只读生产数据，本模块仅提供读会话，禁止任何写操作。
连接参数沿用 expert_paper_cooperation 的 PAPER_COOP_MYSQL_* / LOCAL_MYSQL_* 环境变量；
URL 拼装统一走 infra.mysql.MySQLClient。
"""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy.orm import Session

from infra.mysql import MySQLClient


def _gkx_params() -> dict[str, Any]:
    return {
        "host": os.getenv("PAPER_COOP_MYSQL_HOST") or os.getenv("LOCAL_MYSQL_HOST") or "127.0.0.1",
        "port": int(os.getenv("PAPER_COOP_MYSQL_PORT") or os.getenv("LOCAL_MYSQL_PORT") or 3306),
        "username": os.getenv("PAPER_COOP_MYSQL_USERNAME")
        or os.getenv("LOCAL_MYSQL_USERNAME")
        or "root",
        "password": os.getenv("PAPER_COOP_MYSQL_PASSWORD")
        or os.getenv("LOCAL_MYSQL_PASSWORD")
        or "123456789",
        "database": os.getenv("PAPER_COOP_MYSQL_DATABASE")
        or os.getenv("LOCAL_MYSQL_DATABASE")
        or "gkx_local",
    }


def _gkx_url() -> str:
    return MySQLClient(**_gkx_params()).url


_gkx_client: MySQLClient | None = None


def get_gkx_client() -> MySQLClient:
    """进程级单例。"""
    global _gkx_client
    if _gkx_client is None:
        _gkx_client = MySQLClient(**_gkx_params())
    return _gkx_client


def get_gkx_session() -> Session:
    """获取 gkx 读会话；调用方负责 close。"""
    return get_gkx_client().session()


def reset_gkx_client() -> None:
    """测试用：重置单例。"""
    global _gkx_client
    _gkx_client = None
