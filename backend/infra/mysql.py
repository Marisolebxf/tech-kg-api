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


class MySQLClient:
    """SQLAlchemy engine and session factory for the default MySQL database."""

    def __init__(
        self,
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
        self.host = host or os.getenv("MYSQL_HOST", "127.0.0.1")
        self.port = port or _get_int_env("MYSQL_PORT", 3306)
        self.database = database or os.getenv("MYSQL_DATABASE", "gkx_local")
        self.username = username or os.getenv("MYSQL_USERNAME", "root")
        self.password = (
            password if password is not None else os.getenv("MYSQL_PASSWORD", "123456789")
        )
        self.pool_size = pool_size or _get_int_env("MYSQL_POOL_SIZE", 10)
        self.max_overflow = max_overflow or _get_int_env("MYSQL_MAX_OVERFLOW", 20)
        self.echo = (
            echo if echo is not None else os.getenv("SQLALCHEMY_ECHO", "false").lower() == "true"
        )

        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None

    @property
    def url(self) -> str:
        username = quote_plus(self.username)
        password = quote_plus(self.password)
        return (
            f"mysql+pymysql://{username}:{password}@{self.host}:{self.port}/"
            f"{self.database}?charset=utf8mb4"
        )

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            self._engine = create_engine(
                self.url,
                pool_pre_ping=True,
                pool_recycle=3600,
                pool_size=self.pool_size,
                max_overflow=self.max_overflow,
                echo=self.echo,
                future=True,
            )
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


def model_to_dict(model: Any) -> dict[str, Any]:
    return {column.name: getattr(model, column.name) for column in model.__table__.columns}
