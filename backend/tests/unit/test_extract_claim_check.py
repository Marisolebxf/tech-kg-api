"""抽取载荷 S3 中转（claim-check）activity 级单测：双形状等价 / chunks 归档 / 失败键流转。

契约核心：``rowsKey`` 下载路径组装的 payload 与 ``rows`` 内联路径逐字节等价
（脚本对 S3 无感）；records/失败清单经 S3 后，activity 返回只含元数据。
"""

from __future__ import annotations

import json
from io import BytesIO
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from service import extract_payload_store as store
from service.temporal_workflows import (
    _failure_entries_count,
    _iter_batch_chunks,
    _shape_step_failures,
    _split_rows_for_upload,
    detect_extract_collisions,
    execute_transform,
    read_source_batch,
    record_extract_failures,
    resolve_entity_batch,
    write_records,
)

# ---------------------------------------------------------------------------
# 测试基础设施：内存 S3 + sqlite 假源库 + 假图客户端
# ---------------------------------------------------------------------------


class FakeBody(BytesIO):
    def close(self) -> None:  # noqa: D102
        pass


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    @property
    def bucket(self) -> str:
        return "b"

    def put_bytes(self, key: str, data: bytes, content_type: str) -> SimpleNamespace:
        self.objects[key] = data
        return SimpleNamespace(bucket=self.bucket, object_key=key, etag=None)

    def get_object(self, bucket: str, key: str) -> FakeBody:
        return FakeBody(self.objects[key])

    def dumped(self, key: str) -> Any:
        return store.load_extract_payload_json(key)


class FakeGraphClient:
    """消歧/冲突检测用：DESCRIBE/同名召回都返回空（全部按新实体处理）。"""

    def __init__(self, settings) -> None:
        self.settings = settings
        self.written: list[str] = []

    def connect(self) -> None:
        pass

    def close(self) -> None:
        pass

    def execute_query(self, query: str, params: Any = None):
        return SimpleNamespace(records=[])

    def execute_read(self, query: str, params: Any = None):
        return SimpleNamespace(records=[])

    def execute_write(self, query: str, params: Any = None):
        self.written.append(query)
        return SimpleNamespace(records=[])


@pytest.fixture
def fake_s3(monkeypatch: pytest.MonkeyPatch) -> FakeS3:
    fake = FakeS3()
    monkeypatch.setattr("infra.s3.get_schema_s3_storage", lambda: fake)
    return fake


@pytest.fixture
def relay_on(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SCHEMA_EXTRACT_PAYLOAD_S3_ENABLED", "true")


@pytest.fixture
def relay_off(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SCHEMA_EXTRACT_PAYLOAD_S3_ENABLED", "false")


def _make_source_engine(rows: list[dict[str, Any]]):
    """sqlite 假源库：ATTACH 出 techkg 库 + widgets 表（MySQL 反引号 SQL 可直接跑）。"""
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    with engine.connect() as conn:
        conn.execute(text("ATTACH ':memory:' AS techkg"))
        conn.execute(text("CREATE TABLE techkg.widgets (id TEXT, name TEXT, update_time TEXT)"))
        for row in rows:
            conn.execute(
                text("INSERT INTO techkg.widgets (id, name, update_time) VALUES (:i, :n, :t)"),
                {"i": row["id"], "n": row["name"], "t": row["update_time"]},
            )
        conn.commit()
    return engine


class FakeMySQLClient:
    def __init__(self, engine) -> None:
        self.engine = engine

    def dispose(self) -> None:
        pass


@pytest.fixture
def sqlite_source(monkeypatch: pytest.MonkeyPatch):
    rows = [
        {"id": f"w{i}", "name": f"行{i}", "update_time": f"2026-09-01 00:0{i}:00"} for i in range(7)
    ]
    engine = _make_source_engine(rows)
    monkeypatch.setattr(
        "service.mysql_datasource.get_mysql_settings_by_id",
        lambda ds: {"host": "h", "port": 3306, "username": "u", "password": "p"},
    )
    monkeypatch.setattr("infra.mysql.MySQLClient", lambda **kw: FakeMySQLClient(engine))
    monkeypatch.setattr("service.script_watermark.read_watermark", lambda *a, **k: None)
    return rows


READ_BASE = {
    "datasourceId": "ds-1",
    "database": "techkg",
    "table": "widgets",
    "timeColumn": "",
    "pkColumn": "id",
    "batchSize": 3,
    "batchIdx": 0,
    "stepId": "source:bind-1",
    "definitionId": "schema-extract-widget",
}

# ---------------------------------------------------------------------------
# 纯函数
# ---------------------------------------------------------------------------


class TestSplitRowsForUpload:
    def test_groups_by_batch_size(self):
        rows = [{"id": i} for i in range(7)]
        groups = _split_rows_for_upload(rows, batch_size=3, budget=10**9)
        assert [len(g) for g in groups] == [3, 3, 1]

    def test_halves_oversized_group(self):
        # 每行 ~1KB，预算 2KB：3 行组递归折半到 [1, 1, 1]（2 行子组仍超预算继续折）
        rows = [{"id": i, "blob": "x" * 1000} for i in range(3)]
        groups = _split_rows_for_upload(rows, batch_size=3, budget=2000)
        assert [len(g) for g in groups] == [1, 1, 1]

    def test_halving_stops_when_subgroup_fits(self):
        # 每行 ~1KB，预算 2.2KB：3 行组折半到 [1, 2]（2 行子组已进预算不再折）
        rows = [{"id": i, "blob": "x" * 1000} for i in range(3)]
        groups = _split_rows_for_upload(rows, batch_size=3, budget=2200)
        assert [len(g) for g in groups] == [1, 2]

    def test_single_oversized_row_uploaded_as_is(self):
        rows = [{"id": 0, "blob": "x" * 100_000}]
        groups = _split_rows_for_upload(rows, batch_size=5, budget=1000)
        assert [len(g) for g in groups] == [1]


class TestShapeAndCount:
    def test_shape_filters_and_coerces(self):
        shaped = _shape_step_failures(
            [
                {"recordId": "a", "error": ValueError("x")},
                {"error": "无 recordId，丢弃"},
                "not-a-dict",
                {"recordId": None, "error": "None id 也丢弃"},
            ],
            source_binding_id="bind-1",
            table_label="techkg.widgets",
        )
        assert shaped == [
            {
                "sourceBindingId": "bind-1",
                "sourceTable": "techkg.widgets",
                "recordId": "a",
                "error": "x",
            }
        ]

    def test_failure_entries_count_mixed(self):
        entries = [
            {"failuresKey": "k1", "count": 5},
            {"recordId": "x"},
            {"failuresKey": "k2", "count": 2},
        ]
        assert _failure_entries_count(entries) == 8

    def test_iter_chunks_s3_shape(self):
        batch = {
            "chunks": [
                {"key": "k0", "rowCount": 3, "recordIds": ["a", "b", "c"]},
                {"key": "k1", "rowCount": 1},
            ]
        }
        chunks = list(_iter_batch_chunks(batch, batch_size=3, pk_column="id"))
        assert chunks[0] == {
            "index": 0,
            "rowCount": 3,
            "recordIds": ["a", "b", "c"],
            "rowsKey": "k0",
        }
        assert chunks[1] == {"index": 1, "rowCount": 1, "recordIds": [], "rowsKey": "k1"}

    def test_iter_chunks_inline_shape_matches_history_behavior(self):
        batch = {"rows": [{"id": 1}, {"id": 2}, {"id": 3}]}
        chunks = list(_iter_batch_chunks(batch, batch_size=2, pk_column="id"))
        assert [c["rowCount"] for c in chunks] == [2, 1]
        assert chunks[0]["rows"] == [{"id": 1}, {"id": 2}]
        assert "rowsKey" not in chunks[0]


# ---------------------------------------------------------------------------
# read_source_batch：chunks 归档
# ---------------------------------------------------------------------------


class TestReadSourceBatchRelay:
    async def test_relay_on_returns_chunks_metadata(self, sqlite_source, fake_s3, relay_on):
        result = await read_source_batch({**READ_BASE, "batchSize": 3, "offset": 0})
        assert "rows" not in result
        assert result["totalRows"] == 3
        assert result["effectiveBatchSize"] == 3
        assert len(result["chunks"]) == 1
        chunk = result["chunks"][0]
        assert chunk["rowCount"] == 3
        assert "recordIds" not in chunk  # 普通模式不带（失败由脚本 failures 报）
        assert fake_s3.dumped(chunk["key"]) == [
            {"id": "w0", "name": "行0", "update_time": "2026-09-01 00:00:00"},
            {"id": "w1", "name": "行1", "update_time": "2026-09-01 00:01:00"},
            {"id": "w2", "name": "行2", "update_time": "2026-09-01 00:02:00"},
        ]
        assert (
            chunk["key"].startswith("runs/local-")
            and "/payloads/source:bind-1/0000/" in chunk["key"]
        )

    async def test_relay_on_ids_mode_chunks_with_record_ids(self, sqlite_source, fake_s3, relay_on):
        result = await read_source_batch(
            {**READ_BASE, "batchSize": 2, "recordIds": ["w0", "w1", "w2", "w3", "w4"]}
        )
        assert [c["rowCount"] for c in result["chunks"]] == [2, 2, 1]
        assert result["chunks"][0]["recordIds"] == ["w0", "w1"]
        assert result["chunks"][2]["recordIds"] == ["w4"]
        assert result["totalRows"] == 5

    async def test_relay_off_keeps_inline_shape(self, sqlite_source, fake_s3, relay_off):
        result = await read_source_batch({**READ_BASE, "batchSize": 3, "offset": 0})
        assert "chunks" not in result
        assert len(result["rows"]) == 3
        assert result["recordIds"] == ["w0", "w1", "w2"]
        assert fake_s3.objects == {}  # 关 flag 不写任何对象


# ---------------------------------------------------------------------------
# execute_transform：payload 逐字节等价 + 元数据返回
# ---------------------------------------------------------------------------

HASH_SCRIPT = """
import hashlib, json


def transform(payload):
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    rows = payload.get("rows") or []
    return {
        "entities": [
            {"id": "n_" + str(r["id"]), "props": {"name": r["name"]}}
            for r in rows
            if r["id"] != "bad"
        ],
        "failures": (
            [{"recordId": "bad", "error": "ValueError: 毒行"}]
            if any(r["id"] == "bad" for r in rows)
            else []
        ),
        "stats": {"payloadSha": hashlib.sha256(raw.encode()).hexdigest()},
    }
"""

CHAIN_SCRIPT = """
import json


def step_clean(payload):
    return {
        "cleaned": [{"id": str(r["id"])} for r in payload["rows"]],
        "failures": [],
        "stats": {"n": len(payload.get("rows") or [])},
    }


def step_emit(payload):
    prev = None
    try:
        from kg_sdk import current_context

        ctx = current_context()
        prev = (ctx.prev_outputs or {}) if ctx else None
    except Exception:
        pass
    return {
        "entities": [{"id": "E_" + r["id"], "props": {}} for r in payload["input"]["cleaned"]],
        "_probe": json.dumps(
            {"input": payload["input"], "prev": prev}, ensure_ascii=False, default=str
        ),
    }
"""

SOURCE = {
    "id": "bind-1",
    "datasourceId": "MYSQL-1",
    "databaseName": "gkx",
    "tableName": "scholar",
    "pkColumn": "id",
    "timeColumn": "update_time",
}


def _transform_request(script_path: str, **overrides) -> dict[str, Any]:
    request = {
        "scriptPath": str(script_path),
        "functionName": "transform",
        "source": SOURCE,
        "kind": "entity",
        "timeoutSeconds": 30,
        "selectors": {},
        "definitionId": "schema-extract-widget",
        "stepId": "source:bind-1",
        "batchIdx": 0,
        "chunkIdx": 0,
    }
    request.update(overrides)
    return request


ROWS = [
    {"id": "1", "name": "甲", "金额": 12.5, "tags": ["a", "b"]},
    {"id": "bad", "name": "毒"},
]


class TestExecuteTransformRelay:
    async def test_rows_key_payload_byte_equivalent(self, tmp_path, fake_s3):
        """rowsKey 下载路径与 rows 内联路径：脚本看到的 payload 逐字节一致（hash 钉死）。"""
        script = tmp_path / "transform.py"
        script.write_text(HASH_SCRIPT, encoding="utf-8")
        legacy = await execute_transform(
            _transform_request(script, rows=ROWS, functionName="transform")
        )
        rows_key = store.put_extract_payload_json("source:bind-1", 0, "rows-00", ROWS)
        relay = await execute_transform(
            _transform_request(script, rowsKey=rows_key, functionName="transform")
        )
        # 中转返回元数据形状
        assert set(relay) >= {"outKey", "hasRecords", "entityCount", "edgeCount", "failureCount"}
        assert relay["hasRecords"] is True
        assert relay["entityCount"] == 1
        assert relay["failureCount"] == 1
        assert relay["stats"]["payloadSha"] == legacy["stats"]["payloadSha"]
        # outKey 归档 = 脚本视角的精确输出（含 entities/failures/stats 原样）
        archived = fake_s3.dumped(relay["outKey"])
        assert archived["entities"] == legacy["entities"]
        assert archived["failures"] == legacy["failures"]
        # failuresKey 归档 = 平台整形后的失败记录
        shaped = fake_s3.dumped(relay["failuresKey"])
        assert shaped == [
            {
                "sourceBindingId": "bind-1",
                "sourceTable": "gkx.scholar",
                "recordId": "bad",
                "error": "ValueError: 毒行",
            }
        ]

    async def test_step_chain_input_key_no_truncation(self, tmp_path, fake_s3):
        """第 N>1 步经 inputKey/prevKeys 下载：input = 上一步完整输出，无 _truncated。"""
        script = tmp_path / "steps.py"
        script.write_text(CHAIN_SCRIPT, encoding="utf-8")
        rows_key = store.put_extract_payload_json(
            "source:bind-1#clean", 0, "rows-00", [{"id": "1"}, {"id": "2"}]
        )
        first = await execute_transform(
            _transform_request(
                script,
                functionName="step_clean",
                rowsKey=rows_key,
                ctxStepId="source:bind-1#clean",
            )
        )
        assert "outKey" in first
        second = await execute_transform(
            _transform_request(
                script,
                functionName="step_emit",
                inputKey=first["outKey"],
                prevKeys={"clean": first["outKey"]},
                ctxStepId="source:bind-1#emit",
                chunkIdx=1,
            )
        )
        assert second["entityCount"] == 2
        # 中转返回只带元数据；全量输出（含 _probe 探针）在 outKey 归档里
        archived = fake_s3.dumped(second["outKey"])
        assert [e["id"] for e in archived["entities"]] == ["E_1", "E_2"]
        probe = json.loads(archived["_probe"])
        # input = 上一步归档的全量输出（cleaned + failures + stats），未被截断
        assert probe["input"] == fake_s3.dumped(first["outKey"])
        assert "_truncated" not in json.dumps(probe)
        # ctx.prev_outputs 同样拿到全量
        assert probe["prev"]["clean"] == fake_s3.dumped(first["outKey"])


# ---------------------------------------------------------------------------
# resolve / write / detect / failures：recordsKey 与 failureRefs
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_graph(monkeypatch: pytest.MonkeyPatch) -> list[FakeGraphClient]:
    clients: list[FakeGraphClient] = []

    def factory(settings):
        client = FakeGraphClient(settings)
        clients.append(client)
        return client

    monkeypatch.setattr("infra.graph_db.client.TRSGraphClient", factory)
    return clients


class TestDownstreamRecordsKey:
    async def test_write_records_extracts_from_full_output(self, fake_graph, fake_s3):
        out_key = store.put_extract_payload_json(
            "source:bind-1",
            0,
            "out-00",
            {"entities": [{"id": "n1", "props": {"id": "n1", "name": "甲"}}], "stats": {}},
        )
        result = await write_records(
            {
                "kind": "entity",
                "name": "Widget",
                "activeProps": ["id", "name"],
                "recordsKey": out_key,
                "graph": {},
                "sourceTable": "gkx.scholar",
            }
        )
        assert result == {"written": 1}
        assert any("INSERT VERTEX" in q for q in fake_graph[0].written)

    async def test_resolve_entity_batch_relays_kept_records(self, fake_graph, fake_s3):
        out_key = store.put_extract_payload_json(
            "source:bind-1",
            0,
            "out-00",
            {
                "entities": [
                    {"id": "n1", "props": {"name": "甲"}},
                    {"id": "n2", "props": {"name": "乙"}},
                ]
            },
        )
        result = await resolve_entity_batch(
            {
                "name": "Widget",
                "recordsKey": out_key,
                "graph": {},
                "stepId": "source:bind-1",
                "batchIdx": 0,
                "chunkIdx": 0,
                "sourceTable": "gkx.scholar",
            }
        )
        assert result["keptCount"] == 2
        assert result["new"] == 2
        kept = fake_s3.dumped(result["outKey"])
        assert [r["id"] for r in kept] == ["n1", "n2"]

    async def test_detect_collisions_reads_key(self, fake_graph, fake_s3):
        out_key = store.put_extract_payload_json(
            "source:bind-1",
            0,
            "out-00",
            {"entities": [{"id": "n1", "props": {"name": "甲"}}]},
        )
        result = await detect_extract_collisions(
            {"name": "Widget", "recordsKey": out_key, "graph": {}, "schemaKey": "widget"}
        )
        assert result == {"collisions": 0}


class TestFailureRefs:
    async def test_record_failures_expands_refs_and_caps(self, fake_s3, monkeypatch):
        from service.manual_review_production import manual_review_service

        created: list[dict] = []

        def fake_create(**kwargs):
            created.append(kwargs)
            return {"reviewId": f"MR-{len(created)}"}

        monkeypatch.setattr(manual_review_service, "create_direct_case", fake_create)
        ref_a = store.put_extract_payload_json(
            "s", 0, "failures-00", [{"recordId": f"a{i}", "error": "e"} for i in range(3)]
        )
        ref_b = store.put_extract_payload_json(
            "s", 0, "failures-01", [{"recordId": f"b{i}", "error": "e"} for i in range(2)]
        )
        inline = [{"recordId": "inline-1", "error": "e"}]
        result = await record_extract_failures(
            {
                "failures": inline,
                "failureRefs": [
                    {"failuresKey": ref_a, "count": 3},
                    {"failuresKey": ref_b, "count": 2},
                ],
                "cap": 4,
                "schemaId": "s1",
                "schemaKey": "widget",
                "kind": "entity",
                "name": "Widget",
            }
        )
        assert result == {"recorded": 4}
        # 内联条目先于 refs 展开，cap 截断发生在展开后的清单上
        assert [c["source_record_id"] for c in created] == ["inline-1", "a0", "a1", "a2"]

    async def test_record_failures_inline_only_no_cap(self, fake_s3, monkeypatch):
        from service.manual_review_production import manual_review_service

        created: list[dict] = []

        def fake_create(**kwargs):
            created.append(kwargs)
            return {"reviewId": f"MR-{len(created)}"}

        monkeypatch.setattr(manual_review_service, "create_direct_case", fake_create)
        result = await record_extract_failures(
            {
                "failures": [{"recordId": "x", "error": "e", "sourceTable": "gkx.t"}],
                "schemaId": "s1",
                "kind": "entity",
            }
        )
        assert result == {"recorded": 1}
        assert created[0]["object_name"] == "gkx.t#x"
