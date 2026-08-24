"""控制面 MySQL 引擎（指向 temporal-mysql 的 techkg_control 库）。

跟 infra/mysql.py（业务库 gkx_element）解耦——业务库和控制面用不同实例，
schema 不耦合、备份不耦合。env 变量 WORKFLOW_MYSQL_* 控制连接；不设则默认
指向 temporal-mysql:3306 的 techkg_control 库（root/temporal）。

进程级单例；引擎懒加载；首次 get_workflow_engine() 时若库不存在会自动建。
"""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

load_dotenv()


def _get_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return int(value)


def build_workflow_db_url() -> str:
    """根据 WORKFLOW_MYSQL_* 环境变量拼装 SQLAlchemy URL。"""
    host = os.getenv("WORKFLOW_MYSQL_HOST", "temporal-mysql")
    port = os.getenv("WORKFLOW_MYSQL_PORT", "3306")
    user = os.getenv("WORKFLOW_MYSQL_USERNAME", "root")
    pwd = os.getenv("WORKFLOW_MYSQL_PASSWORD", "temporal")
    db = os.getenv("WORKFLOW_MYSQL_DATABASE", "techkg_control")
    return (
        f"mysql+pymysql://{quote_plus(user)}:{quote_plus(pwd)}@{host}:{port}/{db}?charset=utf8mb4"
    )


class WorkflowMySQLClient:
    """控制面 SQLAlchemy engine + session factory。"""

    def __init__(
        self,
        url: str | None = None,
        *,
        host: str | None = None,
        port: int | None = None,
        database: str | None = None,
        username: str | None = None,
        password: str | None = None,
        pool_size: int | None = None,
        max_overflow: int | None = None,
        echo: bool | None = None,
    ) -> None:
        self._explicit_url = url
        self.host = host or os.getenv("WORKFLOW_MYSQL_HOST", "temporal-mysql")
        self.port = port or _get_int_env("WORKFLOW_MYSQL_PORT", 3306)
        self.database = database or os.getenv("WORKFLOW_MYSQL_DATABASE", "techkg_control")
        self.username = username or os.getenv("WORKFLOW_MYSQL_USERNAME", "root")
        self.password = (
            password if password is not None else os.getenv("WORKFLOW_MYSQL_PASSWORD", "temporal")
        )
        self.pool_size = pool_size or _get_int_env("WORKFLOW_MYSQL_POOL_SIZE", 5)
        self.max_overflow = max_overflow or _get_int_env("WORKFLOW_MYSQL_MAX_OVERFLOW", 10)
        self.echo = (
            echo
            if echo is not None
            else os.getenv("WORKFLOW_SQLALCHEMY_ECHO", "false").lower() == "true"
        )

        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None

    @property
    def url(self) -> str:
        if self._explicit_url:
            return self._explicit_url
        return (
            f"mysql+pymysql://{quote_plus(self.username)}:{quote_plus(self.password)}"
            f"@{self.host}:{self.port}/{self.database}?charset=utf8mb4"
        )

    def _ensure_database(self) -> None:
        """首次连库前确保 techkg_control（或配置的库名）存在。

        连接 URL 里不能带 dbname（MySQL 不支持 CREATE DATABASE IF NOT EXISTS
        跨库执行），所以先连 server 级、CREATE DATABASE IF NOT EXISTS、再 dispose
        让后续 engine 用带 dbname 的 URL 重建。
        """
        server_url = (
            f"mysql+pymysql://{quote_plus(self.username)}:{quote_plus(self.password)}"
            f"@{self.host}:{self.port}/?charset=utf8mb4"
        )
        server_engine = create_engine(server_url, future=True)
        try:
            with server_engine.connect() as conn:
                conn.execute(
                    text(
                        f"CREATE DATABASE IF NOT EXISTS `{self.database}` "
                        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                    )
                )
                conn.commit()
        finally:
            server_engine.dispose()

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            self._ensure_database()
            kwargs: dict[str, Any] = dict(
                pool_pre_ping=True,
                pool_recycle=3600,
                echo=self.echo,
                future=True,
                pool_size=self.pool_size,
                max_overflow=self.max_overflow,
            )
            self._engine = create_engine(self.url, **kwargs)
        return self._engine

    @property
    def session_factory(self) -> sessionmaker[Session]:
        if self._session_factory is None:
            self._session_factory = sessionmaker(
                bind=self.engine,
                autocommit=False,
                autoflush=False,
                expire_on_commit=False,
                future=True,
            )
        return self._session_factory

    def create_session(self) -> Session:
        return self.session_factory()

    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        session = self.create_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def health_check(self) -> bool:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True

    def dispose(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
            self._session_factory = None


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
