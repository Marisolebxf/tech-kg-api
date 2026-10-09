"""Cancellation boundaries, worker sharing, access checks and Spark acceptance."""
from types import SimpleNamespace

import httpx
import pytest

from infra.graph_db.algorithm_client import TRSAlgorithmClient
from infra.graph_db.config import TRSGraphSettings
from infra.graph_db.exceptions import GraphRequestError
from service import graph_algorithm as service
from service.platform_access import PlatformActor


@pytest.fixture
def cancellation(monkeypatch):
    values = {}
    def save(key, value, **kwargs):
        values[key] = value
        return True
    redis = SimpleNamespace(get=lambda key: values.get(key), set=save)
    monkeypatch.setattr(service, '_shared_redis', lambda: redis)
    monkeypatch.setattr(service, '_degree_jobs', {})
    monkeypatch.setattr(service, '_ensure_space_access', lambda actor, space: None)
    monkeypatch.setattr(service, '_ensure_remote_job_access', lambda *args: None)
    return SimpleNamespace(redis=redis, values=values, actor=PlatformActor(
        user_id='101', username='u', display_name='u', email='', is_admin=False,
    ))


def test_cancel_degree_before_execution_across_workers(cancellation, monkeypatch):
    job = service._save_degree_job('dev', ['CITES'], [], False, running=True)
    monkeypatch.setattr(service, '_degree_jobs', {})
    assert service.cancel_job(cancellation.actor, 'dev', job['job_id'])['status'] == 'cancelled'
    calls = []
    monkeypatch.setattr(service, '_degree_rows_via_ngql', lambda *args, **kw: calls.append(1))
    service._run_degree_job(job)
    assert calls == []
    assert service.get_job(cancellation.actor, 'dev', job['job_id'])['status'] == 'cancelled'
    with pytest.raises(service.GraphAlgorithmError) as error:
        service.get_result(cancellation.actor, 'dev', job['job_id'])
    assert error.value.status_code == 409


def test_degree_cancel_between_reads_never_publishes_results(cancellation, monkeypatch):
    job = service._save_degree_job('dev', ['CITES'], [], False, running=True)
    calls = []
    def read(query, **kwargs):
        calls.append(query)
        service.cancel_job(cancellation.actor, 'dev', job['job_id'])
        return SimpleNamespace(records=[{'vid': 'paper1', 'cnt': 1}])
    client = SimpleNamespace(edge_types=lambda: ['CITES'], execute_read=read)
    monkeypatch.setattr('infra.graph_db.get_space_client', lambda space: client)
    service._run_degree_job(job)
    assert len(calls) == 1
    assert job['status'] == 'cancelled'
    assert job['rows'] == []
    assert not hasattr(service._degree_context, 'job')


def test_finished_degree_job_keeps_results(cancellation):
    job = service._save_degree_job('dev', ['CITES'], [{'vid': 'p'}], False)
    assert service.cancel_job(cancellation.actor, 'dev', job['job_id'])['status'] == 'succeeded'
    assert service._DEGREE_CANCEL_PREFIX + job['job_id'] not in cancellation.values


def test_cancel_signal_failure_keeps_job_running(cancellation):
    job = service._save_degree_job('dev', ['CITES'], [], False, running=True)
    cancellation.redis.set = lambda *args, **kwargs: False
    with pytest.raises(service.GraphAlgorithmError) as error:
        service.cancel_job(cancellation.actor, 'dev', job['job_id'])
    assert error.value.status_code == 503
    assert job['status'] == 'running'


def remote_client(monkeypatch):
    job = SimpleNamespace(job_id='remote', status='running', submission_id='driver-1',
        driver_state='RUNNING', created_at=None, started_at=None, finished_at=None,
        error=None, log_tail=None)
    kills = []
    client = SimpleNamespace(get_job=lambda job_id: job,
        kill_submission=lambda submission_id, url: kills.append((submission_id, url)))
    monkeypatch.setattr('infra.graph_db.get_space_algorithm_client', lambda space: client)
    return job, kills


def test_remote_kill_acceptance_waits_for_killed_state(cancellation, monkeypatch):
    monkeypatch.setenv('GRAPH_ALGO_SPARK_REST_URL', 'http://spark:6066')
    job, kills = remote_client(monkeypatch)
    assert service.cancel_job(cancellation.actor, 'dev', 'remote')['status'] == 'running'
    assert kills == [('driver-1', 'http://spark:6066')]
    job.status, job.driver_state = 'failed', 'KILLED'
    assert service.get_job(cancellation.actor, 'dev', 'remote')['status'] == 'cancelled'


def test_remote_cancel_requires_configuration(cancellation, monkeypatch):
    monkeypatch.delenv('GRAPH_ALGO_SPARK_REST_URL', raising=False)
    _, kills = remote_client(monkeypatch)
    with pytest.raises(service.GraphAlgorithmError) as error:
        service.cancel_job(cancellation.actor, 'dev', 'remote')
    assert error.value.status_code == 503
    assert kills == []


def test_remote_cancel_checks_space_before_killing(cancellation, monkeypatch):
    _, kills = remote_client(monkeypatch)
    def deny(*args):
        raise service.GraphAlgorithmError('wrong space', 403)
    monkeypatch.setattr(service, '_ensure_remote_job_access', deny)
    with pytest.raises(service.GraphAlgorithmError) as error:
        service.cancel_job(cancellation.actor, 'other', 'remote')
    assert error.value.status_code == 403
    assert kills == []


@pytest.mark.parametrize('success,returned_id', [(True, 'driver-1'), (False, 'driver-1'), (True, 'other')])
def test_spark_kill_targets_exact_driver_and_checks_acceptance(success, returned_id):
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={'success': success, 'submissionId': returned_id})
    client = TRSAlgorithmClient(TRSGraphSettings(base_url='http://graph', space='dev'),
        transport=httpx.MockTransport(handle))
    if success and returned_id == 'driver-1':
        client.kill_submission('driver-1', 'http://spark:6066')
    else:
        with pytest.raises(GraphRequestError):
            client.kill_submission('driver-1', 'http://spark:6066')
    assert len(requests) == 1
    assert str(requests[0].url) == 'http://spark:6066/v1/submissions/kill/driver-1'
    assert requests[0].method == 'POST'
    assert 'X-API-Key' not in requests[0].headers


def test_late_worker_snapshot_cannot_overwrite_cancel_marker(cancellation, monkeypatch):
    job = service._save_degree_job('dev', ['CITES'], [], False, running=True)
    service.cancel_job(cancellation.actor, 'dev', job['job_id'])
    # A completion snapshot prepared just before another worker cancels arrives late.
    job.update(status='succeeded', rows=[{'vid': 'late-result'}])
    service._shared_job_save(job['job_id'], job)
    monkeypatch.setattr(service, '_degree_jobs', {})
    assert service.get_job(cancellation.actor, 'dev', job['job_id'])['status'] == 'cancelled'
    with pytest.raises(service.GraphAlgorithmError):
        service.get_result(cancellation.actor, 'dev', job['job_id'])
