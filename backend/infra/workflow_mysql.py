"""控制面 MySQL 引擎（指向 temporal-mysql 的 techkg_control 库）。

跟 infra/mysql.py（业务库 gkx_element）解耦——业务库和控制面用不同实例，
schema 不耦合、备份不耦合。env 变量 WORKFLOW_MYSQL_* 控制连接；不设则默认
指向 temporal-mysql:3306 的 techkg_control 库（root/temporal）。

进程级单例；引擎懒加载；首次 get_workflow_engine() 时若库不存在会自动建
（MySQLClient.ensure_database，实现收敛在 infra/mysql.py）。
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from infra.mysql import MySQLClient

_WORKFLOW_DEFAULTS = {
    "host": "temporal-mysql",
    "database": "techkg_control",
    "password": "temporal",
    "pool_size": 5,
    "max_overflow": 10,
}


class WorkflowMySQLClient(MySQLClient):
    """控制面客户端：WORKFLOW_MYSQL_* env 前缀 + techkg_control 默认值 + 自动建库。"""

    def __init__(self, url: str | None = None, **kwargs: Any) -> None:
        kwargs.setdefault("env_prefix", "WORKFLOW_MYSQL_")
        kwargs.setdefault("defaults", _WORKFLOW_DEFAULTS)
        kwargs.setdefault("ensure_database", True)
        super().__init__(url, **kwargs)


def build_workflow_db_url() -> str:
    """根据 WORKFLOW_MYSQL_* 环境变量拼装 SQLAlchemy URL。"""
    return WorkflowMySQLClient().url


workflow_mysql_client = WorkflowMySQLClient()


def get_workflow_engine() -> Engine:
    return workflow_mysql_client.engine


def get_workflow_session_factory() -> sessionmaker[Session]:
    return workflow_mysql_client.session_factory


def create_workflow_session() -> Session:
    return workflow_mysql_client.create_session()


@contextmanager
def workflow_session_scope() -> Generator[Session, None, None]:
    with workflow_mysql_client.session_scope() as session:
        yield session


def get_workflow_session() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a workflow-control-plane session."""
    with workflow_session_scope() as session:
        yield session


def get_workflow_mysql_client() -> WorkflowMySQLClient:
    return workflow_mysql_client


def close_workflow_engine() -> None:
    workflow_mysql_client.dispose()
