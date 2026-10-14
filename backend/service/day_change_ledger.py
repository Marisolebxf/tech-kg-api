"""写图日增台账（P1）：写时记账，昨日新增读取优先于此、现算链路兜底。

``kg_day_change_ledger`` 落在控制库（与 ``workflow_executions`` 同库）：执行记录
每次落库（``WorkflowRepository.save_execution``，api/worker 进程的唯一写出口）时，
把该执行当前 output（含 chain 环展开）的 written 计数按
「统计日 × 空间 × kind × Schema × 执行 × 来源」**覆盖式** upsert 进台账——
同键重放覆盖而非累加，天然幂等：执行进度推进、终态重放、重试都不会双计；
执行没跑完就中断（TERMINATED/CANCELED）时最后一次落库的账即最终账。

昨日新增读取（platform_overview）先查台账：一条 SQL 出精确计数与聚合行；
台账无该日数据（旧执行 / 未部署本代码的栈写入）时回落既有的
payload 现算 + 图反查链路，互为兜底、不产生口径差异。

统计日归属、chain 环展开、时间串归一等纯函数与 platform_overview 共享
（自本模块导出），保证写账与读账同一口径、不漂移。
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# 「昨日新增」日窗口时区：按北京自然日 00:00 翻日（与 platform_overview 同一
# 公式；台账的统计日归属必须与读取口径一致，抽到本模块共享，避免两处漂移）
DAY_TZ = ZoneInfo(os.getenv("PLATFORM_OVERVIEW_DAY_TIMEZONE", "Asia/Shanghai"))

LEDGER_TABLE = "kg_day_change_ledger"

_LEDGER_DDL = f"""
CREATE TABLE IF NOT EXISTS {LEDGER_TABLE} (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    stats_day DATE NOT NULL COMMENT '统计日（日窗口时区自然日）',
    graph_space VARCHAR(64) NOT NULL DEFAULT '' COMMENT '图空间；执行未记录时为空串，读取按默认空间回退',
    kind VARCHAR(16) NOT NULL COMMENT 'entity | relation',
    schema_key VARCHAR(128) NOT NULL,
    schema_label VARCHAR(191) NOT NULL DEFAULT '',
    execution_id VARCHAR(64) NOT NULL,
    source VARCHAR(255) NOT NULL DEFAULT '' COMMENT '物理源表名，缺省 source 标识',
    object_count INT NOT NULL DEFAULT 0 COMMENT '该执行该 Schema 该来源的 written 计数（覆盖式，非累加）',
    exec_status VARCHAR(24) NOT NULL DEFAULT '',
    task_id VARCHAR(64) NULL,
    job_id VARCHAR(64) NULL,
    finished_at DATETIME NULL COMMENT '环级/执行级完成时刻（日窗口时区）',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_ledger (stats_day, graph_space, kind, schema_key, execution_id, source(64)),
    KEY idx_day_space_kind (stats_day, graph_space, kind)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='写图日增台账：save_execution 时覆盖式记账，昨日新增读取优先于此'
"""

# 键列（stats_day/graph_space/kind/schema_key/execution_id/source）不更新；
# 计数与展示列随执行最后一次落库覆盖定局
_UPSERT_SQL = f"""
INSERT INTO {LEDGER_TABLE}
    (stats_day, graph_space, kind, schema_key, schema_label, execution_id, source,
     object_count, exec_status, task_id, job_id, finished_at)
VALUES (:stats_day, :graph_space, :kind, :schema_key, :schema_label, :execution_id, :source,
        :object_count, :exec_status, :task_id, :job_id, :finished_at)
ON DUPLICATE KEY UPDATE
    schema_label = VALUES(schema_label),
    object_count = VALUES(object_count),
    exec_status = VALUES(exec_status),
    task_id = VALUES(task_id),
    job_id = VALUES(job_id),
    finished_at = VALUES(finished_at)
"""

_select_cols = (
    "stats_day, graph_space, kind, schema_key, schema_label, execution_id, source, "
    "object_count, exec_status, task_id, job_id, "
    "DATE_FORMAT(finished_at, '%Y-%m-%d %H:%M:%S') AS finished_at"
)

_ensure_lock = threading.Lock()
_ensured = False


def norm_ts(value: Any) -> str:
    """执行时间串归一：ISO 'T' 分隔 → 空格分隔。保留时区偏移不切片——环级
    时间带 "+08:00"，截掉会被当进程本地钟解读、错 8 小时。"""
    return str(value or "").replace("T", " ", 1).strip()


def iter_record_outputs(record: dict[str, Any]) -> list[tuple[dict[str, Any], str, str]]:
    """一条执行记录的全部写图输出单元，逐项 ``(output, 完成串, 起跑串)``。

    单 Schema 执行即顶层 output 本身；chain 执行顶层无 kind，每个
    ``steps["schema:<id>"]`` 的嵌套 ``output`` 与单 Schema 输出同构
    （kind/schemaLabel/sources[].written/startWatermark 齐全），逐环展开、
    环级时间缺失退整链时间。此前 chain 整段不可见就是只认顶层 kind 所致。"""
    output = record.get("output") or {}
    if not isinstance(output, dict):
        return []
    record_completed = norm_ts(record.get("completedAt"))
    record_started = norm_ts(record.get("startedAt"))
    steps = output.get("steps")
    if not output.get("kind") and isinstance(steps, dict) and steps:
        units: list[tuple[dict[str, Any], str, str]] = []
        for step in steps.values():
            if not isinstance(step, dict):
                continue
            inner = step.get("output") or {}
            if not isinstance(inner, dict) or not inner:
                continue
            units.append(
                (
                    inner,
                    norm_ts(step.get("finishedAt")) or record_completed,
                    norm_ts(step.get("startedAt")) or record_started,
                )
            )
        if units:
            return units
    return [(output, record_completed, record_started)]


def completed_in_day_tz(completed_at: str) -> datetime | None:
    """完成时刻字符串 → 日窗口时区时刻；空/坏格式返回 None。

    chain 环级 startedAt/finishedAt 自带时区偏移（"+08:00"），优先
    fromisoformat 完整解析（绝对准确，不受 api 进程时区影响）；naive 串仍按
    api 进程本地钟解读后折算（dev2 容器 UTC、宿主注入时区的栈都有）。"""
    raw = str(completed_at or "").replace("T", " ", 1).strip()
    if not raw:
        return None
    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        try:
            parsed = datetime.strptime(raw[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed.astimezone(DAY_TZ)


def execution_space(record: dict[str, Any]) -> str:
    """执行记录的目标图空间：调度下发记 ``graph_space``、手动/重跑记 ``graphSpace``。"""
    payload = record.get("payload") or {}
    return str(payload.get("graph_space") or payload.get("graphSpace") or "")


def ensure_day_change_ledger(engine: Any = None) -> None:
    """建台账表（幂等，进程内只跑一次；失败吞掉并允许下次重试——建表失败
    不阻断执行记录保存，读取侧查不到表会回落现算链路）。

    ``engine`` 缺省用全局控制库引擎；``save_execution`` 注入引擎的测试/工具
    场景随调用方传入（session.get_bind()），保证建在与写账同一库上。"""
    global _ensured
    if _ensured:
        return
    with _ensure_lock:
        if _ensured:
            return
        try:
            if engine is None:
                from infra.workflow_mysql import get_workflow_engine

                engine = get_workflow_engine()
            with engine.connect() as connection:
                connection.execute(text(_LEDGER_DDL))
                connection.commit()
            _ensured = True
        except Exception:
            logger.warning("kg_day_change_ledger 建表失败，将在下次写账时重试", exc_info=True)


def ledger_rows_from_execution(
    execution: dict[str, Any], default_space: str = ""
) -> list[dict[str, Any]]:
    """一条执行记录 → 台账行（纯函数，便于单测）。

    chain 按环展开、统计日按环级完成时刻归属（跨午夜环各自归日）；同
    （统计日 × kind × Schema × 来源）多环聚合一行为防 upsert 同键互相覆盖。
    written=0 的来源不入账（与读取端「只数写了的」口径一致）。RUNNING 执行
    已完成的环也先入账——覆盖式记账下终态落库时自然定局。"""
    space = execution_space(execution) or default_space
    status = str(execution.get("status") or "")
    execution_id = str(execution.get("id") or "")
    task_id = str(execution.get("taskId") or "").strip() or None
    job_id = str(execution.get("jobId") or "").strip() or None
    agg: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for output, completed_at, _ in iter_record_outputs(execution):
        local = completed_in_day_tz(completed_at)
        if local is None:
            continue
        kind = str(output.get("kind") or "")
        if kind not in ("entity", "relation"):
            continue
        schema_key = str(
            output.get("schemaKey")
            or output.get("schemaLabel")
            or ("实体" if kind == "entity" else "关系")
        )
        schema_label = str(output.get("schemaLabel") or "")
        day = local.strftime("%Y-%m-%d")
        finished = local.strftime("%Y-%m-%d %H:%M:%S")
        for source in output.get("sources") or []:
            if not isinstance(source, dict):
                continue
            written = max(0, int(source.get("written") or 0))
            if written <= 0:
                continue
            src = str(source.get("table") or source.get("source") or "")
            key = (day, kind, schema_key, src)
            row = agg.get(key)
            if row is None:
                agg[key] = {
                    "stats_day": day,
                    "graph_space": space,
                    "kind": kind,
                    "schema_key": schema_key,
                    "schema_label": schema_label,
                    "execution_id": execution_id,
                    "source": src,
                    "object_count": written,
                    "exec_status": status,
                    "task_id": task_id,
                    "job_id": job_id,
                    "finished_at": finished,
                }
            else:
                # 同执行同键多批/多环：计数累加、完成时刻取较晚（重放时整体覆盖）
                row["object_count"] += written
                if finished > str(row["finished_at"]):
                    row["finished_at"] = finished
    return [agg[key] for key in sorted(agg)]


def sync_execution_to_ledger(session: Session, execution: dict[str, Any]) -> int:
    """把一条执行记录当前 output 记/覆盖进台账（在 save_execution 的事务内）。

    返回写入行数（0 = 该执行无可记账输出）。SQL 异常上抛随事务回滚——
    台账与执行记录同库同事务，杜绝「执行说写了 N、账上没有」的漂移。"""
    rows = ledger_rows_from_execution(execution)
    if not rows:
        return 0
    ensure_day_change_ledger(session.get_bind())
    session.execute(text(_UPSERT_SQL), rows)
    return len(rows)


def load_ledger_day(day: str, space: str, default_space: str = "") -> list[dict[str, Any]]:
    """读某统计日某空间的台账行；表不存在/查询失败返回空（调用方回落现算）。"""
    ensure_day_change_ledger()
    try:
        from infra.workflow_mysql import get_workflow_engine

        with get_workflow_engine().connect() as connection:
            rows = (
                connection.execute(
                    text(
                        f"SELECT {_select_cols} FROM {LEDGER_TABLE} "
                        "WHERE stats_day = :day AND object_count > 0 AND ("
                        "graph_space = :space OR (graph_space = '' AND :space = :default)"
                        ") ORDER BY finished_at DESC"
                    ),
                    {"day": day, "space": space, "default": default_space},
                )
                .mappings()
                .all()
            )
        return [dict(row) for row in rows]
    except Exception:
        logger.warning("kg_day_change_ledger 读取失败，回落 payload 现算", exc_info=True)
        return []
