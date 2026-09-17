"""图算法作业 service：提交 / 轮询 / 结果获取 + 元数据（边类型、引擎状态）。

所有登录用户可在有权访问的图空间（默认空间、已绑定空间或管理员）提交算法作业；
结果去向 v1 固定 csv（前端表格展示），不暴露 Nebula 回写。
labels 传 EDGE（边类型）名——Spark 侧按边类型构建计算图。
"""

from __future__ import annotations

import logging
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
    """提交算法作业（结果去向固定 csv），返回作业快照。"""
    from infra.graph_db import get_space_algorithm_client

    _ensure_space_access(actor, space)
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
    """查询单个算法作业状态快照。"""
    from infra.graph_db import get_space_algorithm_client

    _ensure_space_access(actor, space)
    try:
        job = get_space_algorithm_client(space).get_job(job_id)
    except Exception as exc:  # noqa: BLE001
        raise _map_error(exc) from exc
    return _job_to_data(job)


def get_result(actor: PlatformActor, space: str, job_id: str) -> dict:
    """获取已成功作业的 csv 结果（rows 为 header→cell 字符串字典列表）。"""
    from infra.graph_db import get_space_algorithm_client

    _ensure_space_access(actor, space)
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
