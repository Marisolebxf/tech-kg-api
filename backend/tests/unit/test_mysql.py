from __future__ import annotations

from infra.mysql import MySQLClient, build_db_url


def test_build_db_url_from_env(monkeypatch):
    monkeypatch.setenv("MYSQL_HOST", "h")
    monkeypatch.setenv("MYSQL_PORT", "3307")
    monkeypatch.setenv("MYSQL_USERNAME", "u")
    monkeypatch.setenv("MYSQL_PASSWORD", "p")
    monkeypatch.setenv("MYSQL_DATABASE", "d")
    assert build_db_url() == "mysql+pymysql://u:p@h:3307/d?charset=utf8mb4"


def test_client_engine_and_session():
    client = MySQLClient(url="sqlite:///:memory:")
    assert client.engine is not None
    s = client.session()
    assert s is not None
    s.close()
