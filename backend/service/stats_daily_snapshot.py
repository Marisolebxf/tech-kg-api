"""每日图统计快照（净新增数据源）：api 侧低峰采集 + 相邻两日差分读取。

背景（2026-10-16 口径澄清）：「昨日新增」按当日任务写图记录计数（不去重），
「总量」为图上去重存量，两口径不同、不能直接相减对账。本模块按固定节奏对
每个图空间 ``SUBMIT JOB STATS`` + ``SHOW STATS``，把 per-Tag/Edge 计数持久化
进控制库 ``kg_stats_daily_snapshot``；总览读取侧对相邻两日快照做差分得到
「净新增」——与总量同一数据源（SHOW STATS），总量(D) − 总量(D−1) ≡ 净新增(D)，
天然可对账。

统计日归属：采集运行时刻（日窗口时区）在 03:00 前视为「前一日的定局快照」
（次日凌晨首跑收昨日尾），03:00 及以后归属当日——日内多次采集覆盖式 upsert
同一行，当日值随采集时点更新、次日凌晨定局；天然幂等，多栈重复采集同值
覆盖无害。功能上线前的历史日子无法回补（差分需要两端快照都在）。

规模护栏：亿级空间的 stats job 全量扫存储，超 ``KG_STATS_SNAPSHOT_MAX_VERTICES``
（按既有 SHOW STATS 计数判断）的空间跳过采集，读取侧给原因不编数。
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text

from service.day_change_ledger import DAY_TZ

logger = logging.getLogger(__name__)

SNAPSHOT_TABLE = "kg_stats_daily_snapshot"

# 空间级去重总量行名（SHOW STATS 的 Space/vertices|edges）；per-Tag/Edge 行
# 留作审计与将来按标签差分，读取侧现只用总量行
TOTAL_ITEM = "__total__"

_SNAPSHOT_DDL = f"""
CREATE TABLE IF NOT EXISTS {SNAPSHOT_TABLE} (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    stats_day DATE NOT NULL COMMENT '统计日（日窗口时区自然日；03:00 前的采集归属前一日）',
    graph_space VARCHAR(64) NOT NULL,
    kind VARCHAR(16) NOT NULL COMMENT 'entity(Tag) | relation(Edge)',
    item_name VARCHAR(191) NOT NULL COMMENT 'Tag/Edge 名；__total__ = 空间级去重总量（Space/vertices|edges）',
    item_count BIGINT NOT NULL DEFAULT 0,
    snapshot_at DATETIME NOT NULL COMMENT '采集时刻（日窗口时区）',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_stats_day (graph_space, stats_day, kind, item_name),
    KEY idx_day_space (stats_day, graph_space)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='每日图统计快照：净新增=相邻两日差分，与总量（SHOW STATS）同口径'
"""

# 键列不更新；计数随当日最后一次采集覆盖定局
_SNAPSHOT_UPSERT_SQL = f"""
INSERT INTO {SNAPSHOT_TABLE}
    (stats_day, graph_space, kind, item_name, item_count, snapshot_at)
VALUES (:stats_day, :graph_space, :kind, :item_name, :item_count, :snapshot_at)
ON DUPLICATE KEY UPDATE
    item_count = VALUES(item_count),
    snapshot_at = VALUES(snapshot_at)
"""

_ensure_lock = threading.Lock()
_ensured = False


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def snapshot_enabled() -> bool:
    return _env_bool("KG_STATS_SNAPSHOT_ENABLED", True)


def _interval_hours() -> int:
    return max(1, int(os.getenv("KG_STATS_SNAPSHOT_INTERVAL_HOURS", "6")))


def _max_vertices() -> int:
    return max(0, int(os.getenv("KG_STATS_SNAPSHOT_MAX_VERTICES", "10000000")))


def _job_timeout_seconds() -> float:
    return max(30.0, float(os.getenv("KG_STATS_SNAPSHOT_JOB_TIMEOUT_SECONDS", "900")))


def _space_allowlist() -> list[str]:
    raw = os.getenv("KG_STATS_SNAPSHOT_SPACES", "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def ensure_stats_snapshot_table(engine: Any = None) -> None:
    """建快照表（幂等，进程内只跑一次；失败吞掉并允许下次重试——采集/读取
    各自独立重试，不阻断对方）。模式与 kg_day_change_ledger 一致。"""
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
                connection.execute(text(_SNAPSHOT_DDL))
                connection.commit()
            _ensured = True
        except Exception:
            logger.warning(
                "kg_stats_daily_snapshot 建表失败，将在下次采集/读取时重试", exc_info=True
            )


def resolve_stats_day(run_at: datetime) -> str:
    """采集时刻（日窗口时区）→ 统计日。03:00 前视为前一日的定局快照
    （次日凌晨首跑收昨日尾，含 00:00 后少量溢写——低峰窗口可接受的近似）；
    03:00 及以后归属当日（日内刷新）。纯函数，单测覆盖。"""
    local = run_at.astimezone(DAY_TZ)
    if local.hour < 3:
        local -= timedelta(days=1)
    return local.strftime("%Y-%m-%d")


def parse_show_stats(records: list[Any]) -> dict[str, Any]:
    """SHOW STATS 记录 → {"tags", "edges", "total_nodes", "total_edges"}。

    解析逻辑与 infra.graph_db.client._fetch_stats_snapshot 同构（Space/vertices
    是去重总量，缺失时按标签计数求和兜底）；独立实现避免依赖客户端私有方法，
    采集路径需要绕开 300s 缓存拿新值。"""
    tags: dict[str, int] = {}
    edges: dict[str, int] = {}
    vertices = 0
    edge_total = 0
    for record in records or []:
        if not isinstance(record, dict):
            continue
        rtype = record.get("Type")
        name = record.get("Name")
        try:
            count = int(record.get("Count") or 0)
        except (TypeError, ValueError):
            continue
        if rtype == "Tag" and name:
            tags[str(name)] = count
        elif rtype == "Edge" and name:
            edges[str(name)] = count
        elif rtype == "Space":
            if name == "vertices":
                vertices = count
            elif name == "edges":
                edge_total = count
    return {
        "tags": tags,
        "edges": edges,
        "total_nodes": vertices or sum(tags.values()),
        "total_edges": edge_total or sum(edges.values()),
    }


def _extract_job_id(records: list[Any]) -> int | None:
    """SUBMIT JOB STATS 的返回里解析 job id（Nebula 列名 "New Job Id"）。"""
    for record in records or []:
        if not isinstance(record, dict):
            continue
        for key, value in record.items():
            if "job id" in str(key).lower():
                try:
                    return int(value)
                except (TypeError, ValueError):
                    continue
    return None


def _job_finished(client: Any, job_id: int) -> bool | None:
    """SHOW JOB 状态：True=FINISHED，False=FAILED，None=仍在队列/运行。"""
    result = client.execute_read(f"SHOW JOB {int(job_id)};")
    for record in result.records or []:
        if not isinstance(record, dict):
            continue
        status = str(record.get("Status") or "").upper()
        if status == "FINISHED":
            return True
        if status in {"FAILED", "STOPPED"}:
            return False
    return None


def _wait_stats_job(client: Any, job_id: int | None) -> None:
    """等 stats job 定局。job id 解析失败时短暂等待后放行（小空间 job 秒级
    完成，best-effort；大空间首个采集周期可能拿到 job 前的旧值，次日即正常）。"""
    import time

    if job_id is None:
        time.sleep(10)
        return
    deadline = time.monotonic() + _job_timeout_seconds()
    while time.monotonic() < deadline:
        state = _job_finished(client, job_id)
        if state is True:
            return
        if state is False:
            raise RuntimeError(f"图统计任务失败（SHOW JOB {job_id}）")
        time.sleep(10)
    raise RuntimeError(f"图统计任务超时未定局（SHOW JOB {job_id}）")


def _space_client(space: str) -> Any:
    from service.platform_overview import _connect_graph_for_space

    return _connect_graph_for_space(space)


def collect_space_once(space: str, *, client: Any | None = None) -> dict[str, Any]:
    """采集一个空间：SUBMIT JOB STATS → 等定局 → SHOW STATS → 覆盖式落快照行。

    返回摘要（{"space", "stats_day", "rows", "total_nodes", "total_edges"} 或
    {"space", "skipped", "reason"}）；任何失败上抛由调用方记日志跳过，绝不
    落半截数据（SHOW STATS 成功后才整批 upsert）。"""
    graph_client = client if client is not None else _space_client(space)
    # 规模护栏先看既有计数（空间从未跑过 stats 时 SHOW STATS 会报错——视为
    # 无基线，照常提交首个 job；此后该空间就有了可判规模的计数）
    baseline: dict[str, Any] = {}
    try:
        baseline = parse_show_stats(graph_client.execute_read("SHOW STATS;").records)
    except Exception:
        pass
    max_vertices = _max_vertices()
    if baseline and int(baseline.get("total_nodes") or 0) > max_vertices:
        return {"space": space, "skipped": "size-gate", "total_nodes": baseline["total_nodes"]}
    submit_result = graph_client.execute_write("SUBMIT JOB STATS;")
    _wait_stats_job(graph_client, _extract_job_id(submit_result.records))
    fresh = parse_show_stats(graph_client.execute_read("SHOW STATS;").records)

    now_local = datetime.now(DAY_TZ)
    stats_day = resolve_stats_day(now_local)
    snapshot_at = now_local.strftime("%Y-%m-%d %H:%M:%S")
    rows: list[dict[str, Any]] = [
        {
            "stats_day": stats_day,
            "graph_space": space,
            "kind": "entity",
            "item_name": TOTAL_ITEM,
            "item_count": int(fresh["total_nodes"]),
            "snapshot_at": snapshot_at,
        },
        {
            "stats_day": stats_day,
            "graph_space": space,
            "kind": "relation",
            "item_name": TOTAL_ITEM,
            "item_count": int(fresh["total_edges"]),
            "snapshot_at": snapshot_at,
        },
    ]
    for name, count in fresh["tags"].items():
        rows.append(
            {
                "stats_day": stats_day,
                "graph_space": space,
                "kind": "entity",
                "item_name": name,
                "item_count": int(count),
                "snapshot_at": snapshot_at,
            }
        )
    for name, count in fresh["edges"].items():
        rows.append(
            {
                "stats_day": stats_day,
                "graph_space": space,
                "kind": "relation",
                "item_name": name,
                "item_count": int(count),
                "snapshot_at": snapshot_at,
            }
        )
    from infra.workflow_mysql import get_workflow_engine

    ensure_stats_snapshot_table(get_workflow_engine())
    with get_workflow_engine().begin() as connection:
        connection.execute(text(_SNAPSHOT_UPSERT_SQL), rows)
    return {
        "space": space,
        "stats_day": stats_day,
        "rows": len(rows),
        "total_nodes": fresh["total_nodes"],
        "total_edges": fresh["total_edges"],
    }


def collect_all_once(*, list_spaces: Any | None = None) -> list[dict[str, Any]]:
    """一轮采集：白名单优先，否则 SHOW SPACES 全量；逐空间独立容错。"""
    allowlist = _space_allowlist()
    spaces = list(allowlist)
    if not spaces:
        try:
            if list_spaces is None:
                from infra.graph_db import get_trs_graph_client

                list_spaces = get_trs_graph_client().list_spaces
            spaces = [str(name) for name in list_spaces()]
        except Exception:
            logger.warning("图空间列表读取失败，本轮快照采集跳过", exc_info=True)
            return []
    summaries: list[dict[str, Any]] = []
    for space in spaces:
        try:
            summaries.append(collect_space_once(space))
        except Exception:
            logger.warning("图统计快照采集失败 space=%s，跳过待下轮", space, exc_info=True)
            summaries.append({"space": space, "skipped": "error"})
    return summaries


def _seconds_until_next_slot(now_local: datetime | None = None) -> float:
    """下一采集时点：24 % 间隔 == 0 时对齐本地 00:10 起的整格（00:10/06:10/
    12:10/18:10——次日凌晨定局的可预期节奏），否则简单按间隔滚动。"""
    interval = _interval_hours()
    now_local = now_local or datetime.now(DAY_TZ)
    if 24 % interval == 0:
        first_slot = now_local.replace(hour=0, minute=10, second=0, microsecond=0)
        for offset in range(0, 24, interval):
            slot = first_slot + timedelta(hours=offset)
            if slot > now_local:
                return max(60.0, (slot - now_local).total_seconds())
    return interval * 3600.0


async def run_stats_snapshot_collector() -> None:
    """lifespan 后台任务：启动 2 分钟后先补一轮（新栈/重启后当日快照尽快
    可查），此后按对齐时点滚动；单轮失败只记日志。"""
    await asyncio.sleep(120)
    while True:
        try:
            summaries = await asyncio.to_thread(collect_all_once)
            done = [item for item in summaries if not item.get("skipped")]
            if done:
                logger.info("图统计快照采集完成：%s", done)
        except Exception:
            logger.exception("图统计快照采集轮次异常，将在下一时点重试")
        await asyncio.sleep(_seconds_until_next_slot())


def _prev_day(day: str) -> str:
    return (datetime.strptime(day, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")


def load_net_added(space: str, day: str) -> tuple[dict[str, int | None], str]:
    """相邻两日总量快照差分 → 净新增（entity/relation 各一）。

    与总量同口径（SHOW STATS 去重存量），可为负（删除/清理日）；快照缺失
    时不编数——值为 None、note 给原因。纯读，表不存在/库不可达同样降级。"""
    from infra.workflow_mysql import get_workflow_engine

    prev = _prev_day(day)
    try:
        ensure_stats_snapshot_table()
        with get_workflow_engine().connect() as connection:
            rows = (
                connection.execute(
                    text(
                        f"SELECT stats_day, kind, item_count FROM {SNAPSHOT_TABLE} "
                        "WHERE graph_space = :space AND stats_day IN (:day, :prev) "
                        "AND item_name = :total"
                    ),
                    {"space": space, "day": day, "prev": prev, "total": TOTAL_ITEM},
                )
                .mappings()
                .all()
            )
    except Exception:
        logger.warning("kg_stats_daily_snapshot 读取失败，净新增降级为不可用", exc_info=True)
        return {"entity": None, "relation": None}, "净新增暂不可读取，请稍后重试"
    # MySQL DATE 列回传 datetime.date，str() 即 YYYY-MM-DD
    counts: dict[tuple[str, str], int] = {
        (str(row["stats_day"]), str(row["kind"])): int(row["item_count"]) for row in rows
    }
    if not counts:
        return (
            {"entity": None, "relation": None},
            "净新增按每日图统计快照差分计算；该空间暂无快照（功能上线后自动逐日生成）",
        )
    result: dict[str, int | None] = {}
    missing: list[str] = []
    for kind in ("entity", "relation"):
        curr = counts.get((day, kind))
        base = counts.get((prev, kind))
        if curr is None or base is None:
            result[kind] = None
            missing.append("实体" if kind == "entity" else "关系")
        else:
            result[kind] = curr - base
    if missing:
        # 缺哪一端说哪端：当日端缺（当日/未来日查询且未到采集时点）＝尚未生成；
        # 前一日端缺且统计日已过去＝上线前的日子无法回补；前一日端缺但就是
        # 当日查询＝上线首日无基线（次日起逐日可对账）——首日看到的正是这种
        label = "/".join(missing)
        has_curr = any(d == day for d, _ in counts)
        has_prev = any(d == prev for d, _ in counts)
        today = datetime.now(DAY_TZ).strftime("%Y-%m-%d")
        if not has_curr:
            if day >= today:
                note = f"{label}净新增的当日快照尚未生成（日内按采集时点刷新、次日凌晨定局）"
            else:
                note = f"{label}净新增的当日快照缺失（该统计日未采集）"
        elif not has_prev and day < today:
            note = f"{label}净新增缺少前一日快照（功能上线前的日子无法回补）"
        else:
            note = f"{label}净新增缺少前一日基线快照（上线首日无基线，次日起逐日可对账）"
        return result, note
    return result, ""
