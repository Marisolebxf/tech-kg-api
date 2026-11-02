"""Database names must never override approved driver connection parameters."""

import pytest
from sqlalchemy.dialects.mysql.pymysql import MySQLDialect_pymysql
from sqlalchemy.engine import make_url

from infra.mysql import MySQLClient


@pytest.mark.parametrize(
    "database",
    [
        "approved?host=127.0.0.1&",
        "approved?port=22&",
        "approved?unix_socket=/tmp/unauthorized.sock&",
        "approved?connect_timeout=999&read_timeout=999&",
        "中文数据库",
        "name/with/slash",
        "name#fragment",
        "name%20literal",
        "name?question",
    ],
)
def test_database_is_literal_and_cannot_add_driver_parameters(database):
    client = MySQLClient(
        host="192.0.2.20", port=3306, username="reader", password="synthetic", database=database
    )
    engine = client.engine  # SQLAlchemy engine creation is lazy: no TCP connection.
    try:
        _, params = MySQLDialect_pymysql().create_connect_args(engine.url)
        assert params["host"] == "192.0.2.20"
        assert params["port"] == 3306
        assert params["database"] == database
        assert params["charset"] == "utf8mb4"
        assert "unix_socket" not in params
        assert "connect_timeout" not in params
        assert "read_timeout" not in params
        # Legacy string consumers also cannot turn database text into URL options.
        _, legacy = MySQLDialect_pymysql().create_connect_args(make_url(client.url))
        assert legacy["host"] == "192.0.2.20"
        assert legacy["port"] == 3306
        assert set(make_url(client.url).query) == {"charset"}
    finally:
        client.dispose()


@pytest.mark.parametrize("host", ["2001:db8::1", "[2001:db8::1]"])
def test_ipv6_driver_host_is_bare_and_url_authority_is_bracketed(host):
    client = MySQLClient(
        host=host, port=3306, username="reader", password="synthetic", database="test"
    )
    try:
        _, params = MySQLDialect_pymysql().create_connect_args(client.engine.url)
        assert params["host"] == "2001:db8::1"
        assert make_url(client.url).host == "2001:db8::1"
    finally:
        client.dispose()


def test_explicit_sqlite_url_is_preserved():
    client = MySQLClient(url="sqlite:///:memory:")
    try:
        assert client.url == "sqlite:///:memory:"
        assert client.engine.url.get_backend_name() == "sqlite"
    finally:
        client.dispose()
