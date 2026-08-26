"""平台数据源 / Milvus / embedding / LLM / watermark 解析与水位单测。

standalone get_*_settings_by_id / read/write_watermark 走 infra.mysql.create_session，
用 SQLite + StaticPool 共享内存库 + monkeypatch create_session 注入。
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from dao.embedding_config import EmbeddingConfigDAO
from dao.llm_config import LlmConfigDAO
from dao.milvus_config import MilvusConfigDAO
from dao.mysql_datasource import MysqlDatasourceDAO
from db_model.base import Base
from db_model.embedding_config import EmbeddingConfig
from db_model.llm_config import LlmConfig
from db_model.milvus_config import MilvusConfig
from db_model.mysql_datasource import MysqlDatasource
from db_model.script_watermark import ScriptWatermark


@pytest.fixture
def sqlite_session_factory(monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            MysqlDatasource.__table__,
            MilvusConfig.__table__,
            EmbeddingConfig.__table__,
            LlmConfig.__table__,
            ScriptWatermark.__table__,
        ],
    )
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def fake_create_session():
        return factory()

    # 所有 standalone 解析函数与 DAO 默认都走 infra.mysql.create_session
    monkeypatch.setattr("infra.mysql.create_session", fake_create_session)
    return factory


def _seed(session_factory) -> None:
    s = session_factory()
    now = datetime.utcnow()
    MysqlDatasourceDAO(session=s).create(
        id="MYSQL-1",
        name="ds",
        host="h",
        port=3307,
        default_database="db",
        username="u",
        password="p",
        created_at=now,
        updated_at=now,
    )
    MilvusConfigDAO(session=s).create(
        id="MILVUS-1",
        name="m",
        uri="http://milvus:19530",
        token="t",
        default_db="default",
        created_at=now,
        updated_at=now,
    )
    EmbeddingConfigDAO(session=s).create(
        id="EMB-1",
        name="e",
        base_url="http://emb",
        api_key="ek",
        model="emb-3",
        dimensions=512,
        created_at=now,
        updated_at=now,
    )
    LlmConfigDAO(session=s).create(
        id="LLM-1",
        name="l",
        base_url="http://llm",
        api_key="lk",
        model="m",
        created_at=now,
        updated_at=now,
    )
    s.close()


def test_get_mysql_settings_by_id(sqlite_session_factory) -> None:
    _seed(sqlite_session_factory)
    from service.mysql_datasource import get_mysql_settings_by_id

    params = get_mysql_settings_by_id("MYSQL-1")
    assert params == {"host": "h", "port": 3307, "database": "db", "username": "u", "password": "p"}
    assert get_mysql_settings_by_id("MISSING") is None
    assert get_mysql_settings_by_id(None) is None


def test_get_milvus_settings_by_id(sqlite_session_factory) -> None:
    _seed(sqlite_session_factory)
    from service.milvus_config import get_milvus_settings_by_id

    params = get_milvus_settings_by_id("MILVUS-1")
    assert params == {
        "uri": "http://milvus:19530",
        "token": "t",
        "db_name": "default",
        "timeout": 30,
    }
    assert get_milvus_settings_by_id("MISSING") is None


def test_get_embedding_settings_by_id(sqlite_session_factory) -> None:
    _seed(sqlite_session_factory)
    from service.embedding_config import get_embedding_settings_by_id

    params = get_embedding_settings_by_id("EMB-1")
    assert params == {
        "api_key": "ek",
        "base_url": "http://emb",
        "model": "emb-3",
        "dimensions": 512,
    }
    assert get_embedding_settings_by_id("MISSING") is None


def test_get_llm_settings_by_id(sqlite_session_factory) -> None:
    _seed(sqlite_session_factory)
    from service.llm_config import get_llm_settings_by_id

    params = get_llm_settings_by_id("LLM-1")
    assert params == {"api_key": "lk", "base_url": "http://llm", "model": "m"}
    assert get_llm_settings_by_id("MISSING") is None


def test_watermark_roundtrip_and_advance(sqlite_session_factory) -> None:
    from service.script_watermark import read_watermark, write_watermark

    assert read_watermark("def-1", "load") is None
    write_watermark("def-1", "load", watermark=datetime(2026, 8, 25, 10, 0, 0))
    wm = read_watermark("def-1", "load")
    assert wm is not None
    assert wm["watermark"] == "2026-08-25T10:00:00"
    # 不同 step 独立水位
    assert read_watermark("def-1", "extract") is None
    # 覆盖
    write_watermark(
        "def-1", "load", watermark=datetime(2026, 8, 26, 0, 0, 0), checkpoint={"last_id": 9}
    )
    wm2 = read_watermark("def-1", "load")
    assert wm2["watermark"] == "2026-08-26T00:00:00"
    assert wm2["checkpoint"] == {"last_id": 9}


def test_resolve_resources_merges_overrides_and_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    from service import temporal_workflows

    monkeypatch.setattr(
        "service.mysql_datasource.get_mysql_settings_by_id",
        lambda cid: {"host": "h", "port": 3306, "database": "db", "username": "u", "password": "p"},
    )
    monkeypatch.setattr(
        "service.milvus_config.get_milvus_settings_by_id",
        lambda cid: {"uri": "http://m", "token": None, "db_name": "default", "timeout": 30},
    )
    monkeypatch.setattr(
        "service.llm_config.get_llm_settings_by_id",
        lambda cid: {"api_key": "k", "base_url": "http://x", "model": "m"},
    )
    monkeypatch.setattr(
        "service.embedding_config.get_embedding_settings_by_id",
        lambda cid: {"api_key": "ek", "base_url": "http://e", "model": "emb", "dimensions": None},
    )
    monkeypatch.setattr(
        "service.script_watermark.read_watermark",
        lambda did, sid: {"watermark": "2026-08-01T00:00:00", "checkpoint": {"last_id": 5}},
    )

    payload = {
        "mysql_datasource_id": "MYSQL-1",
        "mysql_database": "override_db",
        "milvus_config_id": "MILVUS-1",
        "milvus_database": "override_mdb",
        "graph_space": "techkg",
        "llm_config_id": "LLM-1",
        "embedding_config_id": "EMB-1",
    }
    resolved = temporal_workflows._resolve_resources(payload, "def-1", "load")
    assert resolved["mysql"]["database"] == "override_db"
    assert resolved["mysql"]["host"] == "h"
    assert resolved["milvus"]["db_name"] == "override_mdb"
    assert resolved["graph"]["space"] == "techkg"
    assert resolved["llm"]["model"] == "m"
    assert resolved["embedding"]["model"] == "emb"
    assert resolved["watermark"] == "2026-08-01T00:00:00"
    assert resolved["checkpoint"] == {"last_id": 5}


def test_resolve_resources_empty_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    from service import temporal_workflows

    monkeypatch.setattr("service.script_watermark.read_watermark", lambda did, sid: None)
    resolved = temporal_workflows._resolve_resources({}, "def-1", "load")
    assert resolved == {}
