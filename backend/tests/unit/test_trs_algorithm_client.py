"""Unit tests for infra.graph_db.algorithm_client (TRSAlgorithmClient, MockTransport)."""

from __future__ import annotations

import inspect
import json

import httpx
import pytest

import infra.graph_db as graph_pkg
from infra.graph_db.algorithm_client import (
    _ALGORITHM_PARAMS,
    AlgorithmJob,
    AlgorithmJobBusyError,
    AlgorithmJobFailedError,
    AlgorithmJobTimeoutError,
    AlgorithmResult,
    TRSAlgorithmClient,
    _build_body,
    _to_camel,
)
from infra.graph_db.config import TRSGraphSettings
from infra.graph_db.exceptions import (
    GraphConnectionError,
    GraphNotFoundError,
    GraphRepoError,
    GraphRequestError,
)

# (方法名, 线上算法名, 算法入参, 期望报文参数) — 覆盖全部 18 个类型化提交方法。
_TYPED_METHOD_CASES = [
    (
        "pagerank",
        "pagerank",
        {"max_iter": 10, "reset_prob": 0.15},
        {"maxIter": 10, "resetProb": 0.15},
    ),
    (
        "louvain",
        "louvain",
        {"max_iter": 20, "internal_iter": 5, "tol": 0.01},
        {"maxIter": 20, "internalIter": 5, "tol": 0.01},
    ),
    ("kcore", "kcore", {"max_iter": 10, "degree": 3}, {"maxIter": 10, "degree": 3}),
    ("labelpropagation", "labelpropagation", {"max_iter": 10}, {"maxIter": 10}),
    ("connected_component", "connectedcomponent", {"max_iter": 10}, {"maxIter": 10}),
    (
        "strongly_connected_component",
        "stronglyconnectedcomponent",
        {"max_iter": 10},
        {"maxIter": 10},
    ),
    ("triangle_count", "trianglecount", {}, {}),
    ("graph_triangle_count", "graphtrianglecount", {}, {}),
    ("degree_static", "degreestatic", {}, {}),
    ("betweenness", "betweenness", {"max_iter": 10}, {"maxIter": 10}),
    ("closeness", "closeness", {}, {}),
    (
        "clustering_coefficient",
        "clusteringcoefficient",
        {"coefficient_type": "global"},
        {"type": "global"},
    ),
    ("jaccard", "jaccard", {"tol": 0.001}, {"tol": 0.001}),
    ("shortest_paths", "shortestpaths", {"landmarks": "1,3"}, {"landmarks": "1,3"}),
    ("bfs", "bfs", {"root": "1", "max_iter": 5}, {"root": "1", "maxIter": 5}),
    ("dfs", "dfs", {"root": "2"}, {"root": "2"}),
    (
        "hanp",
        "hanp",
        {"hop_attenuation": 0.1, "max_iter": 5, "preference": 0.9},
        {"hopAttenuation": 0.1, "maxIter": 5, "preference": 0.9},
    ),
    (
        "node2vec",
        "node2vec",
        {
            "max_iter": 5,
            "lr": 0.02,
            "dim": 16,
            "window": 5,
            "walk_length": 10,
            "num_walks": 3,
            "p": 1.0,
            "q": 0.5,
            "directed": True,
        },
        {
            "maxIter": 5,
            "lr": 0.02,
            "dim": 16,
            "window": 5,
            "walkLength": 10,
            "numWalks": 3,
            "p": 1.0,
            "q": 0.5,
            "directed": True,
        },
    ),
]


def _make_client(handler, *, api_key: str | None = "test-key"):
    """Build a TRSAlgorithmClient backed by a MockTransport handler and connect it."""
    settings = TRSGraphSettings(base_url="http://test", space="test", api_key=api_key, timeout=5)
    client = TRSAlgorithmClient(settings, transport=httpx.MockTransport(handler))
    client.connect()
    return client


def _ok_health(request):
    if request.url.path == "/health":
        return httpx.Response(200, json={"status": "UP"})
    return httpx.Response(404)


def _job_payload(job_id="job-1", status="running", **extra):
    return {"jobId": job_id, "status": status, **extra}


class TestExceptions:
    def test_hierarchy(self):
        assert issubclass(AlgorithmJobBusyError, GraphRequestError)
        assert issubclass(AlgorithmJobFailedError, GraphRepoError)
        assert issubclass(AlgorithmJobTimeoutError, GraphRepoError)

    def test_failed_error_carries_job(self):
        job = AlgorithmJob(job_id="j", status="failed", error="boom")
        err = AlgorithmJobFailedError("job failed", job=job)
        assert err.job is job

    def test_timeout_error_carries_job_id_and_status(self):
        err = AlgorithmJobTimeoutError("timeout", job_id="j", last_status="running")
        assert err.job_id == "j"
        assert err.last_status == "running"


class TestCamel:
    def test_snake_to_camel(self):
        assert _to_camel("max_iter") == "maxIter"
        assert _to_camel("hop_attenuation") == "hopAttenuation"
        assert _to_camel("walk_length") == "walkLength"

    def test_camel_passthrough(self):
        assert _to_camel("maxIter") == "maxIter"
        assert _to_camel("tol") == "tol"


class TestJobModel:
    def test_from_payload_full_mapping(self):
        job = AlgorithmJob.from_payload(
            {
                "jobId": "j-9",
                "status": "running",
                "createdAt": "2026-09-16T10:00:00Z",
                "startedAt": "2026-09-16T10:00:01Z",
                "submissionId": "sub-1",
                "driverState": "RUNNING",
                "error": None,
                "finishedAt": None,
                "logTail": "line1",
            }
        )
        assert job.job_id == "j-9"
        assert job.status == "running"
        assert job.created_at == "2026-09-16T10:00:00Z"
        assert job.started_at == "2026-09-16T10:00:01Z"
        assert job.submission_id == "sub-1"
        assert job.driver_state == "RUNNING"
        assert job.log_tail == "line1"
        assert job.raw["jobId"] == "j-9"

    def test_from_payload_defaults(self):
        job = AlgorithmJob.from_payload({"jobId": "j", "status": "succeeded"})
        assert job.created_at is None
        assert job.error is None
        assert job.raw == {"jobId": "j", "status": "succeeded"}

    def test_status_properties(self):
        running = AlgorithmJob(job_id="j", status="running")
        assert running.is_running and not running.is_done
        ok = AlgorithmJob(job_id="j", status="succeeded")
        assert ok.is_succeeded and ok.is_done
        bad = AlgorithmJob(job_id="j", status="failed")
        assert bad.is_failed and bad.is_done


class TestResultModel:
    def test_csv_payload(self):
        result = AlgorithmResult.from_payload(
            {
                "jobId": "j",
                "sink": "csv",
                "rows": [{"id": "1", "pagerank": "0.5"}],
                "count": 1,
                "truncated": False,
            }
        )
        assert result.sink == "csv"
        assert result.csv_rows == [{"id": "1", "pagerank": "0.5"}]
        assert result.count == 1
        assert result.truncated is False

    def test_text_payload(self):
        result = AlgorithmResult.from_payload(
            {"jobId": "j", "sink": "text", "rows": ["a b", "c"], "count": 2}
        )
        assert result.text_lines == ["a b", "c"]
        assert result.truncated is None

    def test_nebula_payload(self):
        result = AlgorithmResult.from_payload(
            {"jobId": "j", "sink": "nebula", "message": "written", "space": "techkg", "tag": "PR"}
        )
        assert result.message == "written"
        assert result.space == "techkg"
        assert result.tag == "PR"

    def test_from_payload_defaults(self):
        result = AlgorithmResult.from_payload({"jobId": "j", "sink": "csv"})
        assert result.rows == []
        assert result.count is None

    def test_csv_rows_rejects_non_csv(self):
        result = AlgorithmResult.from_payload({"jobId": "j", "sink": "text"})
        with pytest.raises(GraphRequestError) as excinfo:
            _ = result.csv_rows
        assert excinfo.value.status_code == 409

    def test_text_lines_rejects_non_text(self):
        result = AlgorithmResult.from_payload({"jobId": "j", "sink": "csv"})
        with pytest.raises(GraphRequestError) as excinfo:
            _ = result.text_lines
        assert excinfo.value.status_code == 409


class TestBuildBody:
    def _body(self, **overrides):
        kwargs = {
            "sink": "csv",
            "tag": None,
            "write_type": "update",
            "weight_cols": None,
            "has_weight": False,
            "encode_id": False,
            "partition_num": 1,
        }
        kwargs.update(overrides)
        return _build_body(["A", "B"], {"maxIter": 10, "resetProb": None}, **kwargs)

    def test_assembly_drops_none_params(self):
        body = self._body(encode_id=True, partition_num=4)
        assert body == {
            "labels": ["A", "B"],
            "hasWeight": False,
            "sink": "csv",
            "writeType": "update",
            "encodeId": True,
            "partitionNum": 4,
            "maxIter": 10,
        }

    def test_optional_fields_included_when_set(self):
        body = self._body(sink="nebula", tag="PR", weight_cols=["w1", "w2"], has_weight=True)
        assert body["tag"] == "PR"
        assert body["weightCols"] == ["w1", "w2"]
        assert body["hasWeight"] is True

    def test_labels_must_be_non_empty(self):
        with pytest.raises(ValueError, match="labels"):
            _build_body(
                [],
                {},
                sink="csv",
                tag=None,
                write_type="update",
                weight_cols=None,
                has_weight=False,
                encode_id=False,
                partition_num=1,
            )

    def test_labels_must_be_non_blank_strings(self):
        with pytest.raises(ValueError, match="labels"):
            _build_body(
                ["  "],
                {},
                sink="csv",
                tag=None,
                write_type="update",
                weight_cols=None,
                has_weight=False,
                encode_id=False,
                partition_num=1,
            )

    def test_invalid_sink(self):
        with pytest.raises(ValueError, match="sink"):
            self._body(sink="json")

    def test_invalid_write_type(self):
        with pytest.raises(ValueError, match="write_type"):
            self._body(write_type="upsert")

    def test_nebula_requires_tag(self):
        with pytest.raises(ValueError, match="tag"):
            self._body(sink="nebula")

    @pytest.mark.parametrize("weight_cols", [None, [], ["only-one"]])
    def test_has_weight_requires_matching_weight_cols(self, weight_cols):
        with pytest.raises(ValueError, match="weight_cols"):
            self._body(has_weight=True, weight_cols=weight_cols)

    @pytest.mark.parametrize("partition_num", [0, -1, 10001])
    def test_partition_num_bounds(self, partition_num):
        with pytest.raises(ValueError, match="partition_num"):
            self._body(partition_num=partition_num)


class TestConnection:
    def test_connect_sends_headers(self):
        seen = {}

        def handler(request):
            if request.url.path == "/health":
                seen["headers"] = dict(request.headers)
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(404)

        _make_client(handler)
        assert seen["headers"]["x-graph-space"] == "test"
        assert seen["headers"]["x-api-key"] == "test-key"

    def test_connect_without_api_key_omits_header(self):
        seen = {}

        def handler(request):
            if request.url.path == "/health":
                seen["headers"] = dict(request.headers)
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(404)

        _make_client(handler, api_key=None)
        assert "x-api-key" not in seen["headers"]

    def test_connect_health_error(self):
        client = TRSAlgorithmClient(
            TRSGraphSettings(base_url="http://test", space="test"),
            transport=httpx.MockTransport(lambda request: httpx.Response(500)),
        )
        with pytest.raises(GraphConnectionError):
            client.connect()
        assert not client.is_connected()

    def test_connect_transport_error(self):
        def handler(request):
            raise httpx.ConnectError("boom", request=request)

        client = TRSAlgorithmClient(
            TRSGraphSettings(base_url="http://test", space="test"),
            transport=httpx.MockTransport(handler),
        )
        with pytest.raises(GraphConnectionError):
            client.connect()

    def test_connect_is_idempotent(self):
        health_calls = []

        def handler(request):
            if request.url.path == "/health":
                health_calls.append(1)
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(404)

        client = _make_client(handler)
        client.connect()
        assert len(health_calls) == 1

    def test_is_connected_statuses(self):
        client = _make_client(lambda request: httpx.Response(200, json={"status": "UP"}))
        assert client.is_connected()

        down = _make_client(lambda request: httpx.Response(200, json={"status": "DOWN"}))
        assert not down.is_connected()

    def test_request_before_connect_raises(self):
        client = TRSAlgorithmClient(TRSGraphSettings(base_url="http://test", space="test"))
        with pytest.raises(GraphConnectionError, match="Not connected"):
            client.get_job("j")

    def test_close_releases_client(self):
        client = _make_client(_ok_health)
        client.close()
        with pytest.raises(GraphConnectionError, match="Not connected"):
            client.get_job("j")


class TestRequestErrors:
    def _client(self, status, body):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(status, json=body)

        return _make_client(handler)

    def test_404_maps_to_not_found_with_detail(self):
        client = self._client(404, {"error": "NotFound", "message": "no such job"})
        with pytest.raises(GraphNotFoundError) as excinfo:
            client.get_job("missing")
        assert "404: NotFound: no such job" in str(excinfo.value)

    def test_404_without_json_detail(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(404, text="plain")

        client = _make_client(handler)
        with pytest.raises(GraphNotFoundError, match=r"-> 404$"):
            client.get_job("missing")

    def test_429_maps_to_busy(self):
        client = self._client(429, {"error": "Conflict", "message": "job already running"})
        with pytest.raises(AlgorithmJobBusyError) as excinfo:
            client.submit("pagerank", ["Scholar"], max_iter=5)
        assert excinfo.value.status_code == 429
        assert "job already running" in excinfo.value.body

    def test_500_maps_to_request_error(self):
        client = self._client(500, {"error": "Internal", "message": "spark down"})
        with pytest.raises(GraphRequestError) as excinfo:
            client.get_job("j")
        assert excinfo.value.status_code == 500

    def test_transport_error_maps_to_connection_error(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            raise httpx.ReadTimeout("timed out", request=request)

        client = _make_client(handler)
        with pytest.raises(GraphConnectionError):
            client.get_job("j")


class TestSubmit:
    def _capture(self):
        seen = {}

        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            seen["path"] = request.url.path
            seen["body"] = json.loads(request.content)
            return httpx.Response(202, json=_job_payload())

        return handler, seen

    def test_submit_builds_request(self):
        handler, seen = self._capture()
        client = _make_client(handler)
        job = client.submit("pagerank", ["Scholar"], max_iter=5, reset_prob=0.2)
        assert seen["path"] == "/api/v1/algorithms/pagerank"
        assert seen["body"]["labels"] == ["Scholar"]
        assert seen["body"]["maxIter"] == 5
        assert seen["body"]["resetProb"] == 0.2
        assert "tol" not in seen["body"]
        assert job.job_id == "job-1"
        assert job.is_running

    def test_submit_normalizes_algorithm_name(self):
        handler, seen = self._capture()
        client = _make_client(handler)
        client.submit("  PageRank ", ["Scholar"])
        assert seen["path"] == "/api/v1/algorithms/pagerank"

    def test_submit_accepts_camel_case_params(self):
        handler, seen = self._capture()
        client = _make_client(handler)
        client.submit("pagerank", ["Scholar"], maxIter=7)
        assert seen["body"]["maxIter"] == 7

    def test_submit_unknown_algorithm(self):
        client = _make_client(_ok_health)
        with pytest.raises(ValueError, match="unknown algorithm"):
            client.submit("dijkstra", ["Scholar"])

    def test_submit_unknown_param(self):
        client = _make_client(_ok_health)
        with pytest.raises(ValueError, match="does not accept") as excinfo:
            client.submit("pagerank", ["Scholar"], tol=0.1)
        assert "maxIter" in str(excinfo.value)

    def test_submit_missing_required_param(self):
        client = _make_client(_ok_health)
        with pytest.raises(ValueError, match="bfs requires"):
            client.submit("bfs", ["Scholar"], max_iter=5)
        with pytest.raises(ValueError, match="shortestpaths requires"):
            client.submit("shortestpaths", ["Scholar"])

    def test_submit_full_common_options(self):
        handler, seen = self._capture()
        client = _make_client(handler)
        client.submit(
            "pagerank",
            ["Scholar", "EMPLOYED_BY"],
            sink="nebula",
            tag="PR",
            write_type="insert",
            weight_cols=["w", "0"],
            has_weight=True,
            encode_id=True,
            partition_num=8,
            max_iter=3,
        )
        body = seen["body"]
        assert body["labels"] == ["Scholar", "EMPLOYED_BY"]
        assert body["sink"] == "nebula"
        assert body["tag"] == "PR"
        assert body["writeType"] == "insert"
        assert body["weightCols"] == ["w", "0"]
        assert body["hasWeight"] is True
        assert body["encodeId"] is True
        assert body["partitionNum"] == 8
        assert body["maxIter"] == 3


class TestTypedMethods:
    @pytest.mark.parametrize(("method", "wire_name", "kwargs", "expected"), _TYPED_METHOD_CASES)
    def test_request_shape(self, method, wire_name, kwargs, expected):
        seen = {}

        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            seen["path"] = request.url.path
            seen["body"] = json.loads(request.content)
            return httpx.Response(202, json=_job_payload())

        client = _make_client(handler)
        job = getattr(client, method)(["Scholar"], **kwargs)
        assert seen["path"] == f"/api/v1/algorithms/{wire_name}"
        body = seen["body"]
        assert body["labels"] == ["Scholar"]
        for key, value in expected.items():
            assert body[key] == value
        # 未传入的算法参数必须从报文中剔除（交给服务端取默认值）。
        for key in _ALGORITHM_PARAMS[wire_name] - set(expected):
            assert key not in body
        assert job.job_id == "job-1"

    def test_cases_cover_the_whole_registry(self):
        assert {case[1] for case in _TYPED_METHOD_CASES} == set(_ALGORITHM_PARAMS)

    def test_typed_method_passes_common_options(self):
        seen = {}

        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            seen["body"] = json.loads(request.content)
            return httpx.Response(202, json=_job_payload())

        client = _make_client(handler)
        client.pagerank(
            ["Scholar"],
            max_iter=10,
            sink="nebula",
            tag="PR",
            write_type="insert",
            weight_cols=["w"],
            has_weight=True,
            encode_id=True,
            partition_num=7,
        )
        assert seen["body"] == {
            "labels": ["Scholar"],
            "hasWeight": True,
            "sink": "nebula",
            "tag": "PR",
            "writeType": "insert",
            "weightCols": ["w"],
            "encodeId": True,
            "partitionNum": 7,
            "maxIter": 10,
        }

    def test_bfs_dfs_root_is_required(self):
        for method in (TRSAlgorithmClient.bfs, TRSAlgorithmClient.dfs):
            param = inspect.signature(method).parameters["root"]
            assert param.default is inspect.Parameter.empty


class TestJobLifecycle:
    def test_get_job(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            if request.url.path == "/api/v1/algorithms/jobs/j-9":
                return httpx.Response(
                    200,
                    json=_job_payload("j-9", "running", driverState="RUNNING", submissionId="s-1"),
                )
            return httpx.Response(404)

        client = _make_client(handler)
        job = client.get_job("j-9")
        assert job.job_id == "j-9"
        assert job.is_running
        assert job.driver_state == "RUNNING"

    def test_get_job_unknown(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(404)

        client = _make_client(handler)
        with pytest.raises(GraphNotFoundError):
            client.get_job("missing")

    def test_get_result_csv(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            if request.url.path == "/api/v1/algorithms/jobs/j-9/result":
                return httpx.Response(
                    200,
                    json={
                        "jobId": "j-9",
                        "sink": "csv",
                        "rows": [{"id": "1", "pagerank": "0.2"}],
                        "count": 1,
                        "truncated": False,
                    },
                )
            return httpx.Response(404)

        client = _make_client(handler)
        result = client.get_result("j-9")
        assert result.csv_rows == [{"id": "1", "pagerank": "0.2"}]

    def test_get_result_while_running_maps_409(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(409, json={"error": "Conflict", "message": "job still running"})

        client = _make_client(handler)
        with pytest.raises(GraphRequestError) as excinfo:
            client.get_result("j-9")
        assert excinfo.value.status_code == 409

    def test_wait_for_job_immediate_success(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(200, json=_job_payload("j-9", "succeeded"))

        client = _make_client(handler)
        job = client.wait_for_job("j-9", timeout_s=1, poll_interval_s=1)
        assert job.is_succeeded

    def test_wait_for_job_polls_until_success(self):
        statuses = ["running", "running", "succeeded"]
        polls = []

        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            polls.append(1)
            return httpx.Response(200, json=_job_payload("j-9", statuses[len(polls) - 1]))

        client = _make_client(handler)
        job = client.wait_for_job("j-9", timeout_s=5, poll_interval_s=0.001)
        assert job.is_succeeded
        assert len(polls) == 3

    def test_wait_for_job_failed(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(
                200,
                json=_job_payload("j-9", "failed", error="spark oom", driverState="ERROR"),
            )

        client = _make_client(handler)
        with pytest.raises(AlgorithmJobFailedError) as excinfo:
            client.wait_for_job("j-9")
        assert excinfo.value.job.error == "spark oom"
        assert excinfo.value.job.driver_state == "ERROR"

    def test_wait_for_job_timeout(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(200, json=_job_payload("j-9", "running"))

        client = _make_client(handler)
        with pytest.raises(AlgorithmJobTimeoutError) as excinfo:
            client.wait_for_job("j-9", timeout_s=0.05, poll_interval_s=0.05)
        assert excinfo.value.job_id == "j-9"
        assert excinfo.value.last_status == "running"

    @pytest.mark.parametrize(
        "kwargs",
        [{"timeout_s": 0, "poll_interval_s": 1}, {"timeout_s": 1, "poll_interval_s": 0}],
    )
    def test_wait_for_job_rejects_non_positive_args(self, kwargs):
        client = _make_client(_ok_health)
        with pytest.raises(ValueError, match="positive"):
            client.wait_for_job("j-9", **kwargs)

    def test_health(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            if request.url.path == "/api/v1/algorithms/health":
                return httpx.Response(200, json={"status": "UP", "activeJobs": 2})
            return httpx.Response(404)

        client = _make_client(handler)
        assert client.health() == {"status": "UP", "activeJobs": 2}


class TestRun:
    def test_run_full_flow(self):
        polls = []

        def handler(request):
            path = request.url.path
            if path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            if path == "/api/v1/algorithms/pagerank" and request.method == "POST":
                return httpx.Response(202, json=_job_payload("j-run", "running"))
            if path == "/api/v1/algorithms/jobs/j-run":
                polls.append(1)
                status = "running" if len(polls) < 2 else "succeeded"
                return httpx.Response(200, json=_job_payload("j-run", status))
            if path == "/api/v1/algorithms/jobs/j-run/result":
                return httpx.Response(
                    200,
                    json={
                        "jobId": "j-run",
                        "sink": "csv",
                        "rows": [{"id": "1", "pagerank": "0.9"}],
                        "count": 1,
                        "truncated": False,
                    },
                )
            return httpx.Response(404)

        client = _make_client(handler)
        result = client.run("pagerank", ["Scholar"], max_iter=5, poll_interval_s=0.001)
        assert result.csv_rows == [{"id": "1", "pagerank": "0.9"}]

    def test_run_nebula_sink(self):
        def handler(request):
            path = request.url.path
            if path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            if path == "/api/v1/algorithms/pagerank" and request.method == "POST":
                return httpx.Response(202, json=_job_payload("j-n", "running"))
            if path == "/api/v1/algorithms/jobs/j-n":
                return httpx.Response(200, json=_job_payload("j-n", "succeeded"))
            if path == "/api/v1/algorithms/jobs/j-n/result":
                return httpx.Response(
                    200,
                    json={
                        "jobId": "j-n",
                        "sink": "nebula",
                        "message": "written",
                        "space": "techkg",
                        "tag": "PR",
                    },
                )
            return httpx.Response(404)

        client = _make_client(handler)
        result = client.run("pagerank", ["Scholar"], sink="nebula", tag="PR")
        assert result.message == "written"
        assert result.tag == "PR"

    def test_run_busy_propagates(self):
        def handler(request):
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            return httpx.Response(429, json={"error": "Conflict", "message": "busy"})

        client = _make_client(handler)
        with pytest.raises(AlgorithmJobBusyError):
            client.run("pagerank", ["Scholar"])

    def test_run_failed_propagates(self):
        def handler(request):
            path = request.url.path
            if path == "/health":
                return httpx.Response(200, json={"status": "UP"})
            if path == "/api/v1/algorithms/pagerank" and request.method == "POST":
                return httpx.Response(202, json=_job_payload("j-f", "running"))
            return httpx.Response(200, json=_job_payload("j-f", "failed", error="oom"))

        client = _make_client(handler)
        with pytest.raises(AlgorithmJobFailedError):
            client.run("pagerank", ["Scholar"])


class TestSingleton:
    def test_lazy_singleton_and_close(self, monkeypatch):
        created = []

        class FakeClient:
            def __init__(self, settings):
                self.settings = settings
                self.closed = False
                created.append(self)

            def connect(self):
                pass

            def close(self):
                self.closed = True

        monkeypatch.setattr(graph_pkg, "TRSAlgorithmClient", FakeClient)
        graph_pkg._algo_client = None
        try:
            graph_pkg.get_algorithm_client()
            assert graph_pkg.get_algorithm_client() is created[0]
            assert len(created) == 1

            graph_pkg.close_algorithm_client()
            assert created[0].closed

            graph_pkg.get_algorithm_client()
            assert created[1] is not created[0]
            assert len(created) == 2
        finally:
            graph_pkg.close_algorithm_client()
