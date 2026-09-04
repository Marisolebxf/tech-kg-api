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
