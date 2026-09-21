"""图算法作业 service 单测（monkeypatch 假图服务，不触真实 Spark）。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from biz.schemas.graph_algorithm import AlgorithmSubmitRequest
from infra.graph_db import AlgorithmJobBusyError
from infra.graph_db.exceptions import GraphNotFoundError, GraphRequestError
from service import graph_algorithm
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


def test_submit_request_defaults_keep_string_vids_and_use_eight_partitions() -> None:
    request = AlgorithmSubmitRequest(space="dev2", algorithm="louvain", labels=["HAS_KEYWORD"])
    assert request.encode_id is True
    assert request.partition_num == 8
    assert request.model_dump(by_alias=True)["partitionNum"] == 8


@pytest.fixture
def algo_backend(monkeypatch):
    graph_algorithm.clear_algo_info_cache()  # 单飞缓存（空间列表/引擎/元数据）不跨用例泄漏
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

        def stats_snapshot(self):
            return {"tags": {}, "edges": {"HAS_KEYWORD": 8, "EMPLOYED_BY": 3}}

        def execute_read(self, query: str, params=None, *, timeout=None):
            if query.startswith("LOOKUP"):
                # 边索引枚举 src/dst：b 出5，a 出2 入1，其余端点各 1 度
                pairs = [("b", f"t{i}") for i in range(1, 6)] + [
                    ("a", "c"),
                    ("a", "c2"),
                    ("d", "a"),
                ]
                return SimpleNamespace(records=[{"s": s, "d": d} for s, d in pairs])
            # MATCH 回退路径（无索引边类型）：按箭头方向区分出度 / 入度
            if "<-[e:" in query:
                return SimpleNamespace(records=[{"vid": "a", "cnt": 1}, {"vid": "c", "cnt": 4}])
            return SimpleNamespace(records=[{"vid": "a", "cnt": 2}, {"vid": "b", "cnt": 5}])

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
    yield SimpleNamespace(submit_calls=submit_calls, algo=algo_client)
    graph_algorithm.clear_algo_info_cache()


def test_ensure_space_access_caches_space_list(monkeypatch) -> None:
    """/metadata 等查询接口高并发下不应每请求打图服务 SHOW SPACES（会话池瓶颈）。"""
    graph_algorithm.clear_algo_info_cache()
    calls = []

    class Session:
        def close(self):
            pass

    class GraphClient:
        def list_spaces(self):
            calls.append(1)
            return ["dev2"]

    monkeypatch.setenv("TRS_GRAPH_SPACE", "dev2")
    monkeypatch.setattr("infra.mysql.create_session", Session)
    monkeypatch.setattr(
        "service.graph_space.GraphSpaceService",
        type(
            "SpaceService",
            (),
            {
                "__init__": lambda self, session: setattr(self, "client", GraphClient()),
                "is_bound": lambda self, user_id, space: False,
            },
        ),
    )
    try:
        graph_algorithm._ensure_space_access(_actor(), "dev2")
        graph_algorithm._ensure_space_access(_actor(), "dev2")
        assert len(calls) == 1  # 第二次命中缓存，未再回源
    finally:
        graph_algorithm.clear_algo_info_cache()


def test_running_snapshot_not_pinned_locally(monkeypatch) -> None:
    """跨 worker 从 Redis 读到 running 快照不得粘滞本地缓存：
    提交 worker 后台写回 succeeded 后，查询 worker 必须立刻可见（否则 409 到 TTL 过期）。"""
    import time

    graph_algorithm.clear_algo_info_cache()
    graph_algorithm._degree_jobs.clear()
    store = {"status": "running"}
    job_id = "job-pinned"

    def fake_load(key):
        return {
            "job_id": key,
            "space": "dev2",
            "labels": ["STUDIED_AT"],
            "rows": [{"vid": "v1", "degree": "3"}],
            "truncated": False,
            "saved_at": time.time(),
            "created_at": "2026-09-21T00:00:00",
            "finished_at": None,
            "error": None,
            "status": store["status"],
        }

    class Session:
        def close(self):
            pass

    class GraphClient:
        def list_spaces(self):
            return ["dev2"]

    monkeypatch.setenv("TRS_GRAPH_SPACE", "dev2")
    monkeypatch.setattr("infra.mysql.create_session", Session)
    monkeypatch.setattr(
        "service.graph_space.GraphSpaceService",
        type(
            "SpaceService",
            (),
            {
                "__init__": lambda self, session: setattr(self, "client", GraphClient()),
                "is_bound": lambda self, user_id, space: False,
            },
        ),
    )
    monkeypatch.setattr(graph_algorithm, "_shared_job_load", fake_load)
    try:
        # ① running 态：result 409，且不得落入本地缓存
        with pytest.raises(GraphAlgorithmError) as exc_info:
            graph_algorithm.get_result(_actor(), "dev2", job_id)
        assert exc_info.value.status_code == 409
        assert job_id not in graph_algorithm._degree_jobs
        # ② Redis 写回 succeeded：同一 worker 立即可取结果
        store["status"] = "succeeded"
        data = graph_algorithm.get_result(_actor(), "dev2", job_id)
        assert data["rows"] == [{"vid": "v1", "degree": "3"}]
    finally:
        graph_algorithm.clear_algo_info_cache()
        graph_algorithm._degree_jobs.clear()


@pytest.mark.parametrize("space", ["shared_business", "bound_private"])
def test_submit_allowed_on_default_and_bound_space(algo_backend, space) -> None:
    data = submit_job(_actor(), space, "pagerank", ["HAS_KEYWORD"], {"maxIter": 10})
    assert data["jobId"] == "job-9"
    assert data["status"] == "running"
    assert len(algo_backend.submit_calls) == 1
    assert algo_backend.submit_calls[0]["encode_id"] is True
    assert algo_backend.submit_calls[0]["partition_num"] == 8


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


def test_degree_via_ngql_returns_merged_result(algo_backend) -> None:
    # degreestatic 不走 Spark（字符串 VID 限制），边索引 LOOKUP 枚举后本地聚合同步算完
    data = submit_job(_actor(), "shared_business", "degreestatic", ["HAS_KEYWORD"], {})
    assert data["status"] == "succeeded"
    assert algo_backend.submit_calls == []  # 未触碰 Spark 提交
    result = get_result(_actor(), "shared_business", data["jobId"])
    # src/dst 对：b→t1..t5（出5），a→c、a→c2（出2），d→a（a 入1）；总度降序，同度按首见序
    assert result["rows"] == [
        {"vid": "b", "out_degree": "5", "in_degree": "0", "degree": "5"},
        {"vid": "a", "out_degree": "2", "in_degree": "1", "degree": "3"},
        *[
            {"vid": v, "out_degree": "0", "in_degree": "1", "degree": "1"}
            for v in ("t1", "t2", "t3", "t4", "t5", "c", "c2")
        ],
        {"vid": "d", "out_degree": "1", "in_degree": "0", "degree": "1"},
    ]
    assert result["count"] == 10
    assert result["truncated"] is False
    job = get_job(_actor(), "shared_business", data["jobId"])
    assert job["status"] == "succeeded"


def test_degree_falls_back_to_match_when_edge_not_indexed(algo_backend, monkeypatch) -> None:
    # 无索引边类型：LOOKUP 报 "no index" → 回退全空间 MATCH 聚合（服务端 count）
    from infra.graph_db.exceptions import GraphRequestError

    class NoIndexGraphClient:
        def edge_types(self):
            return ["HAS_KEYWORD", "EMPLOYED_BY"]

        def stats_snapshot(self):
            return {"tags": {}, "edges": {"HAS_KEYWORD": 8, "EMPLOYED_BY": 3}}

        def execute_read(self, query: str, params=None, *, timeout=None):
            if query.startswith("LOOKUP"):
                raise GraphRequestError(
                    "POST /api/v1/query/read -> 400: There is no index to use at runtime",
                    status_code=400,
                    body="",
                )
            if "<-[e:" in query:
                return SimpleNamespace(records=[{"vid": "a", "cnt": 1}, {"vid": "c", "cnt": 4}])
            return SimpleNamespace(records=[{"vid": "a", "cnt": 2}, {"vid": "b", "cnt": 5}])

    monkeypatch.setattr("infra.graph_db.get_space_client", lambda space: NoIndexGraphClient())
    data = submit_job(_actor(), "shared_business", "degreestatic", ["HAS_KEYWORD"], {})
    assert data["status"] == "succeeded"
    result = get_result(_actor(), "shared_business", data["jobId"])
    # MATCH 聚合：出度 {a:2,b:5}、入度 {a:1,c:4} 合并后按总度降序
    assert result["rows"] == [
        {"vid": "b", "out_degree": "5", "in_degree": "0", "degree": "5"},
        {"vid": "c", "out_degree": "0", "in_degree": "4", "degree": "4"},
        {"vid": "a", "out_degree": "2", "in_degree": "1", "degree": "3"},
    ]
    assert result["count"] == 3


def test_degree_empty_edge_type_skips_scan(algo_backend, monkeypatch) -> None:
    # SHOW STATS 为 0 的边类型（如 dev2 的 ALUMNI）：结果本就为空，不应触发
    # 任何 LOOKUP/MATCH——共享存储饱和窗口实测全空间扫描 28ms 快败
    calls = []

    class EmptyEdgeClient:
        def edge_types(self):
            return ["ALUMNI", "EMPLOYED_BY"]

        def stats_snapshot(self):
            return {"tags": {}, "edges": {"ALUMNI": 0, "EMPLOYED_BY": 3}}

        def execute_read(self, query: str, params=None, *, timeout=None):
            calls.append(query)
            raise AssertionError("无边数据的类型不应触发图查询")

    monkeypatch.setattr("infra.graph_db.get_space_client", lambda space: EmptyEdgeClient())
    data = submit_job(_actor(), "shared_business", "degreestatic", ["ALUMNI"], {})
    assert data["status"] == "succeeded"
    result = get_result(_actor(), "shared_business", data["jobId"])
    assert result["rows"] == []
    assert result["count"] == 0
    assert calls == []


def test_degree_mixed_labels_keep_lookup_and_match_fallback(algo_backend, monkeypatch) -> None:
    # 有索引类型走 LOOKUP、无索引类型仅自身回退 MATCH：有索引的结果不被丢弃
    from infra.graph_db.exceptions import GraphRequestError

    match_queries = []

    class MixedClient:
        def edge_types(self):
            return ["HAS_KEYWORD", "STUDIED_AT"]

        def stats_snapshot(self):
            return {"tags": {}, "edges": {"HAS_KEYWORD": 3, "STUDIED_AT": 92}}

        def execute_read(self, query: str, params=None, *, timeout=None):
            if query.startswith("LOOKUP ON `HAS_KEYWORD`"):
                pairs = [("b", "t1"), ("b", "t2"), ("a", "c")]
                return SimpleNamespace(records=[{"s": s, "d": d} for s, d in pairs])
            if query.startswith("LOOKUP"):
                raise GraphRequestError(
                    "POST /api/v1/query/read -> 400: There is no index to use at runtime",
                    status_code=400,
                    body="",
                )
            match_queries.append(query)
            if "<-[e:" in query:
                return SimpleNamespace(records=[{"vid": "c", "cnt": 3}])
            return SimpleNamespace(records=[{"vid": "a", "cnt": 2}])

    monkeypatch.setattr("infra.graph_db.get_space_client", lambda space: MixedClient())
    data = submit_job(
        _actor(), "shared_business", "degreestatic", ["HAS_KEYWORD", "STUDIED_AT"], {}
    )
    assert data["status"] == "succeeded"
    result = get_result(_actor(), "shared_business", data["jobId"])
    # LOOKUP：b 出2、a 出1；MATCH 回退（仅 STUDIED_AT）：a 再出2、c 入3
    assert result["rows"] == [
        {"vid": "c", "out_degree": "0", "in_degree": "4", "degree": "4"},
        {"vid": "a", "out_degree": "3", "in_degree": "0", "degree": "3"},
        {"vid": "b", "out_degree": "2", "in_degree": "0", "degree": "2"},
        {"vid": "t1", "out_degree": "0", "in_degree": "1", "degree": "1"},
        {"vid": "t2", "out_degree": "0", "in_degree": "1", "degree": "1"},
    ]
    # MATCH 只覆盖无索引类型，不再拖上有索引的 HAS_KEYWORD
    assert len(match_queries) == 2
    assert all("STUDIED_AT" in q and "HAS_KEYWORD" not in q for q in match_queries)


def test_degree_unknown_label_rejected(algo_backend) -> None:
    with pytest.raises(GraphAlgorithmError) as exc_info:
        submit_job(_actor(), "shared_business", "degreestatic", ["NOT_AN_EDGE"], {})
    assert "不存在边类型" in str(exc_info.value)
    assert algo_backend.submit_calls == []


def test_list_edge_types(algo_backend) -> None:
    # Schema 目录不可读（假 Session 无 query）→ 回退图库 SHOW EDGES
    assert list_edge_types(_actor(), "shared_business") == ["HAS_KEYWORD", "EMPLOYED_BY"]


def test_list_edge_types_prefers_schema_catalog(algo_backend, monkeypatch) -> None:
    # 目录顺序即展示顺序；不在图库中的目录项（COAUTHOR_WITH）被过滤
    monkeypatch.setattr(
        "service.graph_algorithm._relation_schema_keys",
        lambda space: ["EMPLOYED_BY", "COAUTHOR_WITH"],
    )
    assert list_edge_types(_actor(), "shared_business") == ["EMPLOYED_BY"]


def test_list_edge_types_disjoint_catalog_falls_back(algo_backend, monkeypatch) -> None:
    # 目录与图库完全无交集：回退完整图库列表，避免有目录反而看不到边类型
    monkeypatch.setattr(
        "service.graph_algorithm._relation_schema_keys",
        lambda space: ["COAUTHOR_WITH", "CITES"],
    )
    assert list_edge_types(_actor(), "shared_business") == ["HAS_KEYWORD", "EMPLOYED_BY"]


def test_list_edge_types_falls_back_when_catalog_empty(algo_backend, monkeypatch) -> None:
    monkeypatch.setattr("service.graph_algorithm._relation_schema_keys", lambda space: [])
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


@pytest.mark.parametrize("fail", [False, True])
def test_degree_returns_running_before_background_computation(algo_backend, monkeypatch, fail):
    from fastapi import BackgroundTasks

    from service.graph_algorithm import _run_degree_job

    tasks = BackgroundTasks()
    data = submit_job(
        _actor(), "shared_business", "degreestatic", ["HAS_KEYWORD"], {}, background_tasks=tasks
    )
    assert data["status"] == "running"
    assert data["finishedAt"] is None
    assert get_job(_actor(), "shared_business", data["jobId"])["status"] == "running"
    with pytest.raises(GraphAlgorithmError) as exc:
        get_result(_actor(), "shared_business", data["jobId"])
    assert exc.value.status_code == 409
    if fail:

        def reject(*args):
            raise RuntimeError("graph offline")

        monkeypatch.setattr("service.graph_algorithm._degree_rows_via_ngql", reject)
    task = tasks.tasks[0]
    _run_degree_job(*task.args)
    job = get_job(_actor(), "shared_business", data["jobId"])
    assert job["status"] == ("failed" if fail else "succeeded")
    assert job["finishedAt"]
    if fail:
        assert "graph offline" in job["error"]
    else:
        assert get_result(_actor(), "shared_business", data["jobId"])["count"] == 10
