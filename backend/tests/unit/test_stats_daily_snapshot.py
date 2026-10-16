"""每日图统计快照（净新增差分数据源）单测：统计日归属、SHOW STATS 解析、
采集落库（规模护栏 / job 失败不落半截数据）、相邻两日差分读取的降级口径。

净新增动机（2026-10-16 口径澄清）：昨日新增按写图记录计数（不去重），与总量
（图上去重存量）不能直接相减对账；快照差分与总量同一数据源，
总量(D) − 总量(D−1) ≡ 净新增(D)，天然可对账。
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pytest

import service.stats_daily_snapshot as sds
from service.day_change_ledger import DAY_TZ
from service.stats_daily_snapshot import (
    collect_space_once,
    load_net_added,
    parse_show_stats,
    resolve_stats_day,
)

_SHOW_STATS_RECORDS = [
    {"Type": "Tag", "Name": "Person", "Count": 29450},
    {"Type": "Tag", "Name": "Paper", "Count": 4000},
    {"Type": "Edge", "Name": "PUBLISH", "Count": 12000},
    {"Type": "Space", "Name": "vertices", "Count": 33450},
    {"Type": "Space", "Name": "edges", "Count": 12000},
]


class _ScriptedGraphClient:
    """按调用序回放的图客户端替身：基线 SHOW STATS（首次失败=空间从未跑过
    stats）→ SUBMIT JOB STATS → SHOW JOB 轮询 → 定局后 SHOW STATS。"""

    def __init__(self, *, job_status: str = "FINISHED", baseline_fails: bool = True) -> None:
        self.job_status = job_status
        self.baseline_fails = baseline_fails
        self.reads: list[str] = []
        self.writes: list[str] = []
        self._stats_reads = 0

    def execute_read(self, query: str, params: Any = None) -> Any:
        self.reads.append(query)
        if query.startswith("SHOW JOB"):
            return SimpleNamespace(
                records=[{"JobId": 101, "Command": "stats_job", "Status": self.job_status}]
            )
        self._stats_reads += 1
        if self._stats_reads == 1 and self.baseline_fails:
            raise RuntimeError("no any stats info")
        return SimpleNamespace(records=list(_SHOW_STATS_RECORDS))

    def execute_write(self, query: str, params: Any = None) -> Any:
        self.writes.append(query)
        return SimpleNamespace(records=[{"New Job Id": 101}])


class _FakeConnection:
    def __init__(self, store: list[dict[str, Any]]) -> None:
        self.store = store

    def execute(self, stmt: Any, params: Any = None) -> Any:
        if isinstance(params, list):
            self.store.extend(params)
        elif params:
            self.store.append(params)
        return SimpleNamespace()

    def commit(self) -> None:
        return None


class _FakeEngine:
    """控制库引擎替身：connect()（建表 DDL）/ begin()（upsert 批）双通道，
    收集 upsert 参数行供断言。"""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.ddl: list[str] = []

    @contextmanager
    def connect(self):  # noqa: ANN201 - 测试替身无需精确返回类型
        # 建表走 connect+commit：把 DDL 语句记下来便于核对
        yield _DDLConnection(self.ddl)

    @contextmanager
    def begin(self):
        yield _FakeConnection(self.rows)


class _DDLConnection(_FakeConnection):
    def __init__(self, ddl: list[str]) -> None:
        super().__init__([])
        self.ddl = ddl

    def execute(self, stmt: Any, params: Any = None) -> Any:
        self.ddl.append(str(stmt))
        return SimpleNamespace()


@pytest.fixture()
def _reset_ensured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(sds, "_ensured", False)
    yield
    monkeypatch.setattr(sds, "_ensured", False)


@pytest.fixture()
def _fake_engine(monkeypatch: pytest.MonkeyPatch):
    import infra.workflow_mysql as wfm

    engine = _FakeEngine()
    monkeypatch.setattr(wfm, "get_workflow_engine", lambda: engine)
    return engine


def test_resolve_stats_day_before_three_am_belongs_to_previous_day() -> None:
    """03:00 前的采集收前一日尾（次日凌晨定局），03:00 起归属当日（日内刷新）。"""
    base = datetime(2026, 10, 17, 0, 10, tzinfo=DAY_TZ)
    assert resolve_stats_day(base) == "2026-10-16"
    assert resolve_stats_day(datetime(2026, 10, 17, 2, 59, tzinfo=DAY_TZ)) == "2026-10-16"
    assert resolve_stats_day(datetime(2026, 10, 17, 3, 0, tzinfo=DAY_TZ)) == "2026-10-17"
    assert resolve_stats_day(datetime(2026, 10, 16, 23, 50, tzinfo=DAY_TZ)) == "2026-10-16"
    # 其他时区时刻先折算到日窗口时区再判（api 容器 UTC 钟场景）：
    # 18:59 UTC = 北京 10-17 02:59 → 归 10-16；19:00 UTC = 北京 10-17 03:00 → 归 10-17
    utc = ZoneInfo("UTC")
    assert resolve_stats_day(datetime(2026, 10, 16, 18, 59, tzinfo=utc)) == "2026-10-16"
    assert resolve_stats_day(datetime(2026, 10, 16, 19, 0, tzinfo=utc)) == "2026-10-17"


def test_parse_show_stats_parses_totals_and_names() -> None:
    parsed = parse_show_stats(_SHOW_STATS_RECORDS)
    assert parsed["tags"] == {"Person": 29450, "Paper": 4000}
    assert parsed["edges"] == {"PUBLISH": 12000}
    assert parsed["total_nodes"] == 33450
    assert parsed["total_edges"] == 12000
    # Space 行缺失时按标签计数求和兜底（与 graph 客户端解析同构）
    fallback = parse_show_stats([{"Type": "Tag", "Name": "A", "Count": 3}])
    assert fallback["total_nodes"] == 3 and fallback["total_edges"] == 0


def test_collect_space_once_persists_totals_and_tag_rows(
    _reset_ensured, _fake_engine: _FakeEngine
) -> None:
    client = _ScriptedGraphClient()
    summary = collect_space_once("gkx_local_1", client=client)

    assert client.writes == ["SUBMIT JOB STATS;"]
    assert summary["space"] == "gkx_local_1"
    assert summary["rows"] == 2 + 2 + 1  # 两行总量 + 两 Tag + 一 Edge
    stats_day = resolve_stats_day(datetime.now(DAY_TZ))
    totals = {
        (row["kind"], row["item_name"]): row["item_count"]
        for row in _fake_engine.rows
        if row["item_name"] == sds.TOTAL_ITEM
    }
    assert totals == {("entity", sds.TOTAL_ITEM): 33450, ("relation", sds.TOTAL_ITEM): 12000}
    tag_rows = {(row["kind"], row["item_name"]) for row in _fake_engine.rows} - {
        ("entity", sds.TOTAL_ITEM),
        ("relation", sds.TOTAL_ITEM),
    }
    assert tag_rows == {("entity", "Person"), ("entity", "Paper"), ("relation", "PUBLISH")}
    assert all(row["stats_day"] == stats_day for row in _fake_engine.rows)
    # 建表 DDL 已随采集执行（幂等 IF NOT EXISTS）
    assert any("kg_stats_daily_snapshot" in ddl for ddl in _fake_engine.ddl)


def test_collect_space_once_respects_size_gate(
    monkeypatch: pytest.MonkeyPatch, _reset_ensured, _fake_engine: _FakeEngine
) -> None:
    monkeypatch.setenv("KG_STATS_SNAPSHOT_MAX_VERTICES", "10000")
    # 基线 SHOW STATS 成功返回超限总量 → 不提交 stats job、不落任何行
    client = _ScriptedGraphClient(baseline_fails=False)
    summary = collect_space_once("huge_space", client=client)

    assert summary.get("skipped") == "size-gate"
    assert client.writes == []
    assert _fake_engine.rows == []


def test_collect_space_once_job_failed_keeps_table_clean(
    _reset_ensured, _fake_engine: _FakeEngine
) -> None:
    client = _ScriptedGraphClient(job_status="FAILED")
    with pytest.raises(RuntimeError, match="图统计任务失败"):
        collect_space_once("gkx_local_1", client=client)
    assert _fake_engine.rows == []


class _RowsResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self):  # noqa: ANN201 - 测试替身
        return self

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class _QueryEngine:
    """load_net_added 替身：connect() 返回预置行（stats_day/kind/item_count），
    按查询参数里的 day/prev 过滤——与真实 SQL 的 IN (:day, :prev) 同语义。"""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    @contextmanager
    def connect(self):  # noqa: ANN201 - 测试替身无需精确返回类型
        def _execute(stmt: Any, params: dict[str, Any] | None = None) -> _RowsResult:
            days = {params.get("day"), params.get("prev")} if params else None
            return _RowsResult(
                [row for row in self._rows if days is None or row["stats_day"] in days]
            )

        yield SimpleNamespace(execute=_execute)


def _total_row(day: str, kind: str, count: int) -> dict[str, Any]:
    return {"stats_day": day, "kind": kind, "item_count": count}


def test_load_net_added_diffs_adjacent_days(
    monkeypatch: pytest.MonkeyPatch, _reset_ensured
) -> None:
    import infra.workflow_mysql as wfm

    day, prev = "2026-10-16", "2026-10-15"
    engine = _QueryEngine(
        [
            _total_row(prev, "entity", 24188),
            _total_row(day, "entity", 117632),
            _total_row(prev, "relation", 408506),
            _total_row(day, "relation", 408517),
        ]
    )
    monkeypatch.setattr(wfm, "get_workflow_engine", lambda: engine)

    net, note = load_net_added("gkx_local_1", day)

    assert net == {"entity": 93444, "relation": 11}
    assert note == ""


def test_load_net_added_negative_diff_survives(
    monkeypatch: pytest.MonkeyPatch, _reset_ensured
) -> None:
    """清理日差分为负是真实语义（当日删多于增），如实透出不取绝对值。"""
    import infra.workflow_mysql as wfm

    engine = _QueryEngine(
        [_total_row("2026-10-15", "entity", 117632), _total_row("2026-10-16", "entity", 100000)]
    )
    monkeypatch.setattr(wfm, "get_workflow_engine", lambda: engine)

    net, _ = load_net_added("gkx_local_1", "2026-10-16")
    assert net["entity"] == -17632


def test_load_net_added_first_day_without_baseline_note(
    monkeypatch: pytest.MonkeyPatch, _reset_ensured
) -> None:
    """上线首日查当日：当日快照已有、缺前一日基线——note 必须说「首日无基线」，
    不能说「当日快照尚未生成」（2026-10-16 live 验证发现的文案错位）。"""
    import infra.workflow_mysql as wfm

    today = datetime.now(DAY_TZ).strftime("%Y-%m-%d")
    engine = _QueryEngine([_total_row(today, "entity", 117632)])
    monkeypatch.setattr(wfm, "get_workflow_engine", lambda: engine)

    net, note = load_net_added("gkx_local_1", today)
    assert net == {"entity": None, "relation": None}
    assert "首日无基线" in note


def test_load_net_added_today_not_yet_collected_note(
    monkeypatch: pytest.MonkeyPatch, _reset_ensured
) -> None:
    """当日查询且当日尚未采集（如凌晨刚翻日）：两端皆缺 → 尚未生成。"""
    import infra.workflow_mysql as wfm

    today = datetime.now(DAY_TZ).strftime("%Y-%m-%d")
    engine = _QueryEngine([_total_row(sds._prev_day(today), "entity", 117632)])
    monkeypatch.setattr(wfm, "get_workflow_engine", lambda: engine)

    net, note = load_net_added("gkx_local_1", today)
    assert net == {"entity": None, "relation": None}
    assert "尚未生成" in note


def test_load_net_added_historical_gap_gives_no_backfill_note(
    monkeypatch: pytest.MonkeyPatch, _reset_ensured
) -> None:
    import infra.workflow_mysql as wfm

    # 历史日只有当日端、缺前一日端（功能上线前）：明确「无法回补」，不编数
    engine = _QueryEngine([_total_row("2026-10-01", "entity", 500)])
    monkeypatch.setattr(wfm, "get_workflow_engine", lambda: engine)

    net, note = load_net_added("gkx_local_1", "2026-10-01")
    assert net["entity"] is None
    assert "无法回补" in note


def test_load_net_added_no_snapshots_for_space(
    monkeypatch: pytest.MonkeyPatch, _reset_ensured
) -> None:
    import infra.workflow_mysql as wfm

    engine = _QueryEngine([])
    monkeypatch.setattr(wfm, "get_workflow_engine", lambda: engine)

    net, note = load_net_added("fresh_space", "2026-10-16")
    assert net == {"entity": None, "relation": None}
    assert "暂无快照" in note


def test_load_net_added_db_error_degrades(monkeypatch: pytest.MonkeyPatch, _reset_ensured) -> None:
    import infra.workflow_mysql as wfm

    class _BrokenConn:
        def __enter__(self) -> Any:
            raise RuntimeError("control db down")

        def __exit__(self, *args: Any) -> bool:
            return False

    monkeypatch.setattr(
        wfm, "get_workflow_engine", lambda: SimpleNamespace(connect=lambda: _BrokenConn())
    )
    monkeypatch.setattr(sds, "ensure_stats_snapshot_table", lambda *a, **k: None)

    net, note = load_net_added("gkx_local_1", "2026-10-16")
    assert net == {"entity": None, "relation": None}
    assert "暂不可读取" in note
