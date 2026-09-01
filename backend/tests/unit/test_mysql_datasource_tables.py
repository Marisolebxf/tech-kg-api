"""list_tables / list_columns 单测（mock engine，仿 list_databases 模式）。"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from dao.mysql_datasource import MysqlDatasourceDAO
from db_model.base import Base
from db_model.mysql_datasource import MysqlDatasource
from service.mysql_datasource import MysqlDatasourceService


class FakeResult:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple]:
        return self._rows


class FakeConnection:
    def __init__(self) -> None:
        self.queries: list[tuple[str, dict]] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement, params=None):
        sql = str(statement)
        self.queries.append((sql, dict(params or {})))
        if "information_schema.tables" in sql:
            return FakeResult([("scholar", "BASE TABLE"), ("organization", "BASE TABLE")])
        if "information_schema.columns" in sql:
            return FakeResult(
                [
                    ("id", "bigint", "NO"),
                    ("name", "varchar", "YES"),
                    ("update_time", "datetime", "NO"),
                ]
            )
        return FakeResult([])


class FakeMySQLClient:
    connection: FakeConnection = FakeConnection()

    def __init__(self, **kwargs) -> None:
        self.engine = self

    def connect(self) -> FakeConnection:
        return self.connection

    def dispose(self) -> None:
        pass


@pytest.fixture
def datasource_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine, tables=[MysqlDatasource.__table__])
    with Session(engine) as session:
        now = datetime.utcnow()
        MysqlDatasourceDAO(session).create(
            id="MYSQL-1",
            name="ds",
            host="h",
            port=3306,
            default_database="gkx",
            username="u",
            password="p",
            created_at=now,
            updated_at=now,
        )
        session.commit()
        yield session
    engine.dispose()


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch):
    FakeMySQLClient.connection = FakeConnection()
    monkeypatch.setattr("service.mysql_datasource.MySQLClient", FakeMySQLClient)
    return FakeMySQLClient.connection


def test_list_tables_uses_parameterized_query(datasource_session, fake_client) -> None:
    service = MysqlDatasourceService(datasource_session)
    tables = service.list_tables("MYSQL-1", database="gkx_element")
    assert tables == [
        {"name": "scholar", "type": "BASE TABLE"},
        {"name": "organization", "type": "BASE TABLE"},
    ]
    sql, params = fake_client.queries[0]
    assert "information_schema.tables" in sql
    assert params == {"db": "gkx_element"}  # 参数化传递，无标识符拼接


def test_list_tables_defaults_to_default_database(datasource_session, fake_client) -> None:
    service = MysqlDatasourceService(datasource_session)
    service.list_tables("MYSQL-1")
    _, params = fake_client.queries[0]
    assert params == {"db": "gkx"}


def test_list_tables_missing_datasource_returns_empty(datasource_session, fake_client) -> None:
    service = MysqlDatasourceService(datasource_session)
    assert service.list_tables("MYSQL-X") == []
    assert fake_client.queries == []


def test_list_columns_returns_ordered_columns(datasource_session, fake_client) -> None:
    service = MysqlDatasourceService(datasource_session)
    columns = service.list_columns("MYSQL-1", "scholar", database="gkx")
    assert columns == [
        {"name": "id", "dataType": "bigint", "nullable": False},
        {"name": "name", "dataType": "varchar", "nullable": True},
        {"name": "update_time", "dataType": "datetime", "nullable": False},
    ]
    sql, params = fake_client.queries[0]
    assert "information_schema.columns" in sql
    assert params == {"db": "gkx", "t": "scholar"}


def test_list_tables_query_error_returns_empty(datasource_session, monkeypatch) -> None:
    class BrokenClient:
        def __init__(self, **kwargs) -> None:
            self.engine = self

        def connect(self):
            raise RuntimeError("connection refused")

        def dispose(self) -> None:
            pass

    monkeypatch.setattr("service.mysql_datasource.MySQLClient", BrokenClient)
    service = MysqlDatasourceService(datasource_session)
    assert service.list_tables("MYSQL-1", database="gkx") == []
    assert service.list_columns("MYSQL-1", "scholar", database="gkx") == []
