"""kg_sdk.Context 单测：懒构造客户端 + None 降级 + current_context env 入口。"""

from __future__ import annotations

import sys
import types

import pytest

from sdk.kg_sdk import Context, current_context, reset_current_context


def test_none_when_raw_empty() -> None:
    ctx = Context(None)
    assert ctx.mysql is None
    assert ctx.graph is None
    assert ctx.milvus is None
    assert ctx.llm is None
    assert ctx.embedding is None
    assert ctx.config.watermark is None
    assert ctx.config.checkpoint is None


def test_none_when_key_missing() -> None:
    ctx = Context({"mysql": None, "llm": {}})
    assert ctx.mysql is None
    # llm params 缺 api_key → None
    assert ctx.llm is None


def test_config_and_metadata_passthrough() -> None:
    raw = {
        "watermark": "2026-08-25T10:00:00",
        "checkpoint": {"last_id": 7},
        "stepId": "extract",
        "attempt": 2,
        "prevOutputs": {"load": {"rows": 3}},
        "executionId": "EX-1",
        "taskId": "PI-1",
        "definitionId": "paper-pipeline",
    }
    ctx = Context(raw)
    assert ctx.config.watermark == "2026-08-25T10:00:00"
    assert ctx.config.checkpoint == {"last_id": 7}
    assert ctx.step_id == "extract"
    assert ctx.attempt == 2
    assert ctx.prev_outputs == {"load": {"rows": 3}}
    assert ctx.execution_id == "EX-1"
    assert ctx.task_id == "PI-1"
    assert ctx.definition_id == "paper-pipeline"


def test_mysql_builds_client() -> None:
    ctx = Context(
        {"mysql": {"host": "h", "port": 3307, "database": "db", "username": "u", "password": "p"}}
    )
    client = ctx.mysql
    assert client is not None
    assert client.host == "h"
    assert client.port == 3307
    assert client.database == "db"
    # 懒构造：再次访问同一实例
    assert ctx.mysql is client


def test_llm_builds_client() -> None:
    ctx = Context({"llm": {"api_key": "k", "base_url": "http://x", "model": "m"}})
    client = ctx.llm
    assert client is not None
    assert client.model == "m"
    assert client.base_url == "http://x"
    assert client.api_key == "k"


def test_embedding_builds_client() -> None:
    ctx = Context(
        {"embedding": {"api_key": "k", "base_url": "http://x", "model": "emb-3", "dimensions": 512}}
    )
    client = ctx.embedding
    assert client is not None
    assert client.model == "emb-3"
    assert client.base_url == "http://x"


def test_graph_builds_client_with_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict = {}

    class FakeSettings:
        def __init__(self, **kwargs):
            calls["settings"] = kwargs

    class FakeClient:
        def __init__(self, settings):
            calls["client_settings"] = settings
            self.connected = False

        def connect(self):
            self.connected = True

    monkeypatch.setattr("infra.graph_db.TRSGraphClient", FakeClient)
    monkeypatch.setattr("infra.graph_db.config.TRSGraphSettings", FakeSettings)
    ctx = Context(
        {"graph": {"base_url": "http://g", "space": "techkg", "api_key": "key", "timeout": 30}}
    )
    client = ctx.graph
    assert isinstance(client, FakeClient)
    assert client.connected is True
    assert calls["settings"]["space"] == "techkg"


def test_milvus_builds_client_with_fake_module(monkeypatch: pytest.MonkeyPatch) -> None:
    instances: list = []

    class FakeMilvusClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            instances.append(self)

    fake_mod = types.ModuleType("pymilvus")
    fake_mod.MilvusClient = FakeMilvusClient  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pymilvus", fake_mod)
    ctx = Context(
        {"milvus": {"uri": "http://m:19530", "db_name": "techkg", "token": "t", "timeout": 30}}
    )
    client = ctx.milvus
    assert isinstance(client, FakeMilvusClient)
    assert client.kwargs["uri"] == "http://m:19530"
    assert client.kwargs["db_name"] == "techkg"
    assert client.kwargs["token"] == "t"


def test_current_context_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_current_context()
    monkeypatch.setenv(
        "KG_SCRIPT_CTX",
        '{"watermark":"2026-01-01T00:00:00","mysql":{"host":"h","port":3306,"database":"d","username":"u","password":"p"}}',
    )
    ctx = current_context()
    assert ctx is not None
    assert ctx.config.watermark == "2026-01-01T00:00:00"
    assert ctx.mysql is not None
    assert ctx.mysql.host == "h"
    reset_current_context()


def test_current_context_returns_none_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_current_context()
    monkeypatch.delenv("KG_SCRIPT_CTX", raising=False)
    assert current_context() is None
    reset_current_context()
