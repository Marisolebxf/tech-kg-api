"""图算法作业 service 单测（monkeypatch 假图服务，不触真实 Spark）。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from infra.graph_db import AlgorithmJobBusyError
from infra.graph_db.exceptions import GraphNotFoundError, GraphRequestError
from service.graph_algorithm import (
    GraphAlgorithmError,
    engine_status,
    get_job,
    get_result,
    list_edge_types,
    submit_job,
)
from service.platform_access import PlatformActor


def _actor(is_admin: bool = False) -> PlatformActor:
    return PlatformActor(user_id="101", username="u", display_name="u", email="", is_admin=is_admin)


def _job_snapshot(**overrides) -> SimpleNamespace:
    base = dict(
        job_id="job-1",
        status="running",
        created_at="2026-09-17T08:00:00Z",
        started_at=None,
        finished_at=None,
        submission_id=None,
        driver_state=None,
        error=None,
        log_tail=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture
def algo_backend(monkeypatch):
    monkeypatch.setenv("TRS_GRAPH_SPACE", "shared_business")
    submit_calls = []

    class Session:
        closed = False

        def close(self):
            self.closed = True

    class GraphClient:
        def list_spaces(self):
            return ["shared_business", "bound_private", "other_private"]

        def edge_types(self):
            return ["HAS_KEYWORD", "EMPLOYED_BY"]

    graph_client = GraphClient()

    class AlgoClient:
        def submit(self, algorithm, labels, **kwargs):
            submit_calls.append({"algorithm": algorithm, "labels": list(labels), **kwargs})
            return _job_snapshot(job_id="job-9", status="running")

        def get_job(self, job_id):
            return _job_snapshot(job_id=job_id, status="succeeded", driver_state="FINISHED")

        def get_result(self, job_id):
            return SimpleNamespace(
                job_id=job_id,
                sink="csv",
                rows=[{"vid": "p1", "pagerank": "0.15"}, {"vid": "p2", "pagerank": "0.20"}],
                count=2,
                truncated=False,
                message=None,
                space=None,
                tag=None,
                raw={},
            )

        def health(self):
            # Spark 运行器不可用时的真实返回（502）
            raise GraphRequestError(
                "GET /api/v1/algorithms/health -> 502", status_code=502, body="{}"
            )

    algo_client = AlgoClient()

    class SpaceService:
        def __init__(self, session):
            self.session = session
            self.client = graph_client

        def is_bound(self, user_id, space):
            assert not self.session.closed
            return (user_id, space) == ("101", "bound_private")

    monkeypatch.setattr("infra.mysql.create_session", Session)
    monkeypatch.setattr("service.graph_space.GraphSpaceService", SpaceService)
    monkeypatch.setattr("infra.graph_db.get_space_client", lambda space: graph_client)
    monkeypatch.setattr("infra.graph_db.get_space_algorithm_client", lambda space: algo_client)
    return SimpleNamespace(submit_calls=submit_calls, algo=algo_client)


@pytest.mark.parametrize("space", ["shared_business", "bound_private"])
def test_submit_allowed_on_default_and_bound_space(algo_backend, space) -> None:
    data = submit_job(_actor(), space, "pagerank", ["HAS_KEYWORD"], {"maxIter": 10})
    assert data["jobId"] == "job-9"
    assert data["status"] == "running"
    assert len(algo_backend.submit_calls) == 1


def test_submit_forces_csv_and_passes_options(algo_backend) -> None:
    submit_job(
        _actor(),
        "shared_business",
        "pagerank",
        ["HAS_KEYWORD", "EMPLOYED_BY"],
        {"maxIter": 10, "resetProb": 0.15},
        encode_id=True,
        partition_num=4,
    )
    call = algo_backend.submit_calls[0]
    assert call["sink"] == "csv"
    assert call["tag"] is None
    assert call["has_weight"] is False
    assert call["encode_id"] is True
    assert call["partition_num"] == 4
    assert call["maxIter"] == 10
    assert call["resetProb"] == 0.15
    assert call["labels"] == ["HAS_KEYWORD", "EMPLOYED_BY"]


def test_ordinary_user_cannot_submit_unbound_space(algo_backend) -> None:
    with pytest.raises(GraphAlgorithmError) as exc_info:
        submit_job(_actor(), "other_private", "pagerank", ["HAS_KEYWORD"], {})
    assert exc_info.value.status_code == 403
    assert algo_backend.submit_calls == []


def test_invalid_space_name_rejected(algo_backend) -> None:
    with pytest.raises(GraphAlgorithmError, match="图空间名称不合法"):
        submit_job(_actor(), "bad space!", "pagerank", ["HAS_KEYWORD"], {})
    assert algo_backend.submit_calls == []


def test_busy_maps_to_friendly_429(algo_backend) -> None:
    def raise_busy(*args, **kwargs):
        raise AlgorithmJobBusyError("busy", status_code=429, body="")

    algo_backend.algo.submit = raise_busy
    with pytest.raises(GraphAlgorithmError) as exc_info:
        submit_job(_actor(), "shared_business", "pagerank", ["HAS_KEYWORD"], {})
    assert exc_info.value.status_code == 429
    assert "同时仅允许一个作业" in str(exc_info.value)


def test_runner_unavailable_maps_friendly_502(algo_backend) -> None:
    def raise_502(*args, **kwargs):
        raise GraphRequestError(
            "POST /api/v1/algorithms/pagerank -> 502", status_code=502, body="{}"
        )

    algo_backend.algo.submit = raise_502
    with pytest.raises(GraphAlgorithmError) as exc_info:
        submit_job(_actor(), "shared_business", "pagerank", ["HAS_KEYWORD"], {})
    assert exc_info.value.status_code == 502
    assert "Spark 运行器未就绪" in str(exc_info.value)


def test_invalid_params_valueerror_maps_400(algo_backend) -> None:
    def raise_value_error(*args, **kwargs):
        raise ValueError("pagerank does not accept ['foo']")

    algo_backend.algo.submit = raise_value_error
    with pytest.raises(GraphAlgorithmError) as exc_info:
        submit_job(_actor(), "shared_business", "pagerank", ["HAS_KEYWORD"], {"foo": 1})
    assert exc_info.value.status_code == 400
    assert "算法参数不合法" in str(exc_info.value)


def test_get_job_returns_camel_snapshot(algo_backend) -> None:
    data = get_job(_actor(), "shared_business", "job-3")
    assert data["jobId"] == "job-3"
    assert data["status"] == "succeeded"
    assert data["driverState"] == "FINISHED"


def test_get_job_not_found_maps_404(algo_backend) -> None:
    def raise_not_found(job_id):
        raise GraphNotFoundError(f"GET /api/v1/algorithms/jobs/{job_id} -> 404")

    algo_backend.algo.get_job = raise_not_found
    with pytest.raises(GraphAlgorithmError) as exc_info:
        get_job(_actor(), "shared_business", "gone")
    assert exc_info.value.status_code == 404


def test_get_result_passthrough_with_truncated(algo_backend) -> None:
    data = get_result(_actor(), "shared_business", "job-9")
    assert data["sink"] == "csv"
    assert data["rows"] == [
        {"vid": "p1", "pagerank": "0.15"},
        {"vid": "p2", "pagerank": "0.20"},
    ]
    assert data["count"] == 2
    assert data["truncated"] is False


def test_list_edge_types(algo_backend) -> None:
    assert list_edge_types(_actor(), "shared_business") == ["HAS_KEYWORD", "EMPLOYED_BY"]


def test_engine_down_degrades_without_raising(algo_backend) -> None:
    status = engine_status(_actor(), "shared_business")
    assert status["status"] == "DOWN"
    assert status["activeJobs"] is None
    assert "Spark 运行器未就绪" in status["message"]


def test_engine_up(algo_backend) -> None:
    algo_backend.algo.health = lambda: {"status": "UP", "activeJobs": 0}
    status = engine_status(_actor(), "shared_business")
    assert status == {"status": "UP", "activeJobs": 0}
