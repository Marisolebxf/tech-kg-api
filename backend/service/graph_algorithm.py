"""图算法作业 service：提交 / 轮询 / 结果获取 + 元数据（边类型、引擎状态）。

所有登录用户可在有权访问的图空间（默认空间、已绑定空间或管理员）提交算法作业；
结果去向 v1 固定 csv（前端表格展示），不暴露 Nebula 回写。
labels 传 EDGE（边类型）名——Spark 侧按边类型构建计算图。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

import redis as redis_lib

from service.platform_access import PlatformActor

logger = logging.getLogger(__name__)


# 空间列表短 TTL 缓存：查询类接口（元数据/引擎状态/作业状态/结果）每请求都过
# _ensure_space_access，实时 SHOW SPACES 在高并发下会打满图服务会话池
# （2026-09-21 用例08 500 并发实测 6.5% 400/502）。空间列表低频变化，进程内缓存即可。
_SPACE_LIST_TTL_SECONDS = float(os.getenv("GRAPH_ALGO_SPACE_LIST_CACHE_SECONDS", "60"))


def _list_spaces_cached(fetch: Any) -> list[str]:
    """空间列表走统一单飞缓存（key="spaces"，随 clear_algo_info_cache 一并清空）。"""
    return _single_flight_cache("spaces", _SPACE_LIST_TTL_SECONDS, fetch)


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
            spaces = _list_spaces_cached(space_service.client.list_spaces)
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


# ---------- Degree：nGQL 后台计算（绕开 Spark 对字符串 VID 的限制） ----------
# nebula-algorithm 3.1.0 的 DegreeStatic 加载边数据时不消费 encodeId，字符串 VID
# （如 "paper_…"）直接 Long.parseLong 抛 NumberFormatException；同图的 PageRank /
# Louvain 正常。度数本就是图库原生聚合能力：这里用 nGQL 出/入度聚合同步算完，
# 包装成与 Spark 作业一致的 job / result 模型（前端零改动），也不受算法引擎
# "同一时刻仅允许一个作业"的并发限制。
_DEGREE_JOB_TTL_SECONDS = 30 * 60

# 作业快照跨 worker 共享：8 worker 部署下，提交与查询会落在不同进程，
# 纯进程内存会让其余 worker 查询 404（2026-09-20 用例 10 实测 95% 404）。
# 快照同步写 Redis（与 auth 会话共用实例，键前缀隔离），TTL 与本地一致。
_ALGO_JOB_REDIS_PREFIX = "algo:degree_job:"
_algo_redis_client: redis_lib.Redis | None = None
_algo_redis_lock = threading.Lock()


def _shared_redis() -> redis_lib.Redis:
    global _algo_redis_client
    with _algo_redis_lock:
        if _algo_redis_client is None:
            url = os.getenv("REDIS_URL", "redis://auth-redis:6379/0")
            _algo_redis_client = redis_lib.Redis.from_url(url, decode_responses=True)
        return _algo_redis_client


def _shared_job_save(job_id: str, job: dict) -> None:
    try:
        _shared_redis().set(
            _ALGO_JOB_REDIS_PREFIX + job_id,
            json.dumps(job, ensure_ascii=False, default=str),
            ex=_DEGREE_JOB_TTL_SECONDS,
        )
    except Exception:  # noqa: BLE001 — Redis 不可用时不影响本地作业
        logging.getLogger(__name__).warning("算法作业快照写 Redis 失败", exc_info=True)


def _shared_job_load(job_id: str) -> dict | None:
    raw = None
    for attempt in range(2):  # 高压下 Redis 瞬时抖动重试一次
        try:
            raw = _shared_redis().get(_ALGO_JOB_REDIS_PREFIX + job_id)
            break
        except Exception:  # noqa: BLE001
            if attempt == 0:
                time.sleep(0.05)
    if not raw:
        return None
    if not raw:
        return None
    try:
        job = json.loads(raw)
    except ValueError:
        return None
    return job if isinstance(job, dict) else None


_DEGREE_JOB_CAPACITY = 50
_DEGREE_RESULT_LIMIT = 10_000
_DEGREE_LOOKUP_PAGE_SIZE = max(
    1, min(int(os.getenv("GRAPH_ALGO_DEGREE_LOOKUP_PAGE_SIZE", "5000")), 10_000)
)
_DEGREE_INDEX_BUILD_TIMEOUT_SECONDS = float(
    os.getenv("GRAPH_ALGO_DEGREE_INDEX_BUILD_TIMEOUT_SECONDS", "300")
)
_DEGREE_INDEX_POLL_SECONDS = float(os.getenv("GRAPH_ALGO_DEGREE_INDEX_POLL_SECONDS", "2"))
_degree_jobs: dict[str, dict[str, Any]] = {}
_degree_jobs_lock = threading.Lock()


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _save_degree_job(
    space: str,
    labels: list[str],
    rows: list[dict[str, str]],
    truncated: bool,
    *,
    running: bool = False,
) -> dict[str, Any]:
    """登记 Degree 作业并清理过期结果；后台计算最多同时运行两个。"""

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
        "status": "running" if running else "succeeded",
        "finished_at": None if running else now,
        "error": None,
    }
    with _degree_jobs_lock:
        if running and sum(stored["status"] == "running" for stored in _degree_jobs.values()) >= 2:
            raise GraphAlgorithmError("度数计算已有两个作业运行中，请稍后重试", status_code=429)
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
    _shared_job_save(job_id, job)
    return job


def _local_degree_job(space: str, job_id: str) -> dict[str, Any] | None:
    """按 jobId 取本地 Degree 作业；本地未命中时尝试 Redis 共享快照
    （跨 worker：提交与查询可能落在不同进程）。
    不存在 / 已过期 / 空间不匹配返回 None（走图服务）。"""
    with _degree_jobs_lock:
        job = _degree_jobs.get(job_id)
        if job is not None:
            if job["space"] != space:
                return None
            if time.time() - job["saved_at"] > _DEGREE_JOB_TTL_SECONDS:
                del _degree_jobs[job_id]
                return None
            return job
    shared = _shared_job_load(job_id)
    if shared is not None and shared.get("space") == space:
        # 仅终态快照可落本地缓存：running 态若被缓存，本 worker 会拿着旧状态
        # 一直 409 到 TTL 过期（提交 worker 后台写回 succeeded 也不会同步过来）。
        if shared.get("status") != "running":
            with _degree_jobs_lock:
                _degree_jobs.setdefault(job_id, shared)
        return shared
    return None


def _local_job_to_data(job: dict[str, Any]) -> dict:
    """本地 Degree 作业 → 与 Spark 作业一致的 camelCase 快照。"""
    return {
        "jobId": job["job_id"],
        "status": job["status"],
        "createdAt": job["created_at"],
        "startedAt": job["created_at"],
        "finishedAt": job["finished_at"],
        "submissionId": None,
        "driverState": None,
        "error": job["error"],
        "logTail": None,
    }


def _degree_index_name(label: str) -> str:
    """生成稳定、合法且长度受控的 Degree 专用 EDGE 索引名。"""
    digest = hashlib.sha1(label.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
    return f"degree_{label.lower()[:40]}_{digest}_idx"


def _is_missing_index_error(exc: Exception) -> bool:
    message = str(exc).lower()
    # NebulaGraph 的真实错误会把索引名插在 Index 与 not found 之间，例如：
    # "Index degree_has_keyword_..._idx not found in space dev2"。
    return "no index" in message or ("index" in message and "not found" in message)


def _is_transient_index_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return _is_missing_index_error(exc) or any(
        marker in message for marker in ("does not exist", "not ready", "building", "running")
    )


def _is_index_building_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        marker in message
        for marker in ("already rebuilding", "is rebuilding", "in progress", "job is running")
    )


def _lookup_degree_pairs(client: Any, label: str) -> Iterable[tuple[str, str]]:
    """通过边索引分页枚举端点，避免单次返回过大及无索引全空间 MATCH。"""
    offset = 0
    while True:
        result = client.execute_read(
            f"LOOKUP ON `{label}` YIELD src(edge) AS s, dst(edge) AS d "
            f"| LIMIT {_DEGREE_LOOKUP_PAGE_SIZE} OFFSET {offset}",
            timeout=90.0,
        )
        records = [record for record in (result.records or []) if isinstance(record, dict)]
        for record in records:
            yield str(record.get("s") or ""), str(record.get("d") or "")
        if len(records) < _DEGREE_LOOKUP_PAGE_SIZE:
            return
        offset += len(records)


def _degree_edge_index_status(client: Any, index_name: str) -> str | None:
    """读取 Degree 专用边索引最近一次重建状态。"""
    result = client.execute_read("SHOW EDGE INDEX STATUS", timeout=30.0)
    for record in result.records or []:
        if not isinstance(record, dict):
            continue
        normalized = {
            str(key).strip().lower().replace("_", " "): value for key, value in record.items()
        }
        name = str(normalized.get("name") or "").strip("\"'`")
        if name != index_name:
            continue
        return str(normalized.get("index status") or "").strip("\"'`").upper() or None
    return None


def _ensure_degree_edge_index(client: Any, label: str) -> None:
    """为无索引边类型创建并重建 Degree 专用索引，等待到 LOOKUP 可用。

    Degree 在 FastAPI BackgroundTasks 中运行，索引重建期间前端保持 running；
    不再回退两次全空间 MATCH，从根源上避免共享图库 90 秒扫描超时。
    """
    from infra.graph_db.exceptions import GraphRequestError

    index_name = _degree_index_name(label)
    deadline = time.monotonic() + _DEGREE_INDEX_BUILD_TIMEOUT_SECONDS
    try:
        client.execute_write(f"CREATE EDGE INDEX IF NOT EXISTS `{index_name}` ON `{label}`()")
    except Exception as exc:  # noqa: BLE001
        raise GraphAlgorithmError(
            f"关系类型 {label} 缺少边索引，自动创建索引失败: {exc}", status_code=502
        ) from exc

    # CREATE DDL 需要短暂传播；并发 worker 可能发现同一索引已在重建，均转入可用性轮询。
    while True:
        try:
            client.execute_write(f"REBUILD EDGE INDEX `{index_name}`")
            break
        except GraphRequestError as exc:
            # 另一 worker 已触发相同索引的重建时，不再重复提交，直接等待可用。
            if _is_index_building_error(exc):
                break
            if not _is_transient_index_error(exc):
                raise GraphAlgorithmError(
                    f"关系类型 {label} 的索引 {index_name} 重建失败: {exc}", status_code=502
                ) from exc
            if time.monotonic() >= deadline:
                raise GraphAlgorithmError(
                    f"关系类型 {label} 的索引 {index_name} 在创建后未及时可见，请稍后重试",
                    status_code=504,
                ) from exc
            time.sleep(_DEGREE_INDEX_POLL_SECONDS)

    while True:
        try:
            status = _degree_edge_index_status(client, index_name)
            if status in {"FAILED", "STOPPED", "INVALID"}:
                raise GraphAlgorithmError(
                    f"关系类型 {label} 的索引 {index_name} 重建状态为 {status}",
                    status_code=502,
                )
            if status != "FINISHED":
                if time.monotonic() >= deadline:
                    raise GraphAlgorithmError(
                        f"关系类型 {label} 的索引 {index_name} 重建超过 "
                        f"{int(_DEGREE_INDEX_BUILD_TIMEOUT_SECONDS)} 秒，请稍后重试",
                        status_code=504,
                    )
                time.sleep(_DEGREE_INDEX_POLL_SECONDS)
                continue
            # FINISHED 后再确认 LOOKUP 已可用；空结果也是合法结果。
            client.execute_read(f"LOOKUP ON `{label}` YIELD src(edge) AS s | LIMIT 1", timeout=30.0)
            logger.info("Degree 边索引已可用: label=%s index=%s", label, index_name)
            return
        except GraphRequestError as exc:
            if not _is_transient_index_error(exc):
                raise GraphAlgorithmError(
                    f"关系类型 {label} 的索引 {index_name} 校验失败: {exc}", status_code=502
                ) from exc
            if time.monotonic() >= deadline:
                raise GraphAlgorithmError(
                    f"关系类型 {label} 的索引 {index_name} 重建超过 "
                    f"{int(_DEGREE_INDEX_BUILD_TIMEOUT_SECONDS)} 秒，请稍后重试",
                    status_code=504,
                ) from exc
            time.sleep(_DEGREE_INDEX_POLL_SECONDS)


def _degree_rows_via_ngql(space: str, labels: list[str]) -> tuple[list[dict[str, str]], bool]:
    """出/入度聚合并合并为逐顶点行（总度降序，上限对齐图服务 10000 行截断）。

    逐类型通过边索引分页 LOOKUP 枚举 src/dst 并本地聚合：代价只跟该边类型
    的边数相关。若关系类型尚无索引，或索引已创建但历史数据尚未重建进去，
    则自动创建/重建 Degree 专用空属性索引，并等待 SHOW EDGE INDEX STATUS
    返回 FINISHED 后继续；绝不回退全空间 MATCH，避免 CITES 等大边类型扫描
    90 秒超时拖垮共享图库。SHOW STATS 可能滞后，不能据其 0 值跳过真实数据。
    """
    from infra.graph_db import get_space_client
    from infra.graph_db.exceptions import GraphRequestError

    client = get_space_client(space)
    known = set(client.edge_types())
    unknown = [label for label in labels if label not in known]
    if unknown:
        raise GraphAlgorithmError(f"图空间 {space} 不存在边类型: {', '.join(unknown)}")

    degrees: dict[str, dict[str, int]] = {}

    def absorb_pairs(pairs: Iterable[tuple[str, str]]) -> None:
        for src, dst in pairs:
            if not src or not dst:
                continue
            degrees.setdefault(src, {"out": 0, "in": 0})["out"] += 1
            degrees.setdefault(dst, {"out": 0, "in": 0})["in"] += 1

    for label in labels:
        try:
            pairs = _lookup_degree_pairs(client, label)
            # 生成器在迭代时才发请求，先取首项以便捕获无索引错误后自动补建。
            first = next(pairs, None)
        except GraphRequestError as exc:
            if not _is_missing_index_error(exc):
                raise
            _ensure_degree_edge_index(client, label)
            pairs = _lookup_degree_pairs(client, label)
            first = next(pairs, None)
        if first is None:
            # CREATE 成功但 REBUILD 未启动时，LOOKUP 会“成功返回 0 行”。只有本专用
            # 索引最近一次重建已 FINISHED，才能把空结果视为真实无边数据。
            index_name = _degree_index_name(label)
            if _degree_edge_index_status(client, index_name) != "FINISHED":
                _ensure_degree_edge_index(client, label)
                pairs = _lookup_degree_pairs(client, label)
                first = next(pairs, None)
        if first is not None:
            absorb_pairs((first,))
            absorb_pairs(pairs)

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


def _run_degree_job(job: dict[str, Any]) -> None:
    """后台执行计算，成功和失败均更新同一个可轮询作业。"""
    try:
        rows, truncated = _degree_rows_via_ngql(job["space"], job["labels"])
        with _degree_jobs_lock:
            job.update(rows=rows, truncated=truncated, status="succeeded")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Degree 后台计算失败: %s", exc)
        with _degree_jobs_lock:
            job.update(status="failed", error=f"度数计算失败: {exc}")
    finally:
        with _degree_jobs_lock:
            job.update(finished_at=_utc_now_iso(), saved_at=time.time())
        _shared_job_save(job["job_id"], job)


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
    partition_num: int = 8,
    background_tasks: Any = None,
) -> dict:
    """提交算法作业（结果去向固定 csv），返回作业快照。

    degreestatic 使用 nGQL 计算；HTTP 传入 background_tasks 时先返回 running，
    后台计算后通过相同轮询接口获取终态。直接 service 调用保留同步兼容。
    """
    _ensure_space_access(actor, space)
    if algorithm == "degreestatic":
        if background_tasks is None:
            return _submit_degree_via_ngql(space, labels)
        # HTTP 请求先返回 running，避免原生聚合阻塞提交及触发前端超时。
        job = _save_degree_job(space, labels, [], False, running=True)
        background_tasks.add_task(_run_degree_job, job)
        return _local_job_to_data(job)

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
        if local["status"] != "succeeded":
            raise GraphAlgorithmError("作业尚未成功完成，暂不可获取结果", status_code=409)
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
    """算法引擎（Spark 运行器）健康状态；探测失败一律降级为 DOWN，不向上抛。
    结果按 space 缓存 GRAPH_ALGO_INFO_CACHE_SECONDS（默认 60s）：500 并发下
    逐请求探测 runner/Nebula 会耗尽会话池。"""
    return _single_flight_cache(
        f"engine:{space}", _ALGO_INFO_CACHE_SECONDS, lambda: _engine_status_uncached(actor, space)
    )


def _engine_status_uncached(actor: PlatformActor, space: str) -> dict:
    from infra.graph_db import get_space_algorithm_client

    _ensure_space_access(actor, space)
    try:
        health = get_space_algorithm_client(space).health()
        return {"status": "UP", "activeJobs": health.get("activeJobs")}
    except Exception as exc:  # noqa: BLE001
        logger.warning("图算法引擎探测失败: %s", exc)
        return {"status": "DOWN", "activeJobs": None, "message": str(_map_error(exc))}


_ALGO_INFO_CACHE_SECONDS = float(os.getenv("GRAPH_ALGO_INFO_CACHE_SECONDS", "60"))
_algo_info_cache: dict[str, tuple[float, dict]] = {}
_algo_info_lock = threading.Lock()
_algo_fetch_locks: dict[str, threading.Lock] = {}


def _single_flight_cache(key: str, ttl: float, fetch: Any) -> Any:
    """进程内 TTL 缓存 + 同 key 单飞回源：命中直接返回；过期时同一 key 仅放行
    一个线程回源（期间其余线程短暂等待），避免高并发下缓存过期瞬间的回源
    风暴打满图服务会话池（2026-09-21 用例08 500 并发实测）。"""
    with _algo_info_lock:
        cached = _algo_info_cache.get(key)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        fetch_lock = _algo_fetch_locks.setdefault(key, threading.Lock())
    with fetch_lock:
        # 拿到回源锁后再查一次：等锁期间别的线程可能已写回缓存
        with _algo_info_lock:
            cached = _algo_info_cache.get(key)
            if cached and cached[0] > time.monotonic():
                return cached[1]
        value = fetch()
        with _algo_info_lock:
            _algo_info_cache[key] = (time.monotonic() + ttl, value)
        return value


def metadata(actor: PlatformActor, space: str) -> dict:
    """边类型 + 引擎状态聚合；引擎探测失败仅降级，不阻塞边类型返回。
    结果按 space 缓存 GRAPH_ALGO_INFO_CACHE_SECONDS（默认 60s）；
    Schema 新建/删除关系（EDGE 类型变更）时会主动清缓存。"""
    return _single_flight_cache(
        f"meta:{space}",
        _ALGO_INFO_CACHE_SECONDS,
        lambda: {
            "edgeTypes": list_edge_types(actor, space),
            "engine": engine_status(actor, space),
        },
    )


def clear_algo_info_cache() -> None:
    """清空边类型/引擎状态缓存：图类型 DDL 变更（Schema 新建/删除关系）后调用，
    避免算法页边类型下拉最长一个 TTL 内看不到最新类型。"""
    with _algo_info_lock:
        _algo_info_cache.clear()
