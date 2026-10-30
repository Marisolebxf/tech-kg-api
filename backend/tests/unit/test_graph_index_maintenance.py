import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from infra.graph_db import index_maintenance as maintenance
from infra.graph_db.config import TRSGraphSettings
from infra.graph_db.exceptions import GraphRequestError


class Graph:
    def __init__(self, existing=False, finished=False, fail=False):
        self.existing, self.finished, self.fail = existing, finished, fail
        self.writes, self.reads = [], []
        self.name = "existing_school" if existing else ""

    def execute_read(self, query):
        self.reads.append(query)
        rows = []
        if query.startswith("DESCRIBE"):
            rows = [{"Field": "school", "Type": "string"}]
        elif query == "SHOW TAG INDEXES" and self.existing:
            rows = [{"Index Name": self.name, "By Tag": "Person", "Columns": ["school"]}]
        elif query == "SHOW TAG INDEX STATUS" and self.name:
            rows = [
                {
                    "Name": self.name,
                    "Index Status": "FAILED"
                    if self.fail
                    else "FINISHED"
                    if self.finished
                    else "RUNNING",
                }
            ]
        return SimpleNamespace(records=rows)

    def execute_explain(self, query):
        return self.execute_read("EXPLAIN " + query)

    def execute_query(self, query):
        self.writes.append(query)
        if query.startswith("CREATE"):
            self.name = query.split("`")[1]
        if query.startswith("REBUILD"):
            self.finished = True
        return SimpleNamespace(records=[])


def test_create_rebuild_and_explain_are_one_lifecycle():
    graph = Graph()
    names = maintenance.reconcile(graph, "Person", ("school",))
    assert len(names) == 1
    assert "school`(256)" in graph.writes[0]
    assert graph.writes[1].startswith("REBUILD")
    assert any(q.startswith("EXPLAIN LOOKUP") for q in graph.reads)


def test_existing_finished_index_is_reused_without_ddl():
    graph = Graph(existing=True, finished=True)
    assert maintenance.reconcile(graph, "Person", ("school",)) == ["existing_school"]
    assert not graph.writes


def test_existing_unfinished_index_is_rebuilt():
    graph = Graph(existing=True)
    maintenance.reconcile(graph, "Person", ("school",))
    assert len(graph.writes) == 1 and graph.writes[0].startswith("REBUILD")


def test_missing_field_never_executes_ddl():
    graph = Graph()
    with pytest.raises(ValueError, match="does not exist"):
        maintenance.reconcile(graph, "Person", ("injected",))
    assert not graph.writes


def test_failed_rebuild_is_not_reported_ready():
    graph = Graph(fail=True)
    with pytest.raises(RuntimeError, match="FAILED"):
        maintenance.reconcile(graph, "Person", ("school",))


class Store:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, nx=False, **kwargs):
        if nx and key in self.data:
            return False
        self.data[key] = value
        return True

    def delete(self, key):
        self.data.pop(key, None)


def test_workers_coalesce_and_instance_space_are_part_of_identity(monkeypatch):
    monkeypatch.setenv("TRS_GRAPH_AUTO_INDEX_ENABLED", "true")
    store, executor = Store(), SimpleNamespace(submit=MagicMock())
    monkeypatch.setattr(maintenance, "_redis", lambda: store)
    monkeypatch.setattr(maintenance, "_executor", executor)
    monkeypatch.setattr(maintenance, "_pending", set())
    settings = TRSGraphSettings(base_url="http://graph", space="dev")
    assert not maintenance.request_indexes(settings, "Person", ["school"])
    # Simulate a second process's empty in-memory queue: Redis still prevents duplication.
    monkeypatch.setattr(maintenance, "_pending", set())
    assert not maintenance.request_indexes(settings, "Person", ["school"])
    assert executor.submit.call_count == 1
    for other in [
        settings.model_copy(update={"space": "other"}),
        settings.model_copy(update={"base_url": "http://other"}),
    ]:
        assert not maintenance.request_indexes(other, "Person", ["school"])
    assert executor.submit.call_count == 3
    key = maintenance.PREFIX + "job:" + maintenance._identity(settings, "Person", ("school",))
    store.set(key, json.dumps({"status": "ready"}))
    assert maintenance.request_indexes(settings, "Person", ["school"])


def test_invalid_identifiers_never_schedule_ddl(monkeypatch):
    monkeypatch.setenv("TRS_GRAPH_AUTO_INDEX_ENABLED", "true")
    with pytest.raises(GraphRequestError):
        maintenance.request_indexes(TRSGraphSettings(), "Person;DROP", ["name"])


def test_worker_renews_distributed_lease_and_records_ready_only_after_success(monkeypatch):
    store = Store()
    lock = SimpleNamespace(acquire=lambda: True, extend=MagicMock(), release=MagicMock())
    store.lock = lambda *a, **kw: lock
    graph = Graph()
    graph.connect = MagicMock()
    graph.close = MagicMock()
    monkeypatch.setattr(maintenance, "_redis", lambda: store)
    monkeypatch.setattr("infra.graph_db.client.TRSGraphClient", lambda settings: graph)
    settings = TRSGraphSettings(space="test")
    maintenance._run(settings, "Person", ("school",), "test-job")
    row = json.loads(store.get(maintenance.PREFIX + "job:test-job"))
    assert row["status"] == "ready" and row["explainAccepted"]
    assert lock.extend.call_count > 1
    lock.release.assert_called_once()
    graph.close.assert_called_once()


def test_worker_failure_is_visible_and_releases_lease(monkeypatch):
    store = Store()
    lock = SimpleNamespace(acquire=lambda: True, extend=MagicMock(), release=MagicMock())
    store.lock = lambda *a, **kw: lock
    graph = Graph(fail=True)
    graph.connect = MagicMock()
    graph.close = MagicMock()
    monkeypatch.setattr(maintenance, "_redis", lambda: store)
    monkeypatch.setattr("infra.graph_db.client.TRSGraphClient", lambda settings: graph)
    maintenance._run(TRSGraphSettings(), "Person", ("school",), "failed-job")
    row = json.loads(store.get(maintenance.PREFIX + "job:failed-job"))
    assert row["status"] == "failed" and "FAILED" in row["error"]
    lock.release.assert_called_once()


def test_rebuild_retries_storage_schema_propagation_and_tracks_own_job(monkeypatch):
    monkeypatch.setattr(maintenance.time, "sleep", lambda seconds: None)

    class PropagatingGraph(Graph):
        def __init__(self):
            super().__init__()
            self.submissions = 0

        def execute_query(self, query):
            result = super().execute_query(query)
            if query.startswith("REBUILD"):
                self.submissions += 1
                return SimpleNamespace(records=[{"New Job Id": self.submissions}])
            return result

        def execute_read(self, query):
            if query.startswith("SHOW JOB"):
                first = self.submissions == 1
                return SimpleNamespace(
                    records=[
                        {
                            "Status": "FAILED" if first else "FINISHED",
                            "Error Code": "E_INDEX_NOT_FOUND" if first else "SUCCEEDED",
                        }
                    ]
                )
            return super().execute_read(query)

    graph = PropagatingGraph()
    assert maintenance.reconcile(graph, "Person", ("school",))
    assert graph.submissions == 2


def test_redis_outage_does_not_allow_reading_an_unverified_index(monkeypatch):
    monkeypatch.setenv("TRS_GRAPH_AUTO_INDEX_ENABLED", "true")
    store = SimpleNamespace(get=MagicMock(side_effect=ConnectionError("offline")))
    monkeypatch.setattr(maintenance, "_redis", lambda: store)
    with pytest.raises(GraphRequestError) as error:
        maintenance.request_indexes(TRSGraphSettings(), "Person", ["school"])
    assert error.value.status_code == 503
