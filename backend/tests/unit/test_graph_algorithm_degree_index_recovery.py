"""Degree 首建边索引 FAILED 的有界恢复（2026-10-19 v3 方案）单元测试。

背景：定制版 Nebula 的管理作业（stats/索引重建）全局串行，共享图库多空间作业
互相挤兑时，刚 CREATE 出来的专用索引 REBUILD 会很快 FAILED，队列空闲后重跑
即自愈。修复后 FAILED 不再一律当终态：对 Degree 专用索引（按命名匹配，本次
或先前运行 CREATE 的同名索引均在范围内）做 ≤2 次有界重试（单一 deadline、
退避 2/4/8s 封顶 15s、退避中响应任务取消），每一轮提交前都复查取消与
deadline，到期后不再发起任何新的重建提交；SHOW JOBS 只落诊断日志且排除
自身 job id，诊断失败不影响控制流。

测试用 httpx.MockTransport 伪造 trs-graph REST（风格同 test_trs_graph_client.py），
驱动真实的 TRSGraphClient 走 /api/v1/query/read|write；提交时刻口径的回归
用固定时钟（FakeClockTime 替换 graph_algorithm.time）+ 假客户端直接驱动
_submit_degree_index_rebuild。
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from infra.graph_db.client import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings
from infra.graph_db.exceptions import GraphRequestError
from service import graph_algorithm

SPACE = "degree_recovery_space"
LABEL = "HAS_KEYWORD"


class DegreeIndexRestStub:
    """伪造 trs-graph REST：按脚本推进索引状态，记录全部请求供断言。"""

    def __init__(
        self,
        *,
        statuses: list[str] | None = None,
        show_jobs_records: list[dict] | None = None,
        existing_indexes: list[dict] | None = None,
        rebuild_errors: list[str | None] | None = None,
        status_blips: int = 0,
        status_hard_error: bool = False,
        flip_cancel_on_show_jobs: bool = False,
        show_jobs_error: bool = False,
    ) -> None:
        self.statuses = list(statuses or [])
        self.show_jobs_records = show_jobs_records or []
        self.existing_indexes = existing_indexes or []
        self.rebuild_errors = list(rebuild_errors or [])
        self.status_blips = status_blips
        self.status_hard_error = status_hard_error
        self.flip_cancel_on_show_jobs = flip_cancel_on_show_jobs
        self.show_jobs_error = show_jobs_error
        self.cancel_requested = False
        self.writes: list[str] = []
        self.reads: list[tuple[str, dict[str, str]]] = []
        self.rebuild_job_seq = iter(range(101, 200))

    # ---- 请求侧断言辅助 ----

    @property
    def rebuild_writes(self) -> list[str]:
        return [q for q in self.writes if "REBUILD EDGE INDEX" in q]

    @property
    def create_writes(self) -> list[str]:
        return [q for q in self.writes if "CREATE EDGE INDEX" in q]

    @property
    def show_jobs_reads(self) -> list[tuple[str, dict[str, str]]]:
        return [(q, h) for q, h in self.reads if "SHOW JOBS" in q]

    # ---- MockTransport handler ----

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "UP"})
        body = json.loads(request.content)
        query = str(body.get("query") or "")
        if request.url.path == "/api/v1/query/write":
            self.writes.append(query)
            if "CREATE EDGE INDEX" in query:
                return self._ok([])
            if "REBUILD EDGE INDEX" in query:
                error = self.rebuild_errors.pop(0) if self.rebuild_errors else None
                if error is not None:
                    return self._ngql_error(error)
                return self._ok([{"Job Id": next(self.rebuild_job_seq)}])
            return httpx.Response(500, json={"error": f"unexpected write: {query}"})
        if request.url.path == "/api/v1/query/read":
            self.reads.append((query, {k: v for k, v in request.headers.items()}))
            if "SHOW EDGE INDEXES" in query:
                return self._ok(list(self.existing_indexes))
            if "SHOW EDGE INDEX STATUS" in query:
                if self.status_blips > 0:
                    self.status_blips -= 1
                    raise httpx.ConnectError("connection reset by peer")
                if self.status_hard_error:
                    return self._ngql_error("SyntaxError: syntax error near `SHOWX'")
                status = self.statuses.pop(0) if self.statuses else "FINISHED"
                # 同时回报专用索引与 schema 同步索引的状态，供回退路径按名匹配
                return self._ok(
                    [
                        {
                            "Name": graph_algorithm._degree_index_name(LABEL),
                            "Index Status": status,
                        },
                        {"Name": f"{LABEL}_idx", "Index Status": status},
                    ]
                )
            if "SHOW JOBS" in query:
                if self.flip_cancel_on_show_jobs:
                    self.cancel_requested = True
                if self.show_jobs_error:
                    return self._ngql_error("InternalError: job manager not ready")
                return self._ok(list(self.show_jobs_records))
            if query.startswith("LOOKUP"):
                return self._ok([{"s": "vertex-1"}])
            return self._ok([])
        return httpx.Response(404, json={"error": "not found"})

    def _ok(self, records: list[dict[str, Any]]) -> httpx.Response:
        return httpx.Response(
            200,
            json={"summary": {"spaceName": SPACE, "errorCode": 0}, "records": records},
        )

    def _ngql_error(self, comment: str) -> httpx.Response:
        return httpx.Response(
            200,
            json={"summary": {"spaceName": SPACE, "errorCode": -1, "comment": comment}},
        )


def _make_client(stub: DegreeIndexRestStub) -> TRSGraphClient:
    settings = TRSGraphSettings(base_url="http://test", space=SPACE, api_key="k", timeout=5)
    client = TRSGraphClient(settings, transport=httpx.MockTransport(stub.handler))
    client.connect()
    return client


@pytest.fixture
def fast_retries(monkeypatch):
    """退避/轮询归零，deadline 放宽，让有界恢复逻辑全速走完。"""
    monkeypatch.setattr(graph_algorithm, "_DEGREE_INDEX_POLL_SECONDS", 0.0)
    monkeypatch.setattr(graph_algorithm, "_DEGREE_INDEX_REBUILD_BACKOFF_BASE_SECONDS", 0.0)
    monkeypatch.setattr(graph_algorithm, "_DEGREE_INDEX_BUILD_TIMEOUT_SECONDS", 30.0)


OTHER_SPACE_JOBS = [
    # 挤兑者画像：本空间内另一个 stats 作业 + 自身重建作业（应被自排除）
    {"Job Id": 101, "Command": "REBUILD_EDGE_INDEX", "Status": "FAILED"},
    {"Job Id": 55, "Command": "STATS", "Status": "RUNNING"},
]


def test_permanent_failed_exhausts_bounded_retries_then_502(fast_retries) -> None:
    """提交成功后永久 FAILED：恰好重试 2 次（共 3 次重建提交）后以 502 暴露。"""
    stub = DegreeIndexRestStub(statuses=["FAILED"] * 10, show_jobs_records=OTHER_SPACE_JOBS)
    client = _make_client(stub)
    with pytest.raises(graph_algorithm.GraphAlgorithmError) as error:
        graph_algorithm._ensure_degree_edge_index(client, LABEL)
    assert error.value.status_code == 502
    assert "重建状态为 FAILED" in str(error.value)
    assert "共提交 3 次重建" in str(error.value)
    assert len(stub.create_writes) == 1
    assert len(stub.rebuild_writes) == 3
    client.close()


def test_transient_failed_recovers_within_retry_budget(fast_retries) -> None:
    """队列挤兑型 FAILED：一次有界重试后 FINISHED，恢复成功。"""
    stub = DegreeIndexRestStub(statuses=["FAILED", "FINISHED"], show_jobs_records=OTHER_SPACE_JOBS)
    client = _make_client(stub)
    graph_algorithm._ensure_degree_edge_index(client, LABEL)
    assert len(stub.rebuild_writes) == 2
    assert any("LOOKUP" in q for q, _ in stub.reads)  # FINISHED 后校验 LOOKUP
    client.close()


def test_status_read_blip_keeps_polling_and_recovery(fast_retries) -> None:
    """状态读取瞬断（连接错误）不当失败：继续轮询，随后的 FAILED 仍可恢复。"""
    stub = DegreeIndexRestStub(
        statuses=["FAILED", "FINISHED"],
        show_jobs_records=OTHER_SPACE_JOBS,
        status_blips=1,
    )
    client = _make_client(stub)
    graph_algorithm._ensure_degree_edge_index(client, LABEL)
    assert stub.status_blips == 0
    assert len(stub.rebuild_writes) == 2
    client.close()


def test_non_transient_status_read_error_fails_fast(fast_retries) -> None:
    """状态读取的永久性 nGQL 错误：按校验失败 502 上抛，不触发重试。"""
    stub = DegreeIndexRestStub(status_hard_error=True, show_jobs_records=OTHER_SPACE_JOBS)
    client = _make_client(stub)
    with pytest.raises(graph_algorithm.GraphAlgorithmError) as error:
        graph_algorithm._ensure_degree_edge_index(client, LABEL)
    assert error.value.status_code == 502
    assert "校验失败" in str(error.value)
    assert len(stub.rebuild_writes) == 1
    client.close()


def test_deadline_expiring_during_backoff_blocks_resubmission(monkeypatch) -> None:
    """deadline 中途到期：退避醒来后不再重提交，按 504 超时上抛。"""
    monkeypatch.setattr(graph_algorithm, "_DEGREE_INDEX_POLL_SECONDS", 0.0)
    monkeypatch.setattr(graph_algorithm, "_DEGREE_INDEX_BUILD_TIMEOUT_SECONDS", 0.4)
    monkeypatch.setattr(graph_algorithm, "_DEGREE_INDEX_REBUILD_BACKOFF_BASE_SECONDS", 0.5)
    stub = DegreeIndexRestStub(statuses=["FAILED", "FINISHED"], show_jobs_records=OTHER_SPACE_JOBS)
    client = _make_client(stub)
    with pytest.raises(graph_algorithm.GraphAlgorithmError) as error:
        graph_algorithm._ensure_degree_edge_index(client, LABEL)
    assert error.value.status_code == 504
    assert "重建超过" in str(error.value)
    assert len(stub.rebuild_writes) == 1  # 退避耗尽 deadline，未再重提交
    client.close()


def test_cancellation_during_backoff_aborts_recovery(fast_retries, monkeypatch) -> None:
    """退避中任务取消：抛 _DegreeCancelled，且不再重提交重建。"""
    monkeypatch.setattr(graph_algorithm, "_DEGREE_INDEX_REBUILD_BACKOFF_BASE_SECONDS", 0.3)
    stub = DegreeIndexRestStub(
        statuses=["FAILED", "FINISHED"],
        show_jobs_records=OTHER_SPACE_JOBS,
        flip_cancel_on_show_jobs=True,
    )
    client = _make_client(stub)
    graph_algorithm._degree_context.job = {"job_id": "job-1", "status": "running"}
    monkeypatch.setattr(
        graph_algorithm,
        "_degree_cancelled",
        lambda job: stub.cancel_requested,
    )
    try:
        with pytest.raises(graph_algorithm._DegreeCancelled):
            graph_algorithm._ensure_degree_edge_index(client, LABEL)
        assert len(stub.rebuild_writes) == 1
    finally:
        graph_algorithm._degree_context.job = None
        client.close()


def test_show_jobs_diagnostic_excludes_own_job(fast_retries, caplog) -> None:
    """诊断日志排除自身 job id：other_jobs 里只有别的作业。"""
    with caplog.at_level("WARNING", logger="service.graph_algorithm"):
        stub = DegreeIndexRestStub(
            statuses=["FAILED", "FINISHED"], show_jobs_records=OTHER_SPACE_JOBS
        )
        client = _make_client(stub)
        try:
            graph_algorithm._ensure_degree_edge_index(client, LABEL)
        finally:
            client.close()
    messages = [r.getMessage() for r in caplog.records if "其余管理作业" in r.getMessage()]
    assert messages, "FAILED 后应输出 SHOW JOBS 诊断日志"
    assert "'Job Id': 55" in messages[0]  # 其他作业保留
    assert "'Job Id': 101" not in messages[0]  # 自身重建作业被排除
    assert "own_job=101" in messages[0]


def test_foreign_admin_job_records_filters_own_id() -> None:
    """自排除过滤的纯函数口径：匹配/不匹配/脏数据都不误伤。"""
    records = [
        {"Job Id": 101, "Command": "REBUILD_EDGE_INDEX"},
        {"Job Id": "101", "Command": "REBUILD_EDGE_INDEX"},  # 字符串形式的自身 id 同样排除
        {"Job Id": 55, "Command": "STATS"},
        "not-a-dict",  # 非法记录跳过
        {"Command": "NO_ID"},  # 无 job id 的保留
    ]
    others = graph_algorithm._foreign_admin_job_records(records, 101)
    assert others == [
        {"Job Id": 55, "Command": "STATS"},
        {"Command": "NO_ID"},
    ]
    assert graph_algorithm._foreign_admin_job_records([], None) == []


def test_show_jobs_diagnostics_scoped_to_own_space(fast_retries) -> None:
    """跨空间可见性：SHOW JOBS 请求只落本空间（space 头 + USE 前缀），
    其他图空间的挤兑作业在该诊断里结构上不可见。"""
    stub = DegreeIndexRestStub(statuses=["FAILED", "FINISHED"], show_jobs_records=OTHER_SPACE_JOBS)
    client = _make_client(stub)
    try:
        graph_algorithm._ensure_degree_edge_index(client, LABEL)
    finally:
        client.close()
    assert stub.show_jobs_reads, "FAILED 后应发起 SHOW JOBS 诊断读取"
    for query, headers in stub.show_jobs_reads:
        assert query.startswith(f"USE {SPACE};")
        assert headers.get("x-graph-space") == SPACE


def test_failed_on_reused_schema_index_is_terminal(fast_retries) -> None:
    """复用 schema 同步索引的重建 FAILED：不属于本次 CREATE 的专用索引，不重试。"""
    existing = [{"Index Name": f"{LABEL}_idx", "By Edge": LABEL, "Columns": []}]
    stub = DegreeIndexRestStub(
        statuses=["RUNNING", "FAILED"],
        existing_indexes=existing,
        # 首次 REBUILD 专用索引报 not found（CREATE 被定制 Nebula 静默吞掉）→ 回退已有索引
        rebuild_errors=["SemanticError: Index degree_xxx_idx not found in space"],
        show_jobs_records=OTHER_SPACE_JOBS,
    )
    client = _make_client(stub)
    with pytest.raises(graph_algorithm.GraphAlgorithmError) as error:
        graph_algorithm._ensure_degree_edge_index(client, LABEL)
    assert error.value.status_code == 502
    assert "重建状态为 FAILED" in str(error.value)
    # 两次 REBUILD：专用索引尝试（报 not found）+ 回退已有索引；FAILED 后不再重试
    assert len(stub.rebuild_writes) == 2
    client.close()


# ---------------------------------------------------------------------------
# Codex 复核 A：固定时钟回归——瞬态提交失败的退避跨过 deadline 后，
# 不得再发出任何新的 REBUILD 提交（提交时刻序列必须全部 ≤ deadline）。
# ---------------------------------------------------------------------------


class FakeClockTime:
    """替换 graph_algorithm.time 的固定时钟：sleep 只推进时钟，不真等。"""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds

    def time(self) -> float:
        return self.now


class FakeRebuildClient:
    """记录每次 REBUILD 提交时刻的假客户端；errors 队列依次抛瞬态错误后成功。"""

    def __init__(self, clock: FakeClockTime, errors: list[str]) -> None:
        self.clock = clock
        self.errors = list(errors)
        self.submit_times: list[float] = []
        self.queries: list[str] = []

    def execute_write(self, query: str) -> Any:
        self.submit_times.append(self.clock.monotonic())
        self.queries.append(query)
        if self.errors:
            raise GraphRequestError(self.errors.pop(0), status_code=500)
        return SimpleNamespace(records=[{"New Job Id": 777}])


def test_resubmit_backoff_crossing_deadline_times_out(monkeypatch) -> None:
    """Codex 复现口径：deadline=1.0，首提交 t=0 瞬态失败，退避 2s 跨过 deadline。

    修复前：t=2.0 仍会再提交一次且成功返回 job id（越界提交）。修复后：不再有
    第二次 execute_write，按 504 超时上抛，提交时刻序列全部 ≤ deadline。
    """
    clock = FakeClockTime()
    monkeypatch.setattr(graph_algorithm, "time", clock)
    monkeypatch.setattr(graph_algorithm, "_DEGREE_INDEX_POLL_SECONDS", 2.0)
    client = FakeRebuildClient(clock, errors=["Index degree_x_idx not ready"])
    deadline = 1.0
    with pytest.raises(graph_algorithm.GraphAlgorithmError) as error:
        graph_algorithm._submit_degree_index_rebuild(
            client, LABEL, "degree_x_idx", deadline=deadline
        )
    assert error.value.status_code == 504
    assert "重建超过" in str(error.value)
    assert client.submit_times == [0.0]  # 只有首提交，无越界重提交
    assert all(t <= deadline for t in client.submit_times)
    assert client.queries == ["REBUILD EDGE INDEX `degree_x_idx`"]


def test_resubmit_transient_retry_within_budget_succeeds(monkeypatch) -> None:
    """预算充足时瞬态重试照常工作：门禁不误伤合法恢复，提交时刻均 ≤ deadline。"""
    clock = FakeClockTime()
    monkeypatch.setattr(graph_algorithm, "time", clock)
    monkeypatch.setattr(graph_algorithm, "_DEGREE_INDEX_POLL_SECONDS", 1.0)
    client = FakeRebuildClient(clock, errors=["Index degree_x_idx not ready"])
    deadline = 10.0
    job_id = graph_algorithm._submit_degree_index_rebuild(
        client, LABEL, "degree_x_idx", deadline=deadline
    )
    assert job_id == 777
    assert client.submit_times == [0.0, 1.0]
    assert all(t <= deadline for t in client.submit_times)


def test_first_submit_backoff_crossing_deadline_times_out(monkeypatch) -> None:
    """首次提交循环同口径：瞬态失败退避跨过 deadline → 504，无第二次 REBUILD。"""
    clock = FakeClockTime()
    monkeypatch.setattr(graph_algorithm, "time", clock)
    monkeypatch.setattr(graph_algorithm, "_DEGREE_INDEX_POLL_SECONDS", 2.0)
    monkeypatch.setattr(graph_algorithm, "_DEGREE_INDEX_REBUILD_BACKOFF_BASE_SECONDS", 0.0)
    monkeypatch.setattr(graph_algorithm, "_DEGREE_INDEX_BUILD_TIMEOUT_SECONDS", 1.0)
    stub = DegreeIndexRestStub(
        statuses=["FINISHED"],
        rebuild_errors=["Index degree_x_idx not ready"],
        show_jobs_records=OTHER_SPACE_JOBS,
    )
    client = _make_client(stub)
    try:
        with pytest.raises(graph_algorithm.GraphAlgorithmError) as error:
            graph_algorithm._ensure_degree_edge_index(client, LABEL)
    finally:
        client.close()
    assert error.value.status_code == 504
    assert "重建超过" in str(error.value)
    assert len(stub.create_writes) == 1
    assert len(stub.rebuild_writes) == 1  # 退避受剩余预算约束，到期后未再提交


# ---------------------------------------------------------------------------
# Codex 复核 B：恢复策略范围（命名匹配=本次或先前 Degree 运行的专用索引）
# 与终态/诊断场景的逐一证据。
# ---------------------------------------------------------------------------


def test_failed_on_prior_run_dedicated_index_recovers(fast_retries) -> None:
    """先前 Degree 运行遗留的专用索引（本次 CREATE IF NOT EXISTS 幂等复用）
    FAILED 同样按命名匹配恢复——策略范围不能以「仅本次首建」概括。"""
    dedicated = graph_algorithm._degree_index_name(LABEL)
    existing = [{"Index Name": dedicated, "By Edge": LABEL, "Columns": []}]
    stub = DegreeIndexRestStub(
        statuses=["FAILED", "FINISHED"],
        existing_indexes=existing,
        show_jobs_records=OTHER_SPACE_JOBS,
    )
    client = _make_client(stub)
    graph_algorithm._ensure_degree_edge_index(client, LABEL)
    assert len(stub.create_writes) == 1  # CREATE IF NOT EXISTS 幂等提交一次
    assert len(stub.rebuild_writes) == 2  # FAILED → 命名匹配 → 重提交恢复
    assert all(f"`{dedicated}`" in q for q in stub.rebuild_writes)
    client.close()


def test_concurrent_first_create_with_peer_rebuild_still_recovers(fast_retries) -> None:
    """并发首建：双方 CREATE IF NOT EXISTS 幂等；本方 REBUILD 先撞上对方在建
    （转入等待、不重复提交），随后 FAILED（队列挤兑），仍按命名匹配恢复。"""
    dedicated = graph_algorithm._degree_index_name(LABEL)
    existing = [{"Index Name": dedicated, "By Edge": LABEL, "Columns": []}]
    stub = DegreeIndexRestStub(
        statuses=["FAILED", "FINISHED"],
        existing_indexes=existing,
        rebuild_errors=["Job is running: rebuild in progress"],
        show_jobs_records=OTHER_SPACE_JOBS,
    )
    client = _make_client(stub)
    graph_algorithm._ensure_degree_edge_index(client, LABEL)
    assert len(stub.create_writes) == 1
    assert len(stub.rebuild_writes) == 2  # 撞在建被拒一次 + 恢复重提交一次
    client.close()


def test_stopped_status_is_terminal_without_retry(fast_retries) -> None:
    """STOPPED 是终态：不触发恢复重试，直接 502，重建提交只有一次。"""
    stub = DegreeIndexRestStub(statuses=["STOPPED"] * 3, show_jobs_records=OTHER_SPACE_JOBS)
    client = _make_client(stub)
    with pytest.raises(graph_algorithm.GraphAlgorithmError) as error:
        graph_algorithm._ensure_degree_edge_index(client, LABEL)
    assert error.value.status_code == 502
    assert "重建状态为 STOPPED" in str(error.value)
    assert len(stub.rebuild_writes) == 1
    client.close()


def test_invalid_status_is_terminal_without_retry(fast_retries) -> None:
    """INVALID 是终态：不触发恢复重试，直接 502，重建提交只有一次。"""
    stub = DegreeIndexRestStub(statuses=["INVALID"] * 3, show_jobs_records=OTHER_SPACE_JOBS)
    client = _make_client(stub)
    with pytest.raises(graph_algorithm.GraphAlgorithmError) as error:
        graph_algorithm._ensure_degree_edge_index(client, LABEL)
    assert error.value.status_code == 502
    assert "重建状态为 INVALID" in str(error.value)
    assert len(stub.rebuild_writes) == 1
    client.close()


def test_show_jobs_diagnostics_failure_does_not_block_recovery(fast_retries, caplog) -> None:
    """诊断（SHOW JOBS）读取失败只落告警日志，不影响恢复控制流。"""
    with caplog.at_level("WARNING", logger="service.graph_algorithm"):
        stub = DegreeIndexRestStub(
            statuses=["FAILED", "FINISHED"],
            show_jobs_records=OTHER_SPACE_JOBS,
            show_jobs_error=True,
        )
        client = _make_client(stub)
        try:
            graph_algorithm._ensure_degree_edge_index(client, LABEL)
        finally:
            client.close()
    assert len(stub.rebuild_writes) == 2  # 诊断失败后恢复照常发生
    assert any("SHOW JOBS 诊断读取失败" in r.getMessage() for r in caplog.records)
