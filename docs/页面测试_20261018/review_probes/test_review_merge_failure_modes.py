"""Review-only probes; not part of the proposed fix or a production change."""

import asyncio
import json
import threading
from types import SimpleNamespace

import pytest

from tests.unit.test_write_records_merge import (
    MergeFakeGraphClient,
    PERSON_COLS,
    describe,
    entity_request,
)


def setup_client(monkeypatch, client_type):
    monkeypatch.setattr("infra.graph_db.client.TRSGraphClient", client_type)
    monkeypatch.setenv("SCHEMA_EXTRACT_WRITE_PACE_EVERY", "0")
    monkeypatch.setenv("ENTITY_DISAMBIGUATION_PREWRITE_RECHECK", "1")
    monkeypatch.setenv("ENTITY_DISAMBIGUATION_NAME_LOCK", "1")
    from service import temporal_workflows

    async def no_recheck(*args, **kwargs):
        return {}

    monkeypatch.setattr(temporal_workflows, "_prewrite_recheck", no_recheck)
    describe(PERSON_COLS)
    return temporal_workflows.write_records


async def test_corrupt_existing_properties_must_not_allow_overwrite(monkeypatch):
    class CorruptClient(MergeFakeGraphClient):
        def execute_read(self, query, *args, **kwargs):
            if query.startswith("FETCH PROP ON"):
                return SimpleNamespace(records=[{"vid": "v", "props": "not-json"}])
            return super().execute_read(query, *args, **kwargs)

    CorruptClient.instances = []
    write_records = setup_client(monkeypatch, CorruptClient)
    request = entity_request([{"id": "v", "props": {"paper_nums": 46}}])
    with pytest.raises((ValueError, RuntimeError)):
        await write_records(request)
    assert not CorruptClient.instances[-1].write_stmts


async def test_parallel_same_vid_without_name_keeps_both_updates(monkeypatch):
    barrier = threading.Barrier(2)
    state_lock = threading.Lock()
    state = {"id": "v", "scholar_org": "Existing institution"}

    class RacingClient(MergeFakeGraphClient):
        def execute_read(self, query, *args, **kwargs):
            if query.startswith("FETCH PROP ON"):
                with state_lock:
                    snapshot = dict(state)
                barrier.wait(timeout=5)
                return SimpleNamespace(records=[{"vid": "v", "props": snapshot}])
            return super().execute_read(query, *args, **kwargs)

        def execute_write(self, query, *args, **kwargs):
            self.write_stmts.append(query)
            columns_part, values_part = query.split(") VALUES ", 1)
            columns = [s.strip().strip("`") for s in columns_part.split("(", 1)[1].split(",")]
            values = json.loads("[" + values_part.split(":(", 1)[1][:-1] + "]")
            with state_lock:
                # Model the confirmed whole-tag replacement behavior of INSERT VERTEX.
                state.clear()
                state.update(zip(columns, values, strict=True))
            return SimpleNamespace()

    write_records = setup_client(monkeypatch, RacingClient)
    await asyncio.gather(
        write_records(entity_request([{"id": "v", "props": {"paper_nums": 46}}])),
        write_records(entity_request([{"id": "v", "props": {"h_index": 18}}])),
    )
    assert state.get("paper_nums") == 46, state
    assert state.get("h_index") == 18, state
