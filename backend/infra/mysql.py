"""MySQL 同步接入（SQLAlchemy + pymysql）。"""

from __future__ import annotations

import os
from collections.abc import Iterator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

load_dotenv()


def build_db_url() -> str:
    """根据 MYSQL_* 环境变量拼装 SQLAlchemy URL。"""
    host = os.getenv("MYSQL_HOST", "127.0.0.1")
    port = os.getenv("MYSQL_PORT", "3306")
    user = os.getenv("MYSQL_USERNAME", "root")
    pwd = os.getenv("MYSQL_PASSWORD", "")
    db = os.getenv("MYSQL_DATABASE", "techkg")
    return f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{db}?charset=utf8mb4"


class MySQLClient:
    """同步 SQLAlchemy engine + session 工厂。"""

    def __init__(self, url: str | None = None) -> None:
        self._url = url or build_db_url()
        self._engine: Engine = create_engine(self._url, pool_pre_ping=True, pool_size=10)
        self._session_factory = sessionmaker(bind=self._engine, expire_on_commit=False)

    @property
    def engine(self) -> Engine:
        return self._engine

    def session(self) -> Session:
        return self._session_factory()


_client: MySQLClient | None = None


def get_mysql_client() -> MySQLClient:
    """进程级单例（懒加载，默认连 MySQL；测试可注入 sqlite）。"""
    global _client
    if _client is None:
        _client = MySQLClient()
    return _client


def get_session() -> Iterator[Session]:
    """FastAPI 依赖：yield 一个 session。"""
    client = get_mysql_client()
    session = client.session()
    try:
        yield session
    finally:
        session.close()
