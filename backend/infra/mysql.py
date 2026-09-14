"""MySQL 同步接入（SQLAlchemy + pymysql）。"""

import os
from collections.abc import Generator, Mapping
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


def build_db_url() -> str:
    """根据 MYSQL_* 环境变量拼装 SQLAlchemy URL（兼容旧调用）。"""
    return MySQLClient().url


class MySQLClient:
    """SQLAlchemy engine and session factory for a MySQL database.

    连接参数解析顺序：显式 kwargs > ``{env_prefix}*`` 环境变量 > defaults。
    业务库用默认 ``MYSQL_`` 前缀；其他数据面（控制面 ``WORKFLOW_MYSQL_*`` 等）
    通过 ``env_prefix`` + ``defaults`` 复用本类，URL 拼装与引擎逻辑只此一份。
    """

    def __init__(
        self,
        url: str | None = None,
        *,
        env_prefix: str = "MYSQL_",
        host: str | None = None,
        port: int | None = None,
        database: str | None = None,
        username: str | None = None,
        password: str | None = None,
        pool_size: int | None = None,
        max_overflow: int | None = None,
        echo: bool | None = None,
        defaults: Mapping[str, Any] | None = None,
        ensure_database: bool = False,
    ) -> None:
        resolved: dict[str, Any] = {
            "host": "127.0.0.1",
            "port": 3306,
            "database": "gkx_element",
            "username": "root",
            "password": "123456789",
            "pool_size": 10,
            "max_overflow": 20,
        }
        resolved.update(defaults or {})
        self._explicit_url = url
        self.host = host or os.getenv(f"{env_prefix}HOST", resolved["host"])
        self.port = port or _get_int_env(f"{env_prefix}PORT", resolved["port"])
        # database="" 显式表示"不选库"（SHOW DATABASES 等服务器级操作）；
        # None 才回退 env/defaults 默认库
        self.database = (
            database
            if database is not None
            else os.getenv(f"{env_prefix}DATABASE", resolved["database"])
        )
        self.username = username or os.getenv(f"{env_prefix}USERNAME", resolved["username"])
        self.password = (
            password
            if password is not None
            else os.getenv(f"{env_prefix}PASSWORD", resolved["password"])
        )
        self.pool_size = pool_size or _get_int_env(f"{env_prefix}POOL_SIZE", resolved["pool_size"])
        self.max_overflow = max_overflow or _get_int_env(
            f"{env_prefix}MAX_OVERFLOW", resolved["max_overflow"]
        )
        # echo 开关沿用历史变量名：MYSQL_ 前缀是 SQLALCHEMY_ECHO，其余前缀是 {prefix}SQLALCHEMY_ECHO
        echo_env = "SQLALCHEMY_ECHO" if env_prefix == "MYSQL_" else f"{env_prefix}SQLALCHEMY_ECHO"
        self.echo = echo if echo is not None else os.getenv(echo_env, "false").lower() == "true"
        self.ensure_database = ensure_database

        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None

    @property
    def url(self) -> str:
        if self._explicit_url:
            return self._explicit_url
        username = quote_plus(self.username)
        password = quote_plus(self.password)
        db_part = f"{self.database}" if self.database else ""
        return (
            f"mysql+pymysql://{username}:{password}@{self.host}:{self.port}/"
            f"{db_part}?charset=utf8mb4"
        )

    def _ensure_database(self) -> None:
        """首次连库前确保目标库存在。

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
            if self.ensure_database:
                self._ensure_database()
            kwargs: dict[str, Any] = {
                "pool_pre_ping": True,
                "pool_recycle": 3600,
                "echo": self.echo,
                "future": True,
            }
            # SQLite（测试用）不支持 pool_size/max_overflow
            if not self.url.startswith("sqlite"):
                kwargs["pool_size"] = self.pool_size
                kwargs["max_overflow"] = self.max_overflow
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

    def session(self) -> Session:
        """兼容旧调用：返回一个 session（调用方负责关闭）。"""
        return self.create_session()

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


mysql_client = MySQLClient()


def get_engine() -> Engine:
    return mysql_client.engine


def get_session_factory() -> sessionmaker[Session]:
    return mysql_client.session_factory


def create_session() -> Session:
    return mysql_client.create_session()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    with mysql_client.session_scope() as session:
        yield session


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session."""

    with session_scope() as session:
        yield session


def get_mysql_client() -> MySQLClient:
    """进程级单例（兼容旧调用 get_mysql_client().session()）。"""
    return mysql_client


def model_to_dict(model: Any) -> dict[str, Any]:
    return {column.name: getattr(model, column.name) for column in model.__table__.columns}
