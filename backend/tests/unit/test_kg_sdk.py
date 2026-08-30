"""kg_sdk.Context 单测：懒构造客户端 + None 降级 + current_context env 入口 + 访问溯源采集。"""

from __future__ import annotations

import sys
import types

import pytest
from sqlalchemy import text

from sdk import access
from sdk.access import (
    ObservedEmbeddingClient,
    ObservedLLMClient,
    ObservedMilvusClient,
    merge_access_reports,
    record_mysql_statement,
    report_from_sidecar,
    reset_access_report,
)
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
    # 观测代理转发原客户端属性
    assert isinstance(client, access.ObservedGraphClient)
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
    assert isinstance(client, ObservedMilvusClient)
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


# ---- 访问溯源采集（sdk/access.py） ----


@pytest.fixture(autouse=True)
def _clean_access_state():
    reset_access_report()
    yield
    reset_access_report()


def _mysql_tables(report: dict) -> set[tuple[str, str]]:
    return {
        (db, table)
        for db, tables in report["mysql"].items()
        if not db.startswith("_")
        for table in tables
    }


def test_record_mysql_statement_select_join_subquery() -> None:
    record_mysql_statement(
        "SELECT a.id FROM dwd_paper a JOIN dwd_author b ON a.id=b.pid "
        "WHERE b.id IN (SELECT c.aid FROM dwd_coop c)",
        db="gkx",
    )
    report = access.access_report()
    assert _mysql_tables(report) == {
        ("gkx", "dwd_paper"),
        ("gkx", "dwd_author"),
        ("gkx", "dwd_coop"),
    }
    assert report["mysql"]["gkx"]["dwd_paper"]["ops"] == ["SELECT"]


def test_record_mysql_statement_write_ops() -> None:
    record_mysql_statement("INSERT INTO t_target (id) VALUES (1)", db="db1")
    record_mysql_statement("UPDATE t_target SET id = 2", db="db1")
    record_mysql_statement("DELETE FROM t_target WHERE id = 3", db="db1")
    report = access.access_report()
    assert report["mysql"]["db1"]["t_target"]["ops"] == ["DELETE", "INSERT", "UPDATE"]
    assert report["mysql"]["db1"]["t_target"]["statements"] == 3


def test_record_mysql_statement_cte_not_counted_as_table() -> None:
    record_mysql_statement("WITH recent AS (SELECT id FROM t_src) SELECT * FROM recent", db="db1")
    report = access.access_report()
    assert _mysql_tables(report) == {("db1", "t_src")}


def test_record_mysql_statement_unparsed_fallback() -> None:
    record_mysql_statement("SELECT * FROM", db="db1")
    report = access.access_report()
    assert _mysql_tables(report) == set()
    assert report["mysql"]["_unparsed"]["count"] == 1
    assert "SELECT" in report["mysql"]["_unparsed"]["last"]


def test_mysql_engine_hook_records_sqlite_statements() -> None:
    from infra.mysql import MySQLClient

    client = access.observe_mysql_client(MySQLClient(url="sqlite:///:memory:"), "testdb")
    with client.engine.connect() as conn:
        conn.execute(text("CREATE TABLE t1 (id INTEGER)"))
        conn.execute(text("CREATE TABLE t2 (id INTEGER)"))
        conn.execute(text("SELECT t1.id FROM t1 JOIN t2 ON t1.id = t2.id"))
    report = access.access_report()
    assert ("testdb", "t1") in _mysql_tables(report)
    assert ("testdb", "t2") in _mysql_tables(report)
    assert report["mysql"]["testdb"]["t1"]["ops"] == ["DDL", "SELECT"]


class _FakeGraphClient:
    def __init__(self) -> None:
        self.calls: list = []

    def create_node(self, labels, properties=None):
        self.calls.append(("create_node", labels))
        return {"labels": labels}

    def get_nodes_by_label(self, label, *, limit=100, offset=0):
        self.calls.append(("get_nodes_by_label", label))
        return []

    def create_edge(self, source_id, target_id, edge_type, properties=None):
        self.calls.append(("create_edge", edge_type))
        return {}

    def execute_query(self, query, params=None):
        self.calls.append(("execute_query", query))
        return []


def test_graph_proxy_records_tag_and_edge_access() -> None:
    fake = _FakeGraphClient()
    observed = access.ObservedGraphClient(fake)
    observed.create_node(["Scholar", "Expert"], {})
    observed.get_nodes_by_label("Paper")
    observed.create_edge("s", "t", "EMPLOYED_BY")
    observed.execute_query("MATCH (v:Paper) RETURN v")

    report = access.access_report()
    graph = report["graph"]
    assert graph["tag"]["Scholar"] == {"ops": ["write"], "count": 1}
    assert graph["tag"]["Expert"] == {"ops": ["write"], "count": 1}
    assert graph["tag"]["Paper"] == {"ops": ["read"], "count": 1}
    assert graph["edge"]["EMPLOYED_BY"] == {"ops": ["write"], "count": 1}
    assert report["graph"]["_ngql"]["count"] == 1
    assert report["graph"]["_ngql"]["ops"] == ["query"]
    assert len(fake.calls) == 4


class _FakeMilvusClient:
    def query(self, collection_name, filter="", output_fields=None):
        return []

    def insert(self, collection_name, data):
        return {"insert_count": len(data)}


def test_milvus_proxy_records_collections() -> None:
    observed = ObservedMilvusClient(_FakeMilvusClient())
    observed.query("techkg_chunks", filter="id > 0")
    observed.insert("techkg_chunks", data=[{"id": 1}])
    report = access.access_report()
    assert report["milvus"]["techkg_chunks"] == {"ops": ["read", "write"], "count": 2}


class _FakeLlmClient:
    model = "glm-4.7-flash"

    def synthesize(self, prompt):
        return None if prompt == "fail" else f"ok:{prompt}"


class _FakeEmbeddingClient:
    model = "embedding-3"

    def embed(self, texts):
        return None


def test_llm_and_embedding_proxy_record_calls() -> None:
    llm = ObservedLLMClient(_FakeLlmClient())
    assert llm.model == "glm-4.7-flash"
    assert llm.synthesize("hello") == "ok:hello"
    assert llm.synthesize("fail") is None

    embedding = ObservedEmbeddingClient(_FakeEmbeddingClient())
    assert embedding.embed(["a"]) is None

    report = access.access_report()
    assert report["llm"]["glm-4.7-flash"] == {"calls": 2, "failures": 1}
    assert report["embedding"]["embedding-3"] == {"calls": 1, "failures": 1}


def test_context_mysql_attaches_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    """端到端：Context.mysql 挂钩后，经 engine 执行的语句被记录。"""

    class FakeMySQLClient:
        def __init__(self, **kwargs):
            from sqlalchemy import create_engine

            self._engine = create_engine("sqlite:///:memory:")

        @property
        def engine(self):
            return self._engine

    monkeypatch.setattr("infra.mysql.MySQLClient", FakeMySQLClient)
    ctx = Context(
        {"mysql": {"host": "h", "port": 3306, "database": "mydb", "username": "u", "password": "p"}}
    )
    client = ctx.mysql
    with client.engine.connect() as conn:
        conn.execute(text("CREATE TABLE some_table (id INTEGER)"))
        conn.execute(text("SELECT * FROM some_table"))
    report = access.access_report()
    assert ("mydb", "some_table") in _mysql_tables(report)


def test_sidecar_written_and_replayed(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    sidecar = tmp_path / "access.jsonl"
    monkeypatch.setenv("KG_ACCESS_LOG", str(sidecar))

    record_mysql_statement("SELECT * FROM t_a", db="db1")
    access.flush_access_sidecar()

    lines = sidecar.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0].startswith('{"t": "mysql"') or '"t": "mysql"' in lines[0]
    assert '"t": "report"' in lines[-1]

    replayed = report_from_sidecar(str(sidecar))
    assert replayed is not None
    assert ("db1", "t_a") in _mysql_tables(replayed)


def test_report_from_sidecar_missing_file() -> None:
    assert report_from_sidecar("/nonexistent/kg_access.jsonl") is None


def test_merge_access_reports_union_and_max() -> None:
    sidecar_report = {
        "mysql": {
            "db1": {"t_a": {"ops": ["SELECT"], "statements": 3}},
            "_unparsed": {"count": 0, "last": ""},
        },
        "graph": {"tag": {"Scholar": {"ops": ["write"], "count": 2}}},
        "milvus": {},
        "llm": {"m1": {"calls": 2, "failures": 0}},
        "embedding": {},
    }
    stdout_report = {
        "mysql": {
            "db1": {
                "t_a": {"ops": ["SELECT", "UPDATE"], "statements": 2},
                "t_b": {"ops": ["SELECT"], "statements": 1},
            },
            "_unparsed": {"count": 1, "last": "xxx"},
        },
        "graph": {"tag": {"Scholar": {"ops": ["read"], "count": 5}}},
        "milvus": {"c1": {"ops": ["read"], "count": 1}},
        "llm": {},
        "embedding": {},
    }
    merged = merge_access_reports(sidecar_report, stdout_report)
    assert merged is not None
    assert merged["mysql"]["db1"]["t_a"]["ops"] == ["SELECT", "UPDATE"]
    assert merged["mysql"]["db1"]["t_a"]["statements"] == 3
    assert merged["mysql"]["db1"]["t_b"]["statements"] == 1
    assert merged["mysql"]["_unparsed"] == {"count": 1, "last": "xxx"}
    assert merged["graph"]["tag"]["Scholar"] == {"ops": ["read", "write"], "count": 5}
    assert merged["milvus"]["c1"] == {"ops": ["read"], "count": 1}
    assert merged["llm"]["m1"] == {"calls": 2, "failures": 0}


def test_merge_access_reports_empty() -> None:
    assert merge_access_reports(None, None) is None
    # 单边输入直接透传
    assert merge_access_reports({"mysql": {}}, None) == {"mysql": {}}
