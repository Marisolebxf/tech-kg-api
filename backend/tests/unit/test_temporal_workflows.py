import hashlib
from io import BytesIO
from types import SimpleNamespace

import pytest

from service.temporal_workflows import (
    _failure_message,
    execute_schema_script,
    persist_schema_result,
)


def test_failure_message_keeps_nested_activity_details() -> None:
    inner = RuntimeError("intentional failure")
    outer = RuntimeError("Activity task failed")
    outer.__cause__ = inner

    assert _failure_message(outer) == "Activity task failed | intentional failure"


class ScriptStorage:
    def __init__(self, source: bytes) -> None:
        self.source = source

    def get_object(self, bucket: str, object_key: str) -> BytesIO:
        assert bucket == "schemas"
        assert object_key == "technology.py"
        return BytesIO(self.source)


async def test_execute_schema_script_downloads_verifies_and_runs(monkeypatch) -> None:
    source = b"def transform(payload):\n    return {'value': payload['value'] * 2}\n"
    storage = ScriptStorage(source)
    monkeypatch.setattr("infra.s3.get_schema_s3_storage", lambda: storage)

    result = await execute_schema_script(
        {
            "bucket": "schemas",
            "objectKey": "technology.py",
            "sha256": hashlib.sha256(source).hexdigest(),
            "payload": {"value": 4},
        }
    )

    assert result == {"value": 8}


async def test_execute_schema_script_rejects_changed_object(monkeypatch) -> None:
    storage = ScriptStorage(b"def transform(payload):\n    return payload\n")
    monkeypatch.setattr("infra.s3.get_schema_s3_storage", lambda: storage)

    with pytest.raises(ValueError, match="sha256"):
        await execute_schema_script(
            {
                "bucket": "schemas",
                "objectKey": "technology.py",
                "sha256": "0" * 64,
                "payload": {},
            }
        )


class GraphStorageStub:
    def __init__(self) -> None:
        self.queries = []
        self.nodes = {"S1": SimpleNamespace(id="S1"), "S2": SimpleNamespace(id="S2")}
        self.edges = []

    def execute_write(self, query):
        self.queries.append(query)

    def merge_node(self, labels, identity, properties):
        node_id = str(next(iter(identity.values())))
        self.nodes[node_id] = SimpleNamespace(id=node_id)
        return self.nodes[node_id]

    def get_node(self, node_id):
        return self.nodes.get(str(node_id))

    def create_edge(self, source, target, edge_type, properties):
        edge = SimpleNamespace(id=f"{source}->{target}@0")
        self.edges.append((source, target, edge_type, properties))
        return edge


async def test_schema_results_are_validated_and_persisted(monkeypatch) -> None:
    graph = GraphStorageStub()
    monkeypatch.setattr("infra.graph_db.get_graph_client", lambda space=None: graph)

    entity = await persist_schema_result(
        {
            "schemaKind": "entity",
            "schemaName": "Technology",
            "identityKey": "technology_id",
            "properties": [{"name": "technology_id", "dataType": "string"}],
            "result": {"technology_id": "T1", "name": "知识图谱"},
        }
    )
    relation = await persist_schema_result(
        {
            "schemaKind": "relation",
            "schemaName": "COOPERATES_WITH",
            "properties": [{"name": "score", "dataType": "double"}],
            "result": {"sourceId": "S1", "targetId": "S2", "score": 0.9},
        }
    )

    assert entity == {"kind": "entity", "count": 1, "nodeIds": ["T1"]}
    assert relation["count"] == 1
    assert graph.edges[0][2] == "COOPERATES_WITH"
