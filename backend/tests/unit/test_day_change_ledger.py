"""写图日增台账（P1）单元测试：行生成口径、幂等聚合、快照构造、读取优先与回落。"""

import pytest

from service import day_change_ledger as ledger
from service import platform_overview as overview


def _single_execution(**overrides):
    """单 Schema 实体执行：时间带 +08:00 偏移，归属断言不随测试进程时区漂。"""
    record = {
        "id": "EXEC-LEDGERTEST01",
        "definitionId": "schema-extract",
        "workflowId": "wf-1",
        "status": "COMPLETED",
        "startedAt": "2026-10-13T15:00:00+08:00",
        "completedAt": "2026-10-13T16:11:48+08:00",
        "taskId": "task-77",
        "jobId": "job-77",
        "payload": {"graph_space": "gkx_verify_1"},
        "output": {
            "kind": "entity",
            "schemaKey": "expert",
            "schemaLabel": "科技专家",
            "sources": [
                {"table": "gkx.dwd_scholar", "written": 100},
                {"table": "gkx.dwd_scholar_en", "written": 0},
                {"source": "source:abc", "written": 5},
            ],
        },
    }
    record.update(overrides)
    return record


def test_ledger_rows_single_schema_skips_zero_written():
    rows = ledger.ledger_rows_from_execution(_single_execution())
    assert len(rows) == 2  # written=0 的来源不入账
    by_source = {row["source"]: row for row in rows}
    scholar = by_source["gkx.dwd_scholar"]
    assert scholar["object_count"] == 100
    assert scholar["stats_day"] == "2026-10-13"
    assert scholar["finished_at"] == "2026-10-13 16:11:48"
    assert scholar["graph_space"] == "gkx_verify_1"
    assert scholar["schema_key"] == "expert"
    assert scholar["schema_label"] == "科技专家"
    assert scholar["execution_id"] == "EXEC-LEDGERTEST01"
    assert scholar["exec_status"] == "COMPLETED"
    assert scholar["task_id"] == "task-77"
    assert scholar["job_id"] == "job-77"
    assert by_source["source:abc"]["object_count"] == 5  # 无 table 退 source 标识


def test_ledger_rows_chain_splits_stats_day_by_step():
    """chain 环展开：跨午夜环各自归统计日（环级 +08:00 完成时刻为准）。"""
    record = {
        "id": "EXEC-LEDGERCHAIN1",
        "status": "COMPLETED",
        "startedAt": "2026-10-13T22:00:00+08:00",
        "completedAt": "2026-10-14T00:30:00+08:00",
        "payload": {"graph_space": "s1"},
        "output": {
            "steps": {
                "schema:a": {
                    "finishedAt": "2026-10-13T23:50:00+08:00",
                    "startedAt": "2026-10-13T22:00:00+08:00",
                    "output": {
                        "kind": "entity",
                        "schemaKey": "expert",
                        "schemaLabel": "科技专家",
                        "sources": [{"table": "t_a", "written": 10}],
                    },
                },
                "schema:b": {
                    "finishedAt": "2026-10-14T00:05:00+08:00",
                    "startedAt": "2026-10-13T23:55:00+08:00",
                    "output": {
                        "kind": "relation",
                        "schemaKey": "employed_by",
                        "schemaLabel": "任职关系",
                        "sources": [{"table": "t_b", "written": 7}],
                    },
                },
            }
        },
    }
    rows = ledger.ledger_rows_from_execution(record)
    by_day = {(row["stats_day"], row["kind"]): row for row in rows}
    assert by_day[("2026-10-13", "entity")]["object_count"] == 10
    assert by_day[("2026-10-13", "entity")]["finished_at"] == "2026-10-13 23:50:00"
    assert by_day[("2026-10-14", "relation")]["object_count"] == 7
    assert by_day[("2026-10-14", "relation")]["finished_at"] == "2026-10-14 00:05:00"


def test_ledger_rows_aggregate_same_key_and_keep_later_finish():
    """同（统计日×kind×Schema×来源）多块聚合一行为，防 upsert 同键互相覆盖。"""
    record = _single_execution(
        output={
            "kind": "entity",
            "schemaKey": "expert",
            "schemaLabel": "科技专家",
            "sources": [
                {"table": "t_a", "written": 100},
                {"table": "t_a", "written": 50},
            ],
        }
    )
    rows = ledger.ledger_rows_from_execution(record)
    assert len(rows) == 1
    assert rows[0]["object_count"] == 150


def test_ledger_rows_space_defaulting():
    assert (
        ledger.ledger_rows_from_execution(_single_execution())[0]["graph_space"] == "gkx_verify_1"
    )
    no_space = _single_execution(payload={})
    assert (
        ledger.ledger_rows_from_execution(no_space, default_space="dev2")[0]["graph_space"]
        == "dev2"
    )
    assert ledger.ledger_rows_from_execution(no_space)[0]["graph_space"] == ""


def test_ledger_rows_empty_output_and_non_terminal_status():
    assert ledger.ledger_rows_from_execution({"id": "E", "status": "RUNNING", "output": {}}) == []
    # RUNNING 但已有完成环：照样入账（覆盖式，终态落库时定局）
    running_partial = {
        "id": "E2",
        "status": "RUNNING",
        "completedAt": "",
        "payload": {"graph_space": "s"},
        "output": {
            "steps": {
                "schema:a": {
                    "finishedAt": "2026-10-13T10:00:00+08:00",
                    "output": {
                        "kind": "entity",
                        "schemaKey": "k",
                        "sources": [{"table": "t", "written": 3}],
                    },
                }
            }
        },
    }
    rows = ledger.ledger_rows_from_execution(running_partial)
    assert len(rows) == 1 and rows[0]["object_count"] == 3


def _ledger_row(**overrides):
    row = {
        "stats_day": "2026-10-13",
        "graph_space": "gkx_verify_1",
        "kind": "entity",
        "schema_key": "expert",
        "schema_label": "科技专家",
        "execution_id": "EXEC-1",
        "source": "gkx.dwd_scholar",
        "object_count": 100,
        "exec_status": "COMPLETED",
        "task_id": "task-1",
        "job_id": "job-1",
        "finished_at": "2026-10-13 15:47:04",
    }
    row.update(overrides)
    return row


def test_snapshot_from_ledger_builds_totals_and_descriptors(monkeypatch):
    monkeypatch.setattr(
        overview,
        "load_ledger_day",
        lambda day, space, default="": [
            _ledger_row(),
            _ledger_row(
                schema_key="event",
                schema_label="事件",
                source="t_evt",
                object_count=200,
                finished_at="2026-10-13 15:47:06",
            ),
            _ledger_row(
                kind="relation",
                schema_key="employed_by",
                schema_label="任职关系",
                object_count=80,
                execution_id="EXEC-2",
                exec_status="ABNORMAL",
                task_id=None,
                job_id=None,
                finished_at="2026-10-13 23:09:41",
            ),
        ],
    )
    snap = overview._snapshot_from_ledger("2026-10-13", "gkx_verify_1", "gkx_verify_1")
    assert snap is not None
    assert snap.day == "2026-10-13"
    assert snap.entity_added == 300
    assert snap.relation_added == 80
    assert len(snap.entity_rows) == 2 and len(snap.relation_rows) == 1
    # 明细按完成时刻倒序（事件 15:47:06 在专家 15:47:04 前）
    assert snap.entity_rows[0].object.startswith("事件 · 200")
    assert snap.entity_rows[1].object == "科技专家 · 100 条"
    assert snap.entity_rows[1].time == "10-13 15:47:04"  # 展示格式 MM-DD HH:MM:SS
    assert snap.entity_rows[1].is_aggregate is True
    assert snap.relation_rows[0].exec_status == "ABNORMAL"
    # 反查描述按（执行 × kind × Schema）聚合：EXEC-1 两个实体 Schema + EXEC-2 一个关系
    assert len(snap.entity_executions) == 2
    first = snap.entity_executions[0]
    assert first.kind == "entity" and first.schema_key == "event"
    assert first.task_id == "task-1" and first.status == "COMPLETED"
    # window_hi 放宽到统计日终点（UTC 串）；window_lo 台账无水位退统计日起点
    assert first.window_hi == "2026-10-13 15:59:59"
    assert first.window_lo == "2026-10-12 16:00:00"
    assert snap.relation_executions[0].status == "ABNORMAL"


def test_snapshot_from_ledger_returns_none_when_empty(monkeypatch):
    monkeypatch.setattr(overview, "load_ledger_day", lambda *a, **k: [])
    assert overview._snapshot_from_ledger("2026-10-13", "dev2", "dev2") is None


class _FakeResult:
    def fetchall(self):
        return []


class _FakeConnection:
    def execute(self, *_args, **_kwargs):
        return _FakeResult()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _FakeEngine:
    def connect(self):
        return _FakeConnection()


def test_load_prefers_ledger_snapshot(monkeypatch):
    """台账有账：_load 直接构造快照进 enrich，不查 workflow_executions。"""
    import infra.workflow_mysql as wfm

    def _no_engine():
        raise AssertionError("台账命中时不应再查执行记录表")

    monkeypatch.setattr(wfm, "get_workflow_engine", _no_engine)
    monkeypatch.setattr(overview, "load_ledger_day", lambda *a, **k: [_ledger_row()])
    seen = {}

    def _capture(snapshot, space, connect_client=None):
        seen["snapshot"] = snapshot
        return snapshot

    monkeypatch.setattr(overview, "enrich_day_rows_with_graph", _capture)
    provider = overview.WorkflowControlDayChangesProvider()
    snap = provider._load("2026-10-13", "gkx_verify_1")
    assert snap.entity_added == 100
    assert seen["snapshot"] is snap  # 台账快照原样交给 enrich（闸门/反查语义不变）


def test_load_falls_back_to_payload_parsing_when_ledger_empty(monkeypatch):
    """台账无账：回落 payload 现算（旧执行/未部署栈的兜底路径不变）。"""
    monkeypatch.setattr(overview, "load_ledger_day", lambda *a, **k: [])
    import infra.workflow_mysql as wfm

    monkeypatch.setattr(wfm, "get_workflow_engine", lambda: _FakeEngine())
    marker = overview.DayChangesSnapshot(day="2026-10-13", entity_added=42)
    monkeypatch.setattr(
        overview,
        "parse_execution_records",
        lambda *a, **k: marker,
    )
    seen = {}

    def _capture(snapshot, space, connect_client=None):
        seen["snapshot"] = snapshot
        return snapshot

    monkeypatch.setattr(overview, "enrich_day_rows_with_graph", _capture)
    provider = overview.WorkflowControlDayChangesProvider()
    snap = provider._load("2026-10-13", "dev2")
    assert snap is marker and seen["snapshot"] is marker


def test_ledger_snapshot_still_respects_lookup_gate(monkeypatch):
    """台账快照超反查闸门：enrich 仍跳过连图，聚合行 + 精确 written 保留。"""
    monkeypatch.setattr(overview, "_LOOKUP_WRITTEN_LIMIT", 100)
    monkeypatch.setattr(
        overview,
        "load_ledger_day",
        lambda *a, **k: [_ledger_row(object_count=200)],
    )

    def _no_client(space):
        raise AssertionError("闸门命中时不应连接图客户端")

    snap = overview._snapshot_from_ledger("2026-10-13", "gkx_verify_1", "gkx_verify_1")
    result = overview.enrich_day_rows_with_graph(snap, "gkx_verify_1", connect_client=_no_client)
    assert result.entity_gated is True
    assert result.entity_added == 200  # 总数按台账精确给出
    assert len(result.entity_rows) == 1 and result.entity_rows[0].is_aggregate is True


def test_sync_upserts_rows_within_session(monkeypatch):
    """save_execution 挂载点：台账行经 ensure 后批量 upsert（同事务）。"""
    calls = {}

    class _Bind:
        pass

    class _Session:
        def get_bind(self):
            return _Bind()

        def execute(self, stmt, rows):
            calls["rows"] = rows
            calls["stmt"] = str(stmt)

    monkeypatch.setattr(ledger, "ensure_day_change_ledger", lambda engine=None: None)
    written = ledger.sync_execution_to_ledger(_Session(), _single_execution())
    assert written == 2
    assert len(calls["rows"]) == 2
    assert "ON DUPLICATE KEY UPDATE" in calls["stmt"]

    # 无可记账输出：不 ensure、不发 SQL
    calls.clear()

    class _NoopSession(_Session):
        def execute(self, stmt, rows):  # pragma: no cover - 到这里即失败
            raise AssertionError("无账不应发 SQL")

    monkeypatch.setattr(
        ledger,
        "ensure_day_change_ledger",
        lambda engine=None: pytest.fail("无账不应 ensure 建表"),
    )
    assert ledger.sync_execution_to_ledger(_NoopSession(), {"id": "E", "output": {}}) == 0
