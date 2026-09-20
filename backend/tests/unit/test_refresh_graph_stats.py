"""refresh_graph_stats activity 单测：写图后触发 SUBMIT JOB STATS（00918 总览统计更新）。

- 正常：对目标空间提交 stats job，返回 jobId
- 降级：提交失败（如另一 stats job 在跑）只返回 submitted=False，不抛异常
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from service.temporal_workflows import refresh_graph_stats


def _client_mock(job_id: int = 99, exc: Exception | None = None) -> MagicMock:
    client = MagicMock()
    if exc is not None:
        client.execute_write.side_effect = exc
    else:
        result = MagicMock()
        result.records = [{"New Job Id": job_id}]
        client.execute_write.return_value = result
    return client


def _settings_stub(space: str = "techkg") -> MagicMock:
    stub = MagicMock()
    stub.space = space
    return stub


def test_submits_stats_job_to_requested_space() -> None:
    client = _client_mock(job_id=7)
    settings = _settings_stub("techkg")
    with (
        patch("infra.graph_db.client.TRSGraphClient", return_value=client),
        patch("infra.graph_db.config.TRSGraphSettings.from_env", return_value=settings),
    ):
        resp = asyncio.run(refresh_graph_stats({"space": "gaoxing"}))
    assert resp == {"submitted": True, "jobId": 7}
    # 请求显式空间覆盖默认空间（与写图 activity 同口径）
    assert settings.space == "gaoxing"
    client.connect.assert_called_once()
    client.execute_write.assert_called_once_with("SUBMIT JOB STATS")
    client.close.assert_called_once()


def test_defaults_to_env_space_when_request_omits_it() -> None:
    client = _client_mock(job_id=3)
    settings = _settings_stub("techkg")
    with (
        patch("infra.graph_db.client.TRSGraphClient", return_value=client),
        patch("infra.graph_db.config.TRSGraphSettings.from_env", return_value=settings),
    ):
        resp = asyncio.run(refresh_graph_stats({}))
    assert resp["submitted"] is True
    assert settings.space == "techkg"


def test_degrades_when_submit_fails() -> None:
    client = _client_mock(exc=RuntimeError("another stats job is running"))
    settings = _settings_stub("techkg")
    with (
        patch("infra.graph_db.client.TRSGraphClient", return_value=client),
        patch("infra.graph_db.config.TRSGraphSettings.from_env", return_value=settings),
    ):
        resp = asyncio.run(refresh_graph_stats({}))
    assert resp["submitted"] is False
    assert "stats job" in resp["error"]
    client.close.assert_called_once()


def test_missing_job_id_in_records_still_counts_as_submitted() -> None:
    client = MagicMock()
    result = MagicMock()
    result.records = []  # trs-graph 未透出 New Job Id 列（形状变化）时
    client.execute_write.return_value = result
    settings = _settings_stub("techkg")
    with (
        patch("infra.graph_db.client.TRSGraphClient", return_value=client),
        patch("infra.graph_db.config.TRSGraphSettings.from_env", return_value=settings),
    ):
        resp = asyncio.run(refresh_graph_stats({}))
    assert resp == {"submitted": True, "jobId": None}
