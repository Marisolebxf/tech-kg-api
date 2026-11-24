"""算法作业由服务端登记空间，伪造请求空间不得取回他业务结果。"""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db_model.business_algorithm_job import BusinessAlgorithmJob
from infra.graph_db.algorithm_client import AlgorithmJob
from service import graph_algorithm as service
from service.platform_access import PlatformActor


def actor(business="a", admin=False, role="developer", user_id=None):
    return PlatformActor(
        user_id=user_id or business,
        username=business,
        display_name=business,
        email="",
        is_admin=admin,
        business_id=business,
        business_role=role,
    )


@pytest.fixture
def registry(monkeypatch):
    monkeypatch.setenv("BUSINESS_RBAC_ENABLED", "true")
    engine = create_engine("sqlite://")
    BusinessAlgorithmJob.__table__.create(engine)

    @contextmanager
    def session_scope():
        with Session(engine) as session:
            yield session
            session.commit()

    monkeypatch.setattr("infra.mysql.session_scope", session_scope)

    def allow(principal, space, action="read"):
        if not principal.is_admin and space != principal.business_id:
            raise HTTPException(403, "其他业务空间")
        if action == "write" and not principal.is_admin and space == "shared":
            raise HTTPException(403, "共享生产空间只读")

    monkeypatch.setattr("service.business_access_control.ensure_space_access", allow)
    monkeypatch.setattr(service, "_ensure_space_access", allow)
    monkeypatch.setattr(service, "_local_degree_job", lambda *args: None)
    remote = Mock()
    remote.submit.return_value = AlgorithmJob(job_id="remote-job", status="running")
    remote.get_job.return_value = AlgorithmJob(job_id="remote-job", status="succeeded")
    remote.get_result.return_value = SimpleNamespace(
        job_id="remote-job",
        sink="csv",
        rows=[{"id": "private-a"}],
        count=1,
        truncated=False,
        message=None,
    )
    monkeypatch.setattr("infra.graph_db.get_space_algorithm_client", lambda *args: remote)
    yield session_scope, remote
    engine.dispose()


def test_remote_submit_persists_server_owned_space(registry):
    session_scope, _ = registry
    result = service.submit_job(actor(), "a", "pagerank", ["CITES"], {})
    assert result["jobId"] == "remote-job"
    with session_scope() as session:
        row = session.get(BusinessAlgorithmJob, "remote-job")
        assert (row.graph_space, row.created_by) == ("a", "a")


@pytest.mark.parametrize("read", [service.get_job, service.get_result])
def test_cannot_read_foreign_remote_job_by_substituting_authorized_space(registry, read):
    _, remote = registry
    service._register_remote_job(actor(), "a", "remote-job")
    with pytest.raises(HTTPException) as exc:
        read(actor("b"), "b", "remote-job")
    assert exc.value.status_code == 403
    remote.get_job.assert_not_called()
    remote.get_result.assert_not_called()


def test_registry_reads_are_not_cached_across_reassignment(registry):
    session_scope, _ = registry
    service._register_remote_job(actor(), "a", "remote-job")
    assert service.get_result(actor(), "a", "remote-job")["rows"] == [{"id": "private-a"}]
    with session_scope() as session:
        session.get(BusinessAlgorithmJob, "remote-job").graph_space = "b"
    with pytest.raises(HTTPException):
        service.get_result(actor(), "a", "remote-job")


def test_unknown_legacy_jobs_require_admin(registry):
    with pytest.raises(HTTPException) as exc:
        service.get_job(actor(), "a", "legacy-job")
    assert exc.value.status_code == 403
    assert service.get_job(actor(admin=True), "a", "legacy-job")["status"] == "succeeded"


def test_persistence_failure_never_returns_submission_success(registry, monkeypatch):
    _, remote = registry

    @contextmanager
    def broken():
        raise SQLAlchemyError("offline")
        yield

    monkeypatch.setattr("infra.mysql.session_scope", broken)
    with pytest.raises(HTTPException) as exc:
        service.submit_job(actor(), "a", "pagerank", ["CITES"], {})
    assert exc.value.status_code == 503
    remote.submit.assert_called_once()


def test_registry_unavailable_fails_closed(registry, monkeypatch):
    _, remote = registry

    @contextmanager
    def broken():
        raise SQLAlchemyError("offline")
        yield

    monkeypatch.setattr("infra.mysql.session_scope", broken)
    with pytest.raises(HTTPException) as exc:
        service.get_result(actor(), "a", "remote-job")
    assert exc.value.status_code == 503
    remote.get_result.assert_not_called()


def test_plain_member_cannot_submit_jobs(registry):
    """渗透 B3：只读成员（writeAllowed=false）提交作业须 403，且不触达 Spark。"""
    _, remote = registry
    with pytest.raises(service.GraphAlgorithmError) as exc:
        service.submit_job(actor(role="user"), "a", "pagerank", ["CITES"], {})
    assert exc.value.status_code == 403
    remote.submit.assert_not_called()


def test_submit_requires_space_write_permission(registry):
    _, remote = registry
    with pytest.raises(HTTPException) as exc:
        service.submit_job(actor("shared"), "shared", "pagerank", ["CITES"], {})
    assert exc.value.status_code == 403
    remote.submit.assert_not_called()
    assert service.submit_job(actor(admin=True), "shared", "pagerank", ["CITES"], {})


@pytest.mark.parametrize("operation", [service.get_job, service.get_result, service.cancel_job])
def test_same_space_reader_cannot_touch_someone_elses_job(registry, operation):
    _, remote = registry
    service._register_remote_job(actor(), "a", "remote-job")
    with pytest.raises(service.GraphAlgorithmError) as exc:
        operation(actor(user_id="teammate"), "a", "remote-job")
    assert exc.value.status_code == 403
    remote.get_job.assert_not_called()
    remote.get_result.assert_not_called()


def test_executor_log_tail_only_visible_to_admin(registry):
    _, remote = registry
    remote.get_job.return_value = AlgorithmJob(
        job_id="remote-job", status="running", log_tail="spark executor 10.0.0.1"
    )
    service._register_remote_job(actor(), "a", "remote-job")
    assert service.get_job(actor(), "a", "remote-job")["logTail"] is None
    admin_view = service.get_job(actor(admin=True), "a", "remote-job")
    assert admin_view["logTail"] == "spark executor 10.0.0.1"


def test_degree_job_is_bound_to_submitter(registry, monkeypatch):
    job = {
        "job_id": "degree-1",
        "space": "a",
        "status": "succeeded",
        "created_by": "a",
        "created_at": "2026-11-24T00:00:00+00:00",
        "finished_at": "2026-11-24T00:00:01+00:00",
        "error": None,
        "rows": [],
        "truncated": False,
    }
    monkeypatch.setattr(service, "_local_degree_job", lambda space, job_id: job)
    assert service.get_job(actor(), "a", "degree-1")["status"] == "succeeded"
    for operation in (service.get_job, service.get_result, service.cancel_job):
        with pytest.raises(service.GraphAlgorithmError) as exc:
            operation(actor(user_id="teammate"), "a", "degree-1")
        assert exc.value.status_code == 403
