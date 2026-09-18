"""图算法作业 service：提交 / 轮询 / 结果获取 + 元数据（边类型、引擎状态）。

所有登录用户可在有权访问的图空间（默认空间、已绑定空间或管理员）提交算法作业；
结果去向 v1 固定 csv（前端表格展示），不暴露 Nebula 回写。
labels 传 EDGE（边类型）名——Spark 侧按边类型构建计算图。
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from service.platform_access import PlatformActor

logger = logging.getLogger(__name__)


class GraphAlgorithmError(Exception):
    """算法作业被拒绝或执行失败（message 直接作为 API detail）。"""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _ensure_space_access(actor: PlatformActor, space: str) -> None:
    """空间合法性与归属校验：必须存在于图服务，且为默认空间/已绑定/管理员。"""
    from service.graph_space import (
        SPACE_NAME_PATTERN,
        GraphSpaceError,
        GraphSpaceService,
        default_graph_space,
    )

    if not SPACE_NAME_PATTERN.fullmatch(space or ""):
        raise GraphAlgorithmError("图空间名称不合法")

    try:
        from infra.mysql import create_session

        session = create_session()
        try:
            space_service = GraphSpaceService(session)
            spaces = space_service.client.list_spaces()
            space_allowed = (
                actor.is_admin
                or space == default_graph_space()
                or space_service.is_bound(actor.user_id, space)
            )
        finally:
            session.close()
    except GraphSpaceError as exc:
        raise GraphAlgorithmError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.warning("图算法列空间失败: %s", exc)
        raise GraphAlgorithmError(f"图服务不可用: {exc}") from exc
    if space not in spaces:
        raise GraphAlgorithmError(f"图空间 {space} 不存在")
    if not space_allowed:
        raise GraphAlgorithmError("无权访问未绑定的图空间", status_code=403)


def _map_error(exc: Exception) -> GraphAlgorithmError:
    """把算法客户端异常映射为带中文提示的业务错误（绝不漏成全局裸 502）。"""
    from infra.graph_db import AlgorithmJobBusyError
    from infra.graph_db.exceptions import (
        GraphConnectionError,
        GraphNotFoundError,
        GraphRequestError,
    )

    if isinstance(exc, GraphAlgorithmError):
        return exc
    if isinstance(exc, AlgorithmJobBusyError):
        return GraphAlgorithmError(
            "算法引擎已有作业在运行（同时仅允许一个作业），请稍后重试", status_code=429
        )
    if isinstance(exc, GraphConnectionError):
        return GraphAlgorithmError("算法服务不可用，请稍后重试", status_code=502)
    if isinstance(exc, GraphNotFoundError):
        return GraphAlgorithmError("算法作业不存在或结果已过期", status_code=404)
    if isinstance(exc, GraphRequestError):
        if exc.status_code == 502:
            return GraphAlgorithmError("算法引擎暂时不可用（Spark 运行器未就绪），请稍后重试", 502)
        return GraphAlgorithmError(f"算法引擎请求失败: {exc}", status_code=502)
    if isinstance(exc, ValueError):
        return GraphAlgorithmError(f"算法参数不合法: {exc}")
    return GraphAlgorithmError(f"算法作业执行失败: {exc}", status_code=502)


def _job_to_data(job: Any) -> dict:
    """AlgorithmJob dataclass → camelCase 快照。"""
    return {
        "jobId": job.job_id,
        "status": job.status,
        "createdAt": job.created_at,
        "startedAt": job.started_at,
        "finishedAt": job.finished_at,
        "submissionId": job.submission_id,
        "driverState": job.driver_state,
        "error": job.error,
        "logTail": job.log_tail,
    }


# ---------- Degree：nGQL 同步计算（绕开 Spark 对字符串 VID 的限制） ----------
# nebula-algorithm 3.1.0 的 DegreeStatic 加载边数据时不消费 encodeId，字符串 VID
# （如 "paper_…"）直接 Long.parseLong 抛 NumberFormatException；同图的 PageRank /
# Louvain 正常。度数本就是图库原生聚合能力：这里用 nGQL 出/入度聚合同步算完，
# 包装成与 Spark 作业一致的 job / result 模型（前端零改动），也不受算法引擎
# "同一时刻仅允许一个作业"的并发限制。
_DEGREE_JOB_TTL_SECONDS = 30 * 60
_DEGREE_JOB_CAPACITY = 50
_DEGREE_RESULT_LIMIT = 10_000
_degree_jobs: dict[str, dict[str, Any]] = {}
_degree_jobs_lock = threading.Lock()


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _save_degree_job(
    space: str, labels: list[str], rows: list[dict[str, str]], truncated: bool
) -> dict[str, Any]:
    """本地登记 Degree 作业（同步计算，入表即 succeeded）并返回快照；顺手清理过期/超量条目。"""
    job_id = uuid.uuid4().hex
    now = _utc_now_iso()
    job = {
        "job_id": job_id,
        "space": space,
        "labels": list(labels),
        "rows": rows,
        "truncated": truncated,
        "saved_at": time.time(),
        "created_at": now,
    }
    with _degree_jobs_lock:
        expired = [
            key
            for key, stored in _degree_jobs.items()
            if time.time() - stored["saved_at"] > _DEGREE_JOB_TTL_SECONDS
        ]
        for key in expired:
            del _degree_jobs[key]
        while len(_degree_jobs) >= _DEGREE_JOB_CAPACITY:
            del _degree_jobs[min(_degree_jobs, key=lambda key: _degree_jobs[key]["saved_at"])]
        _degree_jobs[job_id] = job
    return job


def _local_degree_job(space: str, job_id: str) -> dict[str, Any] | None:
    """按 jobId 取本地 Degree 作业；不存在 / 已过期 / 空间不匹配返回 None（走图服务）。"""
    with _degree_jobs_lock:
        job = _degree_jobs.get(job_id)
        if job is None or job["space"] != space:
            return None
        if time.time() - job["saved_at"] > _DEGREE_JOB_TTL_SECONDS:
            del _degree_jobs[job_id]
            return None
        return job


def _local_job_to_data(job: dict[str, Any]) -> dict:
    """本地 Degree 作业 → 与 Spark 作业一致的 camelCase 快照。"""
    return {
        "jobId": job["job_id"],
        "status": "succeeded",
        "createdAt": job["created_at"],
        "startedAt": job["created_at"],
        "finishedAt": job["created_at"],
        "submissionId": None,
        "driverState": None,
        "error": None,
        "logTail": None,
    }


def _degree_rows_via_ngql(space: str, labels: list[str]) -> tuple[list[dict[str, str]], bool]:
    """nGQL 出/入度聚合并合并为逐顶点行（总度降序，上限对齐图服务 10000 行截断）。"""
    from infra.graph_db import get_space_client

    client = get_space_client(space)
    known = set(client.edge_types())
    unknown = [label for label in labels if label not in known]
    if unknown:
        raise GraphAlgorithmError(f"图空间 {space} 不存在边类型: {', '.join(unknown)}")
    edge_expr = "|".join(labels)
    # MATCH 聚合在图库服务端完成，只回传逐顶点计数；两个方向分别查后按 vid 合并
    out_result = client.execute_read(
        f"MATCH (v)-[e:{edge_expr}]->(v2) RETURN id(v) AS vid, count(e) AS cnt"
    )
    in_result = client.execute_read(
        f"MATCH (v)<-[e:{edge_expr}]-(v2) RETURN id(v) AS vid, count(e) AS cnt"
    )
    degrees: dict[str, dict[str, int]] = {}

    def absorb(records: list[dict[str, Any]], field: str) -> None:
        for record in records:
            vid = str(record.get("vid") or "")
            if not vid:
                continue
            entry = degrees.setdefault(vid, {"out": 0, "in": 0})
            try:
                entry[field] += int(record.get("cnt") or 0)
            except (TypeError, ValueError):
                continue

    absorb(out_result.records, "out")
    absorb(in_result.records, "in")
    ordered = sorted(degrees.items(), key=lambda item: item[1]["out"] + item[1]["in"], reverse=True)
    truncated = len(ordered) > _DEGREE_RESULT_LIMIT
    rows = [
        {
            "vid": vid,
            "out_degree": str(entry["out"]),
            "in_degree": str(entry["in"]),
            "degree": str(entry["out"] + entry["in"]),
        }
        for vid, entry in ordered[:_DEGREE_RESULT_LIMIT]
    ]
    return rows, truncated


def _submit_degree_via_ngql(space: str, labels: list[str]) -> dict:
    """同步计算 Degree 并登记本地作业，返回 succeeded 快照（失败直接抛业务错误）。"""
    try:
        rows, truncated = _degree_rows_via_ngql(space, labels)
    except GraphAlgorithmError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("Degree nGQL 计算失败: %s", exc)
        raise GraphAlgorithmError(f"度数计算失败: {exc}", status_code=502) from exc
    return _local_job_to_data(_save_degree_job(space, labels, rows, truncated))


def submit_job(
    actor: PlatformActor,
    space: str,
    algorithm: str,
    labels: list[str],
    params: dict[str, Any],
    *,
    has_weight: bool = False,
    weight_cols: list[str] | None = None,
    encode_id: bool = True,
    partition_num: int = 1,
) -> dict:
    """提交算法作业（结果去向固定 csv），返回作业快照。

    degreestatic 例外：Spark 侧不支持字符串 VID，改走 nGQL 同步计算
    （见 _submit_degree_via_ngql），同样返回作业快照，前端轮询模型不变。
    """
    _ensure_space_access(actor, space)
    if algorithm == "degreestatic":
        return _submit_degree_via_ngql(space, labels)

    from infra.graph_db import get_space_algorithm_client

    try:
        client = get_space_algorithm_client(space)
        job = client.submit(
            algorithm,
            labels,
            sink="csv",
            tag=None,
            write_type="update",
            weight_cols=weight_cols,
            has_weight=has_weight,
            encode_id=encode_id,
            partition_num=partition_num,
            **params,
        )
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc) from exc
    return _job_to_data(job)


def get_job(actor: PlatformActor, space: str, job_id: str) -> dict:
    """查询单个算法作业状态快照（本地 Degree 作业优先，其余走图服务）。"""
    from infra.graph_db import get_space_algorithm_client

    _ensure_space_access(actor, space)
    local = _local_degree_job(space, job_id)
    if local is not None:
        return _local_job_to_data(local)
    try:
        job = get_space_algorithm_client(space).get_job(job_id)
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc) from exc
    return _job_to_data(job)


def get_result(actor: PlatformActor, space: str, job_id: str) -> dict:
    """获取已成功作业的 csv 结果（rows 为 header→cell 字符串字典列表）。"""
    from infra.graph_db import get_space_algorithm_client

    _ensure_space_access(actor, space)
    local = _local_degree_job(space, job_id)
    if local is not None:
        return {
            "jobId": local["job_id"],
            "sink": "csv",
            "rows": [dict(row) for row in local["rows"]],
            "count": len(local["rows"]),
            "truncated": local["truncated"],
        }
    try:
        result = get_space_algorithm_client(space).get_result(job_id)
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc) from exc
    data: dict[str, Any] = {
        "jobId": result.job_id,
        "sink": result.sink,
        "rows": [dict(row) for row in result.rows],
    }
    if result.count is not None:
        data["count"] = result.count
    if result.truncated is not None:
        data["truncated"] = result.truncated
    return data


def _relation_schema_keys(space: str) -> list[str]:
    """读 MySQL Schema 目录（kg_schema_definition）中该空间的关系类型。

    与 Schema 管理页同源：按 graph_space 过滤、只取 kind=relation、剔除软删，
    展示顺序沿用目录的 display_order。注意取 name 列——它是 DDL 落到图库的
    EDGE 类型名（schema_key 只是 UI slug，kebab-case，与图库边名不一致）；
    仅取 ddl_status=succeeded，未落库的类型提交算法只会得到空结果。
    读取失败（库不可用等）返回空列表，由调用方回退图库 SHOW EDGES。
    """
    try:
        from sqlalchemy import select

        from db_model.schema_management import GraphSchemaDefinition
        from infra.mysql import create_session

        session = create_session()
        try:
            rows = session.execute(
                select(GraphSchemaDefinition.name)
                .where(
                    GraphSchemaDefinition.graph_space == space,
                    GraphSchemaDefinition.kind == "relation",
                    GraphSchemaDefinition.is_deleted.is_(False),
                    GraphSchemaDefinition.ddl_status == "succeeded",
                )
                .order_by(
                    GraphSchemaDefinition.display_order.asc(),
                    GraphSchemaDefinition.name.asc(),
                )
            ).all()
            return [name for (name,) in rows if name]
        finally:
            session.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("图算法读 Schema 目录失败，回退图库 SHOW EDGES: %s", exc)
        return []


def list_edge_types(actor: PlatformActor, space: str) -> list[str]:
    """列出空间内的关系类型（算法 labels 的取值来源）。

    以图库 SHOW EDGES 为准（保证类型真实存在、提交算法不空跑），当该空间
    在 MySQL Schema 目录中有建模时，用目录做策展：只保留目录中的类型并按
    目录顺序排序——过滤测试遗留/空壳边类型。目录为空（空间未在 Schema
    管理建模）或与图库完全无交集时，回退完整图库边类型列表。
    """
    from infra.graph_db import get_space_client

    _ensure_space_access(actor, space)
    try:
        graph_types = list(get_space_client(space).edge_types())
    except Exception as exc:  # noqa: BLE001
        logger.warning("图算法列边类型失败: %s", exc)
        raise GraphAlgorithmError(f"获取边类型失败: {exc}", status_code=502) from exc

    catalog = _relation_schema_keys(space)
    if not catalog:
        return graph_types
    graph_set = set(graph_types)
    curated = [name for name in catalog if name in graph_set]
    # 目录与图库完全脱节（目录归属与 DDL 实际落点不一致等）：不裁剪，
    # 避免有目录反而看不到任何边类型
    return curated or graph_types


def engine_status(actor: PlatformActor, space: str) -> dict:
    """算法引擎（Spark 运行器）健康状态；探测失败一律降级为 DOWN，不向上抛。"""
    from infra.graph_db import get_space_algorithm_client

    _ensure_space_access(actor, space)
    try:
        health = get_space_algorithm_client(space).health()
        return {"status": "UP", "activeJobs": health.get("activeJobs")}
    except Exception as exc:  # noqa: BLE001
        logger.warning("图算法引擎探测失败: %s", exc)
        return {"status": "DOWN", "activeJobs": None, "message": str(_map_error(exc))}


def metadata(actor: PlatformActor, space: str) -> dict:
    """边类型 + 引擎状态聚合；引擎探测失败仅降级，不阻塞边类型返回。"""
    return {
        "edgeTypes": list_edge_types(actor, space),
        "engine": engine_status(actor, space),
    }
