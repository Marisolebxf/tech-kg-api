"""平台喂数转换 + 写图 activity 单测：临时脚本转换、activeProps 过滤（mock graph client）。"""

from __future__ import annotations

import pytest

from service.temporal_workflows import execute_transform, write_records


class FakeGraphClient:
    def __init__(self, settings) -> None:
        self.settings = settings
        self.merged_nodes: list[tuple] = []
        self.merged_edges: list[tuple] = []
        self.written_queries: list[str] = []

    def connect(self) -> None:
        self.connected = True

    def close(self) -> None:
        pass

    def merge_node(self, labels, identity_props, properties=None):
        self.merged_nodes.append((labels, identity_props, properties or {}))

    def merge_edge(self, source_id, target_id, edge_type, identity_props, properties=None):
        self.merged_edges.append((source_id, target_id, edge_type, properties or {}))

    def execute_write(self, query, params=None):
        self.written_queries.append(query)
        return {"records": []}

    def execute_read(self, query, params=None):
        # DESCRIBE TAG/EDGE 返回空列集（按值类型写图）
        return {"records": []}


@pytest.fixture
def fake_graph(monkeypatch: pytest.MonkeyPatch):
    clients: list[FakeGraphClient] = []

    def factory(settings):
        client = FakeGraphClient(settings)
        clients.append(client)
        return client

    monkeypatch.setattr("infra.graph_db.client.TRSGraphClient", factory)
    return clients


TRANSFORM_SCRIPT = """
def workflow(payload):
    rows = payload["rows"]
    assert payload["source_table"] == "gkx.scholar"
    assert payload["kind"] == "entity"
    return {
        "entities": [
            {
                "id": row["id"],
                "props": {
                    "id": row["id"],
                    "name": row["name"],
                    "rank": row.get("rank"),
                    "legacy": "should-be-filtered",
                },
            }
            for row in rows
        ],
        "_watermark": "1999-01-01T00:00:00",
    }
"""


@pytest.mark.asyncio
async def test_execute_transform_invokes_script_workflow(tmp_path) -> None:
    script = tmp_path / "transform.py"
    script.write_text(TRANSFORM_SCRIPT, encoding="utf-8")
    output = await execute_transform(
        {
            "scriptPath": str(script),
            "functionName": "workflow",
            "rows": [
                {"id": "S-1", "name": "张三", "rank": 1},
                {"id": "S-2", "name": "李四", "rank": 2},
            ],
            "source": {
                "datasourceId": "MYSQL-1",
                "databaseName": "gkx",
                "tableName": "scholar",
                "pkColumn": "id",
                "timeColumn": "update_time",
            },
            "kind": "entity",
            "timeoutSeconds": 30,
        }
    )
    assert [e["id"] for e in output["entities"]] == ["S-1", "S-2"]
    # 脚本的 _watermark 元字段被忽略（平台管理水位）
    assert "_watermark" not in output


MULTI_STEP_PROBE_SCRIPT = """
import json

from kg_sdk import current_context


def step_clean(payload):
    # 第 1 步：与单步 transform 同构（rows/source_table/kind/source）
    assert "rows" in payload and "input" not in payload
    ctx = current_context()
    return {"cleaned": [r for r in payload["rows"] if r.get("ok")], "failures": []}


def step_emit(payload):
    # 第 N>1 步：payload["input"] = 上一步完整输出，无 rows；ctx 带复合 stepId/prevOutputs
    ctx = current_context()
    assert "rows" not in payload and "input" in payload
    return {
        "entities": [
            {"id": "E_" + r["id"], "props": {"name": r["name"]}} for r in payload["input"]["cleaned"]
        ],
        "_probe": json.dumps(
            {
                "stepId": ctx.step_id if ctx else None,
                "attempt": ctx.attempt if ctx else None,
                "prevKeys": sorted((ctx.prev_outputs or {}).keys()) if ctx else [],
                "prevStats": (ctx.prev_outputs or {}).get("clean", {}).get("stats"),
            },
            ensure_ascii=False,
        ),
    }
"""


@pytest.mark.asyncio
async def test_execute_transform_step_chain_payload_and_ctx(tmp_path) -> None:
    """多步链的第 N>1 步：payload= {input: 上一步输出}（无 rows），ctx 带 stepId/attempt/prevOutputs。"""
    script = tmp_path / "steps.py"
    script.write_text(MULTI_STEP_PROBE_SCRIPT, encoding="utf-8")
    source = {
        "datasourceId": "MYSQL-1",
        "databaseName": "gkx",
        "tableName": "scholar",
        "pkColumn": "id",
        "timeColumn": "update_time",
    }
    # 第 1 步：请求形状与单步 transform 相同
    first = await execute_transform(
        {
            "scriptPath": str(script),
            "functionName": "step_clean",
            "rows": [{"id": "1", "name": "甲", "ok": True}, {"id": "2", "name": "乙", "ok": False}],
            "source": source,
            "kind": "entity",
            "timeoutSeconds": 30,
            "selectors": {},
            "definitionId": "schema-extract-widget",
            "stepId": "source:bind-1",
            "ctxStepId": "source:bind-1#clean",
        }
    )
    assert first["cleaned"] == [{"id": "1", "name": "甲", "ok": True}]

    # 第 2 步：input/prevOutputs 由 worker 注入，请求不再带 rows
    second = await execute_transform(
        {
            "scriptPath": str(script),
            "functionName": "step_emit",
            "source": source,
            "kind": "entity",
            "timeoutSeconds": 30,
            "selectors": {},
            "definitionId": "schema-extract-widget",
            "stepId": "source:bind-1",
            "ctxStepId": "source:bind-1#emit",
            "input": first,
            "prevOutputs": {"clean": {**first, "stats": {"cleaned": 1}}},
        }
    )
    import json as _json

    probe = _json.loads(second["_probe"])
    assert probe["stepId"] == "source:bind-1#emit"
    assert probe["attempt"] == 1  # 单测直调无 activity 上下文 → 占位 1
    assert probe["prevKeys"] == ["clean"]
    assert probe["prevStats"] == {"cleaned": 1}
    assert [e["id"] for e in second["entities"]] == ["E_1"]


@pytest.mark.asyncio
async def test_write_records_filters_non_active_props(fake_graph) -> None:
    records = [
        {
            "id": "S-1",
            "props": {"id": "S-1", "name": "张三", "rank": 1, "legacy": "x"},
        },
        {"id": "S-2", "props": {"id": "S-2", "name": "李四"}},
    ]
    result = await write_records(
        {
            "kind": "entity",
            "name": "Scholar",
            "activeProps": ["id", "name", "rank"],  # legacy 已软删
            "records": records,
            "graph": {"space": "techkg"},
        }
    )
    assert result["written"] == 2
    client = fake_graph[0]
    assert client.settings.space == "techkg"
    # 实体走 nGQL INSERT VERTEX（REST merge 会剥离 id/name，schema NOT NULL 列会 400）
    assert len(client.written_queries) == 2
    first = client.written_queries[0]
    assert first.startswith("INSERT VERTEX `Scholar`(")
    assert '"S-1"' in first and '"张三"' in first and "legacy" not in first  # legacy 已剥离


@pytest.mark.asyncio
async def test_write_records_edges(fake_graph) -> None:
    records = [
        {"fromId": "S-1", "toId": "O-1", "props": {"source_table": "gkx.scholar"}},
    ]
    result = await write_records(
        {
            "kind": "relation",
            "name": "EMPLOYED_BY",
            "activeProps": ["source_table"],
            "records": records,
            "graph": {},
        }
    )
    assert result["written"] == 1
    client = fake_graph[0]
    # 关系写入走 nGQL INSERT EDGE（REST merge 的 identityProps 必非空，平台边语义无 identity）
    assert len(client.written_queries) == 1
    stmt = client.written_queries[0]
    assert stmt.startswith("INSERT EDGE `EMPLOYED_BY`(")
    assert '"S-1"->"O-1"' in stmt
    assert "gkx.scholar" in stmt


@pytest.mark.asyncio
async def test_write_records_without_active_props_writes_all(fake_graph) -> None:
    await write_records(
        {
            "kind": "entity",
            "name": "Scholar",
            "activeProps": [],
            "records": [{"id": "S-1", "props": {"id": "S-1", "extra": 1}}],
            "graph": {},
        }
    )
    query = fake_graph[0].written_queries[0]
    assert "`id`" in query and "`extra`" in query
