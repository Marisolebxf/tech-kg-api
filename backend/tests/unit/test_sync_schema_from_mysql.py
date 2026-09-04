from __future__ import annotations

import pytest

from script.sync_schema_from_mysql import required_connection_setting


def test_required_connection_setting_prefers_primary(monkeypatch):
    monkeypatch.setenv("SOURCE_MYSQL_HOST", "source-db.internal")
    monkeypatch.setenv("MYSQL_HOST", "fallback-db.internal")

    assert required_connection_setting("SOURCE_MYSQL_HOST", "MYSQL_HOST") == "source-db.internal"


def test_required_connection_setting_uses_fallback(monkeypatch):
    monkeypatch.delenv("SOURCE_MYSQL_HOST", raising=False)
    monkeypatch.setenv("MYSQL_HOST", "fallback-db.internal")

    assert required_connection_setting("SOURCE_MYSQL_HOST", "MYSQL_HOST") == "fallback-db.internal"


def test_required_connection_setting_rejects_missing_values(monkeypatch):
    monkeypatch.delenv("SOURCE_MYSQL_HOST", raising=False)
    monkeypatch.delenv("MYSQL_HOST", raising=False)

    with pytest.raises(RuntimeError, match="必须通过 SOURCE_MYSQL_HOST 或 MYSQL_HOST"):
        required_connection_setting("SOURCE_MYSQL_HOST", "MYSQL_HOST")
