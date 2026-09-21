"""resolve_embedding_settings 单测：配置管理默认配置优先，env 回退的优先级规则。"""

from __future__ import annotations

from typing import Any

import service.embedding_config as embedding_config_service
from service.embedding_config import resolve_embedding_settings


class _FakeRow:
    def __init__(self, *, api_key: str = "db-key", dimensions: int | None = 512) -> None:
        self.id = "EMB-1"
        self.base_url = "http://m3e:8010/v1"
        self.model = "moka-ai/m3e-small"
        self.api_key = api_key
        self.dimensions = dimensions


def _install_db(monkeypatch, row: _FakeRow | None) -> list[Any]:
    calls: list[Any] = []

    class _FakeDAO:
        def __init__(self, session) -> None:
            calls.append(session)

        def get_default(self):
            return row

    monkeypatch.setattr(embedding_config_service, "EmbeddingConfigDAO", _FakeDAO)
    return calls


def _install_db_error(monkeypatch) -> None:
    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr("infra.mysql.create_session", _boom)


def _clear_env(monkeypatch) -> None:
    for name in (
        "ENTITY_SEARCH_EMBEDDING_BASE_URL",
        "ENTITY_SEARCH_EMBEDDING_MODEL",
        "ENTITY_SEARCH_EMBEDDING_API_KEY",
        "ENTITY_SEARCH_EMBEDDING_DIM",
        "PATENT_EMBEDDING_BASE_URL",
        "PATENT_EMBEDDING_MODEL",
        "PATENT_EMBEDDING_API_KEY",
        "PATENT_EMBEDDING_DIM",
    ):
        monkeypatch.delenv(name, raising=False)


def test_db_default_wins_over_env(monkeypatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("PATENT_EMBEDDING_BASE_URL", "http://env:8010/v1")
    monkeypatch.setenv("PATENT_EMBEDDING_MODEL", "env-model")
    monkeypatch.setenv("PATENT_EMBEDDING_API_KEY", "env-key")
    _install_db(monkeypatch, _FakeRow(dimensions=768))

    settings = resolve_embedding_settings()

    assert settings == {
        "base_url": "http://m3e:8010/v1",
        "model": "moka-ai/m3e-small",
        "api_key": "db-key",
        "dimensions": 768,
        "config_id": "EMB-1",
    }


def test_db_default_without_key_falls_back_to_env(monkeypatch) -> None:
    """DB 默认配置缺 key 而 env 配了可用 key：跳过 DB，避免空 key 屏蔽 env。"""
    _clear_env(monkeypatch)
    monkeypatch.setenv("PATENT_EMBEDDING_BASE_URL", "http://env:8010/v1")
    monkeypatch.setenv("PATENT_EMBEDDING_API_KEY", "env-key")
    _install_db(monkeypatch, _FakeRow(api_key=""))

    settings = resolve_embedding_settings()

    assert settings["base_url"] == "http://env:8010/v1"
    assert settings["api_key"] == "env-key"
    assert settings["config_id"] is None


def test_db_error_falls_back_to_env(monkeypatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("ENTITY_SEARCH_EMBEDDING_BASE_URL", "http://env:8010/v1")
    _install_db_error(monkeypatch)

    settings = resolve_embedding_settings()

    assert settings["base_url"] == "http://env:8010/v1"
    assert settings["model"] == "moka-ai/m3e-small"
    assert settings["api_key"] == "local-no-auth"
    assert settings["dimensions"] is None


def test_no_db_no_env_returns_none(monkeypatch) -> None:
    _clear_env(monkeypatch)
    _install_db(monkeypatch, None)

    assert resolve_embedding_settings() is None


def test_env_dim_parsed_and_entity_search_prefix_preferred(monkeypatch) -> None:
    _clear_env(monkeypatch)
    _install_db(monkeypatch, None)
    monkeypatch.setenv("PATENT_EMBEDDING_BASE_URL", "http://patent:8010/v1")
    monkeypatch.setenv("PATENT_EMBEDDING_MODEL", "patent-model")
    monkeypatch.setenv("PATENT_EMBEDDING_DIM", "512")
    monkeypatch.setenv("ENTITY_SEARCH_EMBEDDING_BASE_URL", "http://entity:8010/v1")
    monkeypatch.setenv("ENTITY_SEARCH_EMBEDDING_DIM", "1024")

    settings = resolve_embedding_settings()

    assert settings["base_url"] == "http://entity:8010/v1"  # ENTITY_SEARCH_* 前缀优先
    assert settings["model"] == "patent-model"  # 未设的前缀字段回退 PATENT_*
    assert settings["dimensions"] == 1024
