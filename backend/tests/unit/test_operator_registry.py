from __future__ import annotations

import json
import time

import pytest

from service.operator_registry import (
    OperatorExecutionError,
    OperatorKind,
    OperatorRegistry,
    OperatorValidationError,
)


class MemoryOperatorStore:
    def __init__(self):
        self.bundles = {}
        self.ready = False

    def ensure_ready(self):
        self.ready = True

    def exists(self, name):
        return name in self.bundles

    def put(self, name, bundle):
        self.bundles[name] = json.loads(json.dumps(bundle))

    def delete(self, name):
        self.bundles.pop(name, None)

    def list_bundles(self):
        return [self.bundles[name] for name in sorted(self.bundles)]


async def test_create_invoke_and_update_operator(tmp_path):
    registry = OperatorRegistry(tmp_path)
    source_v1 = """\
def operator(data, ctx):
    return [{**item, "score": len(item["name"]) * ctx.get("factor", 10)} for item in data]
"""
    source_v2 = source_v1.replace("10)", "100)")

    manifest = registry.create(
        name="user.name_score",
        version="1.0.0",
        kind=OperatorKind.DATA_PROCESSING,
        source=source_v1,
        description="名称评分",
    )

    assert manifest.version == "1.0.0"
    assert await registry.invoke("user.name_score", [{"name": "foo"}]) == [
        {"name": "foo", "score": 30}
    ]

    registry.update(
        name="user.name_score",
        version="2.0.0",
        kind=OperatorKind.DATA_PROCESSING,
        source=source_v2,
    )
    assert await registry.invoke("user.name_score", [{"name": "foo"}]) == [
        {"name": "foo", "score": 300}
    ]


async def test_direct_file_edit_is_hot_reloaded_on_next_invoke(tmp_path):
    registry = OperatorRegistry(tmp_path)
    registry.create(
        name="user.hot",
        version="1.0.0",
        kind=OperatorKind.DATA_PROCESSING,
        source="def operator(data, ctx):\n    return [{**x, 'value': 1} for x in data]\n",
    )
    assert (await registry.invoke("user.hot", [{}]))[0]["value"] == 1

    (tmp_path / "user.hot.py").write_text(
        "def operator(data, ctx):\n    return [{**x, 'value': 2} for x in data]\n",
        encoding="utf-8",
    )

    assert (await registry.invoke("user.hot", [{}]))[0]["value"] == 2


def test_watcher_reload_path_updates_registry_without_api_call(tmp_path):
    registry = OperatorRegistry(tmp_path, watch_interval=0.01)
    registry.create(
        name="user.watched",
        version="1.0.0",
        kind=OperatorKind.DATA_PROCESSING,
        source="def operator(data, ctx):\n    return [{'value': 1}]\n",
    )
    registry.start_watcher()
    try:
        (tmp_path / "user.watched.py").write_text(
            "def operator(data, ctx):\n    return [{'value': 2}]\n", encoding="utf-8"
        )
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            with registry._lock:
                function = registry._operators["user.watched"].function
            if function([], {}) == [{"value": 2}]:
                break
            time.sleep(0.01)
        else:
            pytest.fail("watcher did not reload the edited operator")
    finally:
        registry.stop_watcher()


async def test_broken_hot_reload_keeps_previous_function(tmp_path):
    registry = OperatorRegistry(tmp_path)
    registry.create(
        name="user.stable",
        version="1.0.0",
        kind=OperatorKind.DATA_PROCESSING,
        source="def operator(data, ctx):\n    return [{'ok': True}]\n",
    )
    (tmp_path / "user.stable.py").write_text("def operator(:\n", encoding="utf-8")

    assert await registry.invoke("user.stable", [{}]) == [{"ok": True}]


def test_invalid_source_does_not_replace_persisted_operator(tmp_path):
    registry = OperatorRegistry(tmp_path)
    registry.create(
        name="user.valid",
        version="1.0.0",
        kind=OperatorKind.DATA_PROCESSING,
        source="def operator(data, ctx):\n    return data\n",
    )

    with pytest.raises(OperatorValidationError, match="必须定义"):
        registry.update(
            name="user.valid",
            version="2.0.0",
            kind=OperatorKind.DATA_PROCESSING,
            source="def another(data, ctx):\n    return data\n",
        )

    persisted = json.loads((tmp_path / "user.valid.json").read_text(encoding="utf-8"))
    assert persisted["version"] == "1.0.0"


async def test_invalid_operator_result_is_rejected(tmp_path):
    registry = OperatorRegistry(tmp_path)
    registry.create(
        name="user.bad_result",
        version="1.0.0",
        kind=OperatorKind.DATA_PROCESSING,
        source="def operator(data, ctx):\n    return {'not': 'a list'}\n",
    )

    with pytest.raises(OperatorExecutionError, match=r"list\[dict\]"):
        await registry.invoke("user.bad_result", [{}])


async def test_non_json_operator_result_is_rejected(tmp_path):
    registry = OperatorRegistry(tmp_path)
    registry.create(
        name="user.non_json_result",
        version="1.0.0",
        kind=OperatorKind.DATA_PROCESSING,
        source="def operator(data, ctx):\n    return [{'values': {1, 2}}]\n",
    )

    with pytest.raises(OperatorExecutionError, match="序列化为 JSON"):
        await registry.invoke("user.non_json_result", [{}])


async def test_builtin_entity_load_matches_primary_key_and_name(tmp_path):
    registry = OperatorRegistry(tmp_path)
    result = await registry.invoke(
        "builtin.entity_load",
        [{"id": "1", "name": "新名称"}, {"id": "2", "name": "Alice"}],
        {
            "existing_entities": [
                {"id": "1", "name": "旧名称"},
                {"id": "9", "name": "alice"},
            ]
        },
    )

    assert result[0]["_ingest"] == {
        "action": "merge",
        "matched_by": "primary_key",
        "matched_id": "1",
    }
    assert result[1]["_ingest"] == {
        "action": "merge",
        "matched_by": "name",
        "matched_id": "9",
    }


async def test_operator_snapshot_sync_works_without_shared_filesystem(tmp_path):
    control_registry = OperatorRegistry(tmp_path / "control")
    worker_registry = OperatorRegistry(tmp_path / "worker")
    control_registry.create(
        name="user.distributed",
        version="1.0.0",
        kind=OperatorKind.DATA_PROCESSING,
        source="def operator(data, ctx):\n    return [{**x, 'worker': True} for x in data]\n",
    )

    loaded = worker_registry.sync_user_operators(control_registry.export_user_operators())

    assert loaded == ["user.distributed"]
    assert await worker_registry.invoke("user.distributed", [{"id": 1}]) == [
        {"id": 1, "worker": True}
    ]

    control_registry.delete("user.distributed")
    worker_registry.sync_user_operators(control_registry.export_user_operators())
    assert {item.name for item in worker_registry.list()} == {
        "builtin.data_normalize",
        "builtin.entity_extract",
        "builtin.entity_load",
        "builtin.relation_extract",
        "builtin.relation_load",
    }


async def test_rustfs_style_shared_store_is_source_of_truth(tmp_path):
    store = MemoryOperatorStore()
    control_registry = OperatorRegistry(tmp_path / "control", store=store)
    worker_registry = OperatorRegistry(tmp_path / "worker", store=store)
    control_registry.initialize_store()
    control_registry.create(
        name="user.s3_shared",
        version="1.0.0",
        kind=OperatorKind.DATA_PROCESSING,
        source="def operator(data, ctx):\n    return [{**x, 'version': 1} for x in data]\n",
    )

    worker_registry.initialize_store()
    assert await worker_registry.invoke("user.s3_shared", [{}]) == [{"version": 1}]

    control_registry.update(
        name="user.s3_shared",
        version="2.0.0",
        kind=OperatorKind.DATA_PROCESSING,
        source="def operator(data, ctx):\n    return [{**x, 'version': 2} for x in data]\n",
    )
    worker_registry.sync_from_store()
    assert await worker_registry.invoke("user.s3_shared", [{}]) == [{"version": 2}]

    control_registry.delete("user.s3_shared")
    worker_registry.sync_from_store()
    assert "user.s3_shared" not in {item.name for item in worker_registry.list()}
