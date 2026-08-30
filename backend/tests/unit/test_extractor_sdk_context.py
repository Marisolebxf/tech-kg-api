"""一对一抽取脚本 kg_sdk 上下文单测：优先用任务注入的数据源/图空间，CLI 回退 env。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# 脚本子进程以顶层模块形式导入 kg_sdk（PYTHONPATH 含 backend/sdk）；测试对齐
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sdk"))


def _set_ctx(monkeypatch, ctx: dict | None) -> None:
    import kg_sdk

    kg_sdk.reset_current_context()
    if ctx is None:
        monkeypatch.delenv("KG_SCRIPT_CTX", raising=False)
    else:
        monkeypatch.setenv("KG_SCRIPT_CTX", json.dumps(ctx))


@pytest.fixture(autouse=True)
def _reset_ctx():
    yield ()
    import kg_sdk

    kg_sdk.reset_current_context()


def test_mysql_engine_uses_ctx_params(monkeypatch):
    from script.entity_extractors_one_entity import common

    _set_ctx(
        monkeypatch,
        {
            "mysql": {
                "host": "mysql.internal",
                "port": 3307,
                "database": "gkx_dev",
                "username": "etl",
                "password": "secret",
            }
        },
    )
    engine = common.mysql_engine()
    assert engine.url.render_as_string(hide_password=False) == (
        "mysql+pymysql://etl:secret@mysql.internal:3307/gkx_dev?charset=utf8mb4"
    )


def test_mysql_engine_ctx_database_wins_over_default_arg(monkeypatch):
    """任务触发时选的数据库优先于脚本默认 gkx_element。"""
    from script.relation_extractors_one_relation import common

    _set_ctx(
        monkeypatch,
        {
            "mysql": {
                "host": "h",
                "port": 3306,
                "database": "other",
                "username": "u",
                "password": "p",
            }
        },
    )
    engine = common.mysql_engine("gkx_element")
    assert engine.url.render_as_string(hide_password=False).startswith(
        "mysql+pymysql://u:p@h:3306/other"
    )


def test_mysql_engine_env_fallback_without_ctx(monkeypatch):
    from script.entity_extractors_one_entity import common

    _set_ctx(monkeypatch, None)
    monkeypatch.setenv("MYSQL_USERNAME", "envuser")
    monkeypatch.setenv("MYSQL_PASSWORD", "envpass")
    monkeypatch.setenv("MYSQL_HOST", "127.0.0.2")
    monkeypatch.setenv("MYSQL_PORT", "33061")
    engine = common.mysql_engine()
    assert engine.url.render_as_string(hide_password=False).startswith(
        "mysql+pymysql://envuser:envpass@127.0.0.2:33061/gkx_element"
    )


def test_graph_client_uses_ctx_graph(monkeypatch):
    from script.relation_extractors_one_relation import common

    _set_ctx(monkeypatch, {"graph": {"base_url": "http://graph:8090", "space": "dev2"}})

    class _FakeGraph:
        def merge_node(self, *args, **kwargs):
            return True

    import kg_sdk

    monkeypatch.setattr(
        type(kg_sdk.current_context()), "graph", property(lambda self: _FakeGraph())
    )
    client = common.graph_client()
    assert isinstance(client, _FakeGraph)


def test_graph_client_env_fallback_without_ctx(monkeypatch):
    from script.entity_extractors_one_entity import common

    _set_ctx(monkeypatch, None)

    class _FakeClient:
        def __init__(self, settings):
            self.settings = settings
            self.connected = False

        def connect(self):
            self.connected = True

    monkeypatch.setattr(common, "TRSGraphClient", _FakeClient)
    client = common.graph_client()
    assert client.connected
    assert client.settings.space == common.TRSGraphSettings.from_env().space
